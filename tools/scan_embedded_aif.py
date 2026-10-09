#!/usr/bin/env python3
"""scan_embedded_aif.py -- searches the main menu textures by CONTENT.

Walks ALL the files extracted from both discs, locates each `AIF ` signature
(also inside ASF/MRON/BIN containers), decodes the bitmap and
runs OCR (tesseract) looking for the title labels. Saves the PNGs of the
candidates and a report.
"""
from __future__ import annotations
import subprocess, sys, struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"))
import aif as aif_mod
from PIL import Image

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TMP = REPO / "extract" / "f2" / "re_analysis" / "_scan_emb_tmp.png"
OUT = REPO / "extract" / "f2" / "ui_es" / "emb_scan"
WORDS = ["new game", "newgame", "continue", "option", "xbox", "press start",
         "load game", "loadgame", "infinity", "easy", "normal", "very hard",
         "hard", "icon"]


def ocr(img):
    img.save(TMP)
    out = subprocess.run([TESS, str(TMP), "stdout", "-l", "eng", "--psm", "11"],
                         capture_output=True, encoding="utf-8", errors="replace")
    return (out.stdout or "").lower()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    n_files = n_aif = n_hit = 0
    for disc in ("all_d1ud1", "all_d1ud2"):
        base = REPO / "extract" / "f2" / disc
        for fn in sorted(base.iterdir()):
            if not fn.is_file():
                continue
            ext = fn.suffix.lower()
            if ext not in (".asf", ".mron", ".bin", ".aaf", ".acf", ".aif"):
                continue
            try:
                data = fn.read_bytes()
            except Exception:
                continue
            n_files += 1
            pos = 0
            while True:
                i = data.find(b"AIF ", pos)
                if i < 0:
                    break
                pos = i + 1
                try:
                    at = aif_mod.AifImage(data[i:], base=i)
                except Exception:
                    continue
                if at.width < 32 or at.height < 12 or at.width > 2048 or at.height > 2048:
                    continue
                if at.format != 0x48:  # only A8R8G8B8 (sharp UI labels)
                    continue
                n_aif += 1
                try:
                    rgba = at.to_rgba()
                except Exception:
                    continue
                im = Image.frombytes("RGBA", (at.width, at.height), rgba)
                for pol in ("black", "white"):
                    bg = Image.new("RGB", im.size, (0, 0, 0) if pol == "black" else (255, 255, 255))
                    bg.paste(im, (0, 0), im)
                    if max(im.size) < 800:
                        bg = bg.resize((im.width * 2, im.height * 2), Image.LANCZOS)
                    txt = ocr(bg)
                    for w in WORDS:
                        if w in txt:
                            n_hit += 1
                            name = "%s_%s_%08X_%s.png" % (disc, fn.stem, i, pol)
                            bg.save(OUT / name)
                            line = "HIT %-55s off=%08X %dx%d %s word=%r" % (
                                fn.name, i, at.width, at.height, pol, w)
                            print(line, flush=True)
                            report.append(line)
                            break
                    else:
                        continue
                    break
            if n_files % 200 == 0:
                print("  ... files=%d aif=%d hits=%d" % (n_files, n_aif, n_hit), flush=True)
    (REPO / "extract" / "f2" / "re_analysis" / "emb_scan.out").write_text(
        "\n".join(report), encoding="utf-8")
    print("done files=%d embedded_aif=%d hits=%d" % (n_files, n_aif, n_hit))


if __name__ == "__main__":
    main()
