#!/usr/bin/env python3
"""
extract_rmd.py -- Phase F0: isolate the `RMD-` (message resource) resources of
Infinite Undiscovery.

An `RMD-` resource is a font atlas (`AIF `) followed by message data.
This script:

  1. locates `ud1.bin` / `ud2.bin` inside an XDVDFS ISO (or accepts the already
     extracted `.bin` files, or a single container);
  2. walks the NORM/MRON container and selects each `RMD-` entry;
  3. decompresses the payload if it comes after an `SLZ` wrapper;
  4. splits it into `<label>.aif` (atlas, according to the length declared in the
     AIF header) and `<label>.msg` (the tail = message data, to be decoded in F1);
  5. writes `manifest.csv` and, optionally, exports each atlas to PNG.

It does not modify the original game nor write assets inside the repository: the
output goes to `extract/` (git-ignored).

Usage
-----
    python tools/extract_rmd.py --roms roms --out extract/f0 [--png]
    python tools/extract_rmd.py --iso roms/Disc1.iso --out extract/f0
    python tools/extract_rmd.py --bin extract/D1/ud1.bin extract/D1/ud2.bin --out extract/f0
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VENDOR = REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"
sys.path.insert(0, str(VENDOR))

import aif as aif_mod  # noqa: E402
import mron  # noqa: E402
import slz  # noqa: E402
import xdvdfs  # noqa: E402

SECTOR = 2048
TAG = "RMD-"

# SHA-256 of default.xex per edition (plan, annex 13.2).
XEX_PROFILES = {
    "22893bb8d96a1440ecbdbcae543baeaf89d26588c89c99a2c96fecf611475325": "EUROPE",
    "9523b45e6a724d4988ce9cf70d55b672e461b89303b02dc2f0f9c84329c25555": "USA",
    "42dfaa90814f5b78592bb637ac371df20c30acfa897f922fff96d3251553473b": "USA-UNDUB",
    "cbb789e5e8842398253839b2e320874b3851bd10aaa2392aadf5cdeed438cc91": "JAPAN",
    "fd063de17d98ab1201795efab4ffd06d76e85eeb4da0ce751926792deeeccd33": "ASIA",
}

# The size of ud1.bin identifies the disc.
DISC_BY_UD1_SIZE = {
    2207584256: "d1",
    3217651712: "d2",
}


def maybe_decompress(blob: bytes) -> bytes:
    """Unwraps an SLZ wrapper if the payload carries one; otherwise returns it as is."""
    if blob[:3] != slz.MAGIC:
        return blob
    total = struct.unpack_from(">I", blob, 8)[0] + slz.WRAPPER_SIZE
    return slz.SlzBlock(blob[:total]).decompress()


def sha256_of_entry(img: "xdvdfs.XdvdfsImage", entry: "xdvdfs.Entry") -> str:
    img.fh.seek(img.base + entry.sector * SECTOR)
    h = hashlib.sha256()
    remaining = entry.size
    while remaining > 0:
        buf = img.fh.read(min(1 << 20, remaining))
        if not buf:
            break
        h.update(buf)
        remaining -= len(buf)
    return h.hexdigest()


def iso_containers(iso_path: Path):
    """Returns (edition, {name: {offset, length, size}}) for an XDVDFS ISO."""
    img = xdvdfs.XdvdfsImage(str(iso_path))
    edition = "UNKNOWN"
    found = {}
    for e in img.entries():
        low = e.name.lower()
        if low == "default.xex" and not e.is_dir:
            digest = sha256_of_entry(img, e)
            edition = XEX_PROFILES.get(digest, "UNKNOWN:" + digest[:16])
        if low in ("ud1.bin", "ud2.bin") and not e.is_dir:
            found[low] = {
                "offset": img.base + e.sector * SECTOR,
                "length": e.size,
                "size": e.size,
            }
    img.close()
    return edition, found


def extract_container(path: Path, offset: int, length: int, label: str,
                      outdir: Path, want_png: bool, rows: list):
    con = mron.Container(str(path), offset, length)
    written = 0
    for item in con.walk():
        if isinstance(item, mron.Gap):
            continue
        for index, entry in enumerate(item.entries):
            if entry["tag"] != TAG:
                continue
            blob = con.read(item.offset + entry["offset"], entry["size"])
            try:
                blob = maybe_decompress(blob)
            except Exception as exc:  # noqa: BLE001
                print("  ! %s 0x%08X[%d]: SLZ: %s"
                      % (label, item.offset, index, exc), file=sys.stderr)
                continue
            if blob[:4] != b"AIF ":
                print("  ! %s 0x%08X[%d]: no es AIF (%r)"
                      % (label, item.offset, index, blob[:4]), file=sys.stderr)
                continue

            aif_len = struct.unpack_from(">I", blob, 4)[0]
            if aif_len <= 0 or aif_len > len(blob):
                print("  ! %s 0x%08X[%d]: longitud AIF rara (%d de %d), uso el total"
                      % (label, item.offset, index, aif_len, len(blob)),
                      file=sys.stderr)
                aif_len = len(blob)

            name = "%s_%08X_%03d" % (label, item.offset, index)
            aif_bytes = blob[:aif_len]
            msg_bytes = blob[aif_len:]
            (outdir / (name + ".aif")).write_bytes(aif_bytes)
            (outdir / (name + ".msg")).write_bytes(msg_bytes)

            width = height = 0
            fmt = "?"
            try:
                atlas = aif_mod.AifImage(aif_bytes)
                width, height, fmt = atlas.width, atlas.height, atlas.format_name
                if want_png:
                    rgba = atlas.to_rgba()
                    aif_mod.write_png(str(outdir / (name + ".png")),
                                      atlas.width, atlas.height, rgba)
            except Exception as exc:  # noqa: BLE001
                fmt = "ERR:" + str(exc)

            rows.append({
                "label": label,
                "source": str(path),
                "container_offset": offset,
                "entry_index": index,
                "entry_offset": offset + item.offset + entry["offset"],
                "entry_size": entry["size"],
                "aif_len": aif_len,
                "msg_len": len(msg_bytes),
                "atlas_w": width,
                "atlas_h": height,
                "pixel_format": fmt,
            })
            written += 1
    print("  %-12s -> %d RMD- extraidos" % (label, written))
    return written


def short_label(path: Path) -> str:
    """Short, stable label from the filename."""
    stem = path.stem
    keep = [c if c.isalnum() else "_" for c in stem]
    return "".join(keep).strip("_") or "container"


def process_iso(iso_path: Path, outdir: Path, want_png: bool, rows: list):
    print("ISO  %s" % iso_path)
    edition, found = iso_containers(iso_path)
    print("  edicion: %s   contenedores: %s"
          % (edition, ", ".join(sorted(found)) or "ninguno"))
    if not found:
        print("  ! no hay ud1.bin/ud2.bin en el ISO", file=sys.stderr)
        return
    disc = "disc"
    if "ud1.bin" in found:
        disc = DISC_BY_UD1_SIZE.get(found["ud1.bin"]["size"], "disc")
    for cname in sorted(found):
        info = found[cname]
        label = "%s_%s" % (disc, cname.replace(".bin", ""))
        extract_container(iso_path, info["offset"], info["length"], label,
                          outdir, want_png, rows)


def process_bin(bin_path: Path, outdir: Path, want_png: bool, rows: list):
    print("BIN  %s" % bin_path)
    label = short_label(bin_path)
    size = bin_path.stat().st_size
    head = bin_path.read_bytes()[:8]
    if head != mron.MAGIC:
        print("  ! no empieza por MRON00.2 (primero hay que extraerlo del ISO)",
              file=sys.stderr)
        return
    extract_container(bin_path, 0, size, label, outdir, want_png, rows)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="F0: aislar los RMD- (atlas AIF + datos de mensaje) de Infinite Undiscovery.")
    p.add_argument("--roms", help="carpeta con los ISO/ binarios (p. ej. roms/)")
    p.add_argument("--iso", action="append", default=[], help="ISO XDVDFS (repetible)")
    p.add_argument("--bin", action="append", default=[],
                   help="ud1.bin/ud2.bin ya extraidos (repetible)")
    p.add_argument("--out", default="extract/f0", help="carpeta de salida (por defecto extract/f0)")
    p.add_argument("--png", action="store_true", help="exportar cada atlas a PNG")
    args = p.parse_args(argv)

    if not args.roms and not args.iso and not args.bin:
        p.error("indica al menos --roms, --iso o --bin")

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    isos = [Path(x) for x in args.iso]
    bins = [Path(x) for x in args.bin]

    if args.roms:
        roms = Path(args.roms)
        if not roms.is_dir():
            sys.exit("la carpeta de roms no existe: %s" % roms)
        # Deduplicate: on Windows the filesystem is case-insensitive and
        # several patterns (e.g. *.iso and *.ISO) match the same files.
        seen = set()

        def _uniq(paths):
            out = []
            for p in paths:
                key = str(p.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    out.append(p)
            return sorted(out)

        isos += _uniq(list(roms.rglob("*.iso")) + list(roms.rglob("*.ISO")))
        bins += _uniq(list(roms.rglob("ud1.bin")) + list(roms.rglob("ud2.bin"))
                      + list(roms.rglob("ud1.BIN")) + list(roms.rglob("ud2.BIN")))
        if not isos and not bins:
            sys.exit("no he encontrado ISO ni ud*.bin en %s" % roms)

    if not isos and not bins:
        sys.exit("no hay nada que procesar")

    rows: list = []
    for iso in isos:
        process_iso(iso, outdir, args.png, rows)
    for b in bins:
        process_bin(b, outdir, args.png, rows)

    manifest = outdir / "manifest.csv"
    with open(manifest, "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=[
            "label", "source", "container_offset", "entry_index", "entry_offset",
            "entry_size", "aif_len", "msg_len", "atlas_w", "atlas_h",
            "pixel_format"])
        w.writeheader()
        w.writerows(rows)

    total_msgs = sum(r["msg_len"] for r in rows)
    print("\nTotal: %d RMD- extraidos, %d bytes de datos de mensaje."
          % (len(rows), total_msgs))
    print("Manifiesto: %s" % manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
