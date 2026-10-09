#!/bin/bash
# build.sh -- builds the recomp with the mod, ENSURING main.cpp is recompiled.
#
# Reason: the project does not propagate header dependencies to the ninja
# depfile, so editing `translation_es.h` (or any mod header) does NOT
# recompile main.cpp and the binary becomes STALE (ninja only relinks).  This
# wrapper copies the mod headers and `touch`es main.cpp before building.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
RECOMP="$REPO/extract/f2/recomp"
cp -f "$HERE/translation_es.h"    "$RECOMP/src/translation_es.h"
cp -f "$HERE/translation_cvars.h" "$RECOMP/src/translation_cvars.h"
cp -f "$HERE/zone_names_es.h"     "$RECOMP/src/zone_names_es.h"
cp -f "$HERE/zone_names.h"        "$RECOMP/src/zone_names.h"
cp -f "$HERE/ui_textures_es.h"    "$RECOMP/src/ui_textures_es.h"
cp -f "$HERE/controller_es.h"     "$RECOMP/src/controller_es.h"
cp -f "$HERE/accents_es.h"        "$RECOMP/src/accents_es.h"
touch "$RECOMP/src/main.cpp"
cd "$REPO" || exit 1
cmd //c "extract\\f2\\build_recomp.bat"
