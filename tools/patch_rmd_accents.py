#!/usr/bin/env python3
"""
patch_rmd_accents.py -- WS1: applies an already patched `RMD-` bank (AIF + .msg)
to the **uncompressed** container `ud1.bin` / `ud2.bin`, *in place* (same size).

Of the 81 `RMD-`, **77 are SLZ-compressed** (XCompress/LZX) and `mron.py`/`slz.py`
only decompress; repacking them would require an LZX *compressor*. The remaining 4
(the two copies of `d1_ud1_000A4000_005` and of `..._004`) are **uncompressed** and
are, for the current scope of the translation, the only ones that render Spanish.
For these, the accent patch **does not change the size** of the payload (free
atlas cells are reused and the metric table has room), so it is enough to
overwrite the resource range in the loose file.

It locates the resource via the F0 manifest (`extract/f0/manifest.csv`), verifies
byte for byte that the range contains the original `AIF`+`.msg`, writes the patch
and saves an **`.undo.json`** with the original bytes of the touched runs.

Usage
-----
    # see what it would do (without writing)
    python -X utf8 tools/patch_rmd_accents.py --stem d1_ud1_000A4000_005 \
        --bin extract/f2/run/EUROPE/assets/disc1/ud1.bin --dry-run

    # apply
    python -X utf8 tools/patch_rmd_accents.py --stem d1_ud1_000A4000_005 \
        --bin extract/f2/run/EUROPE/assets/disc1/ud1.bin

    # undo
    python -X utf8 tools/patch_rmd_accents.py --undo extract/f2/run/EUROPE/assets/disc1/ud1.bin.undo.json
"""

from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"))

import aif as aif_mod  # noqa: E402


def infer_label(bin_path: Path) -> str:
    """`.../disc1/ud1.bin` -> `d1_ud1` (manifest convention)."""
    name = bin_path.stem.lower()
    parent = bin_path.parent.name.lower()
    disc = {"disc1": "d1", "disc2": "d2"}.get(parent)
    if disc is None:
        # the other container of the same folder tells the disc
        if name not in ("ud1", "ud2"):
            return name
        disc = "d1"
    return "%s_%s" % (disc, name)


def find_entry(stem, bin_path, label=None):
    """(rel_offset, entry_size, aif_len, msg_len) of the RMD- `stem` in the loose .bin."""
    label = label or infer_label(bin_path)
    man = REPO / "extract" / "f0" / "manifest.csv"
    rows = list(csv.DictReader(open(man, encoding="utf-8")))
    exact = [r for r in rows if r["label"] == label and r["source"].lower().find(".iso") >= 0]
    # 1) clues from the extracted content of the bank
    aif = (REPO / "extract" / "f0" / (stem + ".aif"))
    if not aif.is_file():
        raise SystemExit("no existe %s" % aif)
    aif_len = aif.stat().st_size
    msg = (REPO / "extract" / "f0" / (stem + ".msg"))
    msg_len = msg.stat().st_size
    cand = []
    for r in exact:
        if int(r["aif_len"]) == aif_len and int(r["msg_len"]) == msg_len:
            rel = int(r["entry_offset"]) - int(r["container_offset"])
            cand.append((rel, int(r["entry_size"]), int(r["aif_len"]), int(r["msg_len"])))
    if not cand:
        raise SystemExit("no encuentro el RMD- %s en %s (manifest)" % (stem, label))
    # the first one that fits in the file
    size = bin_path.stat().st_size
    for rel, es, al, ml in cand:
        if rel + es <= size:
            return rel, es, al, ml
    raise SystemExit("el RMD- %s queda fuera de %s" % (stem, bin_path))


def diff_ranges(orig: bytes, new: bytes):
    """Contiguous runs that change: [(offset, original_bytes), ...]."""
    assert len(orig) == len(new)
    ranges = []
    i = 0
    n = len(orig)
    while i < n:
        if orig[i] != new[i]:
            j = i + 1
            while j < n and orig[j] != new[j]:
                j += 1
            ranges.append((i, orig[i:j]))
            i = j
        else:
            i += 1
    return ranges


