# mod/ — Spanish (Castilian) translation mod

Self-contained translation mod for the
[`doc-haz/infinite-undiscovery-recomp`](https://github.com/doc-haz/infinite-undiscovery-recomp)
recompilation. Applied **entirely at runtime** — no original game assets are
modified.

## Contents

```
mod/
├─ recomp/        C++ hooks applied on top of the recomp + build glue
│  ├─ translation_es.h      text hook (message parser override)
│  ├─ ui_textures_es.h      texture replacement by signature + ASF-load hook
│  ├─ accents_es.h          per-bank accent atlas patch
│  ├─ controller_es.h       multi-controller detection (xbox/ps5/steam)
│  ├─ translation_cvars.h   mod CVARs (es_translation, es_textures, …)
│  ├─ translation_trace.h   trace hooks (observation)
│  ├─ local-changes.patch   changes to the recomp (main.cpp / setup UI)
│  └─ build.sh, qa.sh, …    build helpers
└─ translation/   data
   ├─ parts/*.json          source translations (per bank)
   ├─ charmaps/*.json       per-bank code → character maps
   ├─ glossary.md           translation glossary
   ├─ accents_manifest.json per-bank accent metadata
   ├─ es_catalog.bin        built binary catalog  (runtime)
   ├─ accents_atlas.bin     built accent patches   (runtime)
   ├─ ui_textures.txt       texture manifest       (runtime)
   └─ *.aif                 translated textures    (runtime)
```

> `es_catalog.bin`, `accents_atlas.bin`, `ui_textures.txt` and the `*.aif`
> textures are **generated** by the pipeline (see `../docs/TOOLS.md`); they are
> git-ignored and shipped in the release build.

## Build / install

```bash
# 1) apply the local changes to the recomp project
cd <recomp>
git apply /path/to/mod/recomp/local-changes.patch

# 2) copy the mod headers into the recomp src/
cp /path/to/mod/recomp/*.h src/

# 3) build (the wrapper forces main.cpp to be recompiled)
bash /path/to/mod/recomp/build.sh
```

The runtime looks for the data in `translation/` **relative to the game's
working directory** (`run/`), so deploy `mod/translation/` → `run/translation/`.

## Options

Configured from the recomp's own UI (Asset Setup Wizard / Content Profile
Manager, F10) and via CVARs; see `../docs/re/launcher.md`.

| CVAR | Default | Effect |
|---|---|---|
| `es_translation` | `true` | Spanish text |
| `es_textures` | `true` | Spanish bitmap labels |
| `es_controller` | `auto` | controller type: `auto`/`xbox`/`ps5`/`steam` |
| `es_catalog` | `translation/es_catalog.bin` | text catalog path |
| `es_textures_manifest` | `translation/ui_textures.txt` | texture manifest path |

See the repository root `README.md` for the full overview and
`docs/TOOLS.md` for the build pipeline.
