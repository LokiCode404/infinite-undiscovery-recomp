#!/usr/bin/env python3
"""write_texts.py -- decodes ALL .msg banks to readable text.

Output:
  extract/messages/text/<stem>.txt   "id<TAB>text" per message
  extract/messages/text/_coverage.json  per-bank summary

Markers:
  controls           -> {0x400A:2,1}   (hex code : decimal payload)
  unread glyph       -> ?[code]
"""
from __future__ import annotations
import sys, json, glob
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from decode_messages import MsgBank, tokens_to_text  # noqa: E402

F0 = REPO / "extract" / "f0"
OUT = REPO / "extract" / "messages" / "text"
CM = REPO / "mod" / "translation" / "charmaps"


def load_cmap(stem, cache={}):
    if stem in cache:
        return cache[stem]
    p = CM / (stem + ".json")
    m = {}
    if p.is_file():
        raw = json.loads(p.read_text(encoding="utf-8"))
        m = {int(k): v for k, v in raw.items() if not str(k).startswith("_")}
    cache[stem] = m
    return m


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    coverage = {}
    total = 0
    total_ok = 0
    for msg_path in sorted(glob.glob(str(F0 / "*.msg"))):
        stem = Path(msg_path).stem
        aif = msg_path[:-4] + ".aif"
        try:
            bank = MsgBank(msg_path, aif)
        except Exception as e:
            print("ERR", stem, e)
            continue
        cmap = load_cmap(stem)
        lines = []
        n_ok = 0
        n_unknown = 0
        n_ctrl = 0
        for rec in bank.records:
            toks = bank.decode_stream(bank.pool_off + rec["offset"])
            txt = tokens_to_text(toks, cmap)
            for t in toks:
                if t["kind"] == "glyph":
                    if t["code"] in cmap:
                        n_ok += 1
                    else:
                        n_unknown += 1
                elif t["kind"] == "ctrl":
                    n_ctrl += 1
            lines.append("%s\t%s" % (rec["id"], txt))
        (OUT / (stem + ".txt")).write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")
        coverage[stem] = {"msgs": len(bank.records), "glifos_ok": n_ok,
                          "glifos_sin_leer": n_unknown, "controles": n_ctrl,
                          "charmap_entradas": len(cmap)}
        total += n_ok + n_unknown
        total_ok += n_ok
    (OUT / "_coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=1), encoding="utf-8")
    print("bancos:", len(coverage), "glifos:", total,
          "leidos: %d (%.2f%%)" % (total_ok, 100.0 * total_ok / max(1, total)))
    bad = {k: v for k, v in coverage.items() if v["glifos_sin_leer"]}
    for k, v in sorted(bad.items(), key=lambda kv: -kv[1]["glifos_sin_leer"])[:20]:
        print("  %-30s sin leer %d / %d" % (k, v["glifos_sin_leer"],
                                            v["glifos_ok"] + v["glifos_sin_leer"]))


if __name__ == "__main__":
    main()