def apply(stem, bin_path, aif_patch, msg_patch, dry_run, undo_path):
    rel, entry_size, aif_len, msg_len = find_entry(stem, bin_path)
    if entry_size < aif_len + msg_len:
        raise SystemExit("el RMD- %s esta COMPRIMIDO (entry_size=%d < %d); este "
                         "parche solo soporta entradas en claro"
                         % (stem, entry_size, aif_len + msg_len))

    orig_aif = (REPO / "extract" / "f0" / (stem + ".aif")).read_bytes()
    new_aif = Path(aif_patch).read_bytes()
    new_msg = Path(msg_patch).read_bytes()
    assert len(new_aif) == aif_len and len(new_msg) == msg_len

    with open(bin_path, "rb") as fh:
        fh.seek(rel)
        on_disk = fh.read(aif_len + msg_len)
    # the AIF on disk must be the extracted original (it guarantees we point to the
    # correct resource); the `.msg` may have been synchronized (`--sync-f0`), so
    # the reference truth for the patch is the state *on disk*.
    if on_disk[:aif_len] != orig_aif:
        raise SystemExit("el AIF en disco no coincide con %s (offset %d)" % (stem, rel))
    if len(on_disk) != aif_len + msg_len:
        raise SystemExit("el .msg en disco tiene otro tamano (%d)" % len(on_disk))

    ranges = diff_ranges(on_disk, new_aif + new_msg)
    total = sum(len(b) for _, b in ranges)
    print("RMD- %s  @ %d  (aif=%d msg=%d)  tramos=%d  bytes=%d"
          % (stem, rel, aif_len, msg_len, len(ranges), total))
    if not ranges:
        print("  (sin cambios; nada que hacer)")
        return 0

    if dry_run:
        for off, b in ranges[:8]:
            print("  +%8d  %d bytes" % (off, len(b)))
        if len(ranges) > 8:
            print("  ... %d tramos mas" % (len(ranges) - 8))
        print("  [dry-run] no se escribe")
        return 0

    # undo
    undo = {"bin": str(bin_path), "stem": stem, "entry_offset": rel,
            "ranges": [[rel + off, b.hex()] for off, b in ranges]}
    Path(undo_path).write_text(json.dumps(undo), encoding="utf-8")

    with open(bin_path, "r+b") as fh:
        for off, b in ranges:
            fh.seek(rel + off)
            fh.write((new_aif + new_msg)[off:off + len(b)])
    print("  aplicado. undo -> %s" % undo_path)

    # validation: re-read and compare
    with open(bin_path, "rb") as fh:
        fh.seek(rel)
        check = fh.read(aif_len + msg_len)
    assert check == new_aif + new_msg, "la relectura no coincide"
    print("  verificado (relectura == parche)")
    return 0


def undo(undo_path):
    d = json.loads(Path(undo_path).read_text(encoding="utf-8"))
    bin_path = Path(d["bin"])
    with open(bin_path, "r+b") as fh:
        for off, hexb in d["ranges"]:
            fh.seek(off)
            fh.write(bytes.fromhex(hexb))
    print("deshecho %d tramos en %s" % (len(d["ranges"]), bin_path))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Aplica acentos a ud*.bin (solo en claro).")
    ap.add_argument("--stem")
    ap.add_argument("--bin")
    ap.add_argument("--aif", help="AIF parcheado (por defecto extract/f2/accents/<stem>_accents.aif)")
    ap.add_argument("--msg", help=".msg parcheado (por defecto extract/f2/accents/<stem>_accents.msg)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--undo", help="fichero .undo.json a aplicar")
    args = ap.parse_args(argv)

    if args.undo:
        return undo(args.undo)
    if not args.stem or not args.bin:
        ap.error("--stem y --bin son obligatorios (o --undo)")
    aif = args.aif or str(REPO / "extract" / "f2" / "accents"
                          / (args.stem + "_accents.aif"))
    msg = args.msg or str(REPO / "extract" / "f2" / "accents"
                          / (args.stem + "_accents.msg"))
    undo_path = args.bin + ".undo.json"
    return apply(args.stem, Path(args.bin), aif, msg, args.dry_run, undo_path)


if __name__ == "__main__":
    raise SystemExit(main())
