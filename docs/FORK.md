# Publishing: fork + pull request

This repository contains the full **Spanish (Castilian) translation mod** for
*Infinite Undiscovery* (built on the PC recompilation) **plus the audio /
fan-dub research**. It is prepared to be published as a **fork** and offered as
a **pull request** to the base recompilation project.

---

## 1. What this repository is

- **Base project:** `doc-haz/infinite-undiscovery-recomp` — the native PC
  recompilation of the game.
- **This repo adds:** the `mod/` (runtime hooks + translation data), `tools/`
  (offline pipeline) and `docs/` (RE, setup and dubbing notes).
- **Never versioned** (see `.gitignore`): `roms/` (the user's legal discs),
  `extract/` (asset dumps + build) and `dist/` (packaged releases).

## 2. History

The published state is a **single commit** with the whole current project. The
local development history is preserved only in the local branches
`master` / `backup-master` and is **not** published.

```
git log --oneline        # -> one commit on branch `release`
git branch               # -> release (current), master, backup-master
```

## 3. Publish the fork

1. Create an **empty** repository on GitHub, e.g. `<you>/infinite-undiscovery-es`.
2. From this folder:

   ```bash
   git remote add origin https://github.com/<you>/infinite-undiscovery-es.git
   git push -u origin release:main      # publishes the clean single-commit state
   ```

3. (Optional) set `main` as the default branch in the repository settings.

> The submodule `tools/vendor/pc-infiniteundiscovery` (public) is referenced by
> `.gitmodules`; clone with `--recurse-submodules` or run
> `git submodule update --init --recursive`.

## 4. Pull request to the original repository

Open a PR from your fork's `main` to **`doc-haz/infinite-undiscovery-recomp`**.

- **Title:** *Spanish (Castilian) translation mod + audio/fan-dub research*
- **Body:** paste **[`docs/PR.md`](PR.md)** (ready-to-use description).

### Summary of the contribution

- **Text** — 71,386 messages across 81 banks, translated and applied at runtime
  by hooking the message parser (no asset is modified).
- **Textures** — UI atlas, main menu, GAME OVER, Now Loading, Reload and the 51
  CAMP help screens, replaced by signature at runtime.
- **Fonts/accents** — the 16 Spanish glyphs are added per bank.
- **Options** — exposed via the Asset Setup Wizard / Content Profile Manager and
  CVARs.
- **Audio / fan-dub research** — the audio inventory, the dialogue-to-dub list
  (which sounds are voice, per character) and the dubbing procedure
  (`docs/AUDIO_DUB.md`).

## 5. Reproducing the project

The full, from-scratch reproduction is documented in
**[`docs/SETUP.md`](SETUP.md)** (bootstrap → pipeline → build → deploy); the
pipeline reference is in **[`docs/TOOLS.md`](TOOLS.md)**.
