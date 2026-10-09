#!/bin/bash
# qa.sh -- QA harness: validates translation + generates catalog + builds + runs + captures.
#
# Usage: bash mod/recomp/qa.sh [seconds]
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
cd "$REPO" || exit 1

echo "===== 1) validar traduccion ====="
python tools/validate_translation.py 2>&1 | tail -N 2>/dev/null || python tools/validate_translation.py | tail -5

echo "===== 2) generar codigos + catalogo (reflow) ====="
python tools/build_es_codes.py

echo "===== 2b) texturas: render + variantes por mando + manifiesto ====="
python -X utf8 tools/ui_textures.py render --out extract/f2/ui_es
python -X utf8 tools/controller_skins.py all --out extract/f2/ui_es
python -X utf8 tools/ui_textures.py manifest --out extract/f2/ui_es --deploy extract/f2/run/translation

echo "===== 3) compilar recomp ====="
cp -f "$HERE/translation_es.h" "$REPO/extract/f2/recomp/src/translation_es.h"
cp -f "$HERE/translation_cvars.h" "$REPO/extract/f2/recomp/src/translation_cvars.h"
cp -f "$HERE/ui_textures_es.h" "$REPO/extract/f2/recomp/src/ui_textures_es.h"
touch "$REPO/extract/f2/recomp/src/main.cpp"
cmd //c "extract\\f2\\build_recomp.bat" > "$TMPDIR/iu_qa_build.log" 2>&1
echo "build exit=$?"

echo "===== 4) ejecutar + capturar ====="
bash "$REPO/extract/f2/run_capture_es.sh"
