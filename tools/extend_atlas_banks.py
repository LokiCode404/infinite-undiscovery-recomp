#!/usr/bin/env python3
"""
extend_atlas_banks.py -- WS1/F3-b: completes the atlas of each `RMD-` bank.

Each `RMD-` ships a **subset** atlas (only the glyphs of its text); when
translating to Spanish, Latin letters and the 16 accented characters are missing.
This tool, **per bank**:

  1. computes the characters the Spanish translation needs (union of
     `translation/es.json` + `translation/parts/*.json` for that `stem`) plus the
     16 accents, and subtracts the ones the bank already has (charmap + extra);
  2. locates each missing glyph in a **donor bank of the same style**
     (`tools/atlas_glyphs.py`, mask similarity -> same typeface) and copies
     its bitmap; the accents are **composed** (base + diacritic) over the base
     letters of the bank itself;
  3. writes them into **free** cells (after `count`); if there are not enough, it
     reuses cells never referenced by the bank text and, as a last resort, the
     least used ones (recorded in the manifest);
  4. updates the `.msg` metric table (does not touch `count` to avoid changing
     the bank signature);
  5. writes `translation/charmaps_extra/<stem>.json` (code->character of the
     added glyphs), the patched files, the **runtime binary**
     (`translation/extended_atlas.bin`) and a manifest + review montage.

Validation: DXT wrapper round-trip and that the bytes that change fall only
in the added cells.

Usage
-----
    python -X utf8 tools/extend_atlas_banks.py --from-parts        # all banks with translation
    python -X utf8 tools/extend_atlas_banks.py --stems d1_ud2_224F6800_028
"""

from __future__ import annotations

import argparse
import glob
import json
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"))

import aif as aif_mod          # noqa: E402
import aif_edit                # noqa: E402
import add_accents as A        # noqa: E402
import atlas_glyphs as AG      # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

CELL = 32
RT_MAGIC = 0x31415549          # 'IUA1'
ACCENTS = list("áéíóúüñÁÉÍÓÚÜÑ¿¡")
# base of each accent (for composing) and of the rotated ones
ACCENT = A.ACCENT
ROTATE = A.ROTATE
BASE_OF = {ch: (ACCENT[ch][1] if ch in ACCENT else ROTATE[ch]) for ch in ACCENTS}


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def read_msg(path):
    b = Path(path).read_bytes()
    metrics_off = struct.unpack_from(">I", b, 0x28)[0]
    count = struct.unpack_from(">I", b, 0x34)[0]
    return bytearray(b), metrics_off, count


def metric_of_removed():  # placeholder removed
    return None


def charge_msg(bank):
    b, mo, count = read_msg(bank.msg_path)
    bank._msg = b
    bank._metrics_off = mo
    return b, mo, count


def metric_u16(bank, cell):
    o = bank._metrics_off + 2 * cell
    if o + 2 > len(bank._msg):
        return 0
    return struct.unpack_from(">H", bank._msg, o)[0]


def metric_for_char(bank, ch, lib, donor_cache):
    b, mo, _ = charge_msg(bank)
    c2c = bank.char_to_cell()
    if ch in c2c:
        return metric_u16(bank, c2c[ch])
    donor = donor_cache.get((bank.stem, ch))
    if donor:
        db = lib.banks[donor]
        charge_msg(db)
        dc = db.char_to_cell().get(ch)
        if dc is not None:
            return metric_u16(db, dc)
    # last resort: metric of 'o' of the bank, or 14<<8
    c2c = bank.char_to_cell()
    for alt in ("o", "O", "n"):
        if alt in c2c:
            return metric_u16(bank, c2c[alt])
    return 14 << 8


