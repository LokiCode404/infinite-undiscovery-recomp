#!/usr/bin/env python3
"""scan_aif_text.py -- SYSTEMATIC inventory of AIF textures with TEXT.

Walks the files extracted from both discs (loose AIFs and AIFs embedded
in ASF/MRON/BIN/AAF/ACF containers), decodes each bitmap, runs OCR
(tesseract TSV) and saves a JSON report with:

  * location (file, offset inside the container)
  * size/format of the AIF
  * md5 signature of the decoded bitmap (to deduplicate the SAME texture)
  * OCR words with box (x, y, w, h) and confidence, in original coordinates
  * a language estimate (ASCII vs CJK) and a "text score"

Usage
-----
    python -X utf8 tools/scan_aif_text.py --roots extract/f2/all_d1ud1 extract/f2/all_d1ud2 \
        --out extract/f2/re_analysis/aif_text_scan.json
    python -X utf8 tools/scan_aif_text.py --only-1280 --previews
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"))

import aif as aif_mod  # noqa: E402
from PIL import Image  # noqa: E402

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

CONTAINER_EXTS = {".asf", ".mron", ".bin", ".aaf", ".acf", ".aif"}


def _cjk(s: str) -> bool:
    return any(
        ("\u3040" <= c <= "\u30ff") or ("\u4e00" <= c <= "\u9fff")
        for c in s
    )


def ocr_words(img: Image.Image, scale: int = 1, psm: int = 11):
    """OCR TSV -> list of (text, conf, x, y, w, h) in original coords."""
    tmp = Path(tempfile.gettempdir()) / ("_scan_aif_text_%d.png" % os.getpid())
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    img.convert("RGB").save(tmp)
    try:
        out = subprocess.run(
            [TESS, str(tmp), "stdout", "-l", "eng", "--psm", str(psm), "tsv"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=120)
    except Exception:
        return []
    rows = []
    for line in (out.stdout or "").splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 12:
            continue
        if f[0] != "5":
            continue
        try:
            conf = float(f[10])
            x, y, w, h = int(f[6]), int(f[7]), int(f[8]), int(f[9])
        except ValueError:
            continue
        text = f[11].strip()
        if not text:
            continue
        rows.append((text, conf, x // scale, y // scale, w // scale, h // scale))
    return rows


def decode(data: bytes, base: int):
    return aif_mod.AifImage(data, base)


def scan_file(path: Path, min_w=64, min_h=16, max_dim=4096):
    """Returns a list of dicts (one per AIF with candidate text) from the file."""
    try:
        data = path.read_bytes()
    except Exception:
        return []
    results = []
    pos = 0
    while True:
        i = data.find(b"AIF ", pos)
        if i < 0:
            break
        pos = i + 1
        try:
            # the AIF starts at `i`; `base=i` for the 0x1000 alignment inside
            # the container (same as at runtime / ui_textures._load_source).
            at = decode(data[i:], i)
        except Exception:
            continue
        if at.width < min_w or at.height < min_h:
            continue
        if at.width > max_dim or at.height > max_dim:
            continue
        try:
            rgba = at.to_rgba()
        except Exception:
            continue
        digest = hashlib.md5(rgba).hexdigest()
        im = Image.frombytes("RGBA", (at.width, at.height), rgba)
        # white background (transparent textures carry light/dark text)
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, (0, 0), im)
        scale = 2 if max(im.size) <= 1600 else 1
        words = ocr_words(bg, scale=scale)
        ascii_words = [w for w in words if w[0].isascii() and any(c.isalpha() for c in w[0])]
        cjk_words = [w for w in words if _cjk(w[0])]
        conf_ok = [w for w in ascii_words if w[1] >= 55 and len(w[0]) >= 2]
        score = sum(len(w[0]) for w in conf_ok)
        results.append(dict(
            file=path.name, rel=str(path.relative_to(REPO)).replace("\\", "/"),
            offset=i, width=at.width, height=at.height,
            format=hex(at.format), format_name=at.format_name,
            md5=digest, score=score,
            n_ascii=len(ascii_words), n_cjk=len(cjk_words),
            lang="ja" if len(cjk_words) > len(conf_ok) else "en",
            words=[dict(t=w[0], c=round(w[1], 1), x=w[2], y=w[3], w=w[4], h=w[5])
                   for w in conf_ok],
        ))
    return results


def _worker(rel: str):
    """Processes a file (in its own process) and returns its AIFs with text."""
    path = REPO / rel
    try:
        return rel, scan_file(path)
    except Exception:
        return rel, []


def main(argv=None):
    p = argparse.ArgumentParser(description="Inventario OCR de texturas AIF con texto.")
    p.add_argument("--roots", nargs="+",
                   default=["extract/f2/all_d1ud1", "extract/f2/all_d1ud2"])
    p.add_argument("--out", default="extract/f2/re_analysis/aif_text_scan.json")
    p.add_argument("--only-1280", action="store_true",
                   help="solo AIFs de 1280x720 (pantallas de ayuda del CAMP)")
    p.add_argument("--loose-only", action="store_true",
                   help="solo ficheros .aif sueltos (rapido)")
    p.add_argument("--min-score", type=int, default=0,
                   help="puntuacion minima para conservar la entrada")
    p.add_argument("--previews", action="store_true",
                   help="guardar PNG de los candidatos")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args(argv)

    rels = []
    for root in args.roots:
        base = REPO / root
        for fn in sorted(base.rglob("*")):
            if not fn.is_file():
                continue
            ext = fn.suffix.lower()
            if ext == ".aif":
                pass
            elif args.loose_only or ext not in CONTAINER_EXTS:
                continue
            rels.append(str(fn.relative_to(REPO)).replace("\\", "/"))
    if args.limit:
        rels = rels[:args.limit]
    print("ficheros a escanear: %d  (jobs=%d)" % (len(rels), args.jobs), flush=True)

    all_res = []
    seen = {}
    n_files = n_aif = 0
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(_worker, r): r for r in rels}
        for fut in as_completed(futs):
            rel, results = fut.result()
            n_files += 1
            for r in results:
                n_aif += 1
                if args.only_1280 and not (r["width"] == 1280 and r["height"] == 720):
                    continue
                if r["score"] < args.min_score:
                    continue
                if r["md5"] in seen:
                    seen[r["md5"]]["dupes"].append(r["rel"] + "@%X" % r["offset"])
                    continue
                r["dupes"] = []
                seen[r["md5"]] = r
                all_res.append(r)
            if n_files % 500 == 0:
                print("  ... files=%d aif=%d candidatos=%d"
                      % (n_files, n_aif, len(all_res)), flush=True)

    all_res.sort(key=lambda r: -r["score"])
    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("escaneados files=%d aif=%d  con texto=%d  -> %s"
          % (n_files, n_aif, len(all_res), out))

    if args.previews:
        pv = out.parent / "aif_text_previews"
        pv.mkdir(parents=True, exist_ok=True)
        for r in all_res[:60]:
            d = (REPO / r["rel"]).read_bytes()
            try:
                at = decode(d, r["offset"])
            except Exception:
                continue
            im = Image.frombytes("RGBA", (at.width, at.height), at.to_rgba())
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, (0, 0), im)
            if max(bg.size) > 1400:
                bg = bg.resize((bg.width // 2, bg.height // 2), Image.LANCZOS)
            bg.save(pv / ("%s_%08X.png" % (Path(r["rel"]).stem, r["offset"])))
        print("previews ->", pv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
