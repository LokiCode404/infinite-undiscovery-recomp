#!/usr/bin/env python3
"""
verify_controller.py -- OFFLINE verification of the multi-controller support.

Checks, without running the game:
  1. VendorID detection (same logic as `mod/recomp/controller_es.h`:
     the line `SDL OnControllerDeviceAdded: ... VendorID(0x....)` is parsed from
     runtime.log).  Microsoft/Sony/Valve fixtures are tested.
  2. The `translation/ui_textures.txt` manifest (IUT2 format): that the
     per-controller variants exist (ps5 atlas, ps5/steam maps) and that the
     signatures match the origin.
  3. That the variant textures have the SAME size as the origin (a hook
     requirement, which substitutes in-place) and that they decode.
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
VENDOR = REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"
for p in (str(VENDOR), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import aif as aif_mod  # noqa: E402

VENDOR_MAP = {0x045E: "xbox", 0x054C: "ps5", 0x28DE: "steam"}
LINE = re.compile(r"OnControllerDeviceAdded.*?VendorID\(0x([0-9A-Fa-f]+)\)")


def detect_from_log(text: str) -> str:
    """Same logic as controller_es.h::ParseLog/FromVendor (last VendorID)."""
    vendor = None
    for m in LINE.finditer(text):
        vendor = int(m.group(1), 16)
    if vendor is None:
        return "xbox"  # no controller -> default
    return VENDOR_MAP.get(vendor, "xbox")


def check_detection() -> bool:
    ok = True
    fixtures = [
        ('SDL OnControllerDeviceAdded: "Xbox Series X Controller", JoystickType(1), '
         'GameControllerType(3), VendorID(0x045E), ProductID(0x0B13)', "xbox"),
        ('SDL OnControllerDeviceAdded: "DualSense Wireless Controller", JoystickType(1), '
         'GameControllerType(3), VendorID(0x054C), ProductID(0x0CE6)', "ps5"),
        ('SDL OnControllerDeviceAdded: "Steam Controller", JoystickType(1), '
         'GameControllerType(3), VendorID(0x28DE), ProductID(0x1142)', "steam"),
    ]
    for line, want in fixtures:
        got = detect_from_log(line)
        flag = "ok" if got == want else "x"
        if got != want:
            ok = False
        print("[%s] fixture -> %s (esperado %s)" % (flag, got, want))

    real = REPO / "extract/f2/run/EUROPE/logs/runtime.log"
    if real.is_file():
        got = detect_from_log(real.read_text(encoding="utf-8", errors="replace"))
        print("[ok] runtime.log real -> %s" % got)
    return ok


def parse_manifest(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("IUT"), "cabecera desconocida %r" % lines[0]
    v2 = lines[0].startswith("IUT2")
    n = int(lines[1])
    out = []
    for ln in lines[2:2 + n]:
        parts = ln.split()
        if v2:
            sig, length, h, ctrl, p = parts
        else:
            sig, length, h, p = parts
            ctrl = "*"
        out.append((sig, int(length), int(h, 16), ctrl, p))
    return v2, out


def check_manifest(manifest: Path) -> bool:
    if not manifest.is_file():
        print("! no existe el manifiesto %s" % manifest)
        return False
    v2, entries = parse_manifest(manifest)
    print("[%s] manifiesto %s (IUT%d, %d texturas)"
          % ("ok" if v2 else "x", manifest.name, 2 if v2 else 1, len(entries)))
    ok = v2
    ctrls = {}
    for sig, length, h, ctrl, p in entries:
        ctrls.setdefault(ctrl, []).append(p)
    for ctrl in ("xbox", "ps5", "steam"):
        n = len(ctrls.get(ctrl, []))
        print("    variantes %-5s: %d" % (ctrl, n))
    for need in ("atlas_ui_ps5_es.aif",):
        hit = any(p.endswith(Path(need).name) for _, _, _, _, p in entries)
        print("    [%s] %s" % ("ok" if hit else "x", need))
        ok = ok and hit
    return ok


def check_variants() -> bool:
    ok = True
    pairs = [
        ("extract/f2/all_d1ud1/000A4000_002_IMG.aif",
         "extract/f2/ui_es/atlas_ui_ps5_es.aif"),
        ("extract/f2/all_d1ud1/26EF5000_000_IMG.aif",
         "extract/f2/ui_es/controllermap_ps5_es.aif"),
        ("extract/f2/all_d1ud1/26EF5000_000_IMG.aif",
         "extract/f2/ui_es/controllermap_steam_es.aif"),
    ]
    for orig_rel, out_rel in pairs:
        o = (REPO / orig_rel)
        v = (REPO / out_rel)
        if not v.is_file():
            print("! falta %s (ejecuta tools/controller_skins.py all)" % out_rel)
            ok = False
            continue
        ob, vb = o.read_bytes(), v.read_bytes()
        same_len = len(ob) == len(vb)
        same_sig = ob[:0x30] == vb[:0x30]
        try:
            img = aif_mod.AifImage(vb)
            dec = "ok %dx%d %s" % (img.width, img.height, img.format_name)
        except Exception as e:  # noqa: BLE001
            dec = "x %s" % e
            ok = False
        good = same_len and same_sig and dec.startswith("ok")
        ok = ok and good
        print("[%s] %-34s len=%s sig=%s decode=%s"
              % ("ok" if good else "x", Path(out_rel).name,
                 "ok" if same_len else "x", "ok" if same_sig else "x", dec))
    return ok


def main() -> int:
    ok = True
    print("== 1) deteccion por VendorID ==")
    ok &= check_detection()
    print("\n== 2) manifiesto IUT2 ==")
    ok &= check_manifest(REPO / "extract/f2/run/translation/ui_textures.txt")
    print("\n== 3) variantes por mando ==")
    ok &= check_variants()
    print("\nRESULTADO:", "OK" if ok else "FALLOS")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