# --------------------------------------------------------------------------
# images
# --------------------------------------------------------------------------
def find_by_image(bank, ref_img):
    """Cell of the bank whose image matches (or nearly) `ref_img`."""
    ref = ref_img.tobytes()
    ref_mask = AG.normalized_mask(ref_img)
    best, bestiou = None, 0.0
    for idx in range(bank.cells):
        img = bank.cell_image(idx)
        if img.tobytes() == ref:
            return idx
        m = AG.normalized_mask(img)
        if m and ref_mask:
            v = AG.iou(m, ref_mask)
            if v > bestiou:
                best, bestiou = idx, v
    return best if bestiou > 0.985 else None


def base_image(bank, base_ch, lib, donor_cache):
    """32x32 image of the base letter, from the bank itself or from a donor."""
    if base_ch in "?!":
        # the charmap usually has the signs shifted: located by image
        donor = donor_cache.get((bank.stem, base_ch))
        if donor:
            db = lib.banks[donor]
            di = db.char_to_cell().get(base_ch)
            if di is not None:
                ref = db.cell_image(di)
                idx = find_by_image(bank, ref)
                if idx is not None:
                    return bank.cell_image(idx)
                return ref  # same style, used as is
    c2c = bank.char_to_cell()
    if base_ch in c2c and AG.ink_bbox(bank.cell_image(c2c[base_ch])):
        return bank.cell_image(c2c[base_ch])
    donor = donor_cache.get((bank.stem, base_ch))
    if donor:
        db = lib.banks[donor]
        di = db.char_to_cell().get(base_ch)
        if di is not None:
            return db.cell_image(di)
    return None


def draw_symbol(ch, refs):
    """Draws `;` `:` `«` `»` with the bank style from refs."""
    out = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    if ch == ":":
        dot = refs.get(".")
        if dot is not None:
            bb = AG.ink_bbox(dot) or (0, 0, 1, 1)
            g = dot.crop(bb)
            out.alpha_composite(g, (10, 6))
            out.alpha_composite(g, (10, 20))
        return out
    if ch == ";":
        dot = refs.get(".")
        com = refs.get(",")
        if dot is not None and com is not None:
            bb = AG.ink_bbox(dot) or (0, 0, 1, 1)
            out.alpha_composite(dot.crop(bb), (10, 5))
            bb2 = AG.ink_bbox(com) or (0, 0, 1, 1)
            out.alpha_composite(com.crop(bb2), (10, 18))
        return out
    if ch in "«»":
        # two chevrons; if '<'/'>' exist they are reused
        src = refs.get("<" if ch == "«" else ">")
        if src is None:
            def chevron(cx, cy, sgn):
                d.line([(cx + sgn * 5, cy - 7), (cx - sgn * 5, cy), (cx + sgn * 5, cy + 7)],
                       fill=(0, 0, 0, 255), width=5, joint="curve")
                d.line([(cx + sgn * 5, cy - 7), (cx - sgn * 5, cy), (cx + sgn * 5, cy + 7)],
                       fill=(255, 255, 255, 255), width=2, joint="curve")
            sgn = 1 if ch == "«" else -1
            chevron(11, 16, sgn)
            chevron(21, 16, sgn)
        else:
            bb = AG.ink_bbox(src) or (0, 0, 1, 1)
            g = src.crop(bb)
            out.alpha_composite(g, (6, 8))
            out.alpha_composite(g, (16, 8))
        return out
    return None


# --------------------------------------------------------------------------
# patch of a bank
# --------------------------------------------------------------------------
def needed_for(stem, es_by_stem):
    need = set("".join(es_by_stem.get(stem, [])))
    need.discard("\n")
    need.discard(" ")
    need |= set(ACCENTS)
    return need


def used_codes(stem, allc):
    codes = Counter()
    for lst in allc.get(stem, {}).get("msgs", {}).values():
        for c in lst:
            if 0 < c < 0x4000:
                codes[c] += 1
    return codes


