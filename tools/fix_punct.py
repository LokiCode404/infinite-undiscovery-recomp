#!/usr/bin/env python3
"""
fix_punct.py -- fixes the mislabeled punctuation of the per-bank charmap.

Problem: the charmap (visual/OCR reading) sometimes confuses `.`/`,`/`;`/`?`/`!`
and letters (j/J). For `.` and `,` the encoder chose the most frequent glyph, which
sometimes was `?`.

Method: for each bank and for `.`/`,` the atlas cells among the ones
labeled with that character are rendered and the one that MOST looks like a dot/comma
is chosen:
  * `.` -> small ink (minimal box height) and low (attached to the baseline).
  * `,` -> small ink with a "tail" below the baseline.
Those codes are re-labeled in the charmap JSON.

Usage:
    python -X utf8 tools/fix_punct.py --dry-run
    python -X utf8 tools/fix_punct.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"))
import aif as aif_mod  # noqa: E402


def cell(aif, code):
    i = code - 301
    cols = aif.width // 32
    r, c = divmod(i, cols)
    img = Image.frombytes("RGBA", (aif.width, aif.height), aif.to_rgba())
    return img.crop((c * 32, r * 32, c * 32 + 32, r * 32 + 32))


def ink_stats(g):
    a = g.getchannel("A").load()
    bb = g.getbbox()
    if not bb:
        return None
    x0, y0, x1, y1 = bb
    h = y1 - y0
    w = x1 - x0
    # bottom_extra: ink below the approximate baseline (y>26)
    below = sum(1 for y in range(26, 32) for x in range(32) if a[x, y] > 40)
    return {"w": w, "h": h, "y0": y0, "y1": y1, "below": below}


def fix_bank(stem, charmap_dir, aif_dir, dry):
    cm_path = charmap_dir / (stem + ".json")
    aif_path = aif_dir / (stem + ".aif")
    if not cm_path.is_file() or not aif_path.is_file():
        return 0
    cm = json.loads(cm_path.read_text(encoding="utf-8"))
    inv = {}
    for k, v in cm.items():
        inv.setdefault(v, []).append(int(k))
    aif = aif_mod.AifImage(aif_path.read_bytes())
    changed = 0
    for ch in (".", ","):
        codes = inv.get(ch, [])
        if not codes:
            continue
        # of the candidate cells, choose the most "dot/comma": low and small box
        best, best_key = None, None
        for c in codes:
            s = ink_stats(cell(aif, c))
            if not s:
                continue
            key = (s["h"], -s["below"])  # the smallest and lowest
            if best is None or key < best_key:
                best, best_key = c, key
        if best is None:
            continue
        # re-label: only 'best' keeps that character; the rest is renamed
        for c in codes:
            if c != best and cm.get(str(c)) == ch:
                cm[str(c)] = "\ufffd"  # mark as unknown (will not be used for that char)
                changed += 1
        cm[str(best)] = ch
        changed += 1
    if changed and not dry:
        cm_path.write_text(json.dumps(cm, ensure_ascii=False), encoding="utf-8")
    return changed


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--charmaps", default="mod/translation/charmaps")
    p.add_argument("--aif", default="extract/f0")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    cd = REPO / args.charmaps
    ad = REPO / args.aif
    tot = 0
    for f in sorted(cd.glob("*.json")):
        n = fix_bank(f.stem, cd, ad, args.dry_run)
        if n:
            tot += n
            print("%-28s %d cambios" % (f.stem, n))
    print("total cambios:", tot, "(dry-run)" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
