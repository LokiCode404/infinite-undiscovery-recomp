#!/usr/bin/env python3
"""
add_accents.py -- F3: adds the Spanish glyphs to a `RMD-` atlas.

The font atlas of each `RMD-` is a DXT2/3 `AIF ` whose 32x32 cell grid is
ordered by **first appearance** in the text of that bank; the glyph for code
`c` occupies cell `c - 301` (`cols = atlas_w/32`, row-major).

This script, for a specific bank (by default the main Latin atlas
`d1_ud1_000A4000_005`):

  1. decodes the `AIF` and locates the cells of the base letters;
  2. composes, with PIL, the 16 glyphs `á é í ó ú ü ñ Á É Í Ó Ú Ü Ñ ¿ ¡`
     (base + drawn diacritic; `¿`/`¡` = `?`/`!` rotated 180°);
  3. writes them into **free** cells (the ones after `count`, still blank);
  4. re-encodes the `AIF` (see `tools/aif_edit.py`);
  5. updates the `.msg`: `count`/`count2` and the metric table (new
     entries = the metric of the base letter);
  6. renders a test string with the new codes and with the game's
     encoding (`tools/game_text_codec.py`).

Usage
-----
    python tools/add_accents.py                 # default bank, output extract/f2
    python tools/add_accents.py --stem d1_ud1_000A4000_005 --out extract/f2
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"))

import aif as aif_mod          # noqa: E402
import aif_edit                # noqa: E402
import game_text_codec as codec  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

CELL = 32
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)

# Cell (index) of the **NORMAL** copy of each base letter in the Latin atlas
# 005.  The atlas has several variants per character (different size/weight,
# ordered by first appearance); the one used by the NORMAL TEXT must be used,
# which is the MOST FREQUENT in the bank (`build_es_codes.bank_code_freq`).
# Previously BOLD variants were copied (closed counter, filled stroke) -> all
# accents came out bold.
#
#   ch  cell   freq(005)
#   a   18     4208        (previously 97,  freq 1  = bold)
#   e   20     4251        (previously 131, freq 7  = bold)
#   i   27     2127        (previously 128, freq 4  = bold)
#   o   35     2877        (previously 100, freq 3  = bold)
#   u   23     905         (previously 104, freq 1  = bold)
#   n   25     2183        (previously 101, freq 3  = bold)
#   c   28     1038        (previously 142, freq 1  = bold)
#   A   5      199         (previously 130, freq 1  = bold)
#   E   10     286         (previously 140, freq 1  = bold)
#   I   518    --          (previously 124, freq 0; 518 is the NORMAL serif 'I'
#                           of the charmap, c124 was a thick stem without serifs)
#   O   13     107         (previously 105, freq 1  = bold)
#   U   11     62          (previously 118, freq 2  = bold)
#   N   3      101         (previously 125, freq 1  = bold)
#   ?   189    40          (previously 116, freq 1  = bold)
#   !   161    464         (previously 143, freq 3  = bold)
#   f   38     553         (only variant with frequency)
#   l   21     1777        (only normal variant; 196/237 are italic)
#   Q   368    19          (previously 313, freq 1; the charmap maps 'Q' to 368)
BASE_CELL = {
    "a": 18, "e": 20, "i": 27, "o": 35, "u": 23, "n": 25, "c": 28,
    "A": 5, "E": 10, "I": 518, "O": 13, "U": 11, "N": 3,
    "?": 189, "!": 161, "f": 38, "l": 21, "Q": 368,
}

# order of the 16 new glyphs (they are assigned consecutive codes)
NEW_GLYPHS = ["á", "é", "í", "ó", "ú", "ü", "ñ", "Á", "É", "Í", "Ó", "Ú",
              "Ü", "Ñ", "¿", "¡"]

ACCENT = {
    "á": ("acute", "a"), "é": ("acute", "e"), "í": ("acute_i", "i"),
    "ó": ("acute", "o"), "ú": ("acute", "u"), "ü": ("diaeresis", "u"),
    "ñ": ("tilde", "n"),
    "Á": ("acute_up", "A"), "É": ("acute_up", "E"), "Í": ("acute_up", "I"),
    "Ó": ("acute_up", "O"), "Ú": ("acute_up", "U"), "Ü": ("diaeresis_up", "U"),
    "Ñ": ("tilde_up", "N"),
}
ROTATE = {"¿": "?", "¡": "!"}

# Optical horizontal nudge (px, right) of the diacritic, per base letter.  The
# round lowercase vowels have their ink bbox center slightly left of the visual
# center, so the accent is shifted right to align with the vowel.
OPTICAL_DX = {"a": 2, "e": 2, "o": 2}


# --------------------------------------------------------------------------
# image utilities
# --------------------------------------------------------------------------
def cell_image(rgba, width, idx, cw=CELL, ch=CELL):
    img = Image.frombytes("RGBA", (width, width), rgba)
    cols = width // cw
    r, c = divmod(idx, cols)
    return img.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))


def ink_bbox(img):
    a = img.split()[3]
    return a.getbbox()  # (l, t, r, b) or None


def draw_stroke(draw, pts, width, joints=True):
    """Draws a polyline with the atlas style: black border + white core.

    The border is thin (1 px per side) so the diacritic does not become a
    thick bar when scaled down in the game; the white core is `width` px.
    """
    kw = {"joint": "curve"} if joints else {}
    draw.line(pts, fill=BLACK, width=width + 1, **kw)
    draw.line(pts, fill=WHITE, width=width, **kw)


def add_acute(draw, cx, top, bottom, width=1, dx=3):
    """Acute accent: thin diagonal stroke (not a horizontal bar).

    With `dx=3`, `top=2`, `bottom=7` the stroke goes from bottom-left to
    top-right with a slope of ~60°, like the typographic acute.
    """
    draw_stroke(draw, [(cx - dx, bottom), (cx + dx - 1, top)], width)


def add_diaeresis(draw, cx, cy, r=1, dx=3):
    """Two round dots with a thin border."""
    for s in (-1, 1):
        draw.ellipse([cx + s * dx - r - 1, cy - r - 1, cx + s * dx + r + 1, cy + r + 1],
                     fill=BLACK)
        draw.ellipse([cx + s * dx - r, cy - r, cx + s * dx + r, cy + r], fill=WHITE)


def add_tilde(draw, cx, cy, w=12, amp=2.5):
    """Tilde of the ñ: clear wave (more amplitude so it does not look like a bar)."""
    pts = []
    n = 24
    for i in range(n + 1):
        t = i / n
        x = cx - w / 2 + w * t
        y = cy - amp * math.sin(2 * math.pi * t)
        pts.append((x, y))
    draw_stroke(draw, pts, 1)


def compose(base, kind, src=None):
    """Returns a 32x32 image with the base letter + the diacritic.

    `src` = base letter character (e.g. "a","e","o","i"): used for the optical
    horizontal adjustment of the diacritic.  The ink bbox center of the round
    lowercase vowels (a/e/o) sits slightly LEFT of their visual center, so the
    accent came out ~2 px to the left; `OPTICAL_DX` nudges it to the right so it
    aligns with the vowel (tested against the English atlas).
    """
    out = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    b = base
    if kind.endswith("_up"):          # uppercase: shrunk to leave room
        nh = 26
        b = base.resize((nh, nh), Image.LANCZOS)
        # anchored at the bottom (baseline kept) and centered
        out.alpha_composite(b, ((CELL - nh) // 2, CELL - nh))
    else:
        out.alpha_composite(base)
    if kind == "acute_i":
        # í is an i without a dot: the dot is erased before placing the accent
        px = out.load()
        for yy in range(0, 9):
            for xx in range(CELL):
                r, g, bb, _ = px[xx, yy]
                px[xx, yy] = (r, g, bb, 0)
    draw = ImageDraw.Draw(out)
    bb = ink_bbox(out)
    cx = (bb[0] + bb[2]) // 2 if bb else CELL // 2
    cx += OPTICAL_DX.get(src, 0)
    if kind in ("acute", "acute_i", "acute_up"):
        add_acute(draw, cx, top=2, bottom=7)
    elif kind in ("diaeresis", "diaeresis_up"):
        add_diaeresis(draw, cx, cy=5)
    elif kind in ("tilde", "tilde_up"):
        add_tilde(draw, cx, cy=5, w=12)
    return out


def rotate_180(base):
    """`?`/`!` rotated 180° keeping the ink center (¿ / ¡)."""
    bb = ink_bbox(base)
    if bb is None:
        return base
    glyph = base.crop(bb).rotate(180, expand=True)
    out = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    cxc = (bb[0] + bb[2]) // 2
    cyc = (bb[1] + bb[3]) // 2
    out.alpha_composite(glyph, (cxc - glyph.width // 2, cyc - glyph.height // 2))
    return out


# --------------------------------------------------------------------------
# .msg
# --------------------------------------------------------------------------
class Msg:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        self.count = struct.unpack_from(">I", self.data, 0x34)[0]
        self.metrics_off = struct.unpack_from(">I", self.data, 0x28)[0]
        self.total = struct.unpack_from(">I", self.data, 0x30)[0]

    def metric(self, idx):
        return struct.unpack_from(">H", self.data, self.metrics_off + 2 * idx)[0]

    def set_metric(self, idx, value):
        off = self.metrics_off + 2 * idx
        if off + 2 > len(self.data):
            self.data.extend(b"\x00" * (off + 2 - len(self.data)))
        struct.pack_into(">H", self.data, off, value)

    def to_bytes(self):
        return bytes(self.data)


# --------------------------------------------------------------------------
# pipeline
# --------------------------------------------------------------------------
def patch(stem: str, outdir: Path):
    aif_path = REPO / "extract" / "f0" / (stem + ".aif")
    msg_path = REPO / "extract" / "f0" / (stem + ".msg")
    aif_bytes = aif_path.read_bytes()
    msg = Msg(msg_path.read_bytes())
    width, height, rgba = aif_edit.decode_rgba(aif_bytes)

    ed = aif_edit.AifEditor(aif_bytes)
    cols = width // CELL

    # new cells: the first cells without a glyph (transparent or uniform
    # fill) that are above `count`
    free_all = aif_edit.free_cells(aif_bytes)
    free = [i for i in free_all if i >= msg.count]
    if len(free) < len(NEW_GLYPHS):
        raise SystemExit("no hay suficientes celdas libres: %d < %d"
                         % (len(free), len(NEW_GLYPHS)))

    base_imgs = {ch: cell_image(rgba, width, idx) for ch, idx in BASE_CELL.items()}

    plan = []
    for j, ch in enumerate(NEW_GLYPHS):
        idx = free[j]
        code = 301 + idx
        row, col = divmod(idx, cols)
        if ch in ROTATE:
            img = rotate_180(base_imgs[ROTATE[ch]])
            src = ROTATE[ch]
        else:
            kind, src = ACCENT[ch]
            img = compose(base_imgs[src], kind, src)
        ed.write_cell_rgba(row, col, img.tobytes())
        plan.append((ch, code, idx, src))

    patched_aif = ed.to_bytes()
    # the AIF size does not change (same dimensions/format)
    assert len(patched_aif) == len(aif_bytes)

    # verification: the NON-modified blocks stay intact byte for byte
    orig_raw = aif_edit.AifEditor(aif_bytes).raw
    modified = {idx for (_, _, idx, _) in plan}
    allowed = set()
    for idx in modified:
        r0, c0 = divmod(idx, cols)
        for by4 in range(8):
            for bx4 in range(8):
                off = aif_mod.tiled_offset(c0 * 8 + bx4, r0 * 8 + by4,
                                           ed.tw, ed.block_bytes) * ed.block_bytes
                allowed.update(range(off, off + ed.block_bytes))
    diffs = [i for i in range(len(orig_raw)) if orig_raw[i] != ed.raw[i]]
    outside = [d for d in diffs if d not in allowed]
    print("AIF  bloques modificados: %d bytes;  bytes fuera de las celdas nuevas: %d"
          % (len(diffs), len(outside)))
    if outside:
        raise SystemExit("¡se han tocado bloques que no debían! %s" % outside[:8])

    # metrics: the base letter's (for ¿/¡, that of ?/!)
    new_count = msg.count + len(NEW_GLYPHS)
    before_len = len(msg.data)
    for (ch, code, idx, src) in plan:
        src_idx = BASE_CELL[src]
        msg.set_metric(idx, msg.metric(src_idx))
    # if the metric table sits flush against the end of the file, growing it
    # requires updating `total_size` (0x30); in 005 it is not needed (bytes to spare)
    if len(msg.data) != before_len:
        struct.pack_into(">I", msg.data, 0x30, len(msg.data))
    # count/count2
    struct.pack_into(">I", msg.data, 0x34, new_count)
    struct.pack_into(">I", msg.data, 0x54, new_count)

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / (stem + "_accents.aif")).write_bytes(patched_aif)
    (outdir / (stem + "_accents.msg")).write_bytes(msg.to_bytes())
    aif_mod.write_png(str(outdir / (stem + "_accents.png")), width, height,
                      aif_edit.decode_rgba(patched_aif)[2])

    print("AIF  %s -> %s_accents.aif (%d B)" % (aif_path.name, stem, len(patched_aif)))
    print("MSG  %s -> %s_accents.msg (count %d -> %d)"
          % (msg_path.name, stem, msg.count, new_count))
    print("\n%-3s %-6s %-5s %-4s %s" % ("ch", "code", "cell", "fila", "base"))
    for (ch, code, idx, src) in plan:
        print("%-3s %-6d %-5d %-4d %s" % (ch, code, idx, idx // cols, src))
    return patched_aif, msg.to_bytes(), plan, width, height


# --------------------------------------------------------------------------
# test render
# --------------------------------------------------------------------------
def _crop_cell(src, idx, cols):
    r, c = divmod(idx, cols)
    return src.crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL))


def render_board(rows, width, rgba, metrics, out_png, scale=3):
    """`rows`: list of lists of (code, label). Code 0 = space."""
    src = Image.frombytes("RGBA", (width, width), rgba)
    cols = width // CELL
    nrows = len(rows)
    adv = []
    for row in rows:
        adv.append([10 if code == 0 else (metrics(code) or 16) for code, _ in row])
    W = max(sum(a) for a in adv) + 8
    H = 4 + nrows * (CELL + 16) + 4
    canvas = Image.new("RGBA", (W, H), (24, 24, 28, 255))
    dr = ImageDraw.Draw(canvas)
    y = 4
    for row, arow in zip(rows, adv):
        x = 4
        for (code, label), a in zip(row, arow):
            if code:
                idx = code - 301
                if 0 <= idx < cols * (width // CELL):
                    canvas.alpha_composite(_crop_cell(src, idx, cols), (x, y))
                if label:
                    dr.text((x + 1, y + CELL + 2), label, fill=(255, 255, 0, 255))
            x += a
        y += CELL + 16
    if scale != 1:
        canvas = canvas.resize((canvas.width * scale, canvas.height * scale),
                               Image.NEAREST)
    canvas.save(out_png)
    return out_png


def main(argv=None):
    p = argparse.ArgumentParser(description="F3: añade acentos castellanos a un atlas RMD-.")
    p.add_argument("--stem", default="d1_ud1_000A4000_005")
    p.add_argument("--out", default=str(REPO / "extract" / "f2"))
    args = p.parse_args(argv)
    outdir = Path(args.out)
    stem = args.stem
    patched_aif, patched_msg, plan, width, height = patch(stem, outdir)

    _, _, rgba = aif_edit.decode_rgba(patched_aif)
    m = Msg(patched_msg)

    def metric(code):
        idx = code - 301
        if idx < 0:
            return CELL
        return (m.metric(idx) >> 8) & 0xFF  # high byte = advance in pixels

    # 1) the 16 new glyphs in a row (fixed advance to see them separated)
    row_new = [(code, ch) for (ch, code, _, _) in plan]
    render_board([row_new], width, rgba, lambda c: CELL,
                 outdir / (stem + "_accents_row.png"))

    # 2) test sentence with accents, ñ, ¿ and ¡
    # codes = 301 + cell
    WORD = {ord("n"): 301 + 101, ord("i"): 301 + 128, ord("ñ"): 864,
            ord("o"): 301 + 100, ord("O"): 301 + 105, ord("c"): 301 + 142,
            ord("a"): 301 + 97, ord("f"): 301 + 38, ord("é"): 859,
            ord("¡"): 873, ord("l"): 301 + 21, ord("!"): 301 + 143,
            ord("¿"): 872, ord("Q"): 301 + 313, ord("u"): 301 + 104,
            ord("?"): 301 + 116}
    phrases = ["niño", "café", "¡Olé!", "¿Qué?"]
    rows = []
    for ph in phrases:
        rows.append([(WORD[ord(ch)], ch) for ch in ph])
    render_board(rows, width, rgba, metric, outdir / (stem + "_accents_demo.png"))

    # 2b) final acceptance: ONE string with everything, through the game codec
    new_code = {ch: code for (ch, code, _, _) in plan}
    test = "niño café ¡Olé! ¿Qué? áéíóúüñÁÉÍÓÚÜÑ¿¡"
    test_codes = [301 if ch == " " else new_code.get(ch, WORD.get(ord(ch)))
                  for ch in test]
    blob_test = codec.encode(test_codes)
    back_test = codec.decode(blob_test)
    if back_test != test_codes:
        print("[x] la cadena de prueba no sobrevive al códec del juego")
    render_board([[(c, ch) for c, ch in zip(back_test, test)]], width, rgba,
                 metric, outdir / (stem + "_accents_test.png"))

    # 3) before/after evidence of the new cells
    orig_rgba = aif_edit.decode_rgba(
        (REPO / "extract" / "f0" / (stem + ".aif")).read_bytes())[2]
    orig = Image.frombytes("RGBA", (width, width), orig_rgba)
    new = Image.frombytes("RGBA", (width, width), rgba)
    cols = width // CELL
    S = 3
    board = Image.new("RGBA", (len(plan) * (CELL * S + 6), 2 * (CELL * S + 14) + 4),
                      (24, 24, 28, 255))
    dr = ImageDraw.Draw(board)
    for j, (ch, code, idx, _) in enumerate(plan):
        r, c = divmod(idx, cols)
        x = j * (CELL * S + 6)
        before = orig.crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL)) \
                     .resize((CELL * S, CELL * S), Image.NEAREST)
        after = new.crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL)) \
                    .resize((CELL * S, CELL * S), Image.NEAREST)
        board.alpha_composite(before, (x, 2))
        board.alpha_composite(after, (x, 2 + CELL * S + 14))
        dr.text((x + 2, 2 + CELL * S + 1), "%s cod=%d" % (ch, code),
                fill=(255, 255, 0, 255))
    board.save(outdir / (stem + "_accents_cells.png"))

    # alias with the «storefront» name
    alias = outdir / ("atlas005_accents.aif"
                      if stem.endswith("005") else (stem + "_accents.aif"))
    if alias != outdir / (stem + "_accents.aif"):
        alias.write_bytes(patched_aif)
        aif_mod.write_png(str(alias.with_suffix(".png")), width, height, rgba)

    # 4) game encoding: encode -> decode round-trip of the new codes
    codes = [code for (_, code, _, _) in plan]
    blob = codec.encode(codes)
    back = codec.decode(blob)
    print("\ncodificación del juego para los 16 códigos nuevos:")
    print("  bytes : %s" % blob.hex(" "))
    print("  decode: %s" % back)
    print("  round-trip: %s" % ("OK" if back == codes else "FALLO"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
