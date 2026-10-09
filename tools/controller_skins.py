#!/usr/bin/env python3
"""
controller_skins.py -- per-controller variants (Xbox / PS5 / Steam) of the UI
textures that depend on the controller.

Two texture families:

1. **Mapping image** `26EF5000_000_IMG.aif` (960x540, DXT5): drawing of the
   controller with blue callout lines (no text: the labels are dynamic text).
   Xbox = original (untouched).  DualSense (PS5) and Steam Controller variants
   are drawn **keeping the original blue lines** and placing the controls at the
   same positions (the dynamic labels stay aligned).

2. **Button icons** of the UI atlas `000A4000_002_IMG.aif` (1024^2,
   A8R8G8B8).  They are discs with a letter (A/B/X/Y, LB/RB/LT/RT) in two zones:
   - top row: y~639, x = 596,628,660,692,724,756,788,820,852,884,916,948
   - left stack: x = 25,71,117,163,209,255 ; y = 742,792 (Rb/Lb), 837,887
     (A/B/X/Y/Rt/Lt).
   For PS5 the disc is recolored and the letter replaced by the shape
   (cross/circle/square/triangle) and the shoulder label (LB->L1, etc.).
   Steam uses the same buttons as Xbox (A/B/X/Y, LB/RB/LT/RT) -> unchanged.

The result is re-encoded preserving format/size (A8R8G8B8 lossless;
DXT5 by re-encoding blocks).  The runtime hook substitutes by SIGNATURE according
to the detected controller (see `mod/recomp/controller_es.h`).

Usage:
    python -X utf8 tools/controller_skins.py map    --only ps5 --preview
    python -X utf8 tools/controller_skins.py atlas  --preview
    python -X utf8 tools/controller_skins.py selftest
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
VENDOR = REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"
for p in (str(VENDOR), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import aif as aif_mod  # noqa: E402
import aif_edit  # noqa: E402

FONT_DIR = Path("C:/Windows/Fonts")
FONT_CANDIDATES = ["georgiab.ttf", "arialbd.ttf", "timesbd.ttf", "segoeuib.ttf"]

A = "extract/f2/all_d1ud1"
MAP_SRC = f"{A}/26EF5000_000_IMG.aif"
ATLAS_SRC = f"{A}/000A4000_002_IMG.aif"
OUTDIR = "extract/f2/ui_es"

# ---------------------------------------------------------------------------
# "Hand-drawn" style palette (same tone as the original controller)
# ---------------------------------------------------------------------------
BODY = (233, 219, 181, 255)
BODY_DARK = (196, 182, 146, 255)
BODY_SHADOW = (150, 138, 110, 255)
OUTLINE = (24, 22, 18, 255)
RECESS = (168, 156, 126, 255)
STICK_TOP = (86, 80, 56, 255)
STICK_RIM = (60, 56, 40, 255)
BLUE = (40, 90, 200, 255)          # callout lines (kept separately)
TRIGGER = (205, 192, 156, 255)


def _font(size: int):
    for name in FONT_CANDIDATES:
        p = FONT_DIR / name
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Controller map
# ---------------------------------------------------------------------------
# Control positions = those of the original blue dots (the lines are
# kept), so the dynamic labels stay aligned.
DOTS = {
    "lt": (340, 126), "rt": (630, 127),
    "lb": (326, 164), "rb": (645, 164),
    "lstick": (311, 301), "rstick": (566, 381),
    "dpad": (398, 360),
    "y": (667, 228), "x": (601, 277), "b": (708, 271), "a": (662, 307),
    "back": (423, 253), "start": (548, 253),
}


def _blue_mask(img: Image.Image) -> Image.Image:
    """Layer with only the blue pixels (callout lines + dots)."""
    px = img.load()
    w, h = img.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            # Lines = SEMITRANSPARENT blue (low alpha); dots = LIGHT blue
            # opaque.  This EXCLUDES the blue disc/letter of the X button (mid opaque).
            line = a < 60 and b > r + 30 and b > g + 30
            dot = a >= 200 and r > 150 and b > r + 40 and b > g + 40
            if line or dot:
                op[x, y] = (r, g, b, a)
    return out


def _ss_draw(size, ss):
    """Returns (4x image, draw) to draw with supersampling."""
    w, h = size
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _ellipse(d, box, fill, outline=None, width=0):
    d.ellipse(box, fill=fill, outline=outline, width=width)


def _smooth(points, iterations=3):
    """Chaikin: rounds a closed polyline (for the controller silhouette)."""
    pts = list(points)
    for _ in range(iterations):
        out = []
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            out.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            out.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        pts = out
    return pts


def _draw_body_xbox(d, ss):
    # Not used: Xbox keeps the original.
    pass


def _draw_body_ps5(d, ss):
    """Stylized DualSense. Coordinates in px (scaled by ss)."""
    s = lambda v: v * ss
    dot = lambda name: (s(DOTS[name][0]), s(DOTS[name][1]))
    # Silhouette: top bar + two rounded grips (smoothed).
    body = [
        (470, 100), (560, 102), (640, 112), (700, 138), (745, 190),
        (775, 265), (795, 355), (780, 445), (720, 488), (650, 490),
        (600, 455), (560, 415), (520, 398), (480, 398), (440, 398),
        (400, 415), (360, 455), (310, 490), (240, 488), (180, 445),
        (165, 355), (185, 265), (215, 190), (260, 138), (320, 112),
        (400, 102),
    ]
    pts = [(s(x), s(y)) for x, y in _smooth(body, 3)]
    d.polygon(pts, fill=BODY, outline=OUTLINE, width=int(s(4)))
    # Subtle bottom shading on the grips
    for side in (-1, 1):
        cxx = 470 + side * 210
        d.polygon([(s(cxx - 60), s(455)), (s(cxx + 60), s(455)),
                   (s(cxx + 30), s(485)), (s(cxx - 30), s(485))],
                  fill=BODY_DARK)
    # Central touchpad (rounded rectangle)
    d.rounded_rectangle([s(430), s(180), s(560), s(250)], radius=s(18),
                        fill=(222, 216, 200, 255), outline=OUTLINE, width=int(s(3)))
    # Left stick (top-left) and right (bottom-right) -> dot positions
    _draw_stick(d, *dot("lstick"), s(46), ss)
    _draw_stick(d, *dot("rstick"), s(44), ss)
    # D-pad at the dot position
    _draw_dpad(d, *dot("dpad"), s(40), ss)
    # Buttons: triangle, square, circle, cross at the dot positions
    _draw_face(d, *dot("y"), s(30), "tri", ss)
    _draw_face(d, *dot("x"), s(30), "sq", ss)
    _draw_face(d, *dot("b"), s(30), "cir", ss)
    _draw_face(d, *dot("a"), s(30), "cross", ss)
    # PS button (round, under the touchpad)
    d.ellipse([s(470), s(300), s(520), s(350)], fill=(210, 205, 190, 255),
              outline=OUTLINE, width=int(s(3)))
    d.text((s(480), s(312)), "PS", font=_font(int(s(20))), fill=(60, 60, 60, 255))
    # Share / Options
    for cx in (DOTS["back"][0], DOTS["start"][0]):
        d.ellipse([s(cx - 12), s(240), s(cx + 12), s(264)],
                  fill=(200, 195, 180, 255), outline=OUTLINE, width=int(s(2)))
    # L2/R2 triggers (top) and L1/R1 bumpers
    for cx, cy in (DOTS["lt"], DOTS["rt"]):
        d.rounded_rectangle([s(cx - 34), s(cy - 18), s(cx + 34), s(cy + 16)],
                            radius=s(14), fill=TRIGGER, outline=OUTLINE,
                            width=int(s(3)))
    for cx, cy in (DOTS["lb"], DOTS["rb"]):
        d.rounded_rectangle([s(cx - 36), s(cy - 16), s(cx + 36), s(cy + 14)],
                            radius=s(12), fill=(216, 206, 178, 255),
                            outline=OUTLINE, width=int(s(3)))


def _draw_body_steam(d, ss):
    """Stylized Steam Controller (2015): two large trackpads."""
    s = lambda v: v * ss
    dot = lambda name: (s(DOTS[name][0]), s(DOTS[name][1]))
    body = [
        (470, 100), (560, 102), (640, 112), (700, 138), (748, 195),
        (778, 275), (795, 365), (778, 455), (715, 492), (640, 492),
        (580, 460), (530, 425), (480, 412), (430, 425), (380, 460),
        (320, 492), (245, 492), (182, 455), (165, 365), (182, 275),
        (212, 195), (260, 138), (320, 112), (400, 102),
    ]
    pts = [(s(x), s(y)) for x, y in _smooth(body, 3)]
    d.polygon(pts, fill=BODY, outline=OUTLINE, width=int(s(4)))
    d.polygon([(s(200), s(455)), (s(300), s(475)), (s(370), s(455)),
               (s(340), s(485)), (s(240), s(488))], fill=BODY_DARK)
    # Left trackpad (where the left stick dot is) and right
    _draw_trackpad(d, *dot("lstick"), s(52), ss)
    _draw_trackpad(d, *dot("rstick"), s(52), ss)
    # Left stick top-left? Steam has the left stick at the top; we put it at the dpad dot
    _draw_stick(d, *dot("dpad"), s(34), ss)
    # ABXY
    _draw_face_letter(d, *dot("y"), s(28), "Y", (230, 200, 40), ss)
    _draw_face_letter(d, *dot("x"), s(28), "X", (70, 120, 220), ss)
    _draw_face_letter(d, *dot("b"), s(28), "B", (200, 60, 50), ss)
    _draw_face_letter(d, *dot("a"), s(28), "A", (70, 180, 60), ss)
    # Triggers/bumpers
    for cx, cy in (DOTS["lt"], DOTS["rt"]):
        d.rounded_rectangle([s(cx - 34), s(cy - 18), s(cx + 34), s(cy + 16)],
                            radius=s(14), fill=TRIGGER, outline=OUTLINE,
                            width=int(s(3)))
    for cx, cy in (DOTS["lb"], DOTS["rb"]):
        d.rounded_rectangle([s(cx - 36), s(cy - 16), s(cx + 36), s(cy + 14)],
                            radius=s(12), fill=(216, 206, 178, 255),
                            outline=OUTLINE, width=int(s(3)))


def _draw_stick(d, cx, cy, r, ss):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=RECESS,
              outline=OUTLINE, width=max(1, int(r * 0.08)))
    r2 = r * 0.78
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=STICK_TOP,
              outline=STICK_RIM, width=max(1, int(r * 0.06)))
    r3 = r * 0.5
    d.ellipse([cx - r3, cy - r3, cx + r3, cy + r3], outline=STICK_RIM,
              width=max(1, int(r * 0.05)))
    r4 = r * 0.22
    d.ellipse([cx - r4, cy - r4, cx + r4, cy + r4], fill=STICK_RIM)


def _draw_trackpad(d, cx, cy, r, ss):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(200, 196, 182, 255),
              outline=OUTLINE, width=max(1, int(r * 0.07)))
    d.ellipse([cx - r * 0.82, cy - r * 0.82, cx + r * 0.82, cy + r * 0.82],
              fill=(180, 176, 164, 255), outline=(120, 116, 106, 255),
              width=max(1, int(r * 0.04)))


def _draw_dpad(d, cx, cy, r, ss):
    w = r * 0.34
    d.rectangle([cx - w, cy - r, cx + w, cy + r], fill=RECESS)
    d.rectangle([cx - r, cy - w, cx + r, cy + w], fill=RECESS)
    d.rectangle([cx - w, cy - r, cx + w, cy + r], outline=OUTLINE,
                width=max(1, int(r * 0.06)))
    d.rectangle([cx - r, cy - w, cx + r, cy + w], outline=OUTLINE,
                width=max(1, int(r * 0.06)))


def _shape(d, cx, cy, r, kind, color, lw=None):
    if lw is None:
        lw = max(2, int(r * 0.13))
    if kind == "cross":
        d.line([cx - r, cy - r, cx + r, cy + r], fill=color, width=lw)
        d.line([cx - r, cy + r, cx + r, cy - r], fill=color, width=lw)
    elif kind == "cir":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=lw)
    elif kind == "sq":
        d.rectangle([cx - r, cy - r, cx + r, cy + r], outline=color, width=lw)
    elif kind == "tri":
        d.polygon([(cx, cy - r * 1.1), (cx - r * 1.05, cy + r * 0.8),
                   (cx + r * 1.05, cy + r * 0.8)], outline=color, width=lw)


def _draw_face(d, cx, cy, r, kind, ss):
    col = {"cross": (150, 190, 255, 255), "cir": (255, 150, 150, 255),
           "sq": (255, 170, 230, 255), "tri": (160, 240, 160, 255)}[kind]
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(235, 232, 224, 255),
              outline=OUTLINE, width=max(1, int(r * 0.12)))
    _shape(d, cx, cy, r * 0.62, kind, col)


def _draw_face_letter(d, cx, cy, r, letter, col, ss):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col,
              outline=OUTLINE, width=max(1, int(r * 0.12)))
    f = _font(max(4, int(r * 1.1)))
    bb = d.textbbox((0, 0), letter, font=f)
    d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], cy - (bb[3] - bb[1]) / 2 - bb[1]),
           letter, font=f, fill=(255, 255, 255, 255))


def render_map(kind: str, ss: int = 4) -> Image.Image:
    """Returns the 960x540 RGBA map image for `kind` (ps5|steam)."""
    src = aif_mod.AifImage((REPO / MAP_SRC).read_bytes())
    w, h = src.width, src.height
    original = Image.frombytes("RGBA", (w, h), src.to_rgba())
    blue = _blue_mask(original)  # original callout lines, intact
    im, d = _ss_draw((w, h), ss)
    if kind == "ps5":
        _draw_body_ps5(d, ss)
    elif kind == "steam":
        _draw_body_steam(d, ss)
    else:
        raise SystemExit("kind desconocido: %s" % kind)
    im = im.resize((w, h), Image.LANCZOS)
    # composes the blue lines ON TOP (same positions as the original)
    im.alpha_composite(blue)
    # key-color background like the original (RGB (10,28,5) alpha 0)
    bg = Image.new("RGBA", (w, h), (10, 28, 5, 0))
    bg.alpha_composite(im)
    return bg


# ---------------------------------------------------------------------------
# Button icons of the atlas
# ---------------------------------------------------------------------------
# (cx, cy, disc_radius, label)
ROW_ICONS = [
    (596, 639, 13, "cross"), (628, 639, 13, "cross"),
    (660, 639, 13, "cir"), (692, 639, 13, "cir"),
    (724, 639, 13, "sq"), (756, 639, 13, "sq"),
    (788, 639, 13, "tri"), (820, 639, 13, "tri"),
    (852, 639, 13, "L1"), (884, 639, 13, "L1"),
    (916, 639, 13, "R1"), (948, 639, 13, "R1"),
]
STACK_ICONS = [
    (25, 742, 15, "R1"), (71, 742, 15, "L1"),
    (25, 792, 17, "R1"), (71, 792, 17, "L1"),
    (25, 837, 16, "cross"), (71, 837, 16, "cir"), (117, 837, 16, "sq"),
    (163, 837, 16, "tri"), (209, 837, 16, "R2"), (255, 837, 16, "L2"),
    (25, 887, 17, "cross"), (71, 887, 17, "cir"), (117, 887, 17, "sq"),
    (163, 887, 17, "tri"), (209, 887, 17, "R2"), (255, 887, 17, "L2"),
]

DISC_COLORS = {
    "cross": (60, 110, 210), "cir": (200, 55, 45),
    "sq": (220, 120, 200), "tri": (60, 170, 70),
}


def _recolor_disc(base: Image.Image, cx, cy, r, target):
    """Repaints the inner disc with a clean radial shading (without the original
    letter, which would leave a ghost)."""
    px = base.load()
    w, h = base.size
    hl = (cx - r * 0.35, cy - r * 0.45)  # light focus
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if x < 0 or y < 0 or x >= w or y >= h:
                continue
            d = math.hypot(x - cx, y - cy)
            if d > r:
                continue
            dh = math.hypot(x - hl[0], y - hl[1]) / (r * 1.7)
            shade = max(0.45, min(1.35, 1.28 - 0.72 * dh))
            px[x, y] = (min(255, int(target[0] * shade)),
                        min(255, int(target[1] * shade)),
                        min(255, int(target[2] * shade)), px[x, y][3])


def _draw_symbol(d, cx, cy, r, kind, ss):
    if kind in ("cross", "cir", "sq", "tri"):
        _shape(d, cx, cy, r * 0.72, kind, (245, 245, 245, 255),
               lw=max(3, int(r * 0.30)))
    else:  # label like L1/R2
        f = _font(max(6, int(r * 1.9)))
        bb = d.textbbox((0, 0), kind, font=f)
        d.text((cx - (bb[2] - bb[0]) / 2 - bb[0],
                cy - (bb[3] - bb[1]) / 2 - bb[1]),
               kind, font=f, fill=(245, 245, 245, 255),
               stroke_width=max(1, int(ss * 0.5)), stroke_fill=(30, 30, 30, 255))


def render_atlas_ps5(base_img: Image.Image | None = None, ss: int = 4) -> Image.Image:
    if base_img is None:
        src = aif_mod.AifImage((REPO / ATLAS_SRC).read_bytes())
        base = Image.frombytes("RGBA", (src.width, src.height), src.to_rgba())
    else:
        base = base_img.copy()
    icons = ROW_ICONS + STACK_ICONS
    # 1) recolor the discs
    for cx, cy, r, kind in icons:
        if kind in DISC_COLORS:
            _recolor_disc(base, cx, cy, r, DISC_COLORS[kind])
    # 2) draw the shapes/labels with supersampling, cropping to each cell
    for cx, cy, r, kind in icons:
        cell = int(r * 2.6) + 2
        im, d = _ss_draw((cell, cell), ss)
        _draw_symbol(d, cell * ss // 2, cell * ss // 2, r * ss, kind, ss)
        im = im.resize((cell, cell), Image.LANCZOS)
        base.alpha_composite(im, (cx - cell // 2, cy - cell // 2))
    return base


# ---------------------------------------------------------------------------
# AIF encoding
# ---------------------------------------------------------------------------
def encode_full(original: bytes, rgba: bytes, base: int = 0) -> bytes:
    """Re-encodes the WHOLE AIF (DXT or A8R8G8B8) from RGBA of the same size."""
    img = aif_mod.AifImage(original, base)
    w, h = img.width, img.height
    if img.format == aif_mod.FMT_ARGB8888:
        out = bytearray(len(original))
        out[:img.data_offset] = original[:img.data_offset]
        out[img.data_offset + img.base_level_size():] = \
            original[img.data_offset + img.base_level_size():]
        for y in range(h):
            for x in range(w):
                o = (y * w + x) * 4
                off = img.data_offset + aif_mod.tiled_offset(
                    x, y, img.tiled_width, 4) * 4
                out[off:off + 4] = bytes((rgba[o + 3], rgba[o],
                                          rgba[o + 1], rgba[o + 2]))
        return bytes(out)
    ed = aif_edit.AifEditor(original, base)
    for by in range(ed.by):
        for bx in range(ed.bx):
            pixels = []
            for yy in range(4):
                for xx in range(4):
                    x, y = bx * 4 + xx, by * 4 + yy
                    if x < w and y < h:
                        o = (y * w + x) * 4
                        pixels.append(tuple(rgba[o:o + 4]))
                    else:
                        pixels.append((0, 0, 0, 0))
            ed.write_block(bx, by, aif_edit.encode_block(ed.fmt, pixels))
    return ed.to_bytes()


def _preview(base: Image.Image, path: str, bgcol=(60, 60, 60, 255)):
    bg = Image.new("RGBA", base.size, bgcol)
    bg.alpha_composite(base)
    bg.convert("RGB").save(path)
    print("    preview:", path)


def cmd_map(args):
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    orig = (REPO / MAP_SRC).read_bytes()
    kinds = args.only or ["ps5", "steam"]
    for kind in kinds:
        im = render_map(kind, args.ss)
        data = encode_full(orig, im.tobytes())
        assert len(data) == len(orig), "tamano distinto"
        name = "controllermap_%s_es.aif" % kind
        (outdir / name).write_bytes(data)
        print("map %-5s -> %s (%d B)" % (kind, outdir / name, len(data)))
        if args.preview:
            _preview(im, str(outdir / ("controllermap_%s_preview.png" % kind)))
    return 0


def cmd_atlas(args):
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    orig = (REPO / ATLAS_SRC).read_bytes()
    # Base: the already painted ES atlas (labels) if it exists; otherwise, the original.
    base_path = args.base
    if not base_path:
        cand = Path(args.out) / "atlas_ui_es.aif"
        base_path = str(cand) if cand.is_file() else ATLAS_SRC
    bimg = aif_mod.AifImage((REPO / base_path).read_bytes() if not Path(base_path).is_absolute()
                            else Path(base_path).read_bytes())
    base_img = Image.frombytes("RGBA", (bimg.width, bimg.height), bimg.to_rgba())
    print("  base atlas:", base_path)
    im = render_atlas_ps5(base_img, args.ss)
    data = encode_full(orig, im.tobytes())
    assert len(data) == len(orig), "tamano distinto"
    name = "atlas_ui_ps5_es.aif"
    (outdir / name).write_bytes(data)
    print("atlas ps5 -> %s (%d B)" % (outdir / name, len(data)))
    if args.preview:
        _preview(im, str(outdir / "atlas_ui_ps5_preview.png"))
        # verification crops
        im.crop((560, 610, 1024, 675)).resize((928, 130), Image.NEAREST)\
            .convert("RGB").save(str(outdir / "atlas_ui_ps5_row.png"))
        im.crop((0, 690, 300, 930)).resize((600, 480), Image.NEAREST)\
            .convert("RGB").save(str(outdir / "atlas_ui_ps5_stack.png"))
    return 0


def cmd_all(args):
    if not hasattr(args, "only"):
        args.only = []
    if not hasattr(args, "base"):
        args.base = ""
    cmd_map(args)
    cmd_atlas(args)
    return 0


def cmd_selftest(args):
    # round-trip: encoding and re-decoding the map must give the same size
    orig = (REPO / MAP_SRC).read_bytes()
    im = render_map("ps5", 2)
    data = encode_full(orig, im.tobytes())
    assert len(data) == len(orig)
    back = aif_mod.AifImage(data)
    print("[ok] mapa ps5: %dx%d %s, %d B (igual que original)"
          % (back.width, back.height, back.format_name, len(data)))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Variantes de texturas por mando.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("map", help="dibuja el mapa del mando (ps5/steam)")
    s.add_argument("--out", default=OUTDIR)
    s.add_argument("--only", action="append", default=[])
    s.add_argument("--ss", type=int, default=4)
    s.add_argument("--preview", action="store_true")
    s.set_defaults(func=cmd_map)

    s = sub.add_parser("atlas", help="iconos de boton PS5 en el atlas de UI")
    s.add_argument("--out", default=OUTDIR)
    s.add_argument("--base", default="",
                   help="atlas base (por defecto el atlas ES ya renderizado)")
    s.add_argument("--ss", type=int, default=4)
    s.add_argument("--preview", action="store_true")
    s.set_defaults(func=cmd_atlas)

    s = sub.add_parser("all", help="genera mapa (ps5/steam) + atlas ps5")
    s.add_argument("--out", default=OUTDIR)
    s.add_argument("--ss", type=int, default=4)
    s.add_argument("--preview", action="store_true")
    s.set_defaults(func=cmd_all)

    s = sub.add_parser("selftest")
    s.set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