def assign_cells(bank, n, allc):
    """Returns `n` cells: free first, then unreferenced, then rare."""
    free = [i for i in aif_edit.free_cells(bank.aif_bytes) if i >= bank.count]
    if len(free) >= n:
        return free[:n], "free"
    used = used_codes(bank.stem, allc)
    unused = [i for i in range(bank.cells) if (i + 301) not in used and i not in free]
    unused.sort(reverse=True)  # high = end of the atlas
    picks = list(free)
    reuse_extra = []
    for i in unused:
        if len(picks) >= n:
            break
        picks.append(i)
        reuse_extra.append(i)
    if len(picks) < n:
        # used cells, from least frequent to most, from the end of the atlas
        ranked = sorted((i for i in range(bank.cells) if i not in picks),
                        key=lambda i: (used.get(i + 301, 0), -i))
        for i in ranked:
            if len(picks) >= n:
                break
            picks.append(i)
            reuse_extra.append(i)
    return picks[:n], ("free" if not reuse_extra else "reuse:%d" % len(reuse_extra))


def patch_bank(stem, lib, es_by_stem, allc, outdir, donor_cache):
    bank = lib.banks[stem]
    b, mo, count = charge_msg(bank)
    present = set(bank.char_to_cell().keys())
    need = needed_for(stem, es_by_stem)
    missing = sorted(c for c in need if c not in present and c != " ")

    # ensure the accent bases (added before composing)
    base_missing = sorted({BASE_OF[c] for c in missing if c in BASE_OF}
                          - present - set(missing))
    plain = [c for c in missing if c not in ACCENTS]
    order = plain + base_missing + [c for c in ACCENTS if c in missing]
    if not order:
        return None

    cells, how = assign_cells(bank, len(order), allc)
    ed = aif_edit.AifEditor(bank.aif_bytes)
    cols = bank.cols
    plan = []
    # refs for drawn symbols
    refs = {}
    for ch in ". ,< >".split():
        di = bank.char_to_cell().get(ch)
        if di is not None:
            refs[ch] = bank.cell_image(di)
        else:
            donor = donor_cache.get((stem, ch))
            if donor:
                db = lib.banks[donor]
                di = db.char_to_cell().get(ch)
                if di is not None:
                    refs[ch] = db.cell_image(di)

    def make_image(ch):
        if ch in ACCENTS:
            base = base_image(bank, BASE_OF[ch], lib, donor_cache)
            if base is None:
                return None
            if ch in ROTATE:
                return A.rotate_180(base)
            kind, _src = ACCENT[ch]
            return A.compose(base, kind)
        # normal letter/number/symbol
        donor = donor_cache.get((stem, ch))
        if donor:
            db = lib.banks[donor]
            di = db.char_to_cell().get(ch)
            if di is not None:
                return db.cell_image(di)
        if ch in ";:«»":
            return draw_symbol(ch, refs)
        return None

    # the added bases must exist in order to compose; they are generated in order
    img_cache = {}
    for ch in order:
        img = make_image(ch)
        if img is None:
            continue
        img_cache[ch] = img

    glyphs = []
    for i, ch in enumerate(order):
        if ch not in img_cache:
            continue
        idx = cells[i]
        row, col = divmod(idx, cols)
        ed.write_cell_rgba(row, col, img_cache[ch].tobytes())
        metric = metric_for_char(bank, BASE_OF[ch] if ch in ACCENTS else ch,
                                 lib, donor_cache)
        o = mo + 2 * idx
        if o + 2 <= len(b):
            struct.pack_into(">H", b, o, metric)
        glyphs.append({"char": ch, "code": 301 + idx, "cell": idx,
                       "row": row, "col": col, "metric": metric,
                       "kind": ("accent" if ch in ACCENTS else
                                "base" if ch in base_missing else "glyph")})

    if not glyphs:
        return None

    patched_aif = ed.to_bytes()
    assert len(patched_aif) == len(bank.aif_bytes)
    orig = aif_edit.AifEditor(bank.aif_bytes)
    if not (orig.to_bytes() == bank.aif_bytes and orig.verify_wrapper()):
        raise SystemExit("%s: round-trip DXT FALLO" % stem)

    # the bytes that change fall only in the new cells
    allowed = set()
    for p in glyphs:
        r0, c0 = divmod(p["cell"], cols)
        for by4 in range(8):
            for bx4 in range(8):
                off = aif_mod.tiled_offset(c0 * 8 + bx4, r0 * 8 + by4,
                                           ed.tw, ed.block_bytes) * ed.block_bytes
                allowed.update(range(off, off + ed.block_bytes))
    diffs = [i for i in range(len(orig.raw)) if orig.raw[i] != ed.raw[i]]
    outside = [d for d in diffs if d not in allowed]
    if outside:
        raise SystemExit("%s: %d bytes fuera de las celdas nuevas" % (stem, len(outside)))

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / (stem + "_ext.aif")).write_bytes(patched_aif)
    (outdir / (stem + "_ext.msg")).write_bytes(bytes(b))

    # DXT blocks in file order for the runtime
    edp = aif_edit.AifEditor(patched_aif)
    for p in glyphs:
        r0, c0 = divmod(p["cell"], cols)
        blocks = bytearray()
        for gy in range(8):
            for gx in range(8):
                off = aif_mod.tiled_offset(c0 * 8 + gx, r0 * 8 + gy,
                                           edp.tw, edp.block_bytes) * edp.block_bytes
                blocks += edp.raw[off:off + edp.block_bytes]
        p["blocks"] = bytes(blocks)

    meta = {
        "stem": stem, "aif_len": len(bank.aif_bytes),
        "width": bank.width, "height": bank.height,
        "format": bank.img.format, "ident": struct.unpack_from(">I", bank.aif_bytes, 0x20)[0],
        "tiled_width": ed.tw, "pixels_off": bank.img.data_offset,
        "element_bytes": ed.block_bytes,
        "total": struct.unpack_from(">I", b, 0x30)[0],
        "count": count, "atlas_w": struct.unpack_from(">I", b, 0x60)[0],
        "atlas_h": struct.unpack_from(">I", b, 0x64)[0],
        "how": how, "glyphs": glyphs,
    }
    return meta


