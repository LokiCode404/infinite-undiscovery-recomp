#!/usr/bin/env python3
"""
ui_textures.py -- translates the LABELS that are TEXTURES (bitmaps) in AIF.

Context
-------
In Infinite Undiscovery many fixed labels (CAMP menu tabs, "Pause",
"Now Loading...", "GAME OVER", "Reload.") are NOT `.msg` text but pixels baked
into `AIF` textures (see `docs/re/second-text-path.md`).  This module decodes
them, paints the equivalent Spanish with PIL honoring style/size/box and
**re-encodes** them preserving the original format:

* `A8R8G8B8` (0x48)  -> uncompressed; 1:1 byte-exact edit.
* `DXT1/2/3/4/5`     -> only the touched 4x4 blocks are re-encoded (via
  `tools/aif_edit.py`), so the rest of the atlas stays intact.

Fit rules
---------
The new text is **shrunk** (font) until it fits the available gap up to the
neighboring label (the sprite's real sampling limit); it never overlaps
another label. Row height is honored too. The goal is for the label to keep
"fitting" in the same gap where the engine samples the original.

Usage
-----
    python -X utf8 tools/ui_textures.py list
    python -X utf8 tools/ui_textures.py render --out extract/f2/ui_es
    python -X utf8 tools/ui_textures.py render --only atlas_ui --preview
    python -X utf8 tools/ui_textures.py verify extract/f2/ui_es/atlas_ui_es.aif

The default output goes to `extract/` (git-ignored).
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
VENDOR = REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"
for p in (str(VENDOR), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import aif as aif_mod  # noqa: E402
import aif_edit  # noqa: E402

FONT_DIR = Path("C:/Windows/Fonts")
FONT_CANDIDATES = {
    # CAMP labels: serif with strong serifs (resembles Georgia/Times)
    "camp": ["georgiab.ttf", "timesbd.ttf", "BOOKOSB.TTF", "arialbd.ttf"],
    "camp_italic": ["georgiaz.ttf", "timesbi.ttf", "BOOKOSBI.TTF", "arialbi.ttf"],
    # "GAME OVER": heavy display serif
    "display": ["georgiab.ttf", "BOOKOSB.TTF", "timesbd.ttf", "cambriab.ttf"],
    # "Now Loading" / "Reload": thin-stroke serif
    "serif": ["georgia.ttf", "times.ttf", "BOOKOS.TTF", "constan.ttf"],
    "sans": ["arialbd.ttf", "segoeui.ttf", "calibrib.ttf"],
    # main-menu labels: light humanist sans (not bold)
    "title": ["segoeui.ttf", "calibri.ttf", "arial.ttf", "verdana.ttf"],
}


def _font_path(kind: str) -> Path:
    for name in FONT_CANDIDATES.get(kind, []):
        p = FONT_DIR / name
        if p.is_file():
            return p
    raise FileNotFoundError("no hay fuente para %r en %s" % (kind, FONT_DIR))


# --------------------------------------------------------------------------
# Styles
# --------------------------------------------------------------------------
# Each style describes how a label is painted.  Colors in RGBA.
STYLES = {
    # CAMP: white with dark outline and soft shadow (like the atlas)
    "camp": dict(
        font="camp", max_size=19,
        fill=(255, 255, 255, 255),
        outline=(255, 255, 255, 255), outline_w=1,
        shadow=None, glow=None,
    ),
    # Pause: white italic with dark outline
    "pause": dict(
        font="camp_italic", max_size=28,
        fill=(255, 255, 255, 255),
        outline=(30, 30, 30, 255), outline_w=2,
        shadow=(0, 0, 0, 150), shadow_off=(2, 2), shadow_blur=1.5,
        glow=None,
    ),
    # Now Loading: light serif with a slight bluish glow
    "nowload": dict(
        font="serif", max_size=20,
        fill=(247, 252, 255, 255),
        outline=(10, 30, 45, 200), outline_w=1,
        shadow=None, glow=(120, 200, 255, 120), glow_blur=1.5,
    ),
    # GAME OVER: dark fill with red glow (approximation of the original)
    "gameover": dict(
        font="display", max_size=0,
        fill=(24, 6, 4, 255),
        outline=(120, 0, 0, 255), outline_w=1,
        shadow=None, glow=(255, 40, 20, 235), glow_blur=7.0,
    ),
    # Reload: white serif with letter spacing (monospacing of the original)
    "reload": dict(
        font="serif", max_size=30,
        fill=(255, 255, 255, 255),
        outline=(0, 0, 0, 255), outline_w=2,
        shadow=None, glow=None, tracking=5,
    ),
    # --- combat / HUD labels from the UI atlas (000A4000_002) --------------
    # "Player Advantage!": yellow fill with orange outline/glow.
    "adv_player": dict(
        font="sans", max_size=26,
        fill=(255, 205, 40, 255),
        outline=(150, 40, 0, 255), outline_w=2,
        shadow=None, glow=(255, 130, 0, 200), glow_blur=4.0,
    ),
    # "Enemy Advantage!": red-orange fill.
    "adv_enemy": dict(
        font="sans", max_size=26,
        fill=(255, 90, 30, 255),
        outline=(150, 20, 0, 255), outline_w=2,
        shadow=None, glow=(255, 60, 0, 200), glow_blur=4.0,
    ),
    # "Level Up": red italic with glow.
    "levelup": dict(
        font="camp_italic", max_size=26,
        fill=(255, 80, 30, 255),
        outline=(120, 20, 0, 255), outline_w=2,
        shadow=None, glow=(255, 80, 0, 170), glow_blur=3.5,
    ),
    # "TARGET": golden serif.  NOTE: the engine does NOT sample a single label; it
    # draws the word **glyph by glyph** with six independent sprites from the
    # atlas (sprite table `000A4000_003_TTD.bin`, 22x26 ids at y=484.5).  That is
    # why here ONE letter is painted per glyph box (see `_reg()`), not a whole
    # word: painting "BLANCO" across the whole band made the engine clip each
    # sprite and show it in pieces.  The BOLD font is used
    # (camp=Georgia Bold) so the letters survive the rescaling.
    "target": dict(
        font="camp", max_size=28,
        fill=(220, 185, 95, 255),
        outline=(50, 35, 0, 255), outline_w=1,
        shadow=None, glow=None,
    ),
    # "GUARD": blue with white outline.
    "guard": dict(
        font="sans", max_size=24,
        fill=(90, 170, 255, 255),
        outline=(255, 255, 255, 255), outline_w=2,
        shadow=None, glow=(60, 140, 255, 180), glow_blur=3.0,
    ),
    # "CRITICAL": green with white outline.
    "critical": dict(
        font="sans", max_size=20,
        fill=(90, 220, 60, 255),
        outline=(255, 255, 255, 255), outline_w=2,
        shadow=None, glow=(60, 220, 60, 180), glow_blur=1.2,
    ),
    # "Situation Bonus!": light blue with glow.
    "situation": dict(
        font="sans", max_size=26,
        fill=(150, 225, 255, 255),
        outline=(255, 255, 255, 255), outline_w=1,
        shadow=None, glow=(80, 180, 255, 210), glow_blur=4.0,
    ),
    # "CONNECT": white with dark outline.
    "connect": dict(
        font="sans", max_size=22,
        fill=(255, 255, 255, 255),
        outline=(40, 40, 40, 255), outline_w=1,
        shadow=None, glow=None,
    ),
    # HUD stats row (HP MP ATK DEF INT HIT AGL).
    "stat": dict(
        font="sans", max_size=16,
        fill=(255, 185, 240, 255),
        outline=(60, 20, 50, 255), outline_w=1,
        shadow=None, glow=None,
    ),
    "stat2": dict(
        font="sans", max_size=16,
        fill=(120, 255, 200, 255),
        outline=(20, 60, 50, 255), outline_w=1,
        shadow=None, glow=None,
    ),
    # --- MAIN MENU labels (atlas embedded in the title ASF) ------------------
    # White text (the game applies the bluish tint) with a thin dark border.
    "title": dict(
        font="title", max_size=44,
        fill=(255, 255, 255, 255),
        outline=(18, 26, 38, 210), outline_w=1,
        shadow=None, glow=None,
    ),
}


# --------------------------------------------------------------------------
# AIF: writing while preserving format
# --------------------------------------------------------------------------
def rebuild_argb8888(original: bytes, rgba: bytes, base: int = 0) -> bytes:
    """Rebuilds an A8R8G8B8 (0x48) AIF from RGBA.  Byte-exact if unchanged."""
    img = aif_mod.AifImage(original, base)
    if img.format != aif_mod.FMT_ARGB8888:
        raise aif_mod.AifError("no es A8R8G8B8")
    hdr = original[:img.data_offset]
    tail = original[img.data_offset + img.base_level_size():]
    raw = bytearray(img.base_level_size())
    for y in range(img.elements_y):
        for x in range(img.elements_x):
            o = (y * img.width + x) * 4
            # disk: A,R,G,B ; PIL: R,G,B,A
            off = aif_mod.tiled_offset(x, y, img.tiled_width, 4) * 4
            raw[off:off + 4] = bytes((rgba[o + 3], rgba[o], rgba[o + 1], rgba[o + 2]))
    return bytes(hdr) + bytes(raw) + tail


def rebuild_dxt(original: bytes, rgba: bytes, boxes, base: int = 0) -> bytes:
    """Re-encodes ONLY the 4x4 blocks that touch the `boxes` (DXT1/3/5)."""
    ed = aif_edit.AifEditor(original, base)
    img = ed.image
    w, h = img.width, img.height
    touched = set()
    for (x0, y0, x1, y1) in boxes:
        bx0, bx1 = max(0, x0 // 4), min(ed.bx - 1, (x1 - 1) // 4)
        by0, by1 = max(0, y0 // 4), min(ed.by - 1, (y1 - 1) // 4)
        for by in range(by0, by1 + 1):
            for bx in range(bx0, bx1 + 1):
                touched.add((bx, by))
    for (bx, by) in touched:
        pixels = []
        for yy in range(4):
            for xx in range(4):
                x, y = bx * 4 + xx, by * 4 + yy
                if x >= w or y >= h:
                    pixels.append((0, 0, 0, 0))
                else:
                    o = (y * w + x) * 4
                    pixels.append((rgba[o], rgba[o + 1], rgba[o + 2], rgba[o + 3]))
        ed.write_block(bx, by, aif_edit.encode_block(ed.fmt, pixels))
    return ed.to_bytes()


def encode_aif(original: bytes, rgba: bytes, boxes, base: int = 0) -> bytes:
    img = aif_mod.AifImage(original, base)
    if img.format == aif_mod.FMT_ARGB8888:
        return rebuild_argb8888(original, rgba, base)
    if img.format in (aif_mod.FMT_DXT1, aif_mod.FMT_DXT3, aif_mod.FMT_DXT5):
        return rebuild_dxt(original, rgba, boxes, base)
    raise aif_mod.AifError("formato no soportado: %s" % img.format_name)


# --------------------------------------------------------------------------
# Text painting
# --------------------------------------------------------------------------
def _load_font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_font_path(kind)), size)


def _advance(font: ImageFont.FreeTypeFont, text: str) -> float:
    """Real ADVANCE width of `text` (includes bearings/kerning).  This is what
    must be used to place glyphs with `tracking`: using the ink width
    (`getbbox`) overlaps them."""
    if hasattr(font, "getlength"):
        return font.getlength(text)
    return font.getsize(text)[0]


def _measure(font: ImageFont.FreeTypeFont, text: str):
    """(advance width, ink height) of `text` with `font`."""
    if hasattr(font, "getbbox"):
        b = font.getbbox(text)
        h = b[3] - b[1]
    else:
        h = font.getsize(text)[1]
    return _advance(font, text), h


def fit_font(text: str, kind: str, maxw: int, maxh: int, tracking: int = 0,
             max_size: int = 0):
    """Largest font size with which `text` fits in (maxw, maxh).

    `max_size` sets the ceiling (to avoid enlarging short labels relative to the
    original): the new label is never taller than the English it replaces.
    """
    lo, hi = 4, max(8, maxh * 3 + 16)
    if max_size:
        hi = min(hi, max_size)
    best = _load_font(kind, lo)
    while lo <= hi:
        mid = (lo + hi) // 2
        f = _load_font(kind, mid)
        w, h = _measure(f, text)
        w += tracking * max(0, len(text) - 1)
        if w <= maxw and h <= maxh:
            best = f
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _draw_tracked(dr: ImageDraw.ImageDraw, x: float, y: float, text: str,
                  font: ImageFont.FreeTypeFont, fill, tracking: int,
                  stroke_w: int = 0, stroke_fill=None) -> None:
    """Draws `text` glyph by glyph advancing by the REAL WIDTH of each glyph
    (plus `tracking`).  That way the spacing is correct and they do not overlap."""
    cx = x
    for ch in text:
        dr.text((cx, y), ch, font=font, fill=fill,
                stroke_width=stroke_w, stroke_fill=stroke_fill)
        cx += _advance(font, ch) + tracking


def _render_layer(text: str, kind: str, style: dict, maxw: int, maxh: int,
                  ss: int = 4, fixed_size: int = 0) -> Image.Image:
    """Renders the label onto a transparent RGBA layer (supersampling)."""
    tracking = (style.get("tracking", 0) or 0) * ss
    # The margin (outline+glow) consumes box width: it must be RESERVED when
    # fitting the font, or the text would be clipped when composited into the box.
    pad = (style.get("outline_w", 0) + 2) * ss + int(style.get("glow_blur", 0) * ss) * 2
    if fixed_size:
        font = _load_font(kind, max(4, fixed_size * ss))
    else:
        font = fit_font(text, kind, max(1, maxw * ss - 2 * pad), max(1, maxh * ss - 2 * pad),
                        tracking, (style.get("max_size", 0) or 0) * ss)
    # measure to size the layer
    if hasattr(font, "getbbox"):
        b = font.getbbox(text)
    else:
        b = (0, 0) + font.getsize(text)
    if tracking and len(text) > 1:
        # with tracking we draw glyph by glyph: width is the sum of advances.
        adv = sum(_advance(font, ch) for ch in text)
        lw = int(adv) + tracking * (len(text) - 1) + pad * 2
    else:
        lw = b[2] - b[0] + pad * 2
    lh = b[3] - b[1] + pad * 2
    layer = Image.new("RGBA", (max(1, lw), max(1, lh)), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    x = pad - (0 if (tracking and len(text) > 1) else b[0])
    y = pad - b[1]

    def draw_text(fill, stroke_fill=None, stroke_w=0, dx=0, dy=0):
        if tracking and len(text) > 1:
            _draw_tracked(dr, x + dx, y + dy, text, font, fill, tracking,
                          stroke_w, stroke_fill)
        else:
            dr.text((x + dx, y + dy), text, font=font, fill=fill,
                    stroke_width=stroke_w, stroke_fill=stroke_fill)

    def draw_mask(mask_dr, dx=0, dy=0):
        if tracking and len(text) > 1:
            _draw_tracked(mask_dr, x + dx, y + dy, text, font, 255, tracking)
        else:
            mask_dr.text((x + dx, y + dy), text, font=font, fill=255)

    # halo (glow)
    glow = style.get("glow")
    if glow:
        mask = Image.new("L", layer.size, 0)
        draw_mask(ImageDraw.Draw(mask))
        mask = mask.filter(ImageFilter.GaussianBlur(style.get("glow_blur", 3.0) * ss * 0.6))
        g = Image.new("RGBA", layer.size, glow)
        g.putalpha(mask.point(lambda v: min(255, int(v * glow[3] / 255 * 2.2))))
        layer.alpha_composite(g)
    # shadow
    shadow = style.get("shadow")
    if shadow:
        m = Image.new("L", layer.size, 0)
        dx, dy = style.get("shadow_off", (2, 2))
        draw_mask(ImageDraw.Draw(m), dx * ss, dy * ss)
        m = m.filter(ImageFilter.GaussianBlur(style.get("shadow_blur", 1.5) * ss * 0.6))
        s = Image.new("RGBA", layer.size, shadow)
        s.putalpha(m.point(lambda v: int(v * shadow[3] / 255)))
        layer.alpha_composite(s)
    # outline + fill
    draw_text(style["fill"], style.get("outline"), (style.get("outline_w", 0) or 0) * ss)
    return layer


def _clear_to_key(base: Image.Image, box) -> None:
    """Erases the INK of the original label PRESERVING the background (color key).

    The UI atlas uses a *color key*: the background is pixels with `alpha == 0`
    but RGB different from 0 (e.g. orange `(255,128,58,0)` in `TARGET`, white
    `(255,255,255,0)` in the tabs, red `(255,38,0,0)` in `Level Up`).  If filled
    with `(0,0,0,0)` the engine paints a **black box** behind the text
    (and thin letters get lost against the black).  Here ONLY the
    pixels with `alpha > 0` (the old label's ink) are replaced with the dominant
    background color key, leaving the original background intact.
    """
    x0, y0, x1, y1 = box
    region = base.crop((x0, y0, x1, y1))
    px = region.load()
    from collections import Counter
    zeros: Counter = Counter()
    for y in range(region.height):
        for x in range(region.width):
            p = px[x, y]
            if p[3] == 0:
                zeros[p] += 1
    key = zeros.most_common(1)[0][0] if zeros else (0, 0, 0, 0)
    for y in range(region.height):
        for x in range(region.width):
            if px[x, y][3] != 0:
                px[x, y] = key
    base.paste(region, (x0, y0))


def paint_label(base: Image.Image, box, text: str, style_name: str, ss: int = 4,
                fixed_size: int = 0, center: bool = False, clear_box=None):
    """Erases `clear_box` (or `box`) and paints `text` inside `box`, centered on Y.

    `box` = (x0, y0, x1, y1): the available gap (already bounded to the neighbor)
    and the area where the text is clipped.  `clear_box` allows ERASING a wider
    area than the painted one (e.g. removing a neighboring word the engine does
    not sample but that we do not want to leave in English).
    """
    x0, y0, x1, y1 = box
    style = STYLES[style_name]
    maxw, maxh = x1 - x0, y1 - y0
    # erase the original (preserving the background color key)
    _clear_to_key(base, tuple(clear_box) if clear_box else box)

    def composite(layer, top):
        """Composites `layer`, clipping it to the box (never invades the neighbor)."""
        ly0, lx0 = top
        lx1, ly1 = lx0 + layer.width, ly0 + layer.height
        cx0, cy0 = max(lx0, x0), max(ly0, y0)
        cx1, cy1 = min(lx1, x1), min(ly1, y1)
        if cx0 >= cx1 or cy0 >= cy1:
            return
        part = layer.crop((cx0 - lx0, cy0 - ly0, cx1 - lx0, cy1 - ly0))
        base.alpha_composite(part, (cx0, cy0))

    if "\n" in text:
        # multiline: each line is fit to the same width
        lines = text.split("\n")
        lh = maxh // len(lines)
        for i, ln in enumerate(lines):
            if not ln:
                continue
            layer = _render_layer(ln, style["font"], style, maxw, lh, ss, fixed_size)
            layer = layer.resize((max(1, layer.width // ss), max(1, layer.height // ss)),
                                 Image.LANCZOS)
            cy = y0 + i * lh + (lh - layer.height) // 2
            cx = x0 + (maxw - layer.width) // 2 if center else x0
            composite(layer, (max(y0, cy), max(x0, cx)))
    else:
        layer = _render_layer(text, style["font"], style, maxw, maxh, ss, fixed_size)
        layer = layer.resize((max(1, layer.width // ss), max(1, layer.height // ss)),
                             Image.LANCZOS)
        cy = y0 + (maxh - layer.height) // 2
        cx = x0 + (maxw - layer.width) // 2 if center else x0
        composite(layer, (max(y0, cy), max(x0, cx)))


# --------------------------------------------------------------------------
# Texture and label registry
# --------------------------------------------------------------------------
# `box` = available sampling gap (x0,y0,x1,y1).  It is taken from the ink +
# outline crop and bounded to the start of the neighboring label (to avoid overlap).
def _reg():
    A = "extract/f2/all_d1ud1"
    return {
        # ------------------------------------------------------------------
        # Live UI atlas (PG02): CAMP tabs + Pause + Now Loading.
        # It is A8R8G8B8 (lossless editing).  `26D8C000_000` is the same atlas.
        # ------------------------------------------------------------------
        "atlas_ui": {
            "source": f"{A}/000A4000_002_IMG.aif",
            "aliases": [f"{A}/26D8C000_000_IMG.aif"],
            "out": "atlas_ui_es.aif",
            "labels": [
                # row 1 (main tabs)
                {"en": "Items", "es": "Objetos", "box": [1, 510, 92, 548]},
                {"en": "Skills", "es": "Habs.", "box": [96, 510, 188, 548]},
                {"en": "Equipment", "es": "Equipo", "box": [192, 510, 364, 548]},
                {"en": "Creation", "es": "Creaci\u00f3n", "box": [368, 510, 492, 548]},
                {"en": "Status", "es": "Estado", "box": [496, 510, 588, 548]},
                {"en": "Map", "es": "Mapa", "box": [592, 510, 668, 548]},
                {"en": "Party", "es": "Grupo", "box": [672, 510, 758, 548]},
                {"en": "Options", "es": "Opciones", "box": [762, 510, 876, 548]},
                {"en": "Data", "es": "Datos", "box": [880, 510, 959, 548]},
                # "Talk" -> "Hablar": the Spanish word is wider than the 60 px
                # gap at the tab font size (19 -> 68 px), so this label uses an
                # explicit smaller size (16 -> 58 px) that fits the box without
                # clipping and without dragging down the rest of the tabs.
                {"en": "Talk", "es": "Hablar", "box": [963, 512, 1023, 548], "size": 16},
                # row 2
                {"en": "Battle", "es": "Comb.", "box": [0, 558, 92, 596]},
                {"en": "Connect", "es": "Conexi\u00f3n", "box": [96, 558, 220, 596]},
                {"en": "Flute", "es": "Flauta", "box": [224, 558, 300, 596]},
                {"en": "Magic", "es": "Magia", "box": [304, 558, 396, 596]},
                {"en": "Personal", "es": "Personal", "box": [400, 558, 560, 596]},
                # row 3
                {"en": "Enchant", "es": "Encantar", "box": [0, 607, 124, 645]},
                {"en": "Save", "es": "Guard.", "box": [128, 607, 210, 645]},
                {"en": "Load", "es": "Cargar", "box": [206, 607, 279, 645]},
                {"en": "System", "es": "Sistema", "box": [289, 607, 396, 645]},
                {"en": "Tutorial", "es": "Tutorial", "box": [400, 607, 560, 645]},
                # bottom bar
                {"en": "Pause", "es": "Pausa", "box": [538, 993, 703, 1023], "style": "pause", "center": True},
                {"en": "Now Loading...", "es": "Cargando...", "box": [763, 988, 1008, 1024], "style": "nowload", "center": True},
                # --- combat / HUD labels (same atlas) --------------------------
                {"en": "Player Advantage!", "es": "Ventaja aliada", "box": [250, 288, 512, 348], "style": "adv_player"},
                {"en": "Enemy Advantage!", "es": "Ventaja enemiga", "box": [640, 288, 900, 348], "style": "adv_enemy"},
                {"en": "Level Up", "es": "Subir nivel", "box": [248, 448, 430, 482], "style": "levelup"},
                # --- TARGET: drawn GLYPH BY GLYPH (6 sprites from the atlas) ----
                # The engine composites the word from six independent 22-24x26 px
                # boxes (table `000A4000_003_TTD.bin`, y=484.5).  One letter has to
                # be painted per box; painting the whole word makes each sprite
                # get clipped and the label come out in pieces.
                # "BLANCO" (6 letters) replaces "TARGET" (6 letters).
                {"en": "T", "es": "B", "box": [293, 484, 315, 510], "style": "target", "center": True},
                {"en": "A", "es": "L", "box": [325, 484, 348, 510], "style": "target", "center": True},
                {"en": "R", "es": "A", "box": [356, 484, 380, 510], "style": "target", "center": True},
                {"en": "G", "es": "N", "box": [388, 484, 412, 510], "style": "target", "center": True},
                {"en": "E", "es": "C", "box": [420, 484, 444, 510], "style": "target", "center": True},
                {"en": "T", "es": "O", "box": [453, 484, 475, 510], "style": "target", "center": True},
                {"en": "GUARD", "es": "GUARDIA", "box": [733, 447, 857, 480], "style": "guard"},
                {"en": "CRITICAL", "es": "CRÍTICO", "box": [733, 481, 890, 509], "style": "critical"},
                {"en": "Situation Bonus!", "es": "Bonif. situación", "box": [572, 560, 834, 622], "style": "situation"},
                {"en": "CONNECT", "es": "CONEXIÓN", "box": [574, 79, 677, 100], "style": "connect"},
                # stats row (two copies: pink and green)
                {"en": "HP MP ATKDEFINT HITAGL", "es": "PS PV ATQDEFINTPREAGI", "box": [255, 986, 500, 1005], "style": "stat"},
                {"en": "HP MP ATKDEFINT HITAGL", "es": "PS PV ATQDEFINTPREAGI", "box": [255, 1005, 500, 1024], "style": "stat2"},
            ],
        },
        # ------------------------------------------------------------------
        # "GAME OVER" (640x480, A8R8G8B8).  Two lines + red bar.
        # ------------------------------------------------------------------
        "gameover": {
            "source": f"{A}/274AE800_000_IMG.aif",
            "out": "gameover_es.aif",
            "labels": [
                {"en": "GAME\nOVER", "es": "FIN DEL\nJUEGO", "box": [10, 6, 630, 315], "style": "gameover"},
            ],
        },
        # ------------------------------------------------------------------
        # "Now Loading..." (256x32, A8R8G8B8).  The spinner stays on the left.
        # ------------------------------------------------------------------
        "nowloading": {
            "source": f"{A}/28EB4000_000_IMG.aif",
            "out": "nowloading_es.aif",
            "labels": [
                {"en": "Now Loading...", "es": "Cargando...", "box": [34, 1, 254, 31], "style": "nowload"},
            ],
        },
        # NOTE: `00016000_000_IMG.aif` is BYTE-IDENTICAL to `28EB4000_000_IMG.aif`
        # (same texture); a single entry is enough (avoids a duplicate signature).
        # ------------------------------------------------------------------
        # "Reload." (256x256, A8R8G8B8).  Circular icon + text.
        # ------------------------------------------------------------------
        "reload": {
            "source": f"{A}/26F88000_000_IMG.aif",
            "out": "reload_es.aif",
            "labels": [
                {"en": "Reload.", "es": "Recargar.", "box": [2, 158, 230, 192], "style": "reload"},
            ],
        },
        # ------------------------------------------------------------------
        # MAIN MENU: the labels are A8R8G8B8 AIFs EMBEDDED in the ASF
        # `0001F800_000_MESH.asf` (that is why they did not appear as loose
        # `.aif` files).  They were located with `tools/scan_embedded_aif.py`
        # (OCR by content).  The hook substitutes them by signature, like the rest.
        # ------------------------------------------------------------------
        # Atlas A (895x201): Easy/Normal/Hard/VeryHard/Options/New Game/
        # Load Game/Xbox LIVE Marketplace/PRESS START button.
        "title_menu": {
            "source": f"{A}/0001F800_000_MESH.asf",
            "offset": 0x2F51F0,
            "out": "title_menu_es.aif",
            "labels": [
                # Boxes = REAL ink bbox of the original (measured with connected
                # components over the AIF).  The engine draws each label CENTERED
                # on screen, so the ES one is centered in the same box -> same
                # position/alignment as the English.
                {"en": "Easy", "es": "F\u00e1cil", "box": [119, 6, 206, 44], "style": "title", "center": True},
                {"en": "Normal", "es": "Normal", "box": [97, 46, 227, 79], "style": "title", "center": True},
                {"en": "Hard", "es": "Dif\u00edcil", "box": [117, 85, 206, 119], "style": "title", "center": True},
                {"en": "VeryHard", "es": "Muy dif\u00edcil", "box": [71, 125, 251, 164], "style": "title", "center": True},
                {"en": "Options", "es": "Opciones", "box": [296, 5, 447, 43], "style": "title", "center": True},
                {"en": "New Game", "es": "Nueva partida", "box": [546, 5, 743, 38], "style": "title", "center": True},
                {"en": "Load Game", "es": "Cargar partida", "box": [539, 44, 749, 78], "style": "title", "center": True},
                {"en": "Xbox LIVE Marketplace", "es": "Xbox LIVE Marketplace", "box": [288, 84, 737, 123], "style": "title", "center": True},
                # NOTE: the engine samples ONLY the "PRESS START" part (the label
                # is called `PressStart`), not the whole "PRESS START button"
                # band; centering on the whole band shifted "Pulsa START"
                # ~100 px to the right on screen.  The paint box is
                # centered slightly to the right of the original ink (450 vs 432)
                # for the requested fine tuning; `clear_box` also erases the
                # English word "button", which the engine does not sample.
                {"en": "PRESS START button", "es": "Pulsa START", "box": [290, 124, 574, 159], "style": "title", "center": True,
                 "clear_box": [290, 124, 714, 159]},
            ],
        },
        # Atlas B (415x54): Infinity / Continue.
        "title_continue": {
            "source": f"{A}/0001F800_000_MESH.asf",
            "offset": 0x3D21F0,
            "out": "title_continue_es.aif",
            "labels": [
                {"en": "Infinity", "es": "Infinity", "box": [21, 7, 159, 46], "style": "title", "center": True},
                {"en": "Continue", "es": "Continuar", "box": [218, 8, 396, 41], "style": "title", "center": True},
            ],
        },
    }


# --------------------------------------------------------------------------
# Source loading (loose AIF file or AIF embedded in a container)
# --------------------------------------------------------------------------
def _load_source(spec):
    """Returns `(AIF_bytes, base)` for a registry entry.

    * `source` = path to a loose `.aif` -> base 0.
    * `source` + `offset` = embedded AIF (e.g. inside an `.asf`): the payload
      `[offset, offset+total_size)` is cropped and `base=offset` is passed
      so that `AifImage` computes the real `data_offset` (the pixels start at
      the next 0x1000 boundary of the container file).
    """
    src = REPO / spec["source"]
    raw = src.read_bytes()
    if "offset" in spec:
        off = int(spec["offset"])
        total = struct.unpack_from(">I", raw, off + 4)[0]
        return raw[off:off + total], off
    return raw, 0


def _all_labels():
    reg = _reg()
    for key, spec in reg.items():
        for lb in spec["labels"]:
            lb.setdefault("style", "camp")
            yield key, spec, lb


# --------------------------------------------------------------------------
# Assets integrated by the same mechanism but NOT painted here
# --------------------------------------------------------------------------
# Each entry: (on-disk_source, replacement_file).  The substitution SIGNATURE
# is the ORIGIN's header (0x30 bytes), which is what is in guest memory.
def _extra_assets():
    return [
        # Accents of bank 005 (WS1: `count` unchanged -> stable fingerprint).
        # The atlas and its `.msg` are loaded together in the font's RMD-.
        ("extract/f0/d1_ud1_000A4000_005.aif",
         "extract/f2/accents/d1_ud1_000A4000_005_accents.aif"),
        # NOTE: the "original" `.msg` of `extract/f0/d1_..._005.msg` was
        # overwritten by `add_accents_banks.py --sync-f0` (accent metrics).
        # The UNPATCHED copy (identical except the 32 B of metrics 557..572)
        # lives in `extract/f0/d2_..._005.msg`; that is the one matching the
        # game's memory, so it is used as the substitution signature/hash.
        ("extract/f0/d2_ud1_000A4000_005.msg",
         "extract/f2/accents/d1_ud1_000A4000_005_accents.msg"),
    ]


# Textures with a per-controller VARIANT (generated by `tools/controller_skins.py`).
# Map: on_disk_source -> [(controller, replacement_file), ...].  Steam shares
# the Xbox buttons (A/B/X/Y), so its atlas is the same `atlas_ui_es.aif`.
# NOTE: the visual controller *map* image (`26EF5000`) is intentionally NOT
# variant-swapped: the per-controller redraw looked poor, so the original map is
# kept for every controller (only the on-screen button icons change).
def _controller_variants():
    A = "extract/f2/all_d1ud1"
    return {
        f"{A}/000A4000_002_IMG.aif": [
            ("xbox", "extract/f2/ui_es/atlas_ui_es.aif"),
            ("steam", "extract/f2/ui_es/atlas_ui_es.aif"),
            ("ps5", "extract/f2/ui_es/atlas_ui_ps5_es.aif"),
        ],
    }


def _help_assets():
    """CAMP help screens (1280x720) translated by
    `tools/ui_help_screens.py`.  Imported lazily to avoid the
    circular dependency (that module imports this one)."""
    try:
        import ui_help_screens as H
    except Exception:
        return []
    out = []
    for _key, spec in H._reg().items():
        out.append((spec["source"], "extract/f2/ui_es/" + spec["out"]))
    return out


# Substitution signature: AIF/.msg header (includes length, id and resource
# number -> unique per texture).  The hook looks for it as-is in guest memory.
SIG_LEN = 0x30


def _sig(data: bytes, n: int = SIG_LEN) -> bytes:
    return data[:n]


def _fnv64(data: bytes) -> int:
    """64-bit FNV-1a: disambiguates textures with the same header (e.g. the
    EN and JP 'Now Loading')."""
    h = 1469598103934665603
    for b in data:
        h ^= b
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def cmd_manifest(args):
    """Deploys the ES textures to the runtime layout and writes the manifest.

    The hook (`mod/recomp/ui_textures_es.h`) reads `translation/ui_textures.txt`
    (relative to the game cwd) and substitutes each texture by its SIGNATURE.
    """
    outdir = Path(args.out)
    deploy = Path(args.deploy)
    deploy.mkdir(parents=True, exist_ok=True)
    lines = []
    seen = {}
    variants = _controller_variants()

    def add(original, out_path, src_label, ctrl="*"):
        if not out_path.is_file():
            print("! falta salida %s (ejecuta render/controller_skins)" % out_path)
            return
        data = out_path.read_bytes()
        if len(data) != len(original):
            print("! %s: tamaño %d != origen %d" % (out_path.name, len(data), len(original)))
            return
        if data == original:
            print("  = %-32s sin cambios (no se registra)" % out_path.name)
            return
        dst = deploy / out_path.name
        dst.write_bytes(data)
        sig = _sig(original)
        h = _fnv64(original)
        key = (sig, h, ctrl)
        if key in seen and seen[key] != out_path.name:
            print("! COLISIÓN de firma entre %s y %s" % (seen[key], out_path.name))
        seen[key] = out_path.name
        lines.append((sig, len(data), h, ctrl, "translation/" + out_path.name))
        print("  + %-32s [%-5s] <- %s" % (out_path.name, ctrl, src_label))

    handled = set()
    for key, spec in _reg().items():
        original, _base = _load_source(spec)
        if spec["source"] in variants:
            handled.add(spec["source"])
            for ctrl, out_rel in variants[spec["source"]]:
                add(original, REPO / out_rel, "%s [%s]" % (spec["source"], ctrl), ctrl)
        else:
            add(original, outdir / spec["out"], spec["source"])
    for src_rel, out_rel in _extra_assets() + _help_assets():
        add((REPO / src_rel).read_bytes(), REPO / out_rel, src_rel)
    for src_rel, outs in variants.items():
        if src_rel in handled:
            continue
        original = (REPO / src_rel).read_bytes()
        for ctrl, out_rel in outs:
            add(original, REPO / out_rel, "%s [%s]" % (src_rel, ctrl), ctrl)

    manifest = deploy / "ui_textures.txt"
    with open(manifest, "w", encoding="utf-8") as f:
        f.write("IUT2\n")
        f.write("%d\n" % len(lines))
        for sig, ln, h, ctrl, path in lines:
            f.write("%s %d %016x %s %s\n" % (sig.hex(), ln, h, ctrl, path))
    print("manifiesto -> %s (%d texturas, formato IUT2)" % (manifest, len(lines)))
    return 0


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
def cmd_list(args):
    for key, spec in _reg().items():
        print("%-14s %s" % (key, spec["source"]))
        for lb in spec["labels"]:
            print("    %-18r -> %-18r  %s" % (lb["en"], lb["es"], lb["box"]))
    return 0


def _harmonize_sizes(specs):
    """Font size harmonized PER STYLE, shared across ALL specs.

    Previously it was harmonized within each spec: `title_menu` gave 30 and
    `title_continue` gave 39 -> "Continuar" came out larger than the rest of the
    menu.  By harmonizing globally, all main-menu options share the same size.

    Rule: the largest size that fits in ALL the boxes of the group (so the most
    restrictive label rules and nothing overflows).
    """
    fixed = {}
    for spec in specs:
        groups = {}
        for lb in spec["labels"]:
            groups.setdefault(lb.get("style", "camp"), []).append(lb)
        for sname, lbs in groups.items():
            st = STYLES[sname]
            pad1 = (st.get("outline_w", 0) + 2) + int(st.get("glow_blur", 0))
            for lb in lbs:
                if lb.get("size"):
                    # Explicit per-label size (e.g. a long word that does not fit
                    # at the group size): it must NOT drag down the whole group.
                    continue
                x0, y0, x1, y1 = lb["box"]
                f = fit_font(lb["es"], st["font"], max(1, (x1 - x0) - 2 * pad1), (y1 - y0),
                             (st.get("tracking", 0) or 0), (st.get("max_size", 0) or 0))
                if hasattr(f, "size"):
                    fixed[sname] = min(fixed.get(sname, 999), f.size)
    return fixed


def _process(key, spec, outdir: Path, preview: bool, ss: int, fixed=None):
    original, base_off = _load_source(spec)
    img = aif_mod.AifImage(original, base_off)
    base = Image.frombytes("RGBA", (img.width, img.height), img.to_rgba())
    boxes = []
    # Size per style: if `fixed` comes from the global render (harmonized across
    # specs, e.g. main menu), it is used; otherwise it is harmonized within this
    # spec.  A label that does not fit drags down the size of the whole group.
    if fixed is None:
        fixed = _harmonize_sizes([spec])
    for lb in spec["labels"]:
        sn = lb.get("style", "camp")
        # Explicit per-label size wins over the group-harmonized one.
        size = lb.get("size") or fixed.get(sn, 0)
        paint_label(base, lb["box"], lb["es"], sn, ss, fixed_size=size,
                    center=lb.get("center", False), clear_box=lb.get("clear_box"))
        boxes.append(tuple(lb["box"]))
        if lb.get("clear_box"):
            boxes.append(tuple(lb["clear_box"]))
    rgba = base.tobytes()
    out = encode_aif(original, rgba, boxes, base_off)
    dst = outdir / spec["out"]
    dst.write_bytes(out)

    # verification: byte-exact if untouched, and valid recomposition
    verify = _verify_bytes(original, out, img)
    # wrapper round-trip (tiling + byte order) over the new file
    wrap = _wrapper_ok(out, base_off)
    info = ("%s: %dx%d %s  -> %s  (%s, %s)"
            % (key, img.width, img.height, img.format_name, spec["out"],
               "sin pérdida" if not img.compressed else "DXT",
               "envoltorio OK" if wrap else "envoltorio MAL"))
    print(info)
    if preview:
        pv = outdir / (dst.stem + "_preview.png")
        bg = Image.new("RGBA", base.size, (60, 60, 60, 255))
        bg.alpha_composite(base)
        bg.convert("RGB").save(pv)
        print("    preview:", pv)
    return dst


def _wrapper_ok(data: bytes, base: int = 0) -> bool:
    try:
        img = aif_mod.AifImage(data, base)
        if img.compressed:
            ed = aif_edit.AifEditor(data, base)
            return ed.to_bytes() == data and ed.verify_wrapper()
        # A8R8G8B8: rebuilding from RGBA must reproduce the file
        return rebuild_argb8888(data, img.to_rgba(), base) == data
    except Exception:
        return False


def _verify_bytes(original: bytes, new: bytes, img) -> bool:
    if not img.compressed:
        # check that only pixels change (not header/tail)
        return (len(new) == len(original)
                and new[:img.data_offset] == original[:img.data_offset]
                and new[img.data_offset + img.base_level_size():]
                == original[img.data_offset + img.base_level_size():])
    return True


def cmd_render(args):
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    keys = args.only or list(_reg().keys())
    reg = _reg()
    # Style-harmonized size, shared across ALL specs in the
    # registry (so the main menu uses a single size even if only one of its
    # two textures is rendered).
    fixed = _harmonize_sizes(list(reg.values()))
    for key in keys:
        if key not in reg:
            print("! clave desconocida:", key, file=sys.stderr)
            continue
        _process(key, reg[key], outdir, args.preview, args.ss, fixed=fixed)
    return 0


def cmd_verify(args):
    data = Path(args.file).read_bytes()
    base = getattr(args, "base", 0)
    print("envoltorio exacto:", _wrapper_ok(data, base))
    img = aif_mod.AifImage(data, base)
    print("formato:", img.format_name, "%dx%d" % (img.width, img.height))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Traduce rótulos AIF (bitmaps) al ES.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list"); s.set_defaults(func=cmd_list)

    s = sub.add_parser("render")
    s.add_argument("--out", default="extract/f2/ui_es")
    s.add_argument("--only", action="append", default=[])
    s.add_argument("--preview", action="store_true")
    s.add_argument("--ss", type=int, default=4, help="supersampling")
    s.set_defaults(func=cmd_render)

    s = sub.add_parser("verify")
    s.add_argument("file")
    s.add_argument("--base", type=lambda x: int(x, 0), default=0,
                   help="offset del AIF dentro de su contenedor (0 si es suelto)")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("manifest",
                       help="despliega texturas + escribe translation/ui_textures.txt")
    s.add_argument("--out", default="extract/f2/ui_es")
    s.add_argument("--deploy", default="extract/f2/run/translation")
    s.set_defaults(func=cmd_manifest)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
