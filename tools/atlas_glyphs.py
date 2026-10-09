#!/usr/bin/env python3
"""
atlas_glyphs.py -- shared library for extending the `RMD-` atlases.

Each `RMD-` ships its `AIF ` atlas with **only the glyphs its text uses** (union
of the JP+EN lines), in a 32x32 grid ordered by first appearance
(`cell = code - 301`). That is why Latin letters (especially uppercase) and the
16 Spanish characters are missing.

This module:

  * loads a bank (AIF + `.msg` + charmap) and exposes its `char -> cell` map;
  * computes a **style signature** (normalized binary masks of common letters)
    to match banks of the same typeface;
  * chooses, for a character missing in a bank, the closest-style **donor** that
    does have it (so the correct glyph is copied instead of redrawn);
  * reuses the accent composition from `tools/add_accents.py`.

Charmap convention: `translation/charmaps/<stem>.json` (from the F2.5 pipeline)
and, for the glyphs added here, `translation/charmaps_extra/<stem>.json`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for _p in (HERE, REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import aif as aif_mod          # noqa: E402
import aif_edit                # noqa: E402
import add_accents as A        # noqa: E402
from PIL import Image          # noqa: E402

CELL = 32
# render-verified corrections of the `005` charmap (shifted signs)
PUNCT_FIX = {".": 416, ",": 415, "?": 417, "!": 444, "«": None, "»": None}


class Bank:
    def __init__(self, stem: str, decode: bool = True):
        self.stem = stem
        self.aif_path = REPO / "extract" / "f0" / (stem + ".aif")
        self.msg_path = REPO / "extract" / "f0" / (stem + ".msg")
        self.aif_bytes = self.aif_path.read_bytes()
        self.img = aif_mod.AifImage(self.aif_bytes)
        self.width, self.height = self.img.width, self.img.height
        self.cols = self.width // CELL
        self.rows = self.height // CELL
        self.cells = self.cols * self.rows
        self.count = 0
        if self.msg_path.is_file():
            import struct
            self.count = struct.unpack_from(">I", self.msg_path.read_bytes(), 0x34)[0]
        self.charmap = self._charmap("charmaps")
        self.charmap_extra = self._charmap("charmaps_extra")
        self.rgba = aif_edit.decode_rgba(self.aif_bytes)[2] if decode else None

    def _charmap(self, sub):
        p = REPO / "mod" / "translation" / sub / (self.stem + ".json")
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return {}
        return {}

    # -- char -> cell map -------------------------------------------------
    def char_to_cell(self):
        """{char: cell} prioritizing the lowest code >= 300 (valid)."""
        raw = {}
        for src in (self.charmap, self.charmap_extra):
            for k, v in src.items():
                if isinstance(v, str) and len(v) == 1:
                    raw.setdefault(v, [])
        for src in (self.charmap, self.charmap_extra):
            for k, v in src.items():
                if isinstance(v, str) and len(v) == 1:
                    try:
                        code = int(k)
                    except ValueError:
                        continue
                    if code >= 300 and 0 <= code - 301 < self.cells:
                        raw[v].append(code - 301)
        return {ch: min(cs) for ch, cs in raw.items() if cs}

    def chars_present(self):
        return set(self.char_to_cell().keys())

    def cell_image(self, idx, rgba=None):
        img = Image.frombytes("RGBA", (self.width, self.height),
                              rgba if rgba is not None else self.rgba)
        r, c = divmod(idx, self.cols)
        return img.crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL))


def ink_bbox(img):
    g = img.convert("L")
    bb = g.point(lambda v: 255 if v > 96 else 0).getbbox()
    return bb


def normalized_mask(img, size=16):
    """16x16 binary mask of the glyph ink (cropped to its bbox)."""
    bb = ink_bbox(img)
    if bb is None:
        return None
    crop = img.convert("L").crop(bb)
    crop = crop.resize((size, size), Image.BILINEAR)
    px = [1 if v > 96 else 0 for v in crop.getdata()]
    return px


def iou(a, b):
    inter = sum(1 for x, y in zip(a, b) if x and y)
    union = sum(1 for x, y in zip(a, b) if x or y)
    return inter / union if union else 0.0


STYLE_CHARS = list("aeonsiutrlcdhgAEONRSTILCD")


class Library:
    """Index of all banks: cell per character + style signature."""

    def __init__(self, stems=None):
        self.banks = {}
        if stems is None:
            stems = sorted(p.stem for p in (REPO / "extract" / "f0").glob("*.aif"))
        for s in stems:
            try:
                b = Bank(s, decode=True)
            except Exception:  # noqa: BLE001
                continue
            self.banks[s] = b
        self._sig_cache = {}

    def signature(self, stem):
        if stem in self._sig_cache:
            return self._sig_cache[stem]
        b = self.banks[stem]
        c2c = b.char_to_cell()
        sig = {}
        for ch in STYLE_CHARS:
            if ch in c2c:
                m = normalized_mask(b.cell_image(c2c[ch]))
                if m:
                    sig[ch] = m
        self._sig_cache[stem] = sig
        return sig

    def style_sim(self, a, b):
        sa, sb = self.signature(a), self.signature(b)
        common = [ch for ch in sa if ch in sb]
        if not common:
            return 0.0
        return sum(iou(sa[ch], sb[ch]) for ch in common) / len(common)

    def donor_for(self, target, ch):
        """Best bank (other than target) that has `ch`, by style."""
        best, bests = None, -1.0
        for stem, b in self.banks.items():
            if stem == target:
                continue
            c2c = b.char_to_cell()
            if ch in c2c:
                s = self.style_sim(target, stem)
                if s > bests:
                    best, bests = stem, s
        return best, bests
