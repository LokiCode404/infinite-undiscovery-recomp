#!/usr/bin/env python3
"""
game_text_codec.py -- text codec of Infinite Undiscovery (ASKA).

Format resolved and VALIDATED (exact round-trip on 71,386 messages of Disc 1):
see docs/re/font-loader.md.

A `.msg` (`MessageConvertLib_1.0.0.0`):
  BE header: 0x20 records_off, 0x24 pool_off, 0x28 metrics_off, 0x30 total,
             0x34 count, 0x44/0x48 cell=32, 0x60/0x64 atlas_w/h
  directory : 16 B records (id u32, offset u32, w f32, h f32), end (0,0)
  pool      : byte-stream; encoding:
                 b0 = *p++
                 b0 < 0x80  -> code = b0
                 b0 >= 0x80 -> b1 = *p++ ; code = (b1<<7)|(b0&0x7F)
                 code == 0x0000 -> end of message
                 0x4000..0x4019 -> control (26)
                 rest           -> glyph code (= code-301 if >=300, code-1 if <300)
  atlas     : cols = atlas_w/cell_w, row-major; glyph -> cell
"""

from __future__ import annotations

import struct

MAGIC = b"MessageConvertLib_1.0.0.0"


def parse_msg(msg: bytes):
    """Returns (records[(id, offset, w, h)], pool_off, metrics_off, count, atlas_w, atlas_h)."""
    records_off, pool_off, metrics_off = struct.unpack_from(">III", msg, 0x20)
    total, count = struct.unpack_from(">II", msg, 0x30)
    cw, ch = struct.unpack_from(">II", msg, 0x44)
    atlas_w, atlas_h = struct.unpack_from(">II", msg, 0x60)
    recs = []
    off = records_off
    while off + 16 <= pool_off:
        A, B = struct.unpack_from(">II", msg, off)
        if A == 0 and B == 0:
            break
        w, h = struct.unpack_from(">ff", msg, off + 8)
        recs.append((A, B, w, h))
        off += 16
    return recs, pool_off, metrics_off, count, atlas_w, atlas_h


def read_raw(msg: bytes, start: int) -> bytes:
    """Message bytes at `start` (pool+offset) WITHOUT the 0x00 terminator."""
    i = start
    while i < len(msg) and msg[i] != 0:
        i += 1
    return msg[start:i]


def decode(raw: bytes):
    """message bytes -> list of codes (u16)."""
    codes = []
    i = 0
    while i < len(raw):
        b0 = raw[i]
        i += 1
        if b0 == 0:
            break
        if b0 & 0x80:
            if i >= len(raw):
                break
            b1 = raw[i]
            i += 1
            code = (b1 << 7) | (b0 & 0x7F)
        else:
            code = b0
        codes.append(code)
    return codes


def encode(codes) -> bytes:
    """list of codes -> message bytes, with 0x00 terminator."""
    out = bytearray()
    for c in codes:
        if c == 0:
            out.append(0)
            continue
        if c < 0x80:
            out.append(c)
        else:
            out.append((c & 0x7F) | 0x80)
            out.append((c >> 7) & 0xFF)
    out.append(0)
    return bytes(out)


# --- charmap (code -> character), read from each bank's atlas ---

def glyph_cell(code: int, atlas_w: int, atlas_h: int, cell_w: int = 32, cell_h: int = 32):
    """Returns (row, col) of the glyph in the atlas, or None if out of range."""
    if code < 300:
        idx = code - 1
    else:
        idx = code - 301
    cols = atlas_w // cell_w
    rows = atlas_h // cell_h
    if not (0 <= idx < cols * rows):
        return None
    return (idx // cols, idx % cols)


if __name__ == "__main__":
    import sys

    for path in sys.argv[1:]:
        msg = open(path, "rb").read()
        recs, pool, metrics, count, aw, ah = parse_msg(msg)
        print("%s: %d mensajes, atlas %dx%d, count=%d" % (path, len(recs), aw, ah, count))
        for A, B, w, h in recs[:5]:
            codes = decode(read_raw(msg, pool + B))
            print("  id=%d  codes=%s" % (A, ["%04X" % c for c in codes[:12]]))
