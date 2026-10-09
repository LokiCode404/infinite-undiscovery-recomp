#!/usr/bin/env python3
"""
validate_translation.py -- checks that the translations do NOT exceed the size
of the original text (UI requirement: do not overflow text boxes or the screen).

Width model (deduced and validated):
  * advance of a glyph = LOW byte of its metric (table at `metrics_off`, 2 B/glyph,
    index = code-301 for code>=300). See docs/re/font-format.md.
  * the rendered width of a line is approximated by SUM(advance of its glyphs);
    it is consistent across single-line messages (width/sum ratio ~0.88).
  * therefore the check is RELATIVE and scale-independent:
        SUM(translation advance) <= SUM(original advance) * margin

It also checks:
  * number of glyphs   (translation <= original)
  * number of lines   (translation <= original), counting the break controls
  * used glyphs that do not exist in the bank charmap

Usage:
  python tools/validate_translation.py [--es translation/es.json] [--margin 1.02] [--strict]
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))


def read_msg(path: Path):
    b = path.read_bytes()
    rec_off, pool_off, metrics_off = struct.unpack_from(">III", b, 0x20)
    recs = {}
    o = rec_off
    if rec_off:
        while o + 16 <= pool_off:
            A, B = struct.unpack_from(">II", b, o)
            if A == 0 and B == 0:
                break
            C, D = struct.unpack_from(">ff", b, o + 8)
            recs[A] = (B, C, D)
            o += 16
    return b, recs, metrics_off


def load_charmap_inv(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    inv = {}
    for k, v in raw.items():
        if isinstance(v, str) and len(v) == 1:
            inv.setdefault(v, int(k))
    return inv


def advance(b: bytes, metrics_off: int, code: int) -> int:
    i = code - 301 if code >= 300 else code - 1
    off = metrics_off + 2 * i
    if i < 0 or off + 1 >= len(b):
        return 0
    return b[off]


def metrics_sum(b, metrics_off, codes):
    return sum(advance(b, metrics_off, c) for c in codes if 0 < c < 0x4000)


def split_lines(codes):
    lines = [[]]
    for c in codes:
        if c == 0x4000:
            lines.append([])
        elif 0 < c < 0x4000:
            lines[-1].append(c)
    return lines


def max_line_width(b, metrics_off, codes):
    return max((metrics_sum(b, metrics_off, L) for L in split_lines(codes)), default=0)


def n_lines(codes):
    return len(split_lines(codes))


def encode(text, inv):
    codes, missing = [], []
    for ch in text:
        if ch in inv:
            codes.append(inv[ch])
        else:
            missing.append(ch)
    return codes, missing


def find_msgfile(stem):
    for d in ("extract/f0", "extract/f0_d2"):
        p = REPO / d / (stem + ".msg")
        if p.is_file():
            return p
    return None


def main(argv=None):
    p = argparse.ArgumentParser(description="Valida longitudes de la traduccion.")
    p.add_argument("--es", default="mod/translation/es.json")
    p.add_argument("--charmaps", default="mod/translation/charmaps")
    p.add_argument("--all-codes", default="extract/messages/all_codes.json")
    p.add_argument("--margin", type=float, default=1.02)
    p.add_argument("--strict", action="store_true", help="salir con codigo 1 si hay problemas")
    args = p.parse_args(argv)

    es = json.loads(Path(args.es).read_text(encoding="utf-8")).get("strings", [])
    allc = json.loads(Path(args.all_codes).read_text(encoding="utf-8"))
    cache = {}
    bad = 0

    for it in es:
        stem, sid, text = it.get("stem"), str(it.get("id")), it.get("es")
        if not stem or text is None:
            continue
        cm = Path(args.charmaps) / (stem + ".json")
        if not cm.is_file() or stem not in allc or sid not in allc[stem].get("msgs", {}):
            print("SKIP  %s:%s (sin charmap/msg)" % (stem, sid))
            continue
        if stem not in cache:
            cache[stem] = read_msg(find_msgfile(stem))
        b, recs, metrics_off = cache[stem]
        orig = allc[stem]["msgs"][sid]
        inv = load_charmap_inv(cm)
        space = inv.get(" ")

        # target = widest line of the original; number of lines of the original
        ol = split_lines(orig)
        target = max((metrics_sum(b, metrics_off, L) for L in ol), default=0) or 10**9
        max_lines = len(ol)

        # simulate the build reflow to know the REAL result
        import build_es_codes as bec  # noqa: E402
        try:
            lines, wl = bec.wrap(text, inv, space, b, metrics_off, target, max_lines)
        except Exception:
            lines, wl = text.split("\n"), ""
        tr, missing = [], []
        for ch in text:
            if ch in inv or ch == " " or (ch in bec.ASCII_FOLD and bec.ASCII_FOLD[ch] in inv):
                continue
            missing.append(ch)
        for li, line in enumerate(lines):
            if li > 0:
                tr.append(0x4000)
            for ch in line:
                if ch == " ":
                    tr.append(space)
                elif ch in inv:
                    tr.append(inv[ch])
                elif ch in bec.ASCII_FOLD and bec.ASCII_FOLD[ch] in inv:
                    tr.append(inv[bec.ASCII_FOLD[ch]])

        wo = target
        wt = max_line_width(b, metrics_off, tr) or 0
        ratio = (wt / wo) if wo else 0.0
        flags = []
        if wt > wo * args.margin:
            flags.append("ANCHO %.0f%%" % (100 * ratio))
        if len(tr) > len(orig):
            flags.append("glifos %d>%d" % (len(tr), len(orig)))
        if n_lines(tr) > n_lines(orig):
            flags.append("lineas %d>%d" % (n_lines(tr), n_lines(orig)))
        if missing:
            flags.append("sin glifo: %s" % "".join(sorted(set(missing))))

        status = "OK   " if not flags else "AVISO"
        if flags:
            bad += 1
        print("%s %-28s:%s  lin_max=%d/%d (%.2f)  glifos=%d/%d  lineas=%d/%d  %s"
              % (status, stem, sid, wt, wo, ratio, len(tr), len(orig), n_lines(tr), n_lines(orig),
                 "; ".join(flags)))

    print("\n%d cadenas, %d con avisos." % (len(es), bad))
    return 1 if (bad and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
