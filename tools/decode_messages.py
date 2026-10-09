#!/usr/bin/env python3
"""
decode_messages.py -- decoder for the `RMD-`/`.msg` of Infinite Undiscovery.

This module implements the resolved format (see docs/re/font-loader.md and
docs/re/ghidra-msg-loader.md):

  .msg (big-endian)
    0x20 records_off   message directory (16 B records)
    0x24 pool_off      pool of encoded codes
    0x28 metrics_off   metric table (2 B per glyph)
    0x30 total_size
    0x34 count         number of glyphs of the main font
    0x44/0x48 cell_w/cell_h
    0x58 aif_size      length of the AIF atlas
    0x60/0x64 atlas_w/atlas_h

  Directory: 16 B records  (id u32, offset u32, width f32, height f32)
             terminator (0,0).

  Pool: byte-stream.  b0=*p++
        b0 < 0x80            -> code = b0
        b0 >= 0x80           -> b1=*p++; code=(b1<<7)|(b0&0x7F)
        code == 0            -> end of message
        0x4000..0x4019       -> control (consumes variable payload)
        rest                 -> glyph: idx = code-301 (code>=300) or code-1 (<300)

The AIF atlas of each bank is the glyph table in order of FIRST APPEARANCE,
so cell `idx` of the row-major grid (cols=atlas_w/cell_w) is the
character of code `301+idx`.

Usage
-----
    python tools/decode_messages.py --msg extract/f0/xxx.msg --aif extract/f0/xxx.aif \
        [--charmap translation/charmaps/xxx.json] [--out out.txt]
    python tools/decode_messages.py --dir extract/f0 --outdir extract/messages/text \
        --charmapdir translation/charmaps
    python tools/decode_messages.py --msg ... --aif ... --render 2 render.png
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
VENDOR = REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"
sys.path.insert(0, str(VENDOR))

try:
    import aif as aif_mod  # noqa: E402
except Exception:  # pragma: no cover
    aif_mod = None

# -- payload of each control 0x4000..0x4019 --------------------------------
# derived from sub_826D43F8 (recomp.140.cpp): fixed payload size in bytes,
# or 'nul' = NUL-terminated sub-string (0x4010).
CONTROL_PAYLOAD = {
    0x4000: 0, 0x4001: 1, 0x4002: 0, 0x4003: 4, 0x4004: 0,
    0x4005: 0, 0x4006: 0, 0x4007: 4, 0x4008: 4, 0x4009: 1,
    0x400A: 2, 0x400B: 0, 0x400C: 4, 0x400D: 0, 0x400E: 4,
    0x400F: 0, 0x4010: "nul", 0x4011: 0, 0x4012: 0, 0x4013: 0,
    0x4014: 0, 0x4015: 0, 0x4016: 0, 0x4017: 0, 0x4018: 1, 0x4019: 0,
}

CONTROL_NAMES = {
    0x4000: "END", 0x4001: "COLOR_ADJ", 0x4002: "COLOR_RESTORE",
    0x4003: "COLOR_SET4", 0x4004: "COLOR_RESET", 0x4007: "CTRL07",
    0x4008: "CTRL08", 0x4009: "CTRL09", 0x400A: "COLOR2",
    0x400C: "CTRL0C", 0x400E: "CTRL0E", 0x4010: "SUBSTR",
    0x4011: "RECT", 0x4018: "CTRL18", 0x4019: "STATE",
}


class MsgError(Exception):
    pass


class MsgBank:
    """A `.msg` + (optional) its `.aif` atlas."""

    def __init__(self, msg_path: Path, aif_path: Path | None = None):
        self.path = Path(msg_path)
        self.data = self.path.read_bytes()
        d = self.data
        if len(d) < 0x68:
            raise MsgError("fichero .msg demasiado corto")
        (self.records_off, self.pool_off, self.metrics_off) = \
            struct.unpack_from(">III", d, 0x20)
        (self.total_size, self.count) = struct.unpack_from(">II", d, 0x30)
        self.f38, self.f3c = struct.unpack_from(">II", d, 0x38)
        self.f40 = struct.unpack_from(">I", d, 0x40)[0]
        (self.cell_w, self.cell_h) = struct.unpack_from(">II", d, 0x44)
        self.bytes_per_code = struct.unpack_from(">I", d, 0x4C)[0]
        self.f50 = struct.unpack_from(">I", d, 0x50)[0]
        self.count2 = struct.unpack_from(">I", d, 0x54)[0]
        self.aif_size = struct.unpack_from(">I", d, 0x58)[0]
        self.magic2 = struct.unpack_from(">I", d, 0x5C)[0]
        (self.atlas_w, self.atlas_h) = struct.unpack_from(">II", d, 0x60)

        self.records = self._parse_records()
        self.aif_path = Path(aif_path) if aif_path else self._guess_aif()
        self._atlas = None

    # -- directory --------------------------------------------------------
    def _parse_records(self):
        recs = []
        p = self.records_off
        d = self.data
        if self.records_off == 0:
            return recs
        while p + 16 <= len(d):
            A, B = struct.unpack_from(">II", d, p)
            if A == 0 and B == 0:
                break
            w, h = struct.unpack_from(">ff", d, p + 8)
            recs.append({"id": A, "offset": B, "w": w, "h": h})
            p += 16
            if p > self.pool_off and self.pool_off:
                break
        return recs

    def _guess_aif(self):
        cand = self.path.with_suffix(".aif")
        return cand if cand.exists() else None

    # -- pool --------------------------------------------------------------
    def decode(self, msg_id):
        """Returns the list of tokens {'kind':'glyph'|'ctrl','code':..}."""
        rec = next((r for r in self.records if r["id"] == msg_id), None)
        if rec is None:
            raise KeyError("id %r no encontrado" % (msg_id,))
        return self.decode_stream(self.pool_off + rec["offset"])

    def decode_stream(self, off):
        d = self.data
        p = off
        toks = []
        n = len(d)
        while p < n:
            b0 = d[p]
            p += 1
            if b0 == 0:
                toks.append({"kind": "end", "code": 0})
                break
            if b0 < 0x80:
                code = b0
            else:
                if p >= n:
                    break
                b1 = d[p]
                p += 1
                code = (b1 << 7) | (b0 & 0x7F)
            if code >= 0x4000:
                payload = []
                if code in CONTROL_PAYLOAD:
                    spec = CONTROL_PAYLOAD[code]
                    if spec == "nul":
                        while p < n and d[p] != 0:
                            payload.append(d[p])
                            p += 1
                        if p < n:
                            p += 1  # consume NUL
                    else:
                        payload = list(d[p:p + spec])
                        p += spec
                toks.append({"kind": "ctrl", "code": code,
                             "name": CONTROL_NAMES.get(code, "CTRL"),
                             "payload": payload})
            else:
                toks.append({"kind": "glyph", "code": code})
        return toks

    # -- atlas -------------------------------------------------------------
    def atlas(self):
        if self._atlas is None:
            if self.aif_path is None or not Path(self.aif_path).exists():
                raise MsgError("no hay atlas .aif para %s" % self.path.name)
            if aif_mod is None:
                raise MsgError("no se pudo importar aif.py")
            self._atlas = aif_mod.AifImage(
                Path(self.aif_path).read_bytes(), 0)
        return self._atlas

    def atlas_cells(self):
        """List of (idx, code, glyph_index, RGBA bytes) - requires PIL."""
        from PIL import Image
        at = self.atlas()
        img = Image.frombytes("RGBA", (at.width, at.height), at.to_rgba())
        cols = self.atlas_w // self.cell_w if self.cell_w else 0
        rows = self.atlas_h // self.cell_h if self.cell_h else 0
        cells = []
        idx = 0
        for r in range(rows):
            for c in range(cols):
                box = (c * self.cell_w, r * self.cell_h,
                       (c + 1) * self.cell_w, (r + 1) * self.cell_h)
                cells.append((idx, 301 + idx, idx, img.crop(box)))
                idx += 1
        return cells

    # -- charmap -----------------------------------------------------------
    def load_charmap(self, path):
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
        # accepts {"map": {code: char}} or {code: char}
        m = obj.get("map", obj) if isinstance(obj, dict) else {}
        return {int(k): v for k, v in m.items()}


# -- decoding to text -------------------------------------------------------

def code_to_char(code, charmap):
    """Returns (text, status). status: 'ok' | 'unknown' | 'small'."""
    if code in charmap:
        return charmap[code], "ok"
    if code >= 300:
        return "?[%d]" % code, "unknown"
    return "?[small:%d]" % code, "small"


def tokens_to_text(toks, charmap):
    out = []
    for t in toks:
        if t["kind"] == "end":
            break
        if t["kind"] == "ctrl":
            if t["code"] == 0x4000:
                continue
            if t["payload"]:
                pl = ",".join(str(x) for x in t["payload"])
                out.append("{0x%04X:%s}" % (t["code"], pl))
            else:
                out.append("{0x%04X}" % t["code"])
        else:
            ch, st = code_to_char(t["code"], charmap)
            out.append(ch)
    return "".join(out)


# -- render of a message (visual validation) --------------------------------

def render_message(bank: MsgBank, msg_id, out_png: Path, scale=1):
    from PIL import Image, ImageDraw
    toks = bank.decode(msg_id)
    cells = {idx: im for (idx, code, i2, im) in bank.atlas_cells()}
    glyphs = [t["code"] for t in toks if t["kind"] == "glyph" and t["code"] >= 300]
    cw, ch = bank.cell_w, bank.cell_h
    W = max(1, len(glyphs)) * cw
    img = Image.new("RGBA", (W, ch + 14), (0, 0, 0, 255))
    dr = ImageDraw.Draw(img)
    x = 0
    for code in glyphs:
        idx = code - 301
        im = cells.get(idx)
        if im is not None:
            img.paste(im, (x, 0), im)
        dr.text((x + 2, ch + 1), str(code), fill=(255, 255, 0, 255))
        x += cw
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale),
                         Image.NEAREST)
    img.save(out_png)
    return out_png


# -- CLI --------------------------------------------------------------------

def cmd_render(args):
    bank = MsgBank(args.msg, args.aif)
    render_message(bank, args.render, Path(args.out_png), args.scale)
    print("render -> %s" % args.out_png)


def cmd_one(args):
    bank = MsgBank(args.msg, args.aif)
    charmap = bank.load_charmap(args.charmap) if args.charmap else {}
    lines = []
    for rec in bank.records:
        toks = bank.decode_stream(bank.pool_off + rec["offset"])
        lines.append("%s\t%s" % (rec["id"], tokens_to_text(toks, charmap)))
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print("escrito %s (%d mensajes)" % (args.out, len(lines)))
    else:
        sys.stdout.write(text)


def main(argv=None):
    p = argparse.ArgumentParser(description="Decodificador de mensajes IU")
    p.add_argument("--msg", required=True)
    p.add_argument("--aif")
    p.add_argument("--charmap")
    p.add_argument("--out")
    p.add_argument("--render", type=int, help="id de mensaje a renderizar")
    p.add_argument("--out-png")
    p.add_argument("--scale", type=int, default=1)
    args = p.parse_args(argv)
    if args.render is not None:
        args.out_png = args.out_png or "render_%d.png" % args.render
        return cmd_render(args)
    return cmd_one(args)


if __name__ == "__main__":
    raise SystemExit(main())
