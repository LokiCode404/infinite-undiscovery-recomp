# Pull request draft — Spanish (Castilian) translation support

> Ready-to-use description for the PR to the upstream recomp repository
> (`doc-haz/infinite-undiscovery-recomp`). Adjust wording/links as needed.

## Summary

Adds an optional, fully data-driven **Spanish (Castilian) translation** to the
recomp, applied **entirely at runtime** (no original assets are modified).

- **Text** — hooks the message parser and substitutes the resolved text pointer
  with Spanish glyph codes in guest memory. All 71,386 messages across the 81
  message banks are translated.
- **Textures** — bitmap labels (UI atlas, main menu, GAME OVER, Now Loading,
  Reload and the 51 CAMP help screens) are replaced by signature at runtime.
- **Fonts/accents** — the 16 Spanish glyphs (`á é í ó ú ü ñ Á É Í Ó Ú Ü Ñ ¿ ¡`)
  are added per bank so accents and `¿`/`¡` render correctly.
- **Options** — the mod is exposed through the existing **Asset Setup Wizard** /
  **Content Profile Manager** (F10) and as CVARs (`es_translation`,
  `es_textures`, `es_catalog`, …), so it can be enabled/disabled without
  rebuilding.

## Motivation

The game shipped with English/Japanese text only. This PR adds a maintainable
translation layer that other language mods can reuse: the pipeline is
data-driven and the runtime hooks are language-agnostic.

## What changes

| Area | Change |
|---|---|
| `src/main.cpp` | include the mod headers; register the mod CVARs |
| `src/portable_setup.{h,cpp}` | add a "Translation" panel to the Asset Setup Wizard and the Content Profile Manager (persisted in `setup.json`) |
| `src/setup_strings.inc` | bilingual labels for the new panel |
| `mod/recomp/*.h` | text hook, texture hook, per-bank accents, CVARs |
| `tools/*.py` | decoding/rendering pipeline (offline; not needed at runtime) |
| `translation/` | translation data (parts, charmaps, catalog, textures) |
| `mod/audio/`, `tools/audio_inventory.py`, `docs/AUDIO_DUB.md` | audio / fan-dub research (inventory + dialogue-to-dub list + procedure) |

## Design notes

- **No asset patching.** Everything is applied through runtime hooks; the disc
  images are untouched.
- **Robust bank identification.** Banks are identified by a fingerprint of the
  loaded `.msg` header, so the mapping is independent of file paths.
- **Priority** `CVAR > environment > setup wizard > default` keeps backwards
  compatibility with existing scripts.
- **Performance.** The texture scanner is bounded (small budget, low cadence) so
  it does not compete with the game.

## Testing

- Text: 71,386 messages decoded with an exact round-trip; 100% of the English
  text translated.
- Textures: 58 manifest entries verified offline (byte-order/tiling round-trip);
  every text-bearing texture of both discs was inventoried (21,692 files /
  10,316 AIFs).
- Accents: 44 banks patched, round-trip verified.

## Out of scope / future work

- **Zone-title banner** — the serif "entering &lt;area&gt;" banner remains in
  English: it is composed by its own renderer and reads neither the `.msg` banks
  nor the `.exe` `MapName` table nor any static string (all verified in memory);
  see `docs/re/zone-banner.md`.
- **Voice / fan-dub** — investigated and documented in `docs/AUDIO_DUB.md`: the
  audio is `SOND` (`AAC `) banks of **XMA2** voice lines; a dub is feasible on the
  recomp by substituting PCM at runtime (no XMA2 encoder needed), while real
  hardware requires Microsoft's XMA2 encoder. This PR ships the **inventory and
  the dialogue-to-dub list** (`mod/audio/`, `tools/audio_inventory.py`); the
  runtime audio hook is future work.

## Legal

Unofficial; not affiliated with Square Enix, tri-Ace or Microsoft. Only original
code, tools and translation tables are contributed. No copyrighted assets are
included.
