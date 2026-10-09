#!/usr/bin/env python3
"""
gen_es_catalog.py -- generates the binary catalog consumed by the runtime hook
(`mod/recomp/translation_es.h`).

Input:
  * `translation/es_codes.json`  -> { "(bank)stem": { "(id)": [codes] } }
  * the bank signatures (total,count,atlas_w,atlas_h), read directly
    from the `.msg` files in `--msg-dir` (default `extract/f0` + `extract/f0_d2`).

Output:
  * `translation/es_catalog.bin`:  u32 magic 'IUC1', u32 n, and n blocks
        u32 total,count,atlas_w,atlas_h,id,ncodes ; u16 codes[ncodes]

The hook identifies the bank by the signature of the loaded `.msg` header, so
the bank->message matching is independent of the file path.
"""

from __future__ import annotations

import argparse
import glob
import json
import struct
from pathlib import Path

MAGIC = 0x31435549  # 'IUC1'


def msg_fingerprint(path: Path):
    """(total, count, atlas_w, atlas_h) from the BE .msg header, or None."""
    b = path.read_bytes()
    if len(b) < 0x68:
        return None
    total, count = struct.unpack_from(">II", b, 0x30)
    aw, ah = struct.unpack_from(">II", b, 0x60)
    return (total, count, aw, ah)


def build_fingerprints(msg_dirs, accents_dirs=()):
    fp = {}
    for d in msg_dirs:
        for m in glob.glob(str(Path(d) / "*.msg")):
            stem = Path(m).stem
            f = msg_fingerprint(Path(m))
            if f and stem not in fp:
                fp[stem] = f
    # Alias: `<stem>_accents.msg` (enlarged atlas -> higher count).  When that
    # .msg is substituted at runtime, the bank signature changes; the accented
    # signature is also registered so the hook still recognizes the bank.
    aliases = {}
    for d in accents_dirs:
        for m in glob.glob(str(Path(d) / "*_accents.msg")):
            stem = Path(m).stem[: -len("_accents")]
            f = msg_fingerprint(Path(m))
            if f:
                aliases.setdefault(stem, []).append(f)
    return fp, aliases


def main(argv=None):
    p = argparse.ArgumentParser(description="Genera translation/es_catalog.bin.")
    p.add_argument("--es-codes", default="mod/translation/es_codes.json")
    p.add_argument("--msg-dir", action="append", default=["extract/f0", "extract/f0_d2"])
    p.add_argument("--accents-dir", action="append", default=["extract/f2"])
    p.add_argument("--out", default="mod/translation/es_catalog.bin")
    args = p.parse_args(argv)

    fps, aliases = build_fingerprints(args.msg_dir, args.accents_dir)
    es = json.loads(Path(args.es_codes).read_text(encoding="utf-8"))

    blocks = []
    missing_banks = set()
    for stem, by_id in es.items():
        flist = []
        f = fps.get(stem)
        if f:
            flist.append(f)
        flist.extend(aliases.get(stem, []))
        if not flist:
            missing_banks.add(stem)
            continue
        for total, count, aw, ah in flist:
            for sid, codes in by_id.items():
                blocks.append((total, count, aw, ah, int(sid), [int(c) for c in codes]))

    out = Path(args.out)
    with out.open("wb") as fh:
        fh.write(struct.pack("<II", MAGIC, len(blocks)))
        for total, count, aw, ah, sid, codes in blocks:
            fh.write(struct.pack("<6I", total, count, aw, ah, sid, len(codes)))
            if codes:
                fh.write(struct.pack("<%dH" % len(codes), *codes))

    print("escrito %s: %d cadenas, %d bancos" % (out, len(blocks), len(es) - len(missing_banks)))
    if missing_banks:
        print("  AVISO: bancos sin huella (no estan en los .msg):", sorted(missing_banks)[:10])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
