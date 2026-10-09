#!/usr/bin/env python3
"""usage_stats.py -- usage frequency of each cid in the messages (global and per
bank), and list of unread cids ordered by impact."""
from __future__ import annotations
import sys, json, glob, hashlib, collections
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from decode_messages import MsgBank  # noqa: E402

F0 = REPO / "extract" / "f0"
GL = REPO / "extract" / "f2" / "glyphs"


def load_cid_char():
    manual = {}
    for p in [GL / "manual.json"] + sorted((GL / "read").glob("*.json")):
        if p.is_file():
            for k, v in json.loads(p.read_text(encoding="utf-8")).items():
                if not str(k).startswith("_"):
                    manual[str(k)] = v
    gt = json.loads((GL / "ground_truth.json").read_text(encoding="utf-8"))
    return manual, gt


def main():
    h2c = json.loads((GL / "hash_to_cid.json").read_text(encoding="utf-8"))
    manual, gt = load_cid_char()
    meta = json.loads((GL / "cluster_meta.json").read_text(encoding="utf-8"))
    freq = collections.Counter()
    per_bank = {}
    for msg_path in sorted(glob.glob(str(F0 / "*.msg"))):
        stem = Path(msg_path).stem
        bank = MsgBank(msg_path, msg_path[:-4] + ".aif")
        cells = bank.atlas_cells()
        code2cid = {}
        for (idx, code, i2, cell) in cells:
            code2cid[code] = h2c.get(hashlib.md5(cell.tobytes()).hexdigest())
        bf = collections.Counter()
        for rec in bank.records:
            for t in bank.decode_stream(bank.pool_off + rec["offset"]):
                if t["kind"] == "glyph" and t["code"] >= 300:
                    cid = code2cid.get(t["code"])
                    freq[cid] += 1
                    bf[cid] += 1
        per_bank[stem] = bf
    known = set(int(k) for k in manual)
    known |= set(int(k) for k in gt.get("d1_ud1_39513800_022", {}))
    unknown = [(c, n) for c, n in freq.most_common() if c not in known and c is not None]
    total = sum(freq.values())
    unk_total = sum(n for _, n in unknown)
    print("total glifos:", total, "sin leer:", unk_total,
          "(%.2f%% leidos)" % (100.0 * (total - unk_total) / total))
    print("cids distintos usados:", len(freq), "sin leer:", len(unknown))
    print("TOP 80 cids sin leer:")
    for c, n in unknown[:80]:
        m = meta[c]
        print("  cid %-5d freq %-7d owner %s idx %d" % (c, n, m["owner"]["bank"],
                                                        m["owner"]["idx"]))
    (GL / "usage.json").write_text(json.dumps({
        "freq": {str(k): v for k, v in freq.items()},
        "per_bank": {s: {str(k): v for k, v in bf.items()}
                     for s, bf in per_bank.items()},
    }), encoding="utf-8")


if __name__ == "__main__":
    main()
