#!/usr/bin/env python3
"""ui_help_screens.py -- translates the CAMP HELP screens (1280x720 DXT1).

Unlike the UI atlas (transparent background), these screens are
**opaque captures**: the original text is ink over art/background.  Therefore:

1. The original text is **removed** with *inpainting* (`cv2.inpaint`): the local
   background is estimated (median + morphological closing) and the pixels that
   differ from it are masked (light or dark ink).  Filled with TELEA.
2. Spanish is **painted** on top with a style that imitates the original
   (serif font, fill + outline) fitted to the box (never overflowing it).
3. The AIF is **re-encoded** preserving DXT1 and size (`ui_textures.encode_aif`).

Registry
--------
`SCREENS` maps key -> {source, out, labels:[{en,es,box,style,...}]}.
`box` = (x0,y0,x1,y1) of the original INK (with minimal padding).

Usage
-----
    python -X utf8 tools/ui_help_screens.py list
    python -X utf8 tools/ui_help_screens.py render --out extract/f2/ui_es --preview
    python -X utf8 tools/ui_help_screens.py render --only camp_1 --preview
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "vendor" / "pc-infiniteundiscovery" / "tools"))

import aif as aif_mod  # noqa: E402
import ui_textures as U  # noqa: E402

A = "extract/f2/all_d1ud1"


# --------------------------------------------------------------------------
# Styles (RGBA colors).  They approximate the original of each label type.
# --------------------------------------------------------------------------
HELP_STYLES = {
    # Large title in the top-left corner (dark serif with a cream border).
    # It is the most prominent label.
    "h_title": dict(
        font="camp_italic", max_size=60,
        fill=(46, 82, 96, 255), outline=(238, 233, 214, 255), outline_w=2,
        shadow=(90, 80, 60, 110), shadow_off=(2, 3), shadow_blur=2.5, glow=None,
    ),
    # Small white text on a dark panel (help bar, descriptions).
    "h_white": dict(
        font="camp", max_size=17,
        fill=(240, 240, 235, 255), outline=(15, 15, 20, 220), outline_w=1,
        shadow=None, glow=None,
    ),
    # Option labels on a dark panel (Free/Combo/...).
    "h_opt": dict(
        font="camp", max_size=22,
        fill=(245, 245, 245, 255), outline=(10, 10, 10, 230), outline_w=1,
        shadow=None, glow=None,
    ),
    # Gold label (TARGET / panel headers).
    "h_gold": dict(
        font="camp", max_size=18,
        fill=(214, 182, 108, 255), outline=(40, 28, 0, 220), outline_w=1,
        shadow=None, glow=None,
    ),
    # Light text on light art (parchment).
    "h_parch": dict(
        font="camp", max_size=30,
        fill=(70, 70, 60, 255), outline=(240, 236, 220, 220), outline_w=1,
        shadow=None, glow=None,
    ),
}


# --------------------------------------------------------------------------
# Inpainting of the original text
# --------------------------------------------------------------------------
def remove_text(arr: np.ndarray, box, pad: int = 4, thresh: int = 20,
                dilate: int = 3) -> None:
    """Erases the ink of `box` by filling with the local background (in-place)."""
    x0, y0, x1, y1 = box
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(arr.shape[1], x1 + pad); y1 = min(arr.shape[0], y1 + pad)
    if x1 <= x0 or y1 <= y0:
        return
    sub = arr[y0:y1, x0:x1]
    g = cv2.cvtColor(sub, cv2.COLOR_RGB2GRAY)
    # local background: median of a heavily blurred version (removes thin ink)
    bg = cv2.medianBlur(g, 31)
    mask = (np.abs(g.astype(np.int16) - bg.astype(np.int16)) > thresh).astype(np.uint8) * 255
    if dilate:
        mask = cv2.dilate(mask, np.ones((dilate, dilate), np.uint8), iterations=1)
    if mask.max() == 0:
        return
    out = cv2.inpaint(sub, mask, 3, cv2.INPAINT_TELEA)
    arr[y0:y1, x0:x1] = out


# --------------------------------------------------------------------------
# Painting (over an opaque background; does NOT erase to transparent)
# --------------------------------------------------------------------------
def paint_opaque(base: Image.Image, box, text: str, style_name: str,
                 ss: int = 4, center: bool = False) -> None:
    x0, y0, x1, y1 = box
    style = HELP_STYLES[style_name]
    maxw, maxh = x1 - x0, y1 - y0
    lines = text.split("\n")
    if len(lines) > 1:
        lh = maxh // len(lines)
        for i, ln in enumerate(lines):
            if not ln:
                continue
            _paint_line(base, (x0, y0 + i * lh, x1, y0 + (i + 1) * lh), ln, style, ss, center)
    else:
        _paint_line(base, box, text, style, ss, center)


def _paint_line(base: Image.Image, box, text: str, style: dict, ss: int,
                center: bool) -> None:
    x0, y0, x1, y1 = box
    maxw, maxh = x1 - x0, y1 - y0
    layer = U._render_layer(text, style["font"], style, maxw, maxh, ss)
    layer = layer.resize((max(1, layer.width // ss), max(1, layer.height // ss)),
                         Image.LANCZOS)
    cy = y0 + (maxh - layer.height) // 2
    cx = x0 + (maxw - layer.width) // 2 if center else x0
    cx = max(x0, min(cx, x1 - layer.width))
    cy = max(y0, min(cy, y1 - layer.height))
    base.alpha_composite(layer, (cx, cy))


# --------------------------------------------------------------------------
# Screen registry
# --------------------------------------------------------------------------
def _sc(hexid: str, out: str, labels, **kw):
    d = dict(source=f"{A}/{hexid}_000_IMG.aif", out=out, labels=labels)
    d.update(kw)
    return d


# Titles (top-left corner).  Common box for all screens.
# (x0,y0,x1,y1) wide: covers one- and two-line titles
# ("MULTIPLE PARTY SETUP", "INVISIBLE ENEMIES") without invading the "N/M" on the
# right (x>=1100).  The ES text is fitted to this box.
TITLE_BOX = [80, 22, 840, 120]

_TITLES = {
    "28000000": "BATALLA 1", "28044800": "BATALLA 1", "2808B000": "BATALLA 1",
    "280D2800": "CAMPAMENTO", "28119000": "CAMPAMENTO",
    "28164800": "BUSCAR", "281B0000": "COFRES DEL TESORO",
    "281FA800": "COFRES DEL TESORO", "28243000": "COFRES DEL TESORO",
    "2828A800": "CONEXI\u00d3N 1", "282D5000": "CONEXI\u00d3N 1",
    "28323800": "CONEXI\u00d3N 1", "2836D800": "CONEXI\u00d3N 1",
    "283B8800": "GUARDAR", "28404000": "HUIR", "2844E000": "T\u00c1CTICAS",
    "28493800": "T\u00c1CTICAS", "284DF000": "T\u00c1CTICAS",
    "2852C000": "DETECCI\u00d3N", "28577800": "DETECCI\u00d3N",
    "285BF800": "DETECCI\u00d3N", "28608000": "DETECCI\u00d3N",
    "28650800": "PEDIR AYUDA", "28698000": "FLAUTA", "286DF800": "FLAUTA",
    "2872E000": "CREACI\u00d3N 1", "28777000": "CREACI\u00d3N 1",
    "287BB000": "CREACI\u00d3N 1", "28800000": "GRUPO", "28845000": "GRUPO",
    "2888A000": "GRUPO M\u00daLTIPLE", "288D1800": "GRUPO M\u00daLTIPLE",
    "28916800": "BATALLA 2", "28961800": "BATALLA 2", "289AD800": "BATALLA 2",
    "289F7000": "BATALLA 2", "28A40800": "BATALLA 2",
    "28A8B000": "PEDIR CURACI\u00d3N", "28AD6000": "",
    "28B26000": "BATALLA 3", "28B71800": "BATALLA 3",
    "28BB9000": "CONEXI\u00d3N 2", "28C01800": "CONEXI\u00d3N 2",
    "28C4E000": "CREACI\u00d3N 2", "28C94800": "CREACI\u00d3N 2",
    "28CE0000": "CONDICI\u00d3N ESPECIAL 1", "28D32000": "CONDICI\u00d3N ESPECIAL 2",
    "28D7C800": "ENEMIGOS INVISIBLES", "28DC9000": "ENEMIGOS INVISIBLES",
    "28E19000": "TASA DE GLIFOS", "28E67800": "TASA DE GLIFOS",
}


# --------------------------------------------------------------------------
# Screen labels (besides the title).
#   box = (x0,y0,x1,y1) of the original ink;  style = HELP_STYLES style.
# --------------------------------------------------------------------------
def _l(en, es, box, style="h_white", center=False):
    return {"en": en, "es": es, "box": list(box), "style": style, "center": center}


LABELS = {
    # --- CAMP 1/2 ---------------------------------------------------------
    "280d2800": [
        _l("Select an item to use.", "Selecciona un objeto.", (255, 280, 400, 297)),
        _l("Items", "Objetos", (258, 301, 302, 316)),
        _l("Skills", "Habs.", (258, 319, 302, 334)),
        _l("Equipment", "Equipo", (258, 337, 328, 352)),
        _l("Status", "Estado", (258, 355, 308, 370)),
        _l("Map", "Mapa", (258, 373, 295, 388)),
        _l("System", "Sistema", (258, 391, 312, 406)),
        _l("Talk", "Hablar", (258, 409, 298, 424)),
        _l("Skills", "Habs.", (435, 410, 512, 440)),
        _l("Battle", "Combate", (612, 430, 684, 454)),
        _l("Connect", "Conexi\u00f3n", (612, 458, 694, 482)),
        _l("Flute", "Flauta", (612, 486, 670, 510)),
        _l("Magic", "Magia", (612, 514, 674, 538)),
        _l("Personal", "Personal", (612, 542, 694, 566)),
        _l("Items", "Objetos", (828, 282, 1014, 318)),
        _l("~ Items ~", "~ Objetos ~", (1003, 305, 1080, 324)),
        _l("~ Magic ~", "~ Magia ~", (783, 369, 860, 390)),
        _l("Red Berry Potion", "Poci\u00f3n de baya roja", (993, 337, 1095, 354)),
        _l("Medicinal Medicine", "Medicina medicinal", (993, 354, 1105, 371)),
        _l("Description", "Descripci\u00f3n", (988, 498, 1055, 514)),
        _l("Details", "Detalles", (1083, 498, 1130, 514)),
        _l("Made from red berries", "Hecha con bayas rojas", (988, 514, 1112, 530)),
        _l("Slight healing of wounds.", "Cura levemente las heridas.", (988, 530, 1132, 546)),
        _l("Description", "Descripci\u00f3n", (738, 557, 805, 573)),
        _l("Heals ground 30% of\nan ally's HP.", "Cura un 30% de\nlos PS de un aliado.", (736, 573, 884, 600)),
    ],
    # --- CAMP 2/2 (submenu navigation) ------------------------------------
    "28119000": [
        _l("Select an item to use.", "Selecciona un objeto.", (408, 254, 566, 271)),
        _l("Items", "Objetos", (408, 277, 465, 295)),
        _l("Skills", "Habs.", (408, 295, 462, 313)),
        _l("Equipment", "Equipo", (408, 313, 500, 331)),
        _l("Status", "Estado", (408, 331, 470, 349)),
        _l("Map", "Mapa", (408, 349, 448, 367)),
        _l("System", "Sistema", (408, 367, 475, 385)),
        _l("Talk", "Hablar", (408, 385, 455, 403)),
    ],
    # --- BATTLE 1 (4/4): skill list ---------------------------------------
    "2808b000": [
        _l("Items", "Objetos", (73, 246, 113, 264)),
        _l("Skills", "Habs.", (73, 281, 115, 299)),
        _l("Equipment", "Equipo", (73, 316, 123, 334)),
        _l("Status", "Estado", (73, 351, 118, 369)),
        _l("Map", "Mapa", (73, 386, 108, 404)),
        _l("System", "Sistema", (73, 421, 123, 439)),
        _l("Talk", "Hablar", (73, 456, 111, 474)),
        _l("Battle", "Combate", (318, 288, 383, 314)),
        _l("Connect", "Conexi\u00f3n", (318, 316, 388, 342)),
        _l("Flute", "Flauta", (318, 344, 373, 370)),
        _l("Magic", "Magia", (318, 372, 378, 398)),
        _l("Personal", "Personal", (318, 400, 388, 426)),
        _l("~ Battle ~", "~ Combate ~", (513, 330, 602, 356)),
        _l("Battle Skill - 1", "Habilidad de combate - 1", (458, 376, 542, 394)),
        _l("Slashing Canon", "Ca\u00f1\u00f3n cortante", (460, 390, 547, 408)),
        _l("Battle Skill - 2", "Habilidad de combate - 2", (458, 412, 542, 430)),
        _l("Slashing Canon", "Ca\u00f1\u00f3n cortante", (460, 426, 547, 444)),
    ],
    # --- SEARCHING (1/1) --------------------------------------------------
    "28164800": [
        _l("Prissy woman", "Mujer remilgada", (198, 418, 305, 439)),
        _l("Talk", "Hablar", (198, 440, 248, 460)),
        _l("Prissy woman", "Mujer remilgada", (557, 418, 664, 439)),
        _l("Control Lever", "Palanca de control", (898, 452, 1002, 472)),
        _l("Examine", "Examinar", (898, 472, 962, 492)),
    ],
    # --- TREASURE CHESTS (2/3) -------------------------------------------
    "281fa800": [
        _l("Obtains a bottle of black berry potion!",
           "\u00a1Obtienes una botella de poci\u00f3n de baya negra!", (846, 342, 1110, 369)),
        _l("Obtains some junk!", "\u00a1Obtienes chatarra!", (846, 554, 1010, 581)),
        _l("Treasure Chest", "Cofre del tesoro", (122, 528, 228, 547)),
    ],
    # --- TREASURE CHESTS (3/3) -------------------------------------------
    "28243000": [
        _l("Unlocks the treasure chest!", "\u00a1Abre el cofre del tesoro!", (458, 389, 692, 416)),
    ],
    # --- CONNECT 1 (2/4): dialogue box ------------------------------------
    "282d5000": [
        _l("civilized gent", "caballero civilizado", (923, 476, 1012, 494)),
        _l("lifted my spirits!", "me ha animado.", (923, 490, 1032, 508)),
        _l("imprisoned here, but my thoughts and wishes go",
           "encerrado aqu\u00ed, pero mis pensamientos y deseos", (923, 504, 1232, 522)),
        _l("waiting to hear of your success!",
           "esperan o\u00edr tu \u00e9xito.", (923, 518, 1112, 536)),
        _l("Order Jailer", "Carcelero de la Orden", (96, 508, 160, 526)),
        _l("Peacock Plume", "Pluma de pavo real", (503, 516, 612, 534)),
        _l("Ravaging Raptor", "R\u00e1ptor devastador", (503, 530, 612, 548)),
    ],
    # --- CONNECT 1 (4/4) --------------------------------------------------
    "2836d800": [
        _l("Peacock Plume", "Pluma de pavo real", (546, 420, 680, 452)),
        _l("Ravaging Raptor", "R\u00e1ptor devastador", (523, 458, 657, 490)),
        _l("Cancel", "Cancelar", (438, 553, 480, 571)),
        _l("Shoot", "Disparar", (436, 566, 474, 584)),
        _l("Order Jailer", "Carcelero de la Orden", (688, 446, 752, 464)),
        _l("Peacock Plume", "Pluma de pavo real", (1018, 338, 1112, 356)),
        _l("Ravaging Raptor", "R\u00e1ptor devastador", (1018, 468, 1112, 486)),
    ],
    # --- SAVING (1/1) -----------------------------------------------------
    "283b8800": [
        _l("~ Save ~", "~ Guardar ~", (900, 268, 1032, 293)),
        _l("Which slot do you want to save to?",
           "\u00bfEn qu\u00e9 ranura quieres guardar?", (852, 299, 1175, 319)),
        _l("Slot 1", "Ranura 1", (735, 329, 800, 347)),
        _l("Groad Prison", "Prisi\u00f3n de Groad", (805, 329, 905, 347)),
        _l("Rescue", "Rescate", (983, 329, 1042, 347)),
        _l("Normal", "Normal", (735, 367, 792, 385)),
        _l("Slot 2", "Ranura 2", (735, 411, 800, 429)),
        _l("Create New", "Crear nueva", (805, 411, 898, 429)),
        _l("Slot 3", "Ranura 3", (735, 486, 800, 504)),
        _l("Create New", "Crear nueva", (805, 486, 898, 504)),
        _l("Save Point", "Punto de guardado", (138, 524, 218, 543)),
        _l("Examine", "Examinar", (138, 543, 202, 561)),
    ],
    # --- TACTICS (1/3): options list --------------------------------------
    "2844e000": [
        _l("Free", "Libre", (240, 268, 362, 301), style="h_opt"),
        _l("Combo", "Combo", (240, 321, 362, 361), style="h_opt"),
        _l("Focus", "Concentrar", (240, 382, 362, 423), style="h_opt"),
        _l("Spread", "Dispersar", (240, 442, 362, 486), style="h_opt"),
        _l("Wait", "Esperar", (240, 502, 362, 543), style="h_opt"),
        _l("Save MP", "Ahorrar PM", (240, 562, 362, 603), style="h_opt"),
        _l("Fight freely!", "\u00a1Lucha libremente!", (706, 288, 802, 308)),
        _l("Free", "Libre", (453, 562, 512, 582)),
    ],
    # --- TACTICS (2/3) ----------------------------------------------------
    "28493800": [
        _l("Free", "Libre", (85, 264, 152, 293), style="h_opt"),
        _l("Combo", "Combo", (407, 404, 497, 434), style="h_opt"),
        _l("Focus", "Concentrar", (719, 264, 817, 293), style="h_opt"),
    ],
    # --- TACTICS (3/3) ----------------------------------------------------
    "284df000": [
        _l("Wait", "Esperar", (408, 254, 487, 291), style="h_opt"),
        _l("Spread", "Dispersar", (78, 401, 182, 438), style="h_opt"),
        _l("Save MP", "Ahorrar PM", (718, 401, 837, 438), style="h_opt"),
    ],
    # --- DETECTION (1/4) --------------------------------------------------
    "2852c000": [
        _l("Order Jailer", "Carcelero de la Orden", (106, 503, 168, 521)),
    ],
    # --- DETECTION (2/4) --------------------------------------------------
    "28577800": [
        _l("Order Jailer", "Carcelero de la Orden", (150, 476, 212, 494)),
        _l("Treasure Chest", "Cofre del tesoro", (656, 533, 762, 551)),
    ],
    # --- DETECTION (3/4) --------------------------------------------------
    "285bf800": [
        _l("Player Advantage!", "\u00a1Ventaja aliada!", (232, 476, 422, 504)),
        _l("Player Advantage!", "\u00a1Ventaja aliada!", (620, 266, 722, 285), style="h_gold"),
        _l("EXP + 50%", "EXP + 50%", (622, 288, 700, 306), style="h_gold"),
        _l("100% Critical hit rate!", "\u00a1100% de cr\u00edtico!", (622, 304, 762, 322), style="h_gold"),
        _l("Rare item drop rate up!", "\u00a1Sube la tasa de objeto raro!", (622, 320, 772, 338), style="h_gold"),
        _l("Dancing Rhapsody", "Rapsodia danzante", (853, 276, 977, 297)),
        _l("Overkill", "Exterminio", (652, 518, 702, 536)),
        _l("Shoot", "Disparar", (403, 556, 447, 574)),
    ],
    # --- DETECTION (4/4) --------------------------------------------------
    "28608000": [
        _l("Enemy Advantage!", "\u00a1Ventaja enemiga!", (298, 360, 462, 384)),
        _l("Enemy Advantage!", "\u00a1Ventaja enemiga!", (623, 298, 732, 317), style="h_gold"),
        _l("AP falls to zero!", "\u00a1PA a cero!", (623, 317, 732, 335), style="h_gold"),
        _l("100% Susceptible to critical hits!",
           "\u00a1100% sensible a cr\u00edticos!", (623, 333, 792, 351), style="h_gold"),
    ],
    # --- FLUTE (1/2) ------------------------------------------------------
    "28698000": [
        _l("Set flute music.", "Pon m\u00fasica de flauta.", (793, 256, 902, 274)),
        _l("Items", "Objetos", (700, 280, 742, 296)),
        _l("Skills", "Habs.", (700, 298, 742, 314)),
        _l("Equipment", "Equipo", (700, 316, 750, 332)),
        _l("Status", "Estado", (700, 334, 750, 350)),
        _l("Map", "Mapa", (700, 352, 737, 368)),
        _l("Party", "Grupo", (700, 370, 742, 386)),
        _l("System", "Sistema", (700, 388, 750, 404)),
        _l("Talk", "Hablar", (700, 406, 737, 422)),
        _l("Set flute music.", "Pon m\u00fasica de flauta.", (1008, 296, 1117, 314)),
        _l("~ Flute ~", "~ Flauta ~", (998, 318, 1082, 344)),
        _l("(None)", "(Ninguna)", (998, 390, 1042, 407)),
        _l("(None)", "(Ninguna)", (998, 436, 1042, 453)),
        _l("Flute Data", "Datos de la flauta", (953, 550, 1032, 570)),
        _l("An original song which is", "Una canci\u00f3n original que", (953, 566, 1077, 584)),
        _l("just a very noisy racket.", "solo es un ruido ensordecedor.", (953, 582, 1092, 600)),
    ],
    # --- CREATION 1 (1/3) -------------------------------------------------
    "2872e000": [
        _l("Perform item creation.", "Realizar creaci\u00f3n de objeto.", (358, 296, 478, 314)),
        _l("Items", "Objetos", (426, 396, 470, 416)),
        _l("~ Creation ~", "~ Creaci\u00f3n ~", (842, 280, 938, 302)),
        _l("Cooking", "Cocina", (787, 304, 843, 322)),
        _l("Required Materials", "Materiales necesarios", (787, 418, 893, 436)),
        _l("Description", "Descripci\u00f3n", (787, 476, 848, 494)),
        _l("Details", "Detalles", (857, 476, 903, 494)),
        _l("A mix of sap and honey.", "Mezcla de savia y miel.", (787, 492, 918, 510)),
        _l("Used in many desserts.", "Se usa en muchos postres.", (787, 507, 918, 525)),
    ],
    # --- CREATION 1 (2/3) -------------------------------------------------
    "28777000": [
        _l("Display personal skills.", "Muestra habilidades personales.", (116, 260, 240, 278)),
        _l("~ Personal ~", "~ Personal ~", (328, 316, 422, 340)),
        _l("~ Personal ~", "~ Personal ~", (568, 316, 662, 340)),
        _l("Title 1 Acrobat", "T\u00edtulo 1 Acr\u00f3bata", (334, 351, 418, 367)),
        _l("Title 2 Lousy Shot", "T\u00edtulo 2 Mal tiro", (334, 365, 438, 381)),
        _l("Trait 1 Lucky", "Rasgo 1 Suertudo", (334, 393, 412, 409)),
        _l("Trait 2 Commoner", "Rasgo 2 Plebeyo", (334, 407, 438, 423)),
        _l("Title 1 Twerp", "T\u00edtulo 1 Mequetrefe", (574, 351, 654, 367)),
        _l("Title 2 Rabbit Tamer", "T\u00edtulo 2 Domador de conejos", (574, 365, 694, 381)),
        _l("Scribbles", "Garabatos", (574, 393, 642, 409)),
        _l("Beastspeaker", "Charlador de bestias", (574, 407, 662, 423)),
        _l("Trait 1 Hyper", "Rasgo 1 Hiperactivo", (574, 421, 654, 437)),
        _l("Trait 2 Twin", "Rasgo 2 Gemelo", (574, 435, 642, 451)),
        _l("Description", "Descripci\u00f3n", (334, 546, 395, 564)),
        _l("Description", "Descripci\u00f3n", (574, 546, 635, 564)),
        _l("Level 2 IC cooking.", "Nivel 2 IC cocina.", (334, 561, 432, 577)),
        _l("She sure likes to cook.", "Le encanta cocinar.", (334, 575, 462, 591)),
        _l("Good with bread and desserts.",
           "Se le da bien el pan y los postres.", (334, 589, 482, 605)),
        _l("Level 1 IC writing.", "Nivel 1 IC escritura.", (574, 561, 662, 577)),
        _l("Look at him pretend he knows",
           "M\u00edralo fingir que sabe", (574, 575, 717, 591)),
        _l("how to use a pen and paper.",
           "usar l\u00e1piz y papel.", (574, 589, 722, 605)),
    ],
    # --- CREATION 1 (3/3) -------------------------------------------------
    "287bb000": [
        _l("~ Creation ~", "~ Creaci\u00f3n ~", (203, 290, 298, 312)),
        _l("Cooking", "Cocina", (183, 314, 237, 331)),
        _l("Creating..", "Creando..", (298, 316, 357, 333)),
        _l("~ Personal ~", "~ Personal ~", (863, 290, 957, 312)),
        _l("Success!", "\u00a1\u00c9xito!", (545, 296, 630, 324)),
        _l("Failure!", "\u00a1Fracaso!", (545, 360, 630, 388)),
        _l("Required Materials", "Materiales necesarios", (183, 445, 292, 463)),
        _l("Description", "Descripci\u00f3n", (183, 523, 246, 541)),
        _l("Details", "Detalles", (253, 523, 302, 541)),
        _l("Fruit oil extracted from\nberries. Used in food as\nwell as in medicine.",
           "Aceite de fruta extra\u00eddo\nde bayas. Se usa en comida\ny en medicina.", (183, 538, 335, 585)),
    ],
    # --- PARTY SETUP (1/2) ------------------------------------------------
    "28800000": [
        _l("Set and replace party members.", "Asigna y cambia miembros del grupo.", (198, 260, 358, 278)),
        _l("Info", "Info", (972, 288, 997, 306)),
        _l("Confirm", "Confirmar", (1012, 288, 1052, 306)),
        _l("Party A   Manage the party.", "Grupo A   Gestiona el grupo.", (353, 410, 468, 428)),
        _l("Leader", "L\u00edder", (353, 426, 388, 444)),
        _l("Empty   Empty   Empty", "Vac\u00edo   Vac\u00edo   Vac\u00edo", (396, 435, 472, 453)),
        _l("Remove", "Quitar", (533, 410, 578, 428)),
        _l("Party B", "Grupo B", (353, 455, 393, 473)),
        _l("Leader", "L\u00edder", (353, 471, 388, 489)),
        _l("Party C", "Grupo C", (353, 500, 393, 518)),
        _l("Leader", "L\u00edder", (353, 516, 388, 534)),
        _l("Party A   Manage the party.", "Grupo A   Gestiona el grupo.", (728, 306, 843, 324)),
        _l("Leader", "L\u00edder", (728, 322, 763, 340)),
        _l("Party B", "Grupo B", (728, 378, 768, 396)),
        _l("Leader", "L\u00edder", (728, 394, 763, 412)),
        _l("Party C", "Grupo C", (728, 452, 768, 470)),
        _l("Leader", "L\u00edder", (728, 468, 763, 486)),
    ],
    # --- PARTY SETUP (2/2) ------------------------------------------------
    "28845000": [
        _l("Info", "Info", (598, 300, 623, 318)),
        _l("Confirm", "Confirmar", (632, 300, 672, 318)),
        _l("Party A   Manage the party.", "Grupo A   Gestiona el grupo.", (168, 316, 283, 334)),
        _l("Leader", "L\u00edder", (168, 332, 203, 350)),
        _l("Empty   Empty   Empty", "Vac\u00edo   Vac\u00edo   Vac\u00edo", (248, 336, 324, 354)),
        _l("Remove", "Quitar", (450, 343, 495, 361)),
        _l("Party B   Manage the party.", "Grupo B   Gestiona el grupo.", (888, 426, 1003, 444)),
        _l("Leader", "L\u00edder", (888, 442, 923, 460)),
        _l("Party C", "Grupo C", (168, 488, 208, 506)),
        _l("Leader", "L\u00edder", (168, 504, 203, 522)),
        _l("(Secondary)", "(Secundario)", (578, 488, 702, 522)),
        _l("Aya (Secondary)", "Aya (Secundario)", (508, 554, 598, 572)),
    ],
    # --- MULTIPLE PARTY SETUP (1/1) --------------------------------------
    "2888a000": [
        _l("Info", "Info", (972, 303, 997, 321)),
        _l("Confirm", "Confirmar", (1012, 303, 1052, 321)),
        _l("Destroy the Crystals", "Destruye los cristales", (198, 294, 312, 312)),
        _l("Leader", "L\u00edder", (118, 308, 153, 326)),
        _l("Empty   Empty", "Vac\u00edo   Vac\u00edo", (183, 318, 242, 336)),
        _l("Remove", "Quitar", (338, 316, 383, 334)),
        _l("Party B   Destroy the Crystals", "Grupo B   Destruye los cristales", (118, 390, 293, 408)),
        _l("Leader", "L\u00edder", (118, 406, 153, 424)),
        _l("Party C   Exterminate the Monsters",
           "Grupo C   Extermina a los monstruos", (118, 460, 322, 478)),
        _l("Leader", "L\u00edder", (118, 476, 153, 494)),
        _l("Destroy the Crystals", "Destruye los cristales", (713, 312, 827, 330)),
        _l("Party B   Destroy the Crystals", "Grupo B   Destruye los cristales", (633, 408, 808, 426)),
        _l("Party C   Exterminate the Monsters",
           "Grupo C   Extermina a los monstruos", (633, 488, 837, 506)),
    ],
    # --- MULTIPLE PARTY SETUP (2/2) --------------------------------------
    "288d1800": [
        _l("~ Results ~", "~ Resultados ~", (588, 300, 682, 326)),
        _l("Sub-Party Bonus EXP", "EXP de subgrupo", (440, 330, 578, 348)),
        _l("Sub-Party Bonus Fol", "Fol de subgrupo", (440, 346, 578, 364)),
        _l("Sub-Party Bonus Items", "Objetos de subgrupo", (440, 373, 568, 391)),
        _l("Random Boost Bone", "Hueso de mejora aleatorio", (508, 388, 622, 406)),
        _l("Fool's Cloth", "Tela del necio", (508, 402, 588, 420)),
        _l("Giant Eye", "Ojo de gigante", (508, 416, 572, 434)),
        _l("Holy Water", "Agua bendita", (508, 430, 578, 448)),
        _l("Mysterious Medicine", "Medicina misteriosa", (508, 444, 648, 462)),
        _l("\"Apocalypse of Darkness\"", "\"Apocalipsis de la oscuridad\"", (508, 458, 655, 476)),
        _l("Rank", "Rango", (770, 518, 810, 536)),
        _l("Book", "Libro", (795, 563, 832, 581)),
    ],
    # --- HEALING REQUEST --------------------------------------------------
    "28a8b000": [
        _l("Magic", "Magia", (538, 280, 582, 298)),
        _l("Lv. 2", "Nv. 2", (518, 290, 552, 308)),
    ],
    # --- CONNECT 2 (1/2) --------------------------------------------------
    "28bb9000": [
        _l("Talk", "Hablar", (263, 538, 302, 557)),
        _l("Free", "Libre", (263, 560, 307, 579)),
        _l("CONNECT", "CONEXI\u00d3N", (878, 476, 963, 502)),
        _l("Lv. 2", "Nv. 2", (898, 328, 937, 346)),
        _l("Lv. 2", "Nv. 2", (898, 483, 937, 501)),
    ],
    # --- CONNECT 2 (2/2) --------------------------------------------------
    "28c01800": [
        _l("Forgetful dog", "Perro olvidadizo", (93, 466, 177, 484)),
        _l("Talk", "Hablar", (93, 480, 132, 498)),
        _l("Free", "Libre", (93, 498, 137, 516)),
        _l("Who's this? Rico's friend?", "\u00bfQui\u00e9n es este? \u00bfEl amigo de Rico?", (608, 508, 802, 530)),
    ],
    # --- CREATION 2 (1/2) -------------------------------------------------
    "28c4e000": [
        _l("Perform enchantment creation.", "Realizar creaci\u00f3n de encantamiento.", (360, 295, 512, 315)),
        _l("Items", "Objetos", (426, 396, 470, 416)),
        _l("Enchant", "Encantar", (426, 413, 480, 433)),
        _l("~ Enchant ~", "~ Encantar ~", (841, 281, 942, 305)),
        _l("Enchantment", "Encantamiento", (788, 312, 860, 330)),
        _l("ATK +20", "ATQ +20", (808, 328, 862, 346)),
        _l("HIT +5%", "PUN +5%", (808, 342, 862, 360)),
        _l("AGL +5%", "AGI +5%", (808, 356, 862, 374)),
        _l("Fire attack", "Ataque de fuego", (808, 370, 868, 388)),
        _l("Water attack", "Ataque de agua", (808, 384, 878, 402)),
        _l("Required Materials", "Materiales necesarios", (788, 423, 897, 441)),
        _l("Junk", "Chatarra", (788, 438, 828, 456)),
        _l("Sandstone", "Arenisca", (788, 453, 850, 471)),
        _l("Description", "Descripci\u00f3n", (788, 496, 850, 514)),
        _l("Increases ATK by 20", "Aumenta ATQ en 20", (788, 512, 912, 530)),
        _l("(10 minutes)", "(10 minutos)", (788, 526, 868, 544)),
    ],
    # --- CREATION 2 (2/2) -------------------------------------------------
    "28c94800": [
        _l("~ Enchant ~", "~ Encantar ~", (153, 276, 252, 300)),
        _l("Enchantment", "Encantamiento", (93, 310, 167, 328)),
        _l("ATK +20", "ATQ +20", (113, 326, 167, 344)),
        _l("HIT +5%", "PUN +5%", (113, 340, 167, 358)),
        _l("AGL +5%", "AGI +5%", (113, 354, 167, 372)),
        _l("Fire attack", "Ataque de fuego", (113, 368, 173, 386)),
        _l("Water attack", "Ataque de agua", (113, 382, 183, 400)),
        _l("Required Materials", "Materiales necesarios", (93, 418, 202, 436)),
        _l("Junk", "Chatarra", (93, 433, 133, 451)),
        _l("Sandstone", "Arenisca", (93, 448, 155, 466)),
        _l("Description", "Descripci\u00f3n", (93, 493, 155, 511)),
        _l("Increases ATK by 20", "Aumenta ATQ en 20", (93, 508, 217, 526)),
        _l("(10 minutes)", "(10 minutos)", (93, 522, 173, 540)),
        _l("Display characters status", "Muestra el estado de los personajes", (408, 295, 548, 313)),
        _l("~ Status ~", "~ Estado ~", (376, 276, 457, 300)),
        _l("Display characters status", "Muestra el estado de los personajes", (606, 295, 746, 313)),
        _l("~ Status ~", "~ Estado ~", (573, 276, 654, 300)),
        _l("Display characters status", "Muestra el estado de los personajes", (953, 295, 1093, 313)),
        _l("~ Status ~", "~ Estado ~", (918, 276, 999, 300)),
        _l("Display characters status", "Muestra el estado de los personajes", (1076, 430, 1216, 448)),
        _l("~ Status ~", "~ Estado ~", (1058, 408, 1139, 432)),
        _l("Success!", "\u00a1\u00c9xito!", (526, 426, 610, 458)),
        _l("Enchantment Bonus", "Bonif. de encantamiento", (916, 426, 1037, 444)),
        _l("ATK +20", "ATQ +20", (916, 440, 970, 458)),
        _l("Fire attack", "Ataque de fuego", (916, 454, 976, 472)),
        _l("Enchantment Bonus", "Bonif. de encantamiento", (1058, 456, 1179, 474)),
        _l("Fire attack", "Ataque de fuego", (1058, 470, 1118, 488)),
    ],
    # --- SPECIAL CONDITIONS 1 --------------------------------------------
    "28ce0000": [
        _l("Castle Prevant Gate", "Puerta del Castillo Prevant", (148, 218, 292, 242)),
        _l("Defense", "Defensa", (198, 298, 258, 316)),
        _l("Attack the Red Knights", "Ataca a los Caballeros Rojos", (898, 298, 1042, 316)),
        _l("Order Jailer", "Carcelero de la Orden", (106, 503, 168, 521)),
        _l("Free", "Libre", (93, 548, 137, 566)),
        _l("Reload", "Recargar", (1152, 523, 1207, 547)),
        _l("ATK", "ATQ", (553, 563, 592, 581)),
        _l("ATK", "ATQ", (758, 563, 797, 581)),
    ],
    # --- GLYPH RATE (2/2): art only (no text) -----------------------------
}


def _reg():
    reg = {}
    for hexid, es in _TITLES.items():
        labels = []
        if es:
            labels.append({"en": "", "es": es, "box": list(TITLE_BOX), "style": "h_title"})
        labels.extend(LABELS.get(hexid.lower(), []))
        reg["help_" + hexid.lower()] = _sc(hexid, "help_%s_es.aif" % hexid.lower(), labels)
    return reg


def _all():
    return _reg()


# --------------------------------------------------------------------------
# Process
# --------------------------------------------------------------------------
def _load(spec):
    original, base = U._load_source(spec)
    img = aif_mod.AifImage(original, base)
    rgba = np.frombuffer(img.to_rgba(), dtype=np.uint8).reshape(img.height, img.width, 4)
    return original, base, img, rgba


def process(key, spec, outdir: Path, preview: bool):
    original, base, img, rgba = _load(spec)
    pil = Image.frombytes("RGBA", (img.width, img.height), rgba.tobytes())
    arr = np.array(pil.convert("RGB"))
    boxes = []
    for lb in spec["labels"]:
        if not lb["es"]:
            continue
        remove_text(arr, lb["box"])
        boxes.append(tuple(lb["box"]))
    pil2 = Image.frombytes("RGB", (img.width, img.height), arr.tobytes()).convert("RGBA")
    for lb in spec["labels"]:
        if not lb["es"]:
            continue
        paint_opaque(pil2, lb["box"], lb["es"], lb.get("style", "h_white"),
                     center=lb.get("center", False))
    out_rgba = pil2.tobytes()
    out = U.encode_aif(original, out_rgba, boxes, base)
    dst = outdir / spec["out"]
    dst.write_bytes(out)
    wrap = U._wrapper_ok(out, base)
    print("%-16s %dx%d %s -> %s (%s)"
          % (key, img.width, img.height, img.format_name, spec["out"],
             "envoltorio OK" if wrap else "envoltorio MAL"))
    if preview:
        bg = pil2.convert("RGB")
        bg.save(outdir / (dst.stem + "_preview.png"))
    return dst


def cmd_list(args):
    for key, spec in _reg().items():
        print("%-18s %s  (%d rotulos)" % (key, spec["source"], len(spec["labels"])))
        for lb in spec["labels"]:
            print("    %-24r -> %-24r %s" % (lb.get("en"), lb["es"], lb["box"]))
    return 0


def cmd_render(args):
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    reg = _reg()
    keys = args.only or list(reg.keys())
    for key in keys:
        if key not in reg:
            print("! clave desconocida:", key, file=sys.stderr)
            continue
        process(key, reg[key], outdir, args.preview)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Traduce pantallas de ayuda del CAMP.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list"); s.set_defaults(func=cmd_list)
    s = sub.add_parser("render")
    s.add_argument("--out", default="extract/f2/ui_es")
    s.add_argument("--only", action="append", default=[])
    s.add_argument("--preview", action="store_true")
    s.set_defaults(func=cmd_render)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
