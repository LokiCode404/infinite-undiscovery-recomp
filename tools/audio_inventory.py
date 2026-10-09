#!/usr/bin/env python3
"""audio_inventory.py -- exhaustive inventory of the game's audio banks.

Reads every `*_SOND.bin` (AAC containers) in the extracted trees and lists
each sound with its name, format and duration, classifying it as voice
(dialogue to be dubbed), foley, system or other.

Outputs (under `--out`, default `extract/f2`):
  * audio_inventory.csv   -- every sound (all kinds)
  * dialogue_to_dub.csv   -- only the voice/dialogue lines (the dub target)
  * dialogue_summary.md   -- counts, minutes and per-character breakdown

This is read-only; it never modifies assets.
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                "vendor", "pc-infiniteundiscovery", "tools"))
import aac  # noqa: E402

# Voice/dialogue line markers (case-insensitive) as used by the game's own
# source .wav names.  `_SP_` = speech, `_FV_` = field voice, `BTL`/`BATTLE`,
# `SITU` = situational.  Everything else is foley/SFX/system.
VOICE_RE = re.compile(r"(_SP_|_FV_|_BTL|BATTLE|SITU|_VC_|VOICE)", re.I)
FOLEY_RE = re.compile(
    r"(_WALK|_RUN|_FALL|_LANDING|_SIT_|_STAND|_JUMP|_STEP|_HIT|_ATTACK|_DAMAGE|"
    r"_DOWN|_N_|_READY|_GUARD|_ESCAPE|_CLIMB|_SWIM)", re.I)
SYSTEM_RE = re.compile(r"^(SYSTEM|CAMP|GMK|SYS|MENU)", re.I)


def classify(name: str) -> str:
    n = name
    if VOICE_RE.search(n):
        return "voice"
    if SYSTEM_RE.match(n):
        return "system"
    if FOLEY_RE.search(n):
        return "foley"
    return "other"


def voice_kind(name: str) -> str:
    """Finer split of the voice lines: story speech, field voice, battle."""
    if re.search(r"_SP_", name, re.I):
        return "speech"
    if re.search(r"_FV_", name, re.I):
        return "fieldvoice"
    if re.search(r"(BTL|BATTLE|SITU)", name, re.I):
        return "battle"
    return "other"


def character(name: str) -> str:
    """Best-effort speaker tag from the name prefix (AYA, CAPEL, ...)."""
    m = re.match(r"^([A-Za-z]{2,})", name)
    return m.group(1).upper() if m else ""


def scan(roots):
    rows = []
    for disc, root in roots:
        for path in sorted(glob.glob(os.path.join(root, "*_SOND.bin"))):
            try:
                bank = aac.Bank(open(path, "rb").read())
            except Exception as exc:  # noqa: BLE001
                print("  ! %s: %s" % (os.path.basename(path), exc))
                continue
            base = os.path.basename(path)
            for i, e in enumerate(bank.entries):
                w = e.wave
                if w is None:
                    continue
                rows.append(dict(
                    disc=disc, bank=base, index=i, name=e.name,
                    kind=classify(e.name), character=character(e.name),
                    channels=w.channels, rate=w.rate,
                    seconds=round(w.seconds, 3), loops=int(w.loops),
                    bytes=w.data_size))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="extract/f2")
    ap.add_argument("--d1", default="extract/f2/all_d1ud1")
    ap.add_argument("--d2", default="extract/f2/all_d1ud2")
    args = ap.parse_args(argv)

    roots = [("disc1", args.d1), ("disc2", args.d2)]
    rows = scan(roots)
    os.makedirs(args.out, exist_ok=True)

    fields = ["disc", "bank", "index", "name", "kind", "character",
              "channels", "rate", "seconds", "loops", "bytes"]
    with open(os.path.join(args.out, "audio_inventory.csv"), "w",
              newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields)
        wr.writeheader()
        wr.writerows(rows)

    voice = [r for r in rows if r["kind"] == "voice"]
    with open(os.path.join(args.out, "dialogue_to_dub.csv"), "w",
              newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields)
        wr.writeheader()
        wr.writerows(voice)

    # summary
    by_kind = Counter(r["kind"] for r in rows)
    sec_kind = defaultdict(float)
    for r in rows:
        sec_kind[r["kind"]] += r["seconds"]
    by_char = Counter(r["character"] for r in voice)
    sec_char = defaultdict(float)
    for r in voice:
        sec_char[r["character"]] += r["seconds"]

    lines = []
    lines.append("# Audio inventory / dialogue to dub\n")
    lines.append("Total sounds: **%d** across %d banks.\n" %
                 (len(rows), len({r["bank"] for r in rows})))
    lines.append("## By kind\n")
    lines.append("| kind | sounds | minutes |")
    lines.append("|---|---:|---:|")
    for k in sorted(by_kind, key=lambda k: -by_kind[k]):
        lines.append("| %s | %d | %.1f |" % (k, by_kind[k], sec_kind[k] / 60.0))
    lines.append("")
    lines.append("## Voice/dialogue (dub target): %d lines, %.1f min\n" %
                 (len(voice), sum(r["seconds"] for r in voice) / 60.0))
    lines.append("| speaker | lines | minutes |")
    lines.append("|---|---:|---:|")
    for c, n in by_char.most_common():
        lines.append("| %s | %d | %.1f |" % (c or "(other)", n, sec_char[c] / 60.0))
    lines.append("")
    lines.append("Full lists: `audio_inventory.csv`, `dialogue_to_dub.csv`.\n")
    with open(os.path.join(args.out, "dialogue_summary.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print("sounds: %d   voice: %d (%.1f min)" %
          (len(rows), len(voice), sum(r["seconds"] for r in voice) / 60.0))
    for k in sorted(by_kind, key=lambda k: -by_kind[k]):
        print("  %-7s %6d  %6.1f min" % (k, by_kind[k], sec_kind[k] / 60.0))
    print("written: audio_inventory.csv, dialogue_to_dub.csv, dialogue_summary.md")


if __name__ == "__main__":
    main()
