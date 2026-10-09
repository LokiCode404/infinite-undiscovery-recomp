#!/usr/bin/env bash
# run_all.sh -- end-to-end reconstruction: discs -> translation data -> patched recomp -> run/.
#
# Runs the whole pipeline (F0..F6), builds the modded recomp and deploys the
# translation so the game can be launched.  Run from the repository root.
#
#   bash run_all.sh                 # full pipeline + build + deploy
#   bash run_all.sh --no-build      # pipeline + deploy only (skip the C++ build)
#   bash run_all.sh --no-extract    # skip F0 (reuse an existing extract/f0)
#
# Requires (see docs/SETUP.md): Python 3.10+, 7-Zip, Tesseract OCR, and for the
# build: CMake/Ninja/Clang/MSVC and a from-source ReXGlue SDK.  It does NOT
# download game assets: put your legal discs in roms/ first.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

DO_EXTRACT=1
DO_BUILD=1
for a in "$@"; do
  case "$a" in
    --no-build)   DO_BUILD=0 ;;
    --no-extract) DO_EXTRACT=0 ;;
  esac
done

PY="${PY:-python}"
RUN_DIR="extract/f2/run"
DEPLOY="$RUN_DIR/translation"

step() { echo; echo "===== $* ====="; }

# ---------------------------------------------------------------- prerequisites
step "0) prerequisites"
command -v "$PY" >/dev/null 2>&1 || { echo "ERROR: Python not found (set PY=)"; exit 1; }
"$PY" -c "import PIL, numpy, cv2" 2>/dev/null || {
  echo "Missing Python deps. Run:  $PY -m pip install -r requirements.txt"; exit 1; }
if [ "$DO_EXTRACT" = 1 ] && [ ! -d roms ]; then
  echo "ERROR: put your legal discs in roms/ (Disc 1 + Disc 2) or pass --no-extract"; exit 1
fi

# ---------------------------------------------------------------- F0 extract
if [ "$DO_EXTRACT" = 1 ]; then
  step "F0) extract RMD- resources from the discs"
  "$PY" tools/extract_rmd.py --roms roms --out extract/f0
fi

step "F1) decode all .msg banks"
"$PY" tools/write_texts.py

step "F2) build per-bank charmaps"
"$PY" tools/build_charmaps.py

step "F3) add the Spanish glyphs (accents) per bank"
"$PY" tools/add_accents_banks.py --need-from-es --update-charmaps

step "F4) build the translation catalog"
"$PY" tools/build_es_codes.py

step "F6) render translated textures + manifest"
"$PY" -X utf8 tools/ui_textures.py render --out extract/f2/ui_es
"$PY" -X utf8 tools/ui_textures.py manifest --out extract/f2/ui_es --deploy "$DEPLOY"
"$PY" -X utf8 tools/ui_help_screens.py render
"$PY" -X utf8 tools/ui_textures.py manifest --out extract/f2/ui_es --deploy "$DEPLOY"

# keep the source-of-truth data in mod/translation in sync (built artifacts)
cp -f mod/translation/es_catalog.bin "$DEPLOY/es_catalog.bin" 2>/dev/null || true
cp -f mod/translation/accents_atlas.bin "$DEPLOY/accents_atlas.bin" 2>/dev/null || true

# ---------------------------------------------------------------- F5 build
if [ "$DO_BUILD" = 1 ]; then
  step "F5) build the patched recomp"
  bash mod/recomp/build.sh
  cp -f extract/f2/recomp/out/build/local/InfiniteUndiscoveryRecomp.exe "$RUN_DIR/" 2>/dev/null \
    && echo "exe deployed to $RUN_DIR" || echo "WARN: exe not found to deploy"
else
  echo; echo "(skipping the C++ build)"
fi

step "done"
echo "Translation deployed to $DEPLOY"
echo "Run:  $RUN_DIR/InfiniteUndiscoveryRecomp.exe"
