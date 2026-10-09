# Infinite Undiscovery — Spanish (Castilian) Translation

An unofficial **modding/translation** project for *Infinite Undiscovery*
(Xbox 360, 2008, tri-Ace / Square Enix) built on top of the native PC
recompilation [`doc-haz/infinite-undiscovery-recomp`](https://github.com/doc-haz/infinite-undiscovery-recomp).

> **Status:** fully playable translation. Text (71,386 messages across 81 banks)
> and all text-bearing textures are translated and applied **at runtime** via
> hooks — the original assets are never modified.

**New here?** Run `powershell -ExecutionPolicy Bypass -File bootstrap.ps1` and
follow **[`docs/SETUP.md`](docs/SETUP.md)** to reproduce the whole project on a
clean machine. To rebuild everything in one command: **`bash run_all.sh`**
(pipeline → build → deploy).

To publish your own **fork** and open a **pull request** upstream, see
**[`docs/FORK.md`](docs/FORK.md)**.

## Principles

1. **No original game assets are modified** — the mod is a runtime *hook*.
2. **Data-driven:** translations live in `mod/translation/` (per-bank parts + a
   binary catalog consumed by the hook).
3. **No game assets in the repository** (see `.gitignore`).

## Features

- **Text translation** — menus, dialogue, descriptions, credits, tutorials, etc.
  The message parser (`sub_826D52C0`) is hooked and the resolved text pointer is
  replaced with Spanish glyph codes in guest memory.
- **Texture translation** — bitmap labels (UI atlas, main menu, GAME OVER,
  Now Loading, Reload, the 51 CAMP help screens) are replaced by signature at
  runtime.
- **Extended fonts / accents** — `á é í ó ú ü ñ Á É Í Ó Ú Ü Ñ ¿ ¡` are added to
  each message bank's atlas (per-bank), so Spanish punctuation and accents
  render correctly.
- **In-game options** — translation can be toggled from the recomp's own UI
  (Asset Setup Wizard / Content Profile Manager, `F10`) and via CVARs.

## Repository layout

```
├─ mod/             THE translation mod (self-contained — see mod/README.md)
│  ├─ recomp/       C++ hooks applied on top of the recomp + local-changes.patch
│  ├─ translation/  data (parts, charmaps, glossary, manifests, built catalog/textures)
│  └─ audio/        audio inventory + dialogue-to-dub list (fan-dub) — see docs/AUDIO_DUB.md
├─ tools/           offline pipeline (decode, atlas patch, texture render) — see docs/TOOLS.md
├─ docs/            RE & design docs (docs/re/), TOOLS.md, AUDIO_DUB.md, PLAN.md, PR.md
├─ roms/            User's legal disc copies (Disc 1 / Disc 2). Git-ignored
├─ extract/         Analysis dumps (RMD-, atlas, messages). Git-ignored
└─ dist/            Packaged output. Git-ignored
```

## How the mod is applied

The recomp lives in `extract/f2/recomp/` (git-ignored: assets + build). Only the
**local changes** are versioned here so the mod can be reproduced from scratch:

```bash
# 1) apply the local changes to the recomp project
cd extract/f2/recomp
git apply /path/to/mod/recomp/local-changes.patch

# 2) copy the mod headers into src/
cp /path/to/mod/recomp/translation_es.h      src/
cp /path/to/mod/recomp/translation_cvars.h   src/
cp /path/to/mod/recomp/zone_names_es.h       src/
cp /path/to/mod/recomp/zone_names.h          src/
cp /path/to/mod/recomp/accents_es.h          src/
cp /path/to/mod/recomp/ui_textures_es.h      src/
cp /path/to/mod/recomp/controller_es.h       src/

# 3) build (the wrapper forces main.cpp to be recompiled)
bash mod/recomp/build.sh
```

The mod headers:

| File | Purpose |
|---|---|
| `translation_es.h` | runtime Spanish text hook |
| `translation_cvars.h` | mod CVARs (`es_translation`, `es_textures`, `es_catalog`, …) |
| `accents_es.h` | per-bank accent atlas patch (consumes `translation/accents_atlas.bin`) |
| `ui_textures_es.h` | signature-based texture replacement |
| `controller_es.h` | per-controller button icons (auto/xbox/ps5/steam) |
| `zone_names_es.h` + `zone_names.h` | runtime zone-name table (MapName) translation |
| `build.sh` | copies headers and forces `main.cpp` recompilation |

## Options

The mod is configured from the recomp's own UI (Asset Setup Wizard / Content
Profile Manager) and through CVARs. See `docs/re/launcher.md`.

| CVAR | Default | Effect |
|---|---|---|
| `es_translation` | `true` | Spanish text |
| `es_textures` | `true` | Spanish bitmap labels |
| `es_catalog` | `translation/es_catalog.bin` | text catalog path |
| `es_textures_manifest` | `translation/ui_textures.txt` | texture manifest path |
| `es_controller` | `auto` | button icons: `auto`/`xbox`/`ps5`/`steam` |

