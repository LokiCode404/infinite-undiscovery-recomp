#!/usr/bin/env python3
"""glyph_ocr.py -- proposes the character of each glyph cluster by comparing with
rendered templates from system fonts (gothic/mincho) normalized by
bounding box.

Output: extract/f2/glyphs/labels.json  {cid: {"char":..,"score":..,"top":[..]}}
"""
from __future__ import annotations
import sys, json, pickle, argparse, time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[1]
GL = REPO / "extract" / "f2" / "glyphs"

FONTS = [r"C:\Windows\Fonts\msgothic.ttc", r"C:\Windows\Fonts\YuGothM.ttc",
         r"C:\Windows\Fonts\MSMINCHO.TTF", r"C:\Windows\Fonts\meiryo.ttc"]
FONTS = [f for f in FONTS if Path(f).exists()]

NORM = 20  # descriptor size


def bbox_norm_gray(arr, thresh=8):
    """arr float grayscale 0..1 -> cropped to ink bbox and resized to NORMxNORM."""
    m = arr > (thresh / 255.0)
    ys, xs = np.where(m)
    if len(xs) == 0:
        return np.zeros((NORM, NORM), dtype=np.float32)
    sub = arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    im = Image.fromarray((sub * 255).astype(np.uint8), "L").resize((NORM, NORM),
                                                                  Image.BILINEAR)
    a = np.asarray(im, dtype=np.float32) / 255.0
    return a


def vec(a):
    v = a.reshape(-1).astype(np.float32)
    v = v - v.mean()
    n = np.linalg.norm(v)
    return v / n if n > 1e-6 else v


def render_candidate(ch, fontpath, size):
    f = ImageFont.truetype(fontpath, size)
    img = Image.new("L", (int(size * 1.6) + 8, int(size * 1.6) + 8), 0)
    dr = ImageDraw.Draw(img)
    dr.text((4, 4), ch, fill=255, font=f)
    return np.asarray(img, dtype=np.float32) / 255.0


def build_candidates(cps):
    """Returns matrix (N x d) and list of chars."""
    chars = []
    feats = []
    for cp in cps:
        ch = chr(cp)
        for fp in FONTS:
            for size in (28, 34):
                a = render_candidate(ch, fp, size)
                if a.max() < 0.5:
                    continue
                chars.append(ch)
                feats.append(vec(bbox_norm_gray(a)))
    M = np.stack(feats) if feats else np.zeros((0, NORM * NORM), np.float32)
    return chars, M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(GL / "labels.json"))
    args = ap.parse_args()

    reps = pickle.load(open(GL / "reps.pkl", "rb"))

    # set of candidate codepoints
    cps = list(range(0x20, 0x7F))
    cps += list(range(0xA0, 0x100))
    cps += [0x2018, 0x2019, 0x201C, 0x201D, 0x2013, 0x2014, 0x2026, 0x2190,
            0x2191, 0x2192, 0x2193, 0x2194, 0x2195, 0x2022, 0x25CF, 0x25A0,
            0x00D7, 0x00B7, 0x00A5, 0x20AC]
    cps += list(range(0x3000, 0x3040))           # CJK punct
    cps += list(range(0x3041, 0x3097))           # hiragana
    cps += list(range(0x30A1, 0x30FB))           # katakana
    cps += list(range(0xFF01, 0xFF5F))           # fullwidth
    cps += list(range(0xFFE0, 0xFFE6))
    cps += list(range(0x4E00, 0x9FFF + 1))       # CJK unified (JIS L1/L2 incl.)
    cps = sorted(set(cps))
    print("codepoints candidatos:", len(cps), "fuentes:", [Path(f).name for f in FONTS])
    t0 = time.time()
    chars, M = build_candidates(cps)
    print("plantillas:", M.shape[0], "en %.1fs" % (time.time() - t0))

    # descriptors of the game glyphs
    G = np.zeros((len(reps), NORM * NORM), dtype=np.float32)
    for cid, raw in enumerate(reps):
        a = np.frombuffer(raw, dtype=np.uint8).reshape(32, 32, 4)[:, :, :3]
        lum = a.max(axis=2).astype(np.float32) / 255.0  # the glyph is in RGB (white)
        G[cid] = vec(bbox_norm_gray(lum))

    labels = {}
    topk = 5
    # cosine similarity
    for cid in range(len(reps)):
        g = G[cid]
        if not np.any(g):
            labels[str(cid)] = {"char": "", "score": 0.0, "top": []}
            continue
        sims = M @ g
        idx = np.argpartition(-sims, topk)[:topk]
        idx = idx[np.argsort(-sims[idx])]
        top = [{"char": chars[i], "score": round(float(sims[i]), 4)} for i in idx]
        labels[str(cid)] = {"char": top[0]["char"], "score": top[0]["score"],
                            "top": top}
        if cid % 500 == 0:
            print("  cid", cid, "score", labels[str(cid)]["score"])

    Path(args.out).write_text(json.dumps(labels, ensure_ascii=False),
                              encoding="utf-8")
    print("escrito", args.out)


if __name__ == "__main__":
    main()
