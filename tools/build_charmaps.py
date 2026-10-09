#!/usr/bin/env python3
"""build_charmaps.py -- generates translation/charmaps/<stem>.json (code->character).

Source priority for each cluster (cid):
  1. ground_truth.json  (stem,code) -> char   (visually verified seeds)
  2. read/*.json + manual.json                (manual reading of the atlas)
  3. tess.json                                (Tesseract jpn, 1 character)
  4. labels.json                              (font matcher, low confidence)

Output:
  translation/charmaps/<stem>.json    {"301":"セ", ...}   (flat code->char)
  extract/f2/glyphs/cid_char.json     cid -> final char
  extract/f2/glyphs/cid_source.json   cid -> "gt|manual|tess|ocr"
"""
from __future__ import annotations
import sys, json, glob, hashlib, argparse
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from decode_messages import MsgBank  # noqa: E402

F0 = REPO / "extract" / "f0"
GL = REPO / "extract" / "f2" / "glyphs"
CM = REPO / "mod" / "translation" / "charmaps"


def load_json(p, default):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr", action="store_true",
                    help="incluir el matcher de fuentes (labels.json) como ultimo recurso")
    ap.add_argument("--no-tess", action="store_true")
    args = ap.parse_args()

    hash_to_cid = load_json(GL / "hash_to_cid.json", {})
    gt = load_json(GL / "ground_truth.json", {})
    tess = {} if args.no_tess else load_json(GL / "tess.json", {})
    labels = load_json(GL / "labels.json", {})

    read_manual = {}
    if (GL / "read").is_dir():
        for rf in sorted((GL / "read").glob("*.json")):
            for cid, ch in load_json(rf, {}).items():
                if not str(cid).startswith("_") and ch:
                    read_manual[str(cid)] = ch
    for cid, ch in load_json(GL / "manual.json", {}).items():
        if ch:
            read_manual[str(cid)] = ch

    cid_char, cid_src = {}, {}
    # tess (level 3)
    if not args.no_tess:
        for cid, obj in tess.items():
            ch = obj.get("char") if isinstance(obj, dict) else obj
            if ch and len(ch) == 1:
                cid_char[int(cid)] = ch
                cid_src[int(cid)] = "tess"
    # font matcher (level 4, optional)
    if args.ocr:
        for cid, obj in labels.items():
            ch = obj.get("char") if isinstance(obj, dict) else obj
            if ch and int(cid) not in cid_char:
                cid_char[int(cid)] = ch
                cid_src[int(cid)] = "ocr"
    # manual reading (level 2)
    for cid, ch in read_manual.items():
        cid_char[int(cid)] = ch
        cid_src[int(cid)] = "manual"

    CM.mkdir(parents=True, exist_ok=True)
    summary = []
    for m in sorted(glob.glob(str(F0 / "*.msg"))):
        stem = Path(m).stem
        try:
            bank = MsgBank(m, m[:-4] + ".aif")
            cells = bank.atlas_cells()
        except Exception as e:
            print("ERR", stem, e)
            continue
        cmap = {}
        unknown = 0
        for (idx, code, i2, cell) in cells:
            cid = hash_to_cid.get(hashlib.md5(cell.tobytes()).hexdigest())
            ch = cid_char.get(cid) if cid is not None else None
            if ch:
                cmap[str(code)] = ch
            else:
                unknown += 1
        # ground truth (level 1) per bank
        for code, ch in gt.get(stem, {}).items():
            if code.startswith("_"):
                continue
            cmap[str(code)] = ch
        (CM / (stem + ".json")).write_text(
            json.dumps(cmap, ensure_ascii=False), encoding="utf-8")
        summary.append((stem, len(cmap), unknown))

    (GL / "cid_char.json").write_text(
        json.dumps({str(k): v for k, v in cid_char.items()}, ensure_ascii=False),
        encoding="utf-8")
    (GL / "cid_source.json").write_text(
        json.dumps({str(k): v for k, v in cid_src.items()}, ensure_ascii=False),
        encoding="utf-8")
    from collections import Counter
    print("charmaps:", len(summary), " cid_char:", len(cid_char),
          " por fuente:", dict(Counter(cid_src.values())))
    print("celdas sin caracter:", sum(u for _, _, u in summary))


if __name__ == "__main__":
    main()
