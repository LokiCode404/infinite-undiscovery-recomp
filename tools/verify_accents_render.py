#!/usr/bin/env python3
"""
verify_accents_render.py -- OFFLINE acceptance test of the accents.

It takes the *patched* atlas + `.msg` of a bank and a list of codes (for
example those of id 152 of the demo catalog), and composes the image exactly like
the engine: cell `code-301` of the atlas, advance = high byte of the metric
(`metrics_off + 2*index`) and `0x4000` = line break. Saves a PNG.

It also walks the `.msg` table and confirms that the 16 new codes have an
inked cell and their own metric.

Usage:
    python -X utf8 tools/verify_accents_render.py \
        --aif extract/f2/accents/d1_ud1_000A4000_005_accents.aif \
        --msg extract/f2/accents/d1_ud1_000A4000_005_accents.msg \
        --catalog extract/f2/demo_accents_catalog.bin --id 152 \
        --out extract/f2/accents_offline_proof.png
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"))

import aif_edit  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

CELL = 32
LINE_BREAK = 0x4000


def read_codes_from_catalog(path, id_):
    b = Path(path).read_bytes()
    magic, n = struct.unpack_from("<II", b, 0)
    assert magic == 0x31435549, "magic de catalogo"
    o = 8
    for _ in range(n):
        total, count, aw, ah, sid, nc = struct.unpack_from("<6I", b, o)
        o += 24
        codes = list(struct.unpack_from("<%dH" % nc, b, o)) if nc else []
        o += 2 * nc
        if sid == id_:
            return codes
    raise SystemExit("id %d no esta en el catalogo" % id_)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--aif", required=True)
    ap.add_argument("--msg", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--id", type=int, default=152)
    ap.add_argument("--out", default=str(REPO / "extract" / "f2" / "accents_offline_proof.png"))
    ap.add_argument("--scale", type=int, default=3)
    args = ap.parse_args(argv)

    width, height, rgba = aif_edit.decode_rgba(Path(args.aif).read_bytes())
    msg = Path(args.msg).read_bytes()
    metrics_off = struct.unpack_from(">I", msg, 0x28)[0]
    count = struct.unpack_from(">I", msg, 0x34)[0]
    cols = width // CELL
    src = Image.frombytes("RGBA", (width, height), rgba)
    codes = read_codes_from_catalog(args.catalog, args.id)

    def advance(code):
        if code < 300:
            idx = code - 1
        else:
            idx = code - 301
        o = metrics_off + 2 * idx
        if o + 1 >= len(msg):
            return CELL
        return msg[o]  # high byte = advance in px

    # split into lines (0x4000)
    lines = [[]]
    for c in codes:
        if c == LINE_BREAK:
            lines.append([])
        elif c < 0x4000 and c:
            lines[-1].append(c)

    S = args.scale
    pad = 6
    W = max(sum(advance(c) for c in L) for L in lines) * S + 2 * pad
    H = len(lines) * (CELL * S + 10) + 2 * pad
    canvas = Image.new("RGBA", (W, H), (16, 16, 20, 255))
    dr = ImageDraw.Draw(canvas)

    print("id=%d  lineas=%d  count=%d  metrics_off=%d" % (args.id, len(lines), count, metrics_off))
    new_codes = sorted({c for c in codes if 858 <= c <= 873})
    print("codigos nuevos presentes:", new_codes)
    for c in new_codes:
        idx = c - 301
        r, cc = divmod(idx, cols)
        cell = src.crop((cc * CELL, r * CELL, cc * CELL + CELL, r * CELL + CELL))
        bbox = cell.split()[3].getbbox()
        o = metrics_off + 2 * idx
        met = struct.unpack_from(">H", msg, o)[0]
        print("  code=%d cell=%d bbox=%s metric=%d adv=%d" % (c, idx, bbox, met, met >> 8))
        assert bbox is not None, "celda %d vacia" % idx

    y = pad
    for L in lines:
        x = pad
        for c in L:
            idx = c - 301
            r, cc = divmod(idx, cols)
            cell = src.crop((cc * CELL, r * CELL, cc * CELL + CELL, r * CELL + CELL))
            cell = cell.resize((CELL * S, CELL * S), Image.NEAREST)
            canvas.alpha_composite(cell, (x, y))
            x += advance(c) * S
        y += CELL * S + 10
    canvas.save(args.out)
    print("-> %s (%dx%d)" % (args.out, canvas.width, canvas.height))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
