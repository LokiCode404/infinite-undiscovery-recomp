#!/usr/bin/env python3
"""
add_accents_banks.py -- WS1: adds the Spanish glyphs to the `RMD-` atlases
**per bank** and generates the integration material.

For each `RMD-` bank (stem of `extract/f0/<stem>.aif` + `.msg`):

  1. locates the base letters in the atlas of THAT bank (its own style) using the
     charmap (`translation/charmaps/<stem>.json`) and, as a tie-breaker, the
     similarity of the ink box with the verified "clean" copies of `005`
     (`--bases-json` allows fixing them by hand);
  2. composes the requested glyphs (`á é í ó ú ü ñ Á É Í Ó Ú Ü Ñ ¿ ¡`; `¿/¡` = `?/!`
     rotated 180), with the same code validated by F3 (`tools/add_accents.py`);
  3. writes them into **free** cells (transparent or uniform fill).  If there are
     not enough, it reuses cells whose character is kana/kanji (Japanese text,
     which the English PAL version never draws) -- `--no-reuse-unused` disables it;
  4. updates the **metric table** of the `.msg` (each new glyph inherits the
     metric of its base). By default it does NOT change `count`/`count2`: the
     renderer reads the metric by index without consulting `count`, and leaving
     the bank signature intact keeps the runtime catalog stable;
  5. emits the patched files, a **manifest** and the **runtime binary**
     (`translation/accents_atlas.bin`) that `mod/recomp/accents_es.h` consumes;
  6. optionally adds the accented characters to the bank charmap
     (`--update-charmaps`) so that `tools/build_es_codes.py` uses them.

Subset per bank
---------------
By default only the glyphs that THAT bank needs are added, deduced from
`translation/es.json` + `translation/parts/*.json` (`--need-from-es`).  With
`--all` the 16 are attempted in all banks.  This avoids spending cells and,
above all, allows covering banks whose atlas does not have all the base letters
(`Á` cannot be composed if `A` does not exist).

Mandatory validation (always run):
  * DXT wrapper round-trip of the patched AIF;
  * the bytes that change fall **only** in the new cells;
  * the metric table has room for the chosen cells (the .msg does not grow).

Usage
-----
    # all banks that need accents, with just their glyphs:
    python -X utf8 tools/add_accents_banks.py --need-from-es --update-charmaps

    # single bank (the one that renders Spanish today), the 16 glyphs:
    python -X utf8 tools/add_accents_banks.py --stems d1_ud1_000A4000_005 --all

    # fix bases by hand (per bank):
    python -X utf8 tools/add_accents_banks.py --bases-json translation/accents_bases.json
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"))

import aif as aif_mod          # noqa: E402
import aif_edit                # noqa: E402
import add_accents as A        # noqa: E402  (reuses compose/rotate/cell_image)
from PIL import Image          # noqa: E402

CELL = 32
# Runtime binary: 'IUA1'
RT_MAGIC = 0x31415549

# Base letters to locate in each bank (the ones used by the glyphs).
BASES = ["a", "e", "i", "o", "u", "n", "A", "E", "I", "O", "U", "N", "?", "!"]

# Verified "clean" copies of `005` (F3, validated by render). Used as a shape
# reference to choose, among the copies the charmap of another bank gives, the
# one with the same size/style.  Taken from `A.BASE_CELL`, which already points
# to the NORMAL (non-bold) variant of each letter.
REF_005 = dict(A.BASE_CELL)

# Canonical order of the glyphs / composition (from add_accents).
NEW_GLYPHS = A.NEW_GLYPHS
ACCENT = A.ACCENT
ROTATE = A.ROTATE


# --------------------------------------------------------------------------
# shape descriptors
# --------------------------------------------------------------------------
def descriptor(rgba, width, height, cell):
    """(width, height, ink) of the ink box of cell `cell`."""
    cols = width // CELL
    r, c = divmod(cell, cols)
    img = Image.frombytes("RGBA", (width, height), rgba) \
               .crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL))
    alpha = img.split()[3]
    bb = alpha.getbbox()
    if not bb:
        return (0, 0, 0)
    # ink is the RGB channel (see docs/re/charmap.md §3)
    grey = img.convert("L")
    ink = sum(1 for v in grey.getdata() if v > 96)
    return (bb[2] - bb[0], bb[3] - bb[1], ink)


def cell_image(rgba, width, height, idx, cw=CELL, ch=CELL):
    """Cell `idx` of an atlas (supports NON-square atlases: 256x128, ...)."""
    img = Image.frombytes("RGBA", (width, height), rgba)
    cols = width // cw
    r, c = divmod(idx, cols)
    return img.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))


def is_cjk(ch):
    o = ord(ch)
    return (0x3040 <= o <= 0x30FF) or (0x3400 <= o <= 0x9FFF) or \
           (0xFF00 <= o <= 0xFFEF) or (0x4E00 <= o <= 0x9FFF)


def used_cells(stem):
    """Cells referenced by the bank text (to avoid overwriting the space or
    other blank glyphs that are in fact used)."""
    try:
        from decode_messages import MsgBank
    except Exception:  # noqa: BLE001
        return set()
    p = REPO / "extract" / "f0" / (stem + ".msg")
    if not p.is_file():
        return set()
    try:
        bank = MsgBank(p)
    except Exception:  # noqa: BLE001
        return set()
    out = set()
    for r in bank.records:
        try:
            toks = bank.decode(r["id"])
        except Exception:  # noqa: BLE001
            continue
        for t in toks:
            if t.get("kind") == "glyph" and t["code"] >= 301:
                out.add(t["code"] - 301)
    return out


def _cell_hash_cid_index():
    """cid by cell md5, if the F2.5 pipeline left it available."""
    p = REPO / "extract" / "f2" / "glyphs" / "hash_to_cid.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


# --------------------------------------------------------------------------
# base location per bank
# --------------------------------------------------------------------------
def localize_bases(stem, width, height, rgba, cells, override, ref_desc, needed):
    """Returns ({char: cell}, {missing char}). Uses the charmap + ink box."""
    cmap_path = REPO / "mod" / "translation" / "charmaps" / (stem + ".json")
    if not cmap_path.is_file():
        raise SystemExit("sin charmap: %s" % cmap_path)
    cmap = json.loads(cmap_path.read_text(encoding="utf-8"))
    inv = {}
    for k, v in cmap.items():
        if isinstance(v, str) and len(v) == 1:
            inv.setdefault(v, []).append(int(k))

    out, missing = {}, []
    for ch in sorted(needed):
        if ch in override:
            out[ch] = int(override[ch])
            continue
        cands = [c for c in inv.get(ch, []) if c >= 300 and (c - 301) < cells]
        if ch == "I" and not inv.get("I"):
            # I and l share the stem; any is accepted as a base
            cands = [c for c in inv.get("l", []) if c >= 300 and (c - 301) < cells]
        if ch == "i" and not inv.get("i"):
            # the dotless i is a stem: l serves to compose `í`
            cands = [c for c in inv.get("l", []) if c >= 300 and (c - 301) < cells]
        if not cands:
            missing.append(ch)
            continue
        rd = ref_desc.get(ch)
        best, bestscore = None, 1 << 30
        for code in cands:
            d = descriptor(rgba, width, height, code - 301)
            if rd is None:
                best = code - 301
                break
            score = abs(d[0] - rd[0]) + abs(d[1] - rd[1]) + abs(d[2] - rd[2]) // 8
            if score < bestscore:
                best, bestscore = code - 301, score
        out[ch] = best
    return out, missing


# --------------------------------------------------------------------------
# cell selection
# --------------------------------------------------------------------------
def select_cells(stem, free_all, msg_count, cells, bases, charmap, nglyphs,
                 reuse_unused, metrics_entries, used_cells):
    """Returns the `nglyphs` cells where to write.

    Preference order:
      1. free after `count` (transparent / uniform fill) -- like F3;
      2. free before `count` **not referenced** by the bank text
         (internal holes may be the space or other blank glyphs);
      3. (if `reuse_unused`) cells with a kana/kanji character (JP text that the
         English PAL version does not draw).
    Never uses a base cell or a cell without an entry in the metric table
    (`metrics_entries`), because the hook patches the `.msg` in place.
    """
    used = set(bases.values())
    ok = lambda i: i < metrics_entries and i not in used  # noqa: E731
    out = []
    for i in free_all:
        if i >= msg_count and ok(i):
            out.append(i)
    for i in free_all:
        if i < msg_count and ok(i) and i not in used_cells:
            out.append(i)
    if len(out) < nglyphs and reuse_unused:
        cjk_codes = set()
        for k, v in charmap.items():
            if isinstance(v, str) and len(v) == 1 and is_cjk(v):
                cjk_codes.add(int(k))
        for i in range(cells):
            if 301 + i in cjk_codes and ok(i):
                out.append(i)
    # dedupe preserving order
    seen, uniq = set(), []
    for i in out:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    if len(uniq) < nglyphs:
        raise SystemExit("banco %s: solo %d celdas reutilizables < %d"
                         % (stem, len(uniq), nglyphs))
    return uniq[:nglyphs]


# --------------------------------------------------------------------------
# patch of a bank
# --------------------------------------------------------------------------
def fnv64(data: bytes) -> int:
    h = 1469598103934665603
    for b in data:
        h ^= b
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def _ref_base_images():
    """32x32 images of the verified bases of `005` (style fallback)."""
    p = REPO / "extract" / "f0" / "d1_ud1_000A4000_005.aif"
    if not p.is_file():
        return {}
    _, _, rgba = aif_edit.decode_rgba(p.read_bytes())
    return {ch: cell_image(rgba, 768, 768, idx) for ch, idx in REF_005.items()}


def patch_bank(stem, bases_override, outdir, change_count, glyphs, reuse_unused,
               ref_bases=None):
    aif_path = REPO / "extract" / "f0" / (stem + ".aif")
    msg_path = REPO / "extract" / "f0" / (stem + ".msg")
    aif_bytes = aif_path.read_bytes()
    msg = A.Msg(msg_path.read_bytes())
    width, height, rgba = aif_edit.decode_rgba(aif_bytes)
    cols = width // CELL
    cells = cols * (height // CELL)

    ref_rgba = aif_edit.decode_rgba(
        (REPO / "extract" / "f0" / "d1_ud1_000A4000_005.aif").read_bytes())[2]
    ref_desc = {ch: descriptor(ref_rgba, 768, 768, c) for ch, c in REF_005.items()}

    cmap_path = REPO / "mod" / "translation" / "charmaps" / (stem + ".json")
    charmap = json.loads(cmap_path.read_text(encoding="utf-8"))

    # bases needed for the requested glyphs
    needed = set()
    for ch in glyphs:
        if ch in ROTATE:
            needed.add(ROTATE[ch])
        else:
            needed.add(ACCENT[ch][1])

    override = dict(bases_override.get(stem, {}))
    if stem == "d1_ud1_000A4000_005":
        override = {**REF_005, **override}
    bases, missing = localize_bases(stem, width, height, rgba, cells, override,
                                    ref_desc, needed)

    # style fallback for missing bases: image from `005` (same 32x32)
    fallback_img = {}
    if missing:
        if ref_bases is None:
            ref_bases = _ref_base_images()
        for b in missing:
            if b in ref_bases:
                fallback_img[b] = ref_bases[b]
            else:
                raise SystemExit("banco %s: sin base %r y sin fallback" % (stem, b))

    metrics_entries = (len(msg.data) - msg.metrics_off) // 2
    free_all = aif_edit.free_cells(aif_bytes)
    used = used_cells(stem)
    chosen = select_cells(stem, free_all, msg.count, cells, bases, charmap,
                          len(glyphs), reuse_unused, metrics_entries, used)

    # the metric table must have room (the hook patches the .msg in place)
    max_cell = max(chosen)
    if msg.metrics_off + 2 * (max_cell + 1) > len(msg.data):
        raise SystemExit("banco %s: tabla de metricas sin hueco para celda %d"
                         % (stem, max_cell))
    free_all = set(free_all)

    base_imgs = {ch: cell_image(rgba, width, height, idx)
                 for ch, idx in bases.items()}

    # inverse of the charmap (for the metric of bases taken from `005`)
    inv_all = {}
    for k, v in charmap.items():
        if isinstance(v, str) and len(v) == 1:
            inv_all.setdefault(v, int(k) - 301)

    ed = aif_edit.AifEditor(aif_bytes)
    plan = []
    for j, ch in enumerate(glyphs):
        idx = chosen[j]
        code = 301 + idx
        row, col = divmod(idx, cols)
        if ch in ROTATE:
            src = ROTATE[ch]
            img = A.rotate_180(base_imgs.get(src, fallback_img.get(src)))
        else:
            kind, src = ACCENT[ch]
            base = base_imgs.get(src, fallback_img.get(src))
            img = A.compose(base, kind, src)
        ed.write_cell_rgba(row, col, img.tobytes())
        # metric: the base's; if the base is from another bank (image from `005`),
        # it is read from an equivalent local letter for the advance.
        src_cell = bases.get(src)
        from_ref = src_cell is None
        if from_ref:
            src_cell = 0xFFFF
            for alt in (src.upper(), "a", "e", "n", "o", "i", "l"):
                if alt in bases:
                    src_cell = bases[alt]
                    break
                if alt in inv_all:
                    src_cell = inv_all[alt]
                    break
        metric = msg.metric(src_cell) if src_cell != 0xFFFF else 0
        msg.set_metric(idx, metric)
        plan.append({"char": ch, "code": code, "cell": idx, "row": row,
                     "col": col, "base": src, "base_cell": src_cell,
                     "from_ref": from_ref, "metric": metric})

    patched_aif = ed.to_bytes()
    assert len(patched_aif) == len(aif_bytes), "el AIF no debe cambiar de tamano"
    patched_msg = msg.to_bytes()
    assert len(patched_msg) == len(msg_path.read_bytes()), \
        "el .msg no debe cambiar de tamano"

    # -- validation 1: DXT wrapper round-trip (tiling + byte-swap) --
    orig_ed = aif_edit.AifEditor(aif_bytes)
    if not (orig_ed.to_bytes() == aif_bytes and orig_ed.verify_wrapper()):
        raise SystemExit("banco %s: round-trip del envoltorio DXT FALLO" % stem)

    # -- validation 2: the bytes that change fall only in the new cells --
    orig_raw = aif_edit.AifEditor(aif_bytes).raw
    allowed = set()
    for idx in {p["cell"] for p in plan}:
        r0, c0 = divmod(idx, cols)
        for by4 in range(8):
            for bx4 in range(8):
                off = aif_mod.tiled_offset(c0 * 8 + bx4, r0 * 8 + by4,
                                           ed.tw, ed.block_bytes) * ed.block_bytes
                allowed.update(range(off, off + ed.block_bytes))
    diffs = [i for i in range(len(orig_raw)) if orig_raw[i] != ed.raw[i]]
    outside = [d for d in diffs if d not in allowed]
    if outside:
        raise SystemExit("banco %s: %d bytes fuera de las celdas nuevas"
                         % (stem, len(outside)))

    new_count = msg.count
    if change_count:
        new_count = max(msg.count, max(p["cell"] for p in plan) + 1)
        struct.pack_into(">I", msg.data, 0x34, new_count)
        struct.pack_into(">I", msg.data, 0x54, new_count)
        patched_msg = msg.to_bytes()

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / (stem + "_accents.aif")).write_bytes(patched_aif)
    (outdir / (stem + "_accents.msg")).write_bytes(patched_msg)

    # DXT blocks of each glyph, in file order (tiled + swap), for the runtime
    edp = aif_edit.AifEditor(patched_aif)
    for p in plan:
        r0, c0 = divmod(p["cell"], cols)
        blocks = bytearray()
        for gy in range(8):
            for gx in range(8):
                off = aif_mod.tiled_offset(c0 * 8 + gx, r0 * 8 + gy,
                                           edp.tw, edp.block_bytes) * edp.block_bytes
                blocks += edp.raw[off:off + edp.block_bytes]
        p["blocks"] = bytes(blocks)

    meta = {
        "stem": stem,
        "aif_len": len(aif_bytes),
        "aif_fnv": fnv64(aif_bytes),
        "width": width,
        "height": height,
        "format": aif_mod.AifImage(aif_bytes).format,
        "ident": struct.unpack_from(">I", aif_bytes, 0x20)[0],
        "tiled_width": ed.tw,
        "pixels_off": aif_mod.AifImage(aif_bytes).data_offset,
        "element_bytes": ed.block_bytes,
        "count": msg.count,
        "new_count": new_count,
        "total": struct.unpack_from(">I", msg.data, 0x30)[0],
        "atlas_w": struct.unpack_from(">I", msg.data, 0x60)[0],
        "atlas_h": struct.unpack_from(">I", msg.data, 0x64)[0],
        "metrics_off": msg.metrics_off,
        "bases": bases,
        "missing_bases": missing,
        "reused": [i for i in chosen if i not in free_all],
        "glyphs": plan,
    }
    return meta, patched_aif, patched_msg


# --------------------------------------------------------------------------
# runtime bin
# --------------------------------------------------------------------------
def write_runtime_bin(path, metas):
    """Format:
        u32 magic 'IUA1'; u32 n;
        n x {
          u32 aif_len,width,height,format,ident,tiled_width,pixels_off,
              element_bytes,total,count,atlas_w,atlas_h;
          u64 aif_fnv;
          u32 nglyphs;
          nglyphs x { u16 cell, u16 base_cell, u16 metric, u16 pad, u8 blocks[1024] }
        }
    """
    with open(path, "wb") as fh:
        fh.write(struct.pack("<II", RT_MAGIC, len(metas)))
        for m in metas:
            fh.write(struct.pack("<IIIIIIIIIIII",
                                 m["aif_len"], m["width"], m["height"], m["format"],
                                 m["ident"], m["tiled_width"], m["pixels_off"],
                                 m["element_bytes"], m["total"], m["count"],
                                 m["atlas_w"], m["atlas_h"]))
            fh.write(struct.pack("<Q", m["aif_fnv"]))
            fh.write(struct.pack("<I", len(m["glyphs"])))
            for g in m["glyphs"]:
                bc = g["base_cell"] if g["base_cell"] is not None else 0xFFFF
                fh.write(struct.pack("<HHHH", g["cell"], bc, g["metric"], 0))
                assert len(g["blocks"]) == 1024
                fh.write(g["blocks"])
    print("runtime bin -> %s (%d bancos, %.1f KiB)"
          % (path, len(metas), path.stat().st_size / 1024.0))


# --------------------------------------------------------------------------
# review montage
# --------------------------------------------------------------------------
def review_montage(stem, metas_map, outdir):
    m = metas_map[stem]
    aif = (outdir / (stem + "_accents.aif")).read_bytes()
    width, height, rgba = aif_edit.decode_rgba(aif)
    cols = width // CELL
    src = Image.frombytes("RGBA", (width, height), rgba)
    S = 3
    n = len(m["glyphs"])
    canvas = Image.new("RGBA", (n * (CELL * S + 6) + 8, CELL * S + 40), (20, 20, 20, 255))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(canvas)
    for j, g in enumerate(m["glyphs"]):
        r, c = divmod(g["cell"], cols)
        cell = src.crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL)) \
                  .resize((CELL * S, CELL * S), Image.NEAREST)
        x = 4 + j * (CELL * S + 6)
        canvas.alpha_composite(cell, (x, 4))
        dr.text((x + 1, 4 + CELL * S + 2), "%s=%d" % (g["char"], g["code"]),
                fill=(255, 255, 0, 255))
    canvas.save(outdir / (stem + "_accents_row.png"))


# --------------------------------------------------------------------------
# glyphs needed per bank (from es.json + parts)
# --------------------------------------------------------------------------
def needed_from_es(paths):
    accent = set(NEW_GLYPHS)
    need = {}
    for f in paths:
        try:
            data = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for it in data.get("strings", []):
            stem, text = it.get("stem"), it.get("es") or ""
            if not stem:
                continue
            s = set(c for c in text if c in accent)
            if s:
                need.setdefault(stem, set()).update(s)
    return {k: sorted(v) for k, v in need.items()}


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def survey_stems(disc):
    stem = "d1" if disc == "d1" else disc
    import subprocess
    out = subprocess.run([sys.executable, "-X", "utf8", str(HERE / "aif_edit.py"),
                          "survey", "--dir", str(REPO / "extract" / "f0"),
                          "--need", "1"], capture_output=True, text=True)
    stems = []
    for line in out.stdout.splitlines():
        p = line.split()
        if len(p) == 5 and p[0].startswith(stem + "_") and int(p[4]) >= 1:
            stems.append(p[0])
    return stems


def main(argv=None):
    ap = argparse.ArgumentParser(description="WS1: acentos por banco.")
    ap.add_argument("--stems", nargs="*", default=None,
                    help="bancos concretos (stems)")
    ap.add_argument("--auto", action="store_true",
                    help="todos los bancos del disco con >=1 celda libre")
    ap.add_argument("--disc", default="d1", choices=["d1", "d2"])
    ap.add_argument("--need-from-es", action="store_true",
                    help="solo los glifos que cada banco necesita (es.json+parts)")
    ap.add_argument("--es", default=None, help="es.json principal")
    ap.add_argument("--all", action="store_true",
                    help="intenta los 16 glifos en todos los bancos")
    ap.add_argument("--no-reuse-unused", action="store_true",
                    help="no reutilizar celdas kana/kanji")
    ap.add_argument("--out", default=str(REPO / "extract" / "f2" / "accents"))
    ap.add_argument("--bases-json", default=None,
                    help="overrides {stem:{char:cell}}")
    ap.add_argument("--update-charmaps", action="store_true",
                    help="anade los glifos al charmap del banco")
    ap.add_argument("--change-count", action="store_true",
                    help="actualiza count/count2 (por defecto NO, para no cambiar la huella)")
    ap.add_argument("--sync-f0", action="store_true",
                    help="escribe las metricas parcheadas en extract/f0/<stem>.msg "
                         "(para que build_es_codes mida bien el avance; NO toca count)")
    ap.add_argument("--runtime-bin", default=str(REPO / "mod" / "translation" / "accents_atlas.bin"))
    ap.add_argument("--manifest", default=str(REPO / "mod" / "translation" / "accents_manifest.json"))
    args = ap.parse_args(argv)

    outdir = Path(args.out)
    overrides = {}
    if args.bases_json and Path(args.bases_json).is_file():
        overrides = json.loads(Path(args.bases_json).read_text(encoding="utf-8"))

    # glyphs per bank
    glyphs_by_stem = {}
    if args.need_from_es:
        es = Path(args.es) if args.es else (REPO / "mod" / "translation" / "es.json")
        files = [es] if es.is_file() else []
        parts = REPO / "mod" / "translation" / "parts"
        if parts.is_dir():
            files += sorted(parts.glob("*.json"))
        glyphs_by_stem = needed_from_es(files)
    if args.all:
        for stem in (args.stems or []):
            glyphs_by_stem[stem] = list(NEW_GLYPHS)

    stems = list(args.stems or [])
    if args.auto:
        stems += survey_stems(args.disc)
    if args.need_from_es:
        stems += list(glyphs_by_stem.keys())
    stems = sorted(set(stems))
    if not stems:
        ap.error("indica --stems, --auto o --need-from-es")

    ref_bases = _ref_base_images()
    metas, started = [], 0
    for stem in stems:
        glyphs = glyphs_by_stem.get(stem) if args.need_from_es or args.all else None
        if glyphs is None:
            glyphs = list(NEW_GLYPHS)
        if not glyphs:
            print("  - %s: sin glifos necesarios" % stem)
            continue
        try:
            meta, patched_aif, patched_msg = patch_bank(
                stem, overrides, outdir, args.change_count, glyphs,
                not args.no_reuse_unused, ref_bases)
        except SystemExit as exc:
            print("  ! %s: %s" % (stem, exc))
            continue
        metas.append(meta)
        started += 1
        review_montage(stem, {stem: meta}, outdir)
        if args.sync_f0:
            (REPO / "extract" / "f0" / (stem + ".msg")).write_bytes(patched_msg)
        if args.update_charmaps:
            cm_path = REPO / "mod" / "translation" / "charmaps" / (stem + ".json")
            if cm_path.is_file():
                cm = json.loads(cm_path.read_text(encoding="utf-8"))
                for g in meta["glyphs"]:
                    cm[str(g["code"])] = g["char"]
                # compact single-line format (same as build_charmaps.py)
                cm_path.write_text(json.dumps(cm, ensure_ascii=False),
                                   encoding="utf-8")
        reused = len(meta["reused"])
        print("  + %-28s glifos=%2d bases=%s%s" % (
            stem, len(meta["glyphs"]),
            ",".join("%s:%d" % (k, v) for k, v in sorted(meta["bases"].items())),
            (" reutiliza=%d" % reused) if reused else ""))

    if not metas:
        raise SystemExit("no se ha parcheado ningun banco")

    rt = Path(args.runtime_bin)
    rt.parent.mkdir(parents=True, exist_ok=True)
    write_runtime_bin(rt, metas)

    # manifest (without the binary blocks)
    manifest = {"bancos": []}
    for m in metas:
        manifest["bancos"].append({
            "stem": m["stem"], "aif_len": m["aif_len"],
            "aif_fnv": "%016x" % m["aif_fnv"],
            "atlas": [m["width"], m["height"]], "format": m["format"],
            "ident": m["ident"], "tiled_width": m["tiled_width"],
            "pixels_off": m["pixels_off"], "element_bytes": m["element_bytes"],
            "count": m["count"], "new_count": m["new_count"],
            "total": m["total"], "atlas_w": m["atlas_w"], "atlas_h": m["atlas_h"],
            "bases": m["bases"],
            "missing_bases": m["missing_bases"],
            "glyphs": [{"char": g["char"], "code": g["code"], "cell": g["cell"],
                        "base": g["base"], "base_cell": g["base_cell"],
                        "from_ref": g["from_ref"], "metric": g["metric"]}
                       for g in m["glyphs"]],
        })
    man = Path(args.manifest)
    man.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nbancos tratados: %d" % started)
    print("manifiesto     : %s" % man)
    print("runtime bin    : %s" % rt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