# --------------------------------------------------------------------------
# outputs
# --------------------------------------------------------------------------
def write_runtime_bin(path, metas):
    with open(path, "wb") as fh:
        fh.write(struct.pack("<II", RT_MAGIC, len(metas)))
        for m in metas:
            fh.write(struct.pack("<IIIIIIIIIIII", m["aif_len"], m["width"], m["height"],
                                 m["format"], m["ident"], m["tiled_width"], m["pixels_off"],
                                 m["element_bytes"], m["total"], m["count"],
                                 m["atlas_w"], m["atlas_h"]))
            fh.write(struct.pack("<I", len(m["glyphs"])))
            for g in m["glyphs"]:
                fh.write(struct.pack("<HHI", g["cell"], g["metric"], 0))
                fh.write(g["blocks"])
    print("runtime bin -> %s (%d bancos, %.1f KiB)"
          % (path, len(metas), path.stat().st_size / 1024.0))


def write_extra_charmaps(metas):
    d = REPO / "mod" / "translation" / "charmaps_extra"
    d.mkdir(parents=True, exist_ok=True)
    for m in metas:
        cm = {}
        p = d / (m["stem"] + ".json")
        if p.is_file():
            cm = json.loads(p.read_text(encoding="utf-8"))
        for g in m["glyphs"]:
            cm[str(g["code"])] = g["char"]
        p.write_text(json.dumps(cm, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print("charmaps_extra -> %s (%d ficheros)" % (d, len(metas)))


def review_montage(m, outdir):
    aif = (outdir / (m["stem"] + "_ext.aif")).read_bytes()
    w, h, rgba = aif_edit.decode_rgba(aif)
    cols = w // CELL
    src = Image.frombytes("RGBA", (w, h), rgba)
    S = 2
    n = len(m["glyphs"])
    per = 24
    rows = (n + per - 1) // per
    canvas = Image.new("RGBA", (per * (CELL * S + 4) + 8, rows * (CELL * S + 16) + 8),
                       (20, 20, 20, 255))
    dr = ImageDraw.Draw(canvas)
    for j, g in enumerate(m["glyphs"]):
        r, c = divmod(g["cell"], cols)
        im = src.crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL)) \
                .resize((CELL * S, CELL * S), Image.NEAREST)
        x = 4 + (j % per) * (CELL * S + 4)
        y = 4 + (j // per) * (CELL * S + 16)
        canvas.alpha_composite(im, (x, y))
        dr.text((x + 1, y + CELL * S + 1), g["char"], fill=(255, 255, 0, 255))
    canvas.save(outdir / (m["stem"] + "_ext_row.png"))


def load_es_by_stem():
    by = defaultdict(list)
    files = ["mod/translation/es.json"] + sorted(glob.glob("mod/translation/parts/*.json"))
    for f in files:
        try:
            d = json.loads((REPO / f).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for s in d.get("strings", []):
            if s.get("stem") and s.get("es"):
                by[s["stem"]].append(s["es"])
    return by


def main(argv=None):
    ap = argparse.ArgumentParser(description="F3-b: completa los atlas por banco.")
    ap.add_argument("--stems", nargs="*")
    ap.add_argument("--from-parts", action="store_true",
                    help="todos los bancos con traduccion en es.json/parts")
    ap.add_argument("--out", default=str(REPO / "extract" / "f2" / "extended"))
    ap.add_argument("--runtime-bin", default=str(REPO / "mod" / "translation" / "extended_atlas.bin"))
    ap.add_argument("--manifest", default=str(REPO / "mod" / "translation" / "extended_manifest.json"))
    args = ap.parse_args(argv)

    es_by = load_es_by_stem()
    lib = AG.Library()
    allc = json.loads((REPO / "extract" / "messages" / "all_codes.json").read_text(encoding="utf-8"))

    stems = args.stems or []
    if args.from_parts:
        stems += [s for s in es_by if s in lib.banks]
    stems = sorted(set(stems))
    if not stems:
        ap.error("indica --stems o --from-parts")

    # donor cache (target, char) -> stem
    donor_cache = {}
    for stem in stems:
        bank = lib.banks[stem]
        need = needed_for(stem, es_by)
        present = set(bank.char_to_cell().keys())
        for ch in need - present:
            d, s = lib.donor_for(stem, ch)
            if d:
                donor_cache[(stem, ch)] = d

    outdir = Path(args.out)
    metas, ok = [], 0
    for stem in stems:
        try:
            meta = patch_bank(stem, lib, es_by, allc, outdir, donor_cache)
        except SystemExit as exc:
            print("  ! %s: %s" % (stem, exc))
            continue
        if meta is None:
            continue
        metas.append(meta)
        ok += 1
        review_montage(meta, outdir)
        kinds = Counter(g["kind"] for g in meta["glyphs"])
        print("  + %-28s +%2d glifos %-24s %s"
              % (stem, len(meta["glyphs"]), dict(kinds), meta["how"]))

    if not metas:
        raise SystemExit("nada que hacer")
    write_extra_charmaps(metas)
    rt = Path(args.runtime_bin)
    rt.parent.mkdir(parents=True, exist_ok=True)
    write_runtime_bin(rt, metas)

    man = {"bancos": [{"stem": m["stem"], "aif_len": m["aif_len"],
                       "count": m["count"], "how": m["how"],
                       "glyphs": [{"char": g["char"], "code": g["code"],
                                   "cell": g["cell"], "kind": g["kind"]}
                                  for g in m["glyphs"]]} for m in metas]}
    Path(args.manifest).write_text(json.dumps(man, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    print("\nbancos tratados: %d" % ok)
    print("manifiesto     : %s" % args.manifest)
    print("runtime bin    : %s" % rt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
