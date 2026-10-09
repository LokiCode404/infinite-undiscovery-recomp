#!/usr/bin/env python3
"""
aif_edit.py -- AIF (Aska Image File) editor: decodes, modifies pixels and
**re-encodes** the DXT2/3 atlas with the Xbox 360 *tiling*.

`tools/vendor/pc-infiniteundiscovery/tools/aif.py` only **decodes**. This
module reuses its decoder (`AifImage`, `tiled_offset`, `write_png`) and
adds the reverse path, which is what F3 needs to be able to draw new glyphs
in the `RMD-` atlases:

    AIF on disk (BE 16-bit + 360 tiling)
        │  AifImage.untiled()  (already in aif.py)
        ▼
    linear DXT blocks  ──►  _decode_dxt (aif.py)  ──►  RGBA
        ▲
        │  dxt3_encode_block()  (this module)
        │  AifEditor.write_block()  (inverse re-tile + byte-swap)
        │
    AIF on disk

The exact *round-trip* of the wrapper (tiling + byte order) is checked with
`roundtrip`: read the file, rebuild it from the linear blocks and require
byte-for-byte equality. The DXT codec is lossy (it is an RGB565 + 4-bit alpha
quantization), so it is validated separately with an image whose colors fall in
the palette (exact round-trip) and by measuring PSNR in the general case.

Usage
-----
    python tools/aif_edit.py info       <file.aif>
    python tools/aif_edit.py png        <file.aif> <out.png>
    python tools/aif_edit.py roundtrip  <file.aif>
    python tools/aif_edit.py blanks     <file.aif> [--cell 32]
    python tools/aif_edit.py selftest
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor" / "pc-infiniteundiscovery" / "tools"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

import aif as aif_mod  # noqa: E402

FMT_DXT1 = aif_mod.FMT_DXT1
FMT_DXT3 = aif_mod.FMT_DXT3
FMT_DXT5 = aif_mod.FMT_DXT5


# --------------------------------------------------------------------------
# byte order
# --------------------------------------------------------------------------
def swap_words(data: bytes) -> bytearray:
    """Swaps each byte pair (16-bit BE on disk -> LE of the GPU/DXT).

    It is an involution: `swap_words(swap_words(x)) == x`. A8R8G8B8 is left
    untouched (4 B element, 8-bit fields), exactly as in `AifImage.untiled`.
    """
    out = bytearray(len(data))
    out[0::2] = data[1::2]
    out[1::2] = data[0::2]
    return out


# --------------------------------------------------------------------------
# color: RGB565 <-> RGB888
# --------------------------------------------------------------------------
def rgb888_to_565(r: int, g: int, b: int) -> int:
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def rgb565_to_888(value: int):
    r = (value >> 11) & 0x1F
    g = (value >> 5) & 0x3F
    b = value & 0x1F
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


# --------------------------------------------------------------------------
# DXT codec (encode)
# --------------------------------------------------------------------------
def _pick_endpoints(pixels):
    """Returns (c0, c1) RGB565 maximizing the distance. `pixels` = list of RGB.

    For text (almost always white/black) the bounding box gives the de facto
    optimal pair; it is computed as (maxR,maxG,maxB) and (minR,minG,minB).
    """
    if not pixels:
        return 0, 0
    rmin = gmin = bmin = 255
    rmax = gmax = bmax = 0
    for (r, g, b) in pixels:
        if r < rmin: rmin = r
        if g < gmin: gmin = g
        if b < bmin: bmin = b
        if r > rmax: rmax = r
        if g > gmax: gmax = g
        if b > bmax: bmax = b
    c0 = rgb888_to_565(rmax, gmax, bmax)
    c1 = rgb888_to_565(rmin, gmin, bmin)
    return c0, c1


def _palette_dxt1(c0, c1, four_colour):
    r0, g0, b0 = rgb565_to_888(c0)
    r1, g1, b1 = rgb565_to_888(c1)
    pal = [(r0, g0, b0), (r1, g1, b1)]
    if four_colour:
        pal.append(((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3))
        pal.append(((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3))
    else:
        pal.append(((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2))
    return pal


def _nearest(pal, rgb):
    best = 0
    bestd = 1 << 30
    for i, p in enumerate(pal):
        d = ((p[0] - rgb[0]) ** 2 + (p[1] - rgb[1]) ** 2 + (p[2] - rgb[2]) ** 2)
        if d < bestd:
            bestd = d
            best = i
    return best


def _colour_block(pixels, four_colour):
    """`pixels`: 16 (r,g,b). Returns 8 bytes of the color sub-block."""
    visible = [p for p in pixels if p is not None]
    c0, c1 = _pick_endpoints(visible)
    if not four_colour and c0 == c1:
        c0 = min(0xFFFF, c0 + 1) if c0 < 0xFFFF else c0 - 1
    pal = _palette_dxt1(c0, c1, four_colour)
    indices = 0
    for i, p in enumerate(pixels):
        if p is None:
            idx = 0
        else:
            idx = _nearest(pal, p)
        indices |= (idx & 3) << (2 * i)
    return struct.pack("<HH", c0, c1) + struct.pack("<I", indices & 0xFFFFFFFF)


def dxt1_encode_block(rgba16) -> bytes:
    """`rgba16`: 16 tuples (r,g,b,a). DXT1 with 1-bit alpha."""
    # if there is alpha < 128 the 3-color + transparent mode is used (c0<=c1)
    has_transparent = any(a < 128 for (_, _, _, a) in rgba16)
    pixels = []
    for (r, g, b, a) in rgba16:
        pixels.append(None if (has_transparent and a < 128) else (r, g, b))
    if not has_transparent:
        return _colour_block(pixels, four_colour=True)
    visible = [p for p in pixels if p is not None]
    c0, c1 = _pick_endpoints(visible)
    if c0 > c1:
        c0, c1 = c1, c0
    if c0 == c1:
        c1 = max(0, c0 - 1)
    pal = _palette_dxt1(c0, c1, four_colour=False)
    indices = 0
    for i, p in enumerate(pixels):
        if p is None:
            idx = 3
        else:
            idx = _nearest(pal, p)
        indices |= (idx & 3) << (2 * i)
    return struct.pack("<HH", c0, c1) + struct.pack("<I", indices & 0xFFFFFFFF)


def dxt3_encode_block(rgba16) -> bytes:
    """`rgba16`: 16 tuples (r,g,b,a). DXT2/3 = 8 B explicit alpha + color."""
    alpha = bytearray(8)
    for i, (_, _, _, a) in enumerate(rgba16):
        a4 = min(15, (a + 8) // 17)
        if i & 1:
            alpha[i >> 1] |= a4 << 4
        else:
            alpha[i >> 1] |= a4
    pixels = [(r, g, b) for (r, g, b, a) in rgba16]
    # transparent pixels must not condition the color endpoints
    visible = [(r, g, b) for (r, g, b, a) in rgba16 if a > 0]
    if not visible:
        return bytes(alpha) + b"\x00" * 8
    c0, c1 = _pick_endpoints(visible)
    # DXT3 always decodes in 4-color mode (explicit alpha), so the
    # order of c0/c1 does not change the palette; it is left as is.
    pal = _palette_dxt1(c0, c1, four_colour=True)
    indices = 0
    for i, (r, g, b, a) in enumerate(rgba16):
        idx = 0 if a == 0 else _nearest(pal, (r, g, b))
        indices |= (idx & 3) << (2 * i)
    return bytes(alpha) + struct.pack("<HH", c0, c1) + struct.pack("<I", indices & 0xFFFFFFFF)


def dxt5_encode_block(rgba16) -> bytes:
    """`rgba16`: 16 tuples (r,g,b,a). DXT4/5 = interpolated alpha."""
    alphas = [a for (_, _, _, a) in rgba16]
    a0, a1 = max(alphas), min(alphas)
    table = [a0, a1]
    if a0 > a1:
        table += [((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)]
    else:
        table += [((4 - i) * a0 + (i + 1) * a1) // 5 for i in range(4)]
        table += [0, 255]
    bits = 0
    for i, a in enumerate(alphas):
        idx = min(range(len(table)), key=lambda k: abs(table[k] - a))
        bits |= (idx & 7) << (3 * i)
    alpha = bytes((a0, a1)) + bits.to_bytes(6, "little")
    pixels = [(r, g, b) for (r, g, b, a) in rgba16]
    visible = [(r, g, b) for (r, g, b, a) in rgba16 if a > 0]
    if not visible:
        return alpha + b"\x00" * 8
    c0, c1 = _pick_endpoints(visible)
    pal = _palette_dxt1(c0, c1, four_colour=True)
    indices = 0
    for i, (r, g, b, a) in enumerate(rgba16):
        idx = 0 if a == 0 else _nearest(pal, (r, g, b))
        indices |= (idx & 3) << (2 * i)
    return alpha + struct.pack("<HH", c0, c1) + struct.pack("<I", indices & 0xFFFFFFFF)


def encode_block(fmt: int, rgba16) -> bytes:
    if fmt == FMT_DXT1:
        return dxt1_encode_block(rgba16)
    if fmt == FMT_DXT3:
        return dxt3_encode_block(rgba16)
    if fmt == FMT_DXT5:
        return dxt5_encode_block(rgba16)
    raise aif_mod.AifError("encode_block: formato no soportado 0x%02X" % fmt)


# --------------------------------------------------------------------------
# editor
# --------------------------------------------------------------------------
class AifEditor:
    """Wraps an AIF and allows replacing cells/texels by re-encoding DXT."""

    def __init__(self, data: bytes, base: int = 0):
        self.original = bytes(data)
        self.base = base
        self.image = aif_mod.AifImage(self.original, base)
        if not self.image.compressed:
            raise aif_mod.AifError("aif_edit sólo soporta DXT por ahora (%s)"
                                   % self.image.format_name)
        self.fmt = self.image.format
        self.block_bytes = 8 if self.fmt == FMT_DXT1 else 16
        self.header = bytearray(self.original[:self.image.data_offset])
        base = self.image.data_offset
        self.base_size = self.image.base_level_size()
        self.raw = bytearray(self.original[base:base + self.base_size])
        self.tail = bytes(self.original[base + self.base_size:])
        self.tw = self.image.tiled_width
        self.bx = self.image.elements_x  # blocks per row
        self.by = self.image.elements_y

    # -- block access ------------------------------------------------------
    def _swapped(self) -> bytearray:
        return swap_words(self.raw) if self.block_bytes != 4 else self.raw

    def linear_blocks(self) -> bytes:
        """Blocks in PC order (row-major), same as `AifImage.untiled()`."""
        return self.image.untiled()

    def write_block(self, bx: int, by: int, block: bytes):
        """Writes a 4x4 block at (bx, by) [block coordinates]."""
        assert len(block) == self.block_bytes
        off = aif_mod.tiled_offset(bx, by, self.tw, self.block_bytes) * self.block_bytes
        self.raw[off:off + self.block_bytes] = (
            swap_words(block) if self.block_bytes != 4 else block)

    def rebuild_from_linear(self, linear: bytes):
        """Re-tiles `self.raw` from linear blocks (inverse of untiled)."""
        size = self.block_bytes
        assert len(linear) == self.bx * self.by * size
        for y in range(self.by):
            for x in range(self.bx):
                o = (y * self.bx + x) * size
                self.write_block(x, y, linear[o:o + size])

    # -- 32x32 cells -------------------------------------------------------
    def write_cell_rgba(self, row: int, col: int, rgba: bytes,
                        cell_w: int = 32, cell_h: int = 32):
        """Replaces cell (row,col) with an RGBA of `cell_w`x`cell_h`."""
        assert len(rgba) == cell_w * cell_h * 4
        for by in range(cell_h // 4):
            for bx in range(cell_w // 4):
                pixels = []
                for yy in range(4):
                    for xx in range(4):
                        gx = bx * 4 + xx
                        gy = by * 4 + yy
                        o = (gy * cell_w + gx) * 4
                        pixels.append(tuple(rgba[o:o + 4]))
                block = encode_block(self.fmt, pixels)
                self.write_block(col * (cell_w // 4) + bx,
                                 row * (cell_h // 4) + by, block)

    def to_bytes(self) -> bytes:
        return bytes(self.header) + bytes(self.raw) + self.tail

    # -- round-trip --------------------------------------------------------
    def verify_wrapper(self) -> bool:
        """The wrapper (tiling + byte-swap) is exact if rebuilding the
        linear blocks reproduces the original pixel byte for byte."""
        linear = self.linear_blocks()
        fresh = AifEditor(self.original, self.base)
        fresh.rebuild_from_linear(linear)
        return bytes(fresh.raw) == bytes(self.raw)


# --------------------------------------------------------------------------
# utilities
# --------------------------------------------------------------------------
def decode_rgba(data: bytes, base: int = 0):
    img = aif_mod.AifImage(data, base)
    return img.width, img.height, img.to_rgba()


def blank_cells(data: bytes, cell_w: int = 32, cell_h: int = 32):
    """Returns the indices of fully transparent cells (alpha==0)."""
    w, h, rgba = decode_rgba(data)
    cols = w // cell_w
    rows = h // cell_h
    blanks = []
    for idx in range(cols * rows):
        r, c = divmod(idx, cols)
        empty = True
        for yy in range(r * cell_h, (r + 1) * cell_h):
            for xx in range(c * cell_w, (c + 1) * cell_w):
                if rgba[(yy * w + xx) * 4 + 3] != 0:
                    empty = False
                    break
            if not empty:
                break
        if empty:
            blanks.append(idx)
    return blanks


def free_cells(data: bytes, cell_w: int = 32, cell_h: int = 32):
    """Cells without a glyph: transparent **or** uniform fills (white/black).

    The atlases reserve leftover cells as an opaque white square; for the
    purpose of drawing new glyphs, transparent and uniform fill are both
    reusable "holes".
    """
    w, h, rgba = decode_rgba(data)
    cols = w // cell_w
    rows = h // cell_h
    out = []
    for idx in range(cols * rows):
        r, c = divmod(idx, cols)
        first = rgba[((r * cell_h) * w + c * cell_w) * 4:
                     ((r * cell_h) * w + c * cell_w) * 4 + 4]
        uniform = True
        for yy in range(r * cell_h, (r + 1) * cell_h):
            base = (yy * w + c * cell_w) * 4
            for xx in range(cell_w):
                o = base + xx * 4
                if rgba[o:o + 4] != first:
                    uniform = False
                    break
            if not uniform:
                break
        if uniform:
            out.append(idx)
    return out


# --------------------------------------------------------------------------
# self-checks
# --------------------------------------------------------------------------
def _psnr_visible(a: bytes, b: bytes) -> float:
    """PSNR over alpha + RGB only where either of the two is visible."""
    import math
    n = len(a) // 4
    se = 0.0
    count = 0
    for i in range(n):
        o = i * 4
        aa, ba = a[o + 3], b[o + 3]
        for ch in range(3):
            if aa > 0 or ba > 0:
                se += (a[o + ch] - b[o + ch]) ** 2
                count += 1
        se += (aa - ba) ** 2
        count += 1
    mse = se / count if count else 0.0
    if mse == 0:
        return float("inf")
    return 10.0 * math.log10(255 * 255 / mse)


def selftest() -> int:
    ok = True

    # 1) DXT3 codec: exact per-pixel explicit alpha + exact white
    rgba16 = [(0, 0, 0, i * 17) for i in range(16)]
    aout = [p[3] for p in _decode_one_block(dxt3_encode_block(rgba16), FMT_DXT3)]
    if aout != [i * 17 for i in range(16)]:
        print("[x] DXT3: alpha por píxel no exacta:", aout)
        ok = False
    else:
        print("[ok] DXT3 alpha por píxel exacta")
    exact = _decode_one_block(dxt3_encode_block(
        [(255, 255, 255, 255)] * 8 + [(0, 0, 0, 0)] * 8), FMT_DXT3)
    if exact[:8] != [(255, 255, 255, 255)] * 8:
        print("[x] DXT3: blanco no exacto:", exact[:3])
        ok = False
    else:
        print("[ok] DXT3 blanco/transparente exacto")

    # 2) round-trip of a real atlas
    sample = None
    for cand in ("extract/f0/d1_ud1_000A4000_005.aif",
                 "extract/f0/d1_ud2_A4DAA000_040.aif"):
        p = HERE.parent / cand
        if p.is_file():
            sample = p
            break
    if sample:
        data = sample.read_bytes()
        ed = AifEditor(data)
        r1 = ed.to_bytes() == data
        r2 = ed.verify_wrapper()
        print("[%s] fichero sin tocar se re-emite idéntico" % ("ok" if r1 else "x"))
        print("[%s] envoltorio (tiling+byteorder) exacto en %s"
              % ("ok" if r2 else "x", sample.name))
        ok = ok and r1 and r2

        # 3) DXT3 round-trip over the whole atlas (lossy)
        w, h, rgba = decode_rgba(data)
        ed2 = AifEditor(data)
        for row in range(0, h // 32):
            for col in range(0, w // 32):
                off = 0
                cell = bytearray(32 * 32 * 4)
                for yy in range(32):
                    s = ((row * 32 + yy) * w + col * 32) * 4
                    cell[yy * 32 * 4:(yy * 32 + 32) * 4] = rgba[s:s + 32 * 4]
                ed2.write_cell_rgba(row, col, bytes(cell))
        w2, h2, rgba2 = decode_rgba(ed2.to_bytes())
        p = _psnr_visible(rgba, rgba2)
        print("[ok] re-encode DXT3 del atlas completo: PSNR(visible)=%.2f dB" % p)
        if p < 25:
            print("[x] PSNR demasiado bajo")
            ok = False
    else:
        print("[!] no hay atlas de muestra para el round-trip")
    return 0 if ok else 1


def _decode_one_block(block: bytes, fmt: int):
    """Decodes a single 4x4 block to a list of 16 (r,g,b,a)."""
    if fmt == FMT_DXT3:
        bits = int.from_bytes(block[0:8], "little")
        alphas = [((bits >> (4 * i)) & 0xF) * 17 for i in range(16)]
        colour = block[8:16]
    elif fmt == FMT_DXT1:
        alphas = [255] * 16
        colour = block
    else:
        raise ValueError
    c0, c1 = struct.unpack_from("<HH", colour, 0)
    r0, g0, b0 = rgb565_to_888(c0)
    r1, g1, b1 = rgb565_to_888(c1)
    pal = [(r0, g0, b0), (r1, g1, b1),
           ((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3),
           ((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3)]
    indices = int.from_bytes(colour[4:8], "little")
    out = []
    for i in range(16):
        r, g, b = pal[(indices >> (2 * i)) & 3]
        out.append((r, g, b, alphas[i]))
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cmd_info(args):
    img = aif_mod.AifImage(Path(args.file).read_bytes())
    print("format   : 0x%02X %s" % (img.format, img.format_name))
    print("size     : %dx%d  elements %dx%d of %dB"
          % (img.width, img.height, img.elements_x, img.elements_y,
             img.element_bytes))
    print("pitch    : %d  tiled_width=%d tiled_height=%d"
          % (img.pitch, img.tiled_width, img.tiled_height))
    return 0


def cmd_png(args):
    img = aif_mod.AifImage(Path(args.file).read_bytes())
    aif_mod.write_png(args.output, img.width, img.height, img.to_rgba())
    print("-> %s (%dx%d)" % (args.output, img.width, img.height))
    return 0


def cmd_roundtrip(args):
    data = Path(args.file).read_bytes()
    ed = AifEditor(data)
    same = ed.to_bytes() == data
    wrapper = ed.verify_wrapper()
    print("re-emitir idéntico      : %s" % same)
    print("envoltorio exacto       : %s" % wrapper)
    return 0 if (same and wrapper) else 1


def cmd_blanks(args):
    data = Path(args.file).read_bytes()
    bl = blank_cells(data, args.cell, args.cell)
    print("celdas en blanco (%d): %s" % (len(bl), bl))
    return 0


def cmd_montage(args):
    """Contact sheet of a range of cells, labeled with their index."""
    from PIL import Image, ImageDraw  # lazy import (only this command)
    data = Path(args.file).read_bytes()
    img = aif_mod.AifImage(data)
    rgba = img.to_rgba()
    src = Image.frombytes("RGBA", (img.width, img.height), rgba)
    cols_grid = img.width // args.cell
    S = args.scale
    lab = 20
    ncols = args.cols
    nrows = (args.count + ncols - 1) // ncols
    canvas = Image.new("RGBA",
                       (ncols * (args.cell * S + 4),
                        nrows * (args.cell * S + lab + 4)), (20, 20, 20, 255))
    dr = ImageDraw.Draw(canvas)
    for j in range(args.count):
        idx = args.start + j
        r, c = divmod(idx, cols_grid)
        cell = src.crop((c * args.cell, r * args.cell,
                         c * args.cell + args.cell, r * args.cell + args.cell))
        cell = cell.resize((args.cell * S, args.cell * S), Image.NEAREST)
        gx = (j % ncols) * (args.cell * S + 4)
        gy = (j // ncols) * (args.cell * S + lab + 4)
        canvas.paste(cell, (gx, gy), cell)
        dr.text((gx + 2, gy + args.cell * S + 2), str(idx), fill=(255, 255, 0, 255))
    canvas.save(args.out)
    print("-> %s (%d celdas desde %d)" % (args.out, args.count, args.start))
    return 0


def cmd_survey(args):
    """Count of free cells per bank (to decide where to add glyphs)."""
    base = Path(args.dir)
    files = sorted(base.glob("*.aif"))
    if not files:
        sys.exit("no hay .aif en %s" % base)
    print("%-30s %6s %6s %6s %8s" % ("stem", "cells", "count", "free",
                                     ">=count"))
    n_big = 0
    rows = []
    for aif in files:
        stem = aif.stem
        try:
            data = aif.read_bytes()
            img = aif_mod.AifImage(data)
        except Exception as exc:  # noqa: BLE001
            print("  ! %s: %s" % (stem, exc), file=sys.stderr)
            continue
        cols = img.width // args.cell
        rws = img.height // args.cell
        cells = cols * rws
        count = 0
        msg = aif.with_suffix(".msg")
        if msg.is_file():
            d = msg.read_bytes()
            if len(d) >= 0x38:
                count = struct.unpack_from(">I", d, 0x34)[0]
        free = free_cells(data, args.cell, args.cell)
        free_ge = sum(1 for i in free if i >= count)
        rows.append((stem, cells, count, len(free), free_ge))
        n_big += free_ge >= args.need
    for stem, cells, count, free, free_ge in rows:
        print("%-30s %6d %6d %6d %8d" % (stem, cells, count, free, free_ge))
    print("\nbancos=%d  con >=%d celdas libres tras count: %d"
          % (len(rows), args.need, n_big))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Editor de atlas AIF (DXT2/3).")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info"); s.add_argument("file"); s.set_defaults(func=cmd_info)
    s = sub.add_parser("png"); s.add_argument("file"); s.add_argument("output")
    s.set_defaults(func=cmd_png)
    s = sub.add_parser("roundtrip"); s.add_argument("file")
    s.set_defaults(func=cmd_roundtrip)
    s = sub.add_parser("blanks"); s.add_argument("file")
    s.add_argument("--cell", type=int, default=32); s.set_defaults(func=cmd_blanks)
    s = sub.add_parser("survey", help="celdas libres por banco de una carpeta")
    s.add_argument("--dir", default="extract/f0")
    s.add_argument("--cell", type=int, default=32)
    s.add_argument("--need", type=int, default=16,
                   help="nº de glifos a añadir (para el resumen)")
    s.set_defaults(func=cmd_survey)
    s = sub.add_parser("montage", help="hoja de contacto de un rango de celdas")
    s.add_argument("file")
    s.add_argument("start", type=int)
    s.add_argument("count", type=int)
    s.add_argument("--out", default="montage.png")
    s.add_argument("--cols", type=int, default=12)
    s.add_argument("--scale", type=int, default=3)
    s.add_argument("--cell", type=int, default=32)
    s.set_defaults(func=cmd_montage)
    s = sub.add_parser("selftest"); s.set_defaults(func=lambda a: selftest())

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
