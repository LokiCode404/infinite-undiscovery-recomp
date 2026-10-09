#!/usr/bin/env python3
"""aif_text_report.py -- summary of the inventory of AIF textures with TEXT.

Reads the JSON files from `tools/scan_aif_text.py` (loose + embedded AIFs),
filters OCR false positives (words that do not exist in the game's own English
vocabulary) and classifies the real textures:

  * 1280x720 help screens (EN / JP by address block),
  * loose UI AIFs with text,
  * AIFs embedded in containers with text.

Usage:
    python -X utf8 tools/aif_text_report.py \
        --loose extract/f2/re_analysis/aif_text_loose.json \
        --embedded extract/f2/re_analysis/aif_text_embedded.json
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

EN_BLOCK_START = 0x28000000  # EN screens (JP: 26FEE000..27FB8800)


def load_vocab():
    vocab = set()
    for f in glob.glob(str(REPO / "extract/messages/text/*.txt")):
        for w in re.findall(r"[A-Za-z]{3,}", Path(f).read_text(encoding="utf-8", errors="replace")):
            vocab.add(w.lower())
    return vocab


def real_words(entry, vocab):
    out = []
    for w in entry["words"]:
        t = w["t"]
        if len(t) < 3 or not re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", t):
            continue
        if t.lower() in vocab:
            out.append(t)
    return out


def hexid(rel):
    name = Path(rel).name
    m = re.match(r"([0-9A-Fa-f]+)_", name)
    return int(m.group(1), 16) if m else -1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--loose", default="extract/f2/re_analysis/aif_text_loose.json")
    ap.add_argument("--embedded", default="extract/f2/re_analysis/aif_text_embedded.json")
    ap.add_argument("--min-real", type=int, default=2)
    args = ap.parse_args(argv)

    vocab = load_vocab()
    entries = {}
    for p in (args.loose, args.embedded):
        fp = REPO / p
        if fp.is_file():
            for e in json.loads(fp.read_text(encoding="utf-8")):
                entries[(e["rel"], e["offset"])] = e

    screens, loose_ui, embedded_ui = [], [], []
    for e in entries.values():
        is_screen = e["width"] == 1280 and e["height"] == 720
        if is_screen:
            screens.append(e)
            continue
        rw = real_words(e, vocab)
        if len(rw) < args.min_real:
            continue
        if e["rel"].endswith(".aif"):
            loose_ui.append((e, rw))
        else:
            embedded_ui.append((e, rw))

    print("== Pantallas de ayuda 1280x720 (bitmaps unicos) ==")
    en = [e for e in screens if hexid(e["rel"]) >= EN_BLOCK_START]
    jp = [e for e in screens if hexid(e["rel"]) < EN_BLOCK_START]
    print("  total %d   EN %d   JP %d" % (len(screens), len(en), len(jp)))

    print("== AIF sueltos (no pantallas) con texto real ==")
    for e, rw in sorted(loose_ui, key=lambda x: -len(x[1])):
        print("  %-32s %4dx%-4d %-8s %s"
              % (Path(e["rel"]).name, e["width"], e["height"], e["format_name"], " ".join(rw)[:70]))

    print("== AIF incrustados en contenedores con texto real ==")
    for e, rw in sorted(embedded_ui, key=lambda x: -len(x[1])):
        print("  %-40s @%08X %4dx%-4d %-8s %s"
              % (Path(e["rel"]).name, e["offset"], e["width"], e["height"],
                 e["format_name"], " ".join(rw)[:60]))

    print("\nRESUMEN: pantallas=%d  sueltos_ui=%d  incrustados_ui=%d  (entradas analizadas=%d)"
          % (len(screens), len(loose_ui), len(embedded_ui), len(entries)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
