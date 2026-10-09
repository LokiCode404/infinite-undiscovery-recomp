# `mod/recomp/` — cambios locales sobre el recomp de ReXGlue

El recomp vive en `extract/f2/recomp/` (ignorado por git: son assets + build).
Aquí se versionan **los cambios locales** para poder reproducir el mod desde cero.

## Ficheros

| Fichero | Para qué |
|---|---|
| `local-changes.patch` | parche sobre el proyecto recomp (hashes de DLL, `src/main.cpp` con CVARs e `src/portable_setup.cpp/.h` + `src/setup_strings.inc` con el soporte de mods) |
| `translation_es.h` | hook de **traducción** ES en runtime (texto) |
| `translation_cvars.h` | **CVARs** del mod (`es_translation`, `es_textures`, `es_catalog`, `es_controller`, …) |
| `accents_es.h` | parche de **acentos** por banco (usa `translation/accents_atlas.bin`) |
| `ui_textures_es.h` | sustitución de **texturas** por firma (manifiesto IUT2 con variantes por mando) |
| `controller_es.h` | **detección del mando** (auto por SDL/`runtime.log`) para iconos |
| `zone_names_es.h` + `zone_names.h` | traducción en runtime de la **tabla de nombres de zona** del `.exe` |
| `run_es_test.sh` | ejecuta el juego con el hook y muestra el log |
| `build.sh` | compila copiando los headers y forzando recompilar `main.cpp` |

Opciones del mod: dentro de la UI del recomp (Asset Setup / Content Profile
Manager) y por CVARs; ver `docs/re/launcher.md`.

## Puesta en marcha (desde un `extract/f2/recomp` limpio)

```bash
# 1) aplicar los cambios locales al proyecto recomp
cd extract/f2/recomp
git apply /ruta/a/mod/recomp/local-changes.patch      # hashes + includes + CVARs en main.cpp

# 2) copiar los headers del mod a src/
cp /ruta/a/mod/recomp/translation_es.h    src/
cp /ruta/a/mod/recomp/translation_cvars.h src/
cp /ruta/a/mod/recomp/accents_es.h        src/
cp /ruta/a/mod/recomp/ui_textures_es.h    src/
cp /ruta/a/mod/recomp/controller_es.h     src/
cp /ruta/a/mod/recomp/zone_names_es.h     src/
cp /ruta/a/mod/recomp/zone_names.h        src/

# 3) compilar (usa el wrapper: fuerza recompilar main.cpp)
bash mod/recomp/build.sh

# 4) prueba en vivo del hook
bash mod/recomp/run_es_test.sh 120
```

> Si `extract/f2/recomp` no es un repo git, aplicar el parche a mano: cambiar los
> dos hashes de `cmake/verify_rexglue_dlls.cmake` y añadir los `#include` del mod
> + `IU_TRANSLATION_DEFINE_CVARS();` en `src/main.cpp`.

Ver `docs/re/runtime-hook.md` para el diseño del hook.