Priority: `CVAR > environment > setup wizard > default`, so legacy scripts using
`IU_ES=1 …` keep working.

## How it was done — research & translation process

This section documents the real steps that led to the full translation, so
others can reuse the method to translate the game into **other languages**.

### 1. Isolate the game resources
Each disc image (`ud1.bin`/`ud2.bin`) packs the assets into `RMD-` entries.
`tools/extract_rmd.py` extracts each one (decompressing `SLZ` blocks) and splits
its payload into `<label>.aif` (the font atlas) and `<label>.msg` (the message
data), plus a manifest.

### 2. Reverse-engineer the message format
The message subsystem was located with **Ghidra** (community scripts in
`tools/vendor/`) and the recomp's generated code. The key functions are the
message parser `sub_826D52C0` (id → text), the decoder `sub_826D43F8` and the
charmap loader `sub_826D3268`.

Findings:
- The `.msg` is a record table plus a code pool.
- Codes `0x4000–0x4019` are **controls** (line breaks, button prompts, …);
  line breaks are `0x4000` (menus) and `0x4005` (dialogue).
- A glyph is `code − 301` (its cell index in the atlas).

`tools/decode_messages.py` (`MsgBank`) decodes with an **exact round-trip**
(validated on 71,386 messages). A naive flat decoder truncates control payloads,
so the structured decoder was required.

### 3. Identify the glyphs (per-bank charmap)
Every `RMD-` has its own font atlas, so a `code → character` map must be built
**per bank**. `tools/build_charmaps.py` (with `tools/glyph_ocr.py` /
`tools/atlas_glyphs.py`) identifies each glyph by OCR + template matching, and
picks the **most-used variant** of each character (the atlas stores several
copies — normal/bold/small — and the first is often the bold one).

### 4. Translate the text
71,386 messages across **81 banks** were decoded and translated using a
consistent glossary (`mod/translation/glossary.md`), stored as per-bank
`mod/translation/parts/*.json`. `tools/build_es_codes.py` merges the parts, applies
**reflow** (re-emitting the control codes so lines fit the original boxes) and
writes the binary `mod/translation/es_catalog.bin`. `tools/validate_translation.py`
flags any line wider/taller than the English original.

### 5. Apply the text at runtime
`mod/recomp/translation_es.h` overrides the message parser `sub_826D52C0`,
identifies the bank by a **fingerprint of the loaded `.msg` header** (so the
mapping is path-independent) and injects Spanish codes into guest memory,
cached per `(fingerprint, id)`. No asset is modified.

### 6. Translate the textures
Some UI labels are **bitmaps**, not text. `tools/scan_embedded_aif.py` /
`tools/scan_aif_text.py` inventory every AIF (loose and embedded inside
`ASF`/`MRON` containers, OCR'd with Tesseract); `tools/ui_textures.py` renders
the translated labels; `mod/recomp/ui_textures_es.h` replaces them **by
signature** at runtime. Two hard cases:
- **Main menu** — its labels are AIFs *embedded in the title ASF*, loaded and
  uploaded in one go, so a late scanner misses them. They are substituted at
  **ASF load time** (`OnAif` on `sub_821EF618`/`sub_821EF678`) *before* the
  texture is created.
- **CAMP help screens** (1280×720, baked text) — `tools/ui_help_screens.py`
  removes the original text with **inpainting** and repaints the Spanish.

### 7. Extend the fonts (accents)
The English font lacks `á é í ó ú ü ñ ¿ ¡`. `tools/add_accents_banks.py` adds
those glyphs **per bank** into free cells and patches the `.msg` metrics
*without* changing the header (which keeps the bank fingerprint — and therefore
the catalog — stable). `mod/recomp/accents_es.h` applies the patch at load time
from `translation/accents_atlas.bin`.

### 8. Options & packaging
The mod is exposed through the recomp's own UI (Asset Setup Wizard / Content
Profile Manager) and as CVARs (`mod/recomp/translation_cvars.h`), so it can be
toggled without rebuilding.

### Tooling used
Ghidra (with community scripts), Capstone, Python + Pillow, Tesseract OCR,
OpenCV (inpainting), 7-Zip, and the recomp / ReXGlue toolchain.

### Reusing this for another language
The runtime hooks are **language-agnostic**. To translate into another language:
replace `mod/translation/parts/*.json` with your language, keep the per-bank
charmaps, rebuild `es_catalog.bin`, and re-render the textures. If your language
uses glyphs the game's fonts lack (accents, non-Latin scripts), extend the fonts
with the same per-bank approach as step 7. Technical details live in `docs/re/`;
a **full reference of every pipeline script** is in [`docs/TOOLS.md`](docs/TOOLS.md).

## Audio assets & fan-dub (dubbing into other languages)

The same runtime-hook philosophy applies to **audio**: the game's voice lines
can be re-recorded in another language and substituted at runtime, without
modifying `ud1.bin`/`ud2.bin`. Full technical guide:
**[`docs/AUDIO_DUB.md`](docs/AUDIO_DUB.md)**; deep RE in
[`docs/re/audio-dub.md`](docs/re/audio-dub.md).

### Where the audio lives
- **Voice + SFX** are `SOND` resources = **`AAC `** containers (tri-Ace's own
  format, *not* MPEG-AAC) inside the NORM/MRON archives of `ud1.bin`/`ud2.bin`.
  The entry names are the **original `.wav` filenames**
  (`AYA_SP_0001.wav`, `CAPEL_1_FV_0061.wav`).
- **Music** is *not* in `SOND`: it sits in the gaps between archives as bare
  `AAC ` runs (79 tracks / 189 min), so a dialogue-only dub never touches it.
- Corpus: **22,601 sounds** across 1,113 `SOND` banks (Disc 1 + Disc 2).

### Codec
Every sound is **XMA2** (Xbox 360's hardware codec; a `WAVE` chunk with format
tag `0x0166`, `0x8000`-byte blocks). Decoders: ffmpeg, vgmstream, and the
recomp's own software `XmaDecoder`. **No free XMA2 encoder exists** — only
Microsoft's GDK/XDK (`xma2encode.exe`, XACT).

### Which lines are dialogue — and which character
Dialogue is identified by the source `.wav` name:

| Marker | Meaning | Dub? |
|---|---|---|
| `_SP_` | story/cutscene **speech** | **yes (main target)** |
| `_FV_` | **field voice** (in-world quips) | **yes** |
| `BTL` / `BATTLE` / `SITU` | **battle / situational** lines | **yes** |
| `_WALK_ _RUN_ _FALL_ _HIT_ …`, `SYSTEM_…`, `CAMP_…`, `GMK_…` | foley / UI SFX | no |

**Dub target: 3,149 voice lines ≈ 36.9 minutes.** Speakers: enemies (ENM) 519,
soldiers 469, female 222, male 216, mercenaries 182, **Capel 143**, NPCs 113,
**Leonid 84**, **Aya 48**, **Ed 47**, plus the named cast (Sigmund, Kiriya,
Miruce, Roca, Yugene, Sarande, Venbat, Vika, Dmitri, Grymon…). The exhaustive
list is **[`mod/audio/dialogue_to_dub.csv`](mod/audio/dialogue_to_dub.csv)**
(plus `audio_inventory.csv` for all 22,601 sounds and `dialogue_summary.md`).

### Procedure to make a dub
1. **List** — `python -X utf8 tools/audio_inventory.py` regenerates the CSVs
   (every sound with its speaker, rate, duration and size).
2. **Extract** — `aac.py xma` exports each sound as RIFF-wrapped XMA2;
   `ffmpeg` decodes it to WAV to transcribe/re-record.
3. **Record/translate** the lines into your language, named **exactly like the
   originals**, in e.g. `mod/audio/<lang>/`.
4. **Substitute at runtime** — hook the guest XAudio2 submission
   (`XAudioSubmitRenderDriverFrame`, `XMACreateContext`, …), map the submitted
   buffer back to its `AAC ` name and play your file instead. Music and SFX stay
   untouched (mixed-language dub).
5. **Package** it like the text mod (self-contained `mod/audio/<lang>/`).

On a **real Xbox 360** this instead needs the on-disk route: re-encode to XMA2
(Microsoft's encoder), repack the `AAC ` / MRON / `ud*.bin` containers and the
disc (no checksums in the containers, but the recomp verifies `ud*.bin` by
SHA-256) on **RGH/JTAG**. A community **undub** (Japanese voices) proves on-disk
replacement works — but it *splices existing XMA2*; a new language has none,
which is why the recomp runtime path is the practical one.

## End-user requirements (to play)

- A legal copy of *Infinite Undiscovery* (Disc 1 + Disc 2).
- Windows 10/11 x64, GPU with Direct3D 12.
- Microsoft Visual C++ Redistributable 2015-2022 (x64).

## Known limitations

- **Zone-title banner** — the serif "entering <area>" banner (e.g. *Graad
  Prison*) is still shown in English. It is composed with a dedicated serif
  glyph set at runtime and does **not** read the `.msg` banks, the `.exe`
  `MapName` table, nor any static string (all verified in memory). Localising it
  requires hooking its own renderer; see `docs/re/zone-banner.md`.

## Legal notice

Unofficial project, not affiliated with Square Enix, tri-Ace or Microsoft. No
copyrighted content is distributed: only original code, tools and translation
tables. The recomp's **BSD-3-Clause** license and the ReXGlue licenses are
respected.
