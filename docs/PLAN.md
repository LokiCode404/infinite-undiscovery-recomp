# PLAN MAESTRO — Traducción al castellano de *Infinite Undiscovery* (Recomp PC)

> **Fichero:** `PLAN-TRADUCCION-INFINITE-UNDISCOVERY-ES.md`
> **Ubicación:** `C:\Users\eleaz\Downloads\`
> **Versión del documento:** 1.0.0
> **Fecha de creación:** 2026-10-07
> **Autor del plan:** sesión de análisis (agente)
> **Estado:** listo para arrancar — **Fase 0 pendiente**
> **Proyecto destino (nuevo):** `C:\Users\eleaz\Downloads\Projects\infinite-undiscovery-es` (propuesto; ver §7.3)

---

## 0. Cómo usar este documento (para una sesión nueva)

Este plan está pensado para **desacoplarse** de la sesión de análisis original y
ejecutarse desde un **directorio de proyecto nuevo**. Para arrancar:

1. Crea/copía el proyecto en el directorio destino (§7.3) o trabaja directamente
   sobre el fork en `Projects\infinite-undiscovery-es`.
2. Abre una sesión de agente **en ese directorio** y pásale este fichero como
   contexto, con un prompt del tipo:

   > «Lee `PLAN-TRADUCCION-INFINITE-UNDISCOVERY-ES.md`. Vamos a ejecutar la
   > **Fase F0**. Pregúntame lo que necesites (ruta del ISO/carpeta del Disco 1,
   > Python, capstone) y déjame el volcado de los recursos `RMD-` descrito en la
   > fase.»

3. Ejecuta las fases **en orden**. Las fases `F0–F3` son de **análisis** (solo
   requieren Python + tu copia legal del juego). Las fases `F4–F8` requieren
   **toolchain de compilación** y construyen el mod.
4. La §8 contiene el detalle por fase con: objetivo, tareas, comandos,
   entregables, **criterio de cierre**, riesgos y estimación.
5. La §13 (Anexos) reúne comandos, rutas de referencia y un glosario.

**Regla de oro del proyecto:** *nada de assets del juego versionados*. El
repositorio de trabajo contiene **solo código, herramientas, tablas de
traducción y documentación**. Los volcados de texto (que derivan del juego) se
mantienen **fuera** del control de versiones (`.gitignore`).

---

## 1. Resumen ejecutivo

Se quiere **traducir al castellano** *Infinite Undiscovery* (Xbox 360, 2008,
tri-Ace / Square Enix) jugando a la **recompilación nativa para PC**
(`doc-haz/infinite-undiscovery-recomp`), **a través de un mod**.

**Veredicto: es posible, pero no es un parche “drop-in”.** Es un proyecto de
*modding* sobre un **fork del recomp** que consta de dos partes:

1. **Ingeniería inversa (riesgo principal, se hace ya con Python):** el texto del
   juego vive en recursos `RMD-` (“message resource”: atlas de fuente + datos de
   mensaje) cuyo **formato de texto aún no está decodificado** por la comunidad.
   Hay que decodificarlo y localizar la función(es) del juego que resuelven
   `ID → cadena`.
2. **Mod de runtime (hook):** el recomp ya engancha funciones del juego por
   dirección (`function_dispatcher()->SetFunction`). Se añade un módulo que
   intercepta la resolución de mensajes y sustituye el texto por una tabla ES
   (`es.json`) cargada del disco portátil. **No se tocan los assets originales**,
   por lo que pasan las verificaciones de integridad del recomp.

**Datos duros que condicionan todo:**

- La **edición europea/PAL es solo inglés** (no hay español oficial). El
  bilingüe EN/ES del recomp es **solo su propia UI**, no el juego.
- El recomp **verifica SHA-256 de `ud1.bin`/`ud2.bin`** al instalar y detecta
  cambios después (`src/asset_setup.cpp`). Por eso se elige el **hook**, no el
  parcheo de binarios.
- El **toolchain de compilación no está instalado** aún: ReXGlue SDK v0.10.0
  **desde fuente** + CMake/Ninja/Clang/MSVC. Se monta en `F4`, tras confirmar
  la forma del texto en `F1`.

**Alcance acordado:** **todo el texto, incluido el guion** (diálogos +
cinemáticas + menús + ítems + tutoriales).

---

## 2. Objetivo y alcance

### 2.1 Objetivo

Disponer de una versión jugable de *Infinite Undiscovery Recomp* con **todo el
texto en castellano**, distribuible como **mod/fork** (BSD-3 respetado) que
requiere que el usuario aporte su **copia legítima** del juego.

### 2.2 Dentro de alcance

- Diálogos y mensajes de guion (incluidas cinemáticas con subtítulos).
- Menús, HUD, descripciones de ítems/habilidades, tutoriales, textos de sistema.
- Herramientas: pipeline de extracción/traducción/inyección + validador.
- Documentación técnica de la ingeniería inversa (formatos, direcciones).

### 2.3 Fuera de alcance (explícito)

- Doblaje de voz (el juego es *English-only* en texto y voz; USA-UNDUB trae voz
  japonesa). Este plan **no** produce audio en español.
- Redistribuir cualquier asset, ISO, `default.xex`, `ud1.bin`, `ud2.bin`, DLC,
  saves o código generado del juego.
- Emulación: se trabaja sobre la **recompilación nativa**, no sobre emulador.
- Otras plataformas (el recomp es **Windows x64 + D3D12**).

### 2.4 Principios

1. **No tocar los assets originales** si es evitable (usar hook).
2. **Data-driven**: las traducciones viven en ficheros (`es.json`) editables sin
   recompilar.
3. **Trazable**: cada hallazgo de RE lleva su evidencia (comando + resultado).
4. **Reproducible**: entorno y versiones fijadas.
5. **Legalmente limpio**: sin assets del juego en el repo.

---

## 3. Decisiones tomadas (ADR resumidos)

| ID | Decisión | Motivo |
|---|---|---|
| ADR-01 | **Ruta A: hook en runtime** sobre un fork del recomp | No toca assets → pasa la verificación de integridad; mantenible; sigue el patrón ya usado por el proyecto (`save_anywhere`, `disc_swap`). |
| ADR-02 | **Alcance total** (guion incluido) desde el principio | Evita rediseñar el pipeline; el guion es el grueso del `RMD-`. |
| ADR-03 | **Traducciones en `es.json`** cargado en caliente | Iterar sin recompilar por cada corrección de texto. |
| ADR-04 | **RE primero, build después** | El toolchain es costoso y no aporta hasta saber qué enganchar. F0–F3 en Python. |
| ADR-05 | Trabajar sobre **EU/PAL y USA** (mismo `.text` y direcciones de hook) | El proyecto documenta que el payload ejecutable relevante es idéntico; un hook sirve para ambas. |
| ADR-06 | **Nada de assets del juego en el repo** | Legal + política del ecosistema. |

---

## 4. Reconocimiento: repositorios y activos analizados

### 4.1 Repositorios

| Repo | Rama | Rol | Licencia | Uso en el proyecto |
|---|---|---|---|---|
| `doc-haz/infinite-undiscovery-recomp` | `main` | Recompilación nativa Windows x64; RC pública `v1.0.0-rc1` | BSD-3-Clause | **Base del fork.** Fuente del hook, validación de assets, app. |
| `vs-sr-dev/pc-infiniteundiscovery` | `master` | Notas de RE + especificación de formatos + 20 herramientas Python (sin datos del juego) | — (sin licencia declarada) | **Herramientas de análisis** y especificaciones de formato. |
| `doc-haz/iu-save-bridge` | `main` | Editor de saves (C#), EN/ES; `resources/ItemNames.txt` (1023 ítems) | — | Fuente de **nombres de ítems** y referencia de términos. |
| `freefrank/LostOdysseyRecomp` | — | Recomp análogo (referencia de flujo/portabilidad) | — | Precedente metodológico. |
| ReXGlue / XenonRecomp | `v0.10.0` (`f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`) | Toolchain + runtime (`rexruntime.dll`, `rexgpu-xenos.dll`) | (ver `LICENSES/`) | Mecanismo de hooks (`function_dispatcher`) y build. |

### 4.2 El juego

- **Título:** *Infinite Undiscovery* (tri-Ace / Square Enix, Xbox 360, 2008).
- **Motor:** **ASKA** (“tri-Ace Superlative Knowledge-based Architecture”).
- **Title ID:** `535107DB`.
- **Ediciones soportadas por el recomp:** `USA`, `USA-UNDUB` (voz japonesa, texto
  USA), `EUROPE` (PAL), `JAPAN`, `ASIA`.
- **Ficheros raíz esperados por disco:** `default.xex`, `ud1.bin`, `ud2.bin`.
- **Dos discos**; el recomp conserva los assets de cada disco por separado.

### 4.3 Dónde está el texto (hallazgo central)

El censo de recursos (`pc-infiniteundiscovery/docs/census.txt`) identifica:

```
RMD-  = "message resource -- font atlas (AIF) plus text data"
```

| Contenedor | `RMD-` |
|---|---|
| Disco 1 `ud1.bin` | 5 |
| Disco 1 `ud2.bin` | 31 |
| Disco 2 `ud1.bin` | 14 |
| Disco 2 `ud2.bin` | 31 |

- La mitad imagen es un **atlas de fuente `AIF`** con glifos de **latino, kana y
  kanji** (`docs/formats/aif.md` §6).
- En 3 flujos `RMD-` aparece la cadena de *build tool*
  `MessageConvertLib_1.0.0.0` (`docs/sessions/session-04.md`), señal de que el
  juego **convierte** un formato de mensaje fuente al formato de runtime.
- **La mitad “texto” del `RMD-` no está decodificada** por la comunidad: no hay
  ficha de formato ni lector, ni figura entre los formatos “resueltos”.

Además, hay **cadenas de UI/índice potenciales** en el `.xex` (el repo de RE
recupera strings del ejecutable) y los **nombres de ítems** viven, para el editor
de saves, en `iu-save-bridge/resources/ItemNames.txt`.

### 4.4 Formatos relevantes ya resueltos por la comunidad (para reutilizar)

`XDVDFS`, `NORM/MRON` (contenedor), `SLZ` (XCompress en 360), `AIF` (texturas),
`ASF` (escenas), `AAF` (animación), `ACF` (colisión), `SNC` (guion de escena),
`NODE` (navmesh), `AAC` (audio), `XEX2`, `XDBF`. Todo ello está documentado en
`pc-infiniteundiscovery/docs/formats/`.

### 4.5 Réplica de herramientas (análisis)

| Herramienta | Función para este plan |
|---|---|
| `xdvdfs.py` | Leer el sistema de ficheros del disco / extraer carpetas. |
| `mron.py` | Recorrer `ud1.bin`/`ud2.bin` y extraer payloads por tag (`RMD-`), descomprimiendo. |
| `slz.py` | Descompresión `SLZ`/XCompress. |
| `aif.py` | Leer el atlas de fuente `AIF` y exportar PNG. |
| `xex.py` | Desencriptar/extraer el `default.xex` → PE. |
| `disasm.py` | xrefs y desensamblado (MIPS/PPC) — **requiere `capstone`**. |
| `xdbf.py` | Metadatos del título (logros multiidioma, tablas de strings). |
| `aska.py` | Clasificar payloads por motor. |

> Estado del entorno medido: **Python 3.14.6 presente**; `capstone` **no instalado**
> (solo lo usa `disasm.py`). El resto de herramientas son **solo stdlib**.

---

## 5. Viabilidad, restricciones y límites

### 5.1 ¿Por qué es viable?

- El recomp expone un **mecanismo de hooks probado**:
  `runtime->function_dispatcher()->SetFunction(dir, fn)` / `GetFunction`,
  `PatchIAT`, y llamadas a funciones invitadas con `DECLARE_REX_FUNC(sub_…)`.
- El juego ejecuta **su propio código** recompilado, así que basta con
  interceptar la **resolución de mensajes** (una función) y devolver texto
  distinto.
- El texto está localizado en recursos concretos (`RMD-`), que se pueden volcar y
  analizar sin tocar el juego.

### 5.2 Restricciones reales

1. **Formato `RMD-` desconocido** → riesgo principal (F1).
2. **Cobertura de glifos** para acentos castellanos (`á é í ó ú ü ñ ¿ ¡`) en el
   atlas → si faltan, hay que añadirlos o evitar acentos (F3).
3. **Validación de integridad de assets** del recomp (`src/asset_setup.cpp`):
   `CanLaunch`, `ExpectedBinHash`, `Ready` (rechaza cambios por tamaño/fecha y
   hash). **El hook evita este problema**; el parcheo de BINs lo sufre.
4. **Toolchain pesado** (ReXGlue SDK desde fuente, hashes fijados) → F4.
5. **Mantenimiento**: el recomp evoluciona; el fork debe reaplicar parches.

### 5.3 Límites (qué NO demuestra este plan)

- Un volcado correcto de mensajes **no** prueba que la fuente renderice todos los
  caracteres.
- Que una cadena se sustituya en pantalla **no** prueba que no haya rutas de
  texto alternativas (tooltips dinámicos, texto compuesto en runtime, imágenes
  con texto).
- El recomp es un **RC**: puede haber bugs de base ajenos a la traducción.

---

## 6. Arquitectura propuesta del mod

### 6.1 Visión general

```
InfiniteUndiscoveryRecomp.exe        (fork con módulo de traducción)
        │
        │  runtime->function_dispatcher()->SetFunction(<dir función mensajes>, Hook_Message)
        ▼
┌──────────────────────────┐        ┌───────────────────────────┐
│  Motor del juego (ASKA)  │        │  iu::translation          │
│  resuelve ID → cadena    │ ◄────► │  - hook resolución/print  │
│  desde recursos RMD-     │        │  - carga es.json          │
└──────────────────────────┘        │  - lookup id → texto ES    │
        │                           │  - gestión de buffers      │
        ▼                           └───────────┬───────────────┘
   Render (font atlas AIF)                     │
                                    <portable>\translation\es.json
```

### 6.2 Componentes

1. **Módulo de hook** (`src/translation.h` / `.cpp` en el fork):
   intercepta la función de mensajes y devuelve el texto traducido. Sigue el
   patrón de `src/disc_swap.h` y `src/disc2_io_trace.h`.
2. **Cargador de traducción**: lee `<portable>\translation\es.json` (o `.toml`),
   con mapa `id → cadena`. Recarga en caliente (opcional).
3. **Tabla de traducción** (`translation/es.json`, versionable, sin assets del
   juego): texto original + texto ES + metadatos (contexto, longitud máx.).
4. **Pipeline** (`tools/`): extraer mensajes → traducir → validar → empaquetar.
5. **Validador**: comprueba longitud/reflow/glifos soportados antes de build.

### 6.3 Estrategia de hook (a decidir en F2 según lo que se encuentre)

- **H1 — Función de resolución `ID → char*`** (preferida): se intercepta, se
  busca el `id` en `es.json` y se devuelve el buffer traducido. Limpio.
- **H2 — Punto de carga de `RMD-`**: se intercepta la lectura del recurso y se
  sustituye su contenido en memoria por el traducido (útil si el texto no se
  resuelve por ID único).
- **H3 — Capa de render de texto**: se intercepta la función que convierte
  cadena → glifos (último recurso, más frágil).
- **H4 (si el texto va por índices a glifos y no hay función de cadena)**:
  mapear a índices de glifos; requiere tocar el atlas (F3).

### 6.4 Esqueleto de código (pseudocódigo, patrón del proyecto)

```cpp
// src/translation.h  (borrador; firma real se fija en F2)
#pragma once
#include <rex/system/function_dispatcher.h>
#include "iu_trace.h"

namespace iu::translation {

// Direcciones y firma reales se determinan en F2.
inline PPCRegister* g_original = nullptr;   // puntero a la función original
extern bool g_enabled;

void Hook_Message(PPCRegister& r3, PPCRegister& r4 /*, …*/);

inline bool Install(rex::Runtime* runtime) {
  if (!runtime || !runtime->function_dispatcher()) return false;
  // runtime->function_dispatcher()->SetFunction(0xXXXXXXXX, Hook_Message);
  return true;
}

}  // namespace iu::translation
```

Punto de enganche en el ciclo de vida: `src/infinite_undiscovery_app.h`
(junto a `iu::disc_swap::Install(runtime(), …)` y `iu::disc2_io::Install(runtime())`).

Interruptor: `REXCVAR_DEFINE_BOOL(translation, true, "Translation", "…")` al estilo
de `src/main.cpp`.

---

## 7. Entorno: cadenas de herramientas y directorio de proyecto

### 7.1 Cadena de análisis (F0–F3) — disponible ya

- **Python 3** (tienes 3.14.6).
- `pip install capstone` (solo para `disasm.py`, en F2).
- Tu **copia legal** del/los disco(s) (ISO XDVDFS o carpeta extraída).
- Herramientas: clonar `vs-sr-dev/pc-infiniteundiscovery`.

### 7.2 Cadena de compilación (F4+) — a instalar

Requisitos (según `recomp/docs/RELEASE-BUILD.md` y `README`):

- **Windows 10/11 x64**.
- **ReXGlue SDK v0.10.0 desde fuente**, tag `v0.10.0`, commit
  `f5337cdc947ff6d4c4196737e2c807a48f2a1fc2` (NO el SDK precompilado antiguo; el
  recomp rechaza esos DLL por hash).
- **CMake ≥ 3.25**, **Ninja**, **Clang/LLVM**, **MSVC + Windows SDK**.
- Hashes DLL de release exigidos por `cmake/verify_rexglue_dlls.cmake`:
  ```
  25C0F2D1DBB7FE3147FC59E22C9A3E4C764DC2E0B0C6877FC86F0DA499E0F67F  rexruntime.dll
  98CEF22E2AC1667F3A42910DD7474C0409BBEF7DB7599B3A48DF1EDBB0739A2D  rexgpu-xenos.dll
  ```
- La recompilación del juego requiere **código generado localmente** desde tu
  `default.xex` con `run-codegen.ps1` (usa `tools/rexglue/rexglue.exe`, que el
  propio proyecto espera junto a la SDK).
- Runtime de escritorio: **Direct3D 12** + *Microsoft Visual C++ Redistributable
  2015-2022 (x64)*.

### 7.3 Directorio de proyecto propuesto

```
C:\Users\eleaz\Downloads\Projects\infinite-undiscovery-es\
├─ PLAN-TRADUCCION-INFINITE-UNDISCOVERY-ES.md   (copia de este plan)
├─ README.md                                     (estado y cómo usar)
├─ .gitignore                                    (excluye volcados y assets)
├─ docs/
│  ├─ re/                                        (hallazgos de ingeniería inversa)
│  │  ├─ rmd-format.md
│  │  ├─ message-subsystem.md
│  │  └─ glyph-coverage.md
│  └─ build.md
├─ tools/                                        (Python: extraer/validar/empaquetar)
│  ├─ extract_rmd.py
│  ├─ dump_messages.py
│  ├─ validate_translation.py
│  └─ vendor/pc-infiniteundiscovery/             (submódulo o copia de las tools)
├─ translation/
│  ├─ es.json                                    (id → texto castellano)
│  └─ glossary.md                                (términos fijados)
├─ mod/                                          (parches sobre el fork del recomp)
│  └─ src/translation.{h,cpp}
└─ dist/                                         (salida; NO versionada)
```

**`.gitignore` mínimo**: `dist/`, `*.iso`, `*.bin`, `*.xex`, `extract/`,
`*.es.json.bak`, volcados de mensajes originales.

---

## 8. Plan por fases

> Convención: `[ ]` pendiente · `[~]` en curso · `[x]` hecho · `[!]` bloqueado.
> Cada fase tiene **criterio de cierre** verificable.

### F0 — Entorno de análisis y aislamiento de `RMD-`  `[x]`

**Objetivo:** dejar listos los `RMD-` de los dos discos, con atlas y datos de
mensaje separados.

**Tareas**
1. Crear el directorio de proyecto (§7.3) y el `.gitignore`.
2. Instalar dependencias: `pip install capstone`.
3. Clonar/integrar `pc-infiniteundiscovery` en `tools/vendor/`.
4. Con `xdvdfs.py`, localizar el/los `ud1.bin`/`ud2.bin` en el ISO (offsets en
   §13.1) o usar la carpeta extraída.
5. Con `mron.py`, extraer los payloads `RMD-` con `--decompress`.
6. Con `aif.py`, exportar el atlas de cada `RMD-` a PNG y separar los bytes que
   siguen al `AIF`.

**Comandos (ejemplo, ajustar rutas)**
```bash
python tools/xdvdfs.py list "D1.iso" --csv d1.csv
python tools/mron.py extract "D1.iso" --offset 0x6589E800 --length 2207584256 \
       --tag RMD- --decompress extract/d1_ud1
python tools/mron.py extract "D1.iso" --offset 0xE99D0000 --length 2800330752 \
       --tag RMD- --decompress extract/d1_ud2
python tools/aif.py png extract/d1_ud1/<...>.aif atlas.png
```

**Entregables:** `extract/**/RMD-*`, atlas PNG, notas en `docs/re/rmd-format.md`.

**Criterio de cierre:** todos los `RMD-` identificados en el censo están
extraídos y cada uno tiene su atlas PNG y su cola de bytes aislada.

**Riesgo:** offsets de región distintos a EU → resolver con `xdvdfs.py info`/censo.

**Estimación:** 0,5–1 día.

---

### F1 — Decodificar el “message resource” (nudo del proyecto)  `[x]`

**Objetivo:** entender y documentar la **mitad texto** del `RMD-` y **volcar
todos los mensajes** de forma legible.

**Tareas**
1. Analizar la cola de bytes tras el `AIF`: magic interno, cabeceras, tamaño,
   posible tabla de offsets/IDs, contadores.
2. Determinar el **encoding** probando hipótesis: ASCII, Shift-JIS, UTF-16LE,
   o **índices a celdas del atlas** (grid del `AIF`).
3. Correlacionar con `MessageConvertLib_1.0.0.0` y con el atlas (número de
   glifos vs. rango de códigos).
4. Escribir `(legacy exploration tool, removed)`: `RMD- → (id, texto)`.
5. Volcar **todos** los mensajes (Disc 1 y 2) a `extract/messages/` (fuera de git).

**Entregables:** `docs/re/rmd-format.md` (especificación), `(legacy exploration tool, removed)`,
volcado completo.

**Criterio de cierre:** volcado legible y consistente (mensajes con sentido en
inglés) para los 4 contenedores, y una hipótesis de encoding con evidencia.

**Riesgo: ALTO.** Si el texto es **índices a glifos**, el “volcado” requiere
mapear celdas del atlas → caracteres; podría necesitar OCR o la tabla de la
herramienta de build. Plan B: decodificar al menos la estructura y trabajar con
`ID → índices` (la traducción mapea a índices y se restringe a glifos existentes).

**Estimación:** 2–5 días (depende del encoding).

---

### F2 — Localizar el subsistema de mensajes en `default.xex`  `[x]`

**Objetivo:** hallar la(s) función(es) del juego que resuelven/renderizan
mensajes y su firma, para diseñar el hook.

**Tareas**
1. `python tools/xex.py extract default.xex default.exe` (desencriptar).
2. Con `disasm.py` (`--base 0x82000000`), hacer **xref** desde:
   - la cadena `MessageConvertLib_1.0.0.0`,
   - las cadenas de rutas/archivo de los `RMD-` (`game:\...`),
   - los textos de UI si procede.
3. Identificar la función de **resolución `ID → cadena`** y/o la de **carga de
   `RMD-`**; documentar dirección, argumentos y valor de retorno.
4. Confirmar estabilidad de direcciones entre **EU/PAL y USA** (el proyecto dice
   que el `.text` relevante es idéntico).
5. Elegir estrategia de hook (H1/H2/H3/H4 de §6.3).

**Entregables:** `docs/re/message-subsystem.md` con direcciones y firma;
decisión de hook.

**Criterio de cierre:** dirección(es) y firma documentadas, con la cadena de
llamada trazada desde una xref hasta la resolución de mensaje.

**Riesgo:** medio-alto (código optimizado, funciones grandes). Mitigación:
`disasm.py` + RTTI (`rtti.py`) + strings.

**Estimación:** 1–3 días.

---

### F3 — Cobertura de glifos para castellano  `[~]`

**Objetivo:** saber si el atlas `AIF` puede renderizar `á é í ó ú ü ñ ¿ ¡` (y
mayúsculas).

**Tareas**
1. Inspeccionar los atlas PNG (F0) y el mapa de celdas.
2. Probar si existen glifos acentuados (latino extendido) además de ASCII.
3. Documentar el layout de la grid (celdas, tamaño, orden) y si hay margen.
4. Decidir: (a) usar acentos si existen; (b) **añadir glifos** al `AIF` +
   metadatos; (c) plan C sin acentos (peor calidad, evitable).

**Entregables:** `docs/re/glyph-coverage.md` + conclusión.

**Criterio de cierre:** decisión sobre acentos con evidencia visual y de datos.

**Riesgo:** alto si faltan glifos (tocar `AIF` es más trabajo). **Estimación:**
0,5–2 días.

---

### F4 — Toolchain y build limpio del recomp  `[x]`

**Objetivo:** compilar la versión **stock** del recomp desde fuente, sin cambios.

**Tareas**
1. Instalar CMake, Ninja, Clang/LLVM, MSVC + Windows SDK.
2. Clonar ReXGlue en el commit fijado y **construir el install tree** (Release).
3. Forkear `infinite-undiscovery-recomp` en `infinite-undiscovery-es`.
4. Proveer tu `default.xex` legítimo y ejecutar **codegen** (`run-codegen.ps1`)
   para generar el código del juego localmente.
5. Configurar y compilar (`CMakePresets.json` del proyecto).
6. Ejecutar con tus assets (setup wizard) y **verificar arranque**.

**Entregables:** `InfiniteUndiscoveryRecomp.exe` compilado; `docs/build.md`.

**Criterio de cierre:** el binario compilado por ti arranca y carga el juego.

**Riesgo:** alto (SDK desde fuente, versión de compilador, hashes de DLL).
**Estimación:** 2–5 días.

---

### F5 — Prueba de concepto del hook  `[~]`

**Objetivo:** cambiar **un** mensaje concreto por “HOLA” en pantalla.

**Tareas**
1. Añadir `mod/src/translation.{h,cpp}` con un hook trivial (H1/H2/H3 de F2).
2. Instalar el hook en `infinite_undiscovery_app.h` + `REXCVAR` de interruptor.
3. Cargar una tabla mínima y sustituir **un** `id` conocido (de F1).
4. Trazar con el framework `iu::trace` (categoría nueva) para confirmar el paso
   por el hook.

**Entregables:** diff del fork + evidencia (captura/log).

**Criterio de cierre:** el texto aparece cambiado en el juego.

**Riesgo:** medio. **Estimación:** 1–2 días.

---

### F6 — Pipeline de traducción + menús/ítems  `[ ]`

**Objetivo:** traducir **menús, HUD e ítems** de forma data-driven.

**Tareas**
1. `tools/validate_translation.py`: longitudes, reflow, glifos soportados,
   placeholders/iconos incrustados.
2. `translation/es.json` con el esquema `{ id, en, es, ctx, max_len }`.
3. Traducción asistida (con revisión humana) de menús/ítems; término fijado en
   `glossary.md` (aprovechar `iu-save-bridge/resources/ItemNames.txt`).
4. Recarga en caliente de `es.json` (sin recompilar).
5. QA de pantallas de menú.

**Entregables:** pipeline + `es.json` (menús/ítems) + screenshots.

**Criterio de cierre:** menús e ítems en castellano, sin desbordes ni glifos
faltantes.

**Estimación:** 3–7 días.

---

### F7 — Guion completo  `[ ]`

**Objetivo:** traducir **todo** el texto restante (diálogos, cinemáticas,
tutoriales, sistema).

**Tareas**
1. Volcar todo el guion (F1) y traducirlo por contexto.
2. QA de diálogos: reflow, velocidad de aparición, cajas con nombre de
   personaje, subtítulos de cinemáticas.
3. Pasada de juego amplia (o por capítulos) con checklist.

**Entregables:** `es.json` completo + informe de QA.

**Criterio de cierre:** partida en castellano sin inglés residual en las zonas
verificadas (documentar cobertura).

**Riesgo:** volumen + formato (longitud). **Estimación:** 2–6 semanas (según
método de traducción e intensidad de QA).

---

### F8 — Empaquetado, distribución y legal  `[ ]`

**Objetivo:** entregar el mod de forma instalable y legal.

**Tareas**
1. Página de release: mod = (a) instrucciones + `es.json` + parche de código, o
   (b) binario del fork compilado.
2. Documentar requisitos (tu copia del juego, VC++ redist, D3D12).
3. Mantener el **aviso legal** (no se distribuyen assets).
4. `CHANGELOG` y política de actualización con el upstream.

**Entregables:** `dist/` reproducible + `README` de instalación.

**Criterio de cierre:** una persona con su copia legal puede instalar y jugar en
castellano siguiendo el README.

**Estimación:** 1–2 días.

---

### Resumen de fases

| Fase | Tipo | Requiere toolchain C++ | Estado | Estimación | Riesgo |
|---|---|---|---|---|---|
| F0 | Análisis | No | **Hecho** (81 `RMD-`, atlas PNG) | 0,5–1 d | Bajo |
| F1 | Análisis (nudo) | No | **Hecho** (71 386 mensajes, round-trip 100%) | 2–5 d | **Alto** |
| F2 | Análisis | No | **Hecho** (parser/decoder/render localizados) | 1–3 d | Medio-alto |
| F3 | Análisis | No | **En curso** (acentos en el atlas DXT) | 0,5–2 d | Alto |
| F4 | Build | Sí | **Hecho** (recomp v0.10.0 compila y arranca) | 2–5 d | Alto |
| F5 | Mod (PoC) | Sí | **En curso** (hook inyecta texto; validando en vivo) | 1–2 d | Medio |
| F6 | Traducción (UI) | Sí | En curso (**texto+charmap 100 % listos**) | 3–7 d | Medio |
| F7 | Traducción (guion) | Sí | Pendiente | 2–6 sem | Medio |
| F8 | Entrega | Sí | Pendiente | 1–2 d | Bajo |

> El **camino crítico** era **F0 → F1 → F2**: ya cerrado. Ahora el cuello de botella
> es el **charmap por banco** (F1→F6) y la **cobertura de glifos** (F3).
>
> **Hito (texto):** los **71 386 mensajes** de los 81 bancos están decodificados a
> texto legible (`extract/messages/text/<stem>.txt`), con **charmap por banco**
> (`translation/charmaps/<stem>.json`), **100 % de glifos** de la fuente principal y
> **clasificación por contexto** (diálogo/menú/sistema/objeto/…). Ver `docs/re/charmap.md`.
> Falta únicamente el texto de un recurso de **fuente pequeña** (iconos de botón).
>
> **Rótulos = texturas:** verificado que los rótulos de menú (`New Game`, `Items`…)
> son **bitmaps en texturas `AIF`**, no texto `.msg` (`docs/re/second-text-path.md`).
> Se integran sustituyendo el `AIF` (`tools/aif_edit.py`) y/o el hook `sub_82182070`.
>
> **Frentes en curso (sesión larga):**
> 1. Integración de **acentos** en runtime/asset (por banco).
> 2. Traducción de **texturas de UI** (menú principal, CAMP, GAME OVER, `Now Loading`…).
> 3. Traducción de **menús/sistema/objetos** (`translation/parts/menu_*.json`).
> 4. Traducción de **diálogos** (`translation/parts/dialog_*.json`).
>
> El pipeline (`tools/build_es_codes.py`) une `translation/es.json` + `translation/parts/*.json`,
> hace **reflow** (`0x4000`) y valida el ancho con `tools/validate_translation.py`
> (`docs/re/ui-length.md`).
>
> Referencias: `docs/re/font-loader.md` (formato+codec), `docs/re/disc2-messages.md`
> (censo), `docs/re/runtime-hook.md` (hook F5), `docs/re/charmap.md` (en curso).

---

## 9. Diseño técnico detallado

### 9.1 Formato `RMD-` (hipótesis a validar en F1)

```
RMD- payload
├─ AIF  (atlas de fuente; cabecera 4096 B + textura hasta "fin de imagen")
│        ver pc-infiniteundiscovery/docs/formats/aif.md
└─ <datos de mensaje>   ← A DECODIFICAR
         hipótesis: cabecera + tabla de mensajes (id/offset/longitud) + blobs
         encoding: ASCII | Shift-JIS | UTF-16 | índices a celdas del atlas
   (en 3 flujos aparece "MessageConvertLib_1.0.0.0" al final)
```

Preguntas que F1 debe responder:
- ¿La mitad de mensaje lleva magic/cabecera propia?
- ¿Cómo se indexa un mensaje (ID entero? nombre? hash?)?
- ¿Es texto plano o índices a glifos?
- ¿Hay longitud explícita por mensaje? ¿alineación?
- ¿Incluye marcas de control (saltos, iconos de botón, variables como `%s`)?

### 9.2 Contrato del hook

- **Entrada:** el `id` del mensaje (o el puntero a la cadena original).
- **Salida:** puntero a una cadena válida para el motor (mismo encoding que
  espere).
- **Gestión de memoria:** buffer estable (por ejemplo, un ring de buffers
  estáticos o reutilizar la semántica del motor; **nunca** devolver un temporal).
- **Fallback:** si no hay traducción, devolver la **cadena original** (nunca
  vacío).
- **Encoding:** si el motor usa índices a glifos, el hook devuelve índices; se
  exige que `es.json` se valide contra el conjunto de glifos (F3).

### 9.3 Esquema de `es.json`

```json
{
  "meta": { "game": "Infinite Undiscovery", "edition": ["EU", "USA"],
            "encoding": "ascii|sjis|utf16|glyph-index", "version": "1.0.0" },
  "strings": [
    { "id": "menu.newgame", "en": "New Game", "es": "Nueva partida",
      "ctx": "menu principal", "max_len": 16, "glyphs_ok": true }
  ]
}
```

### 9.4 Reflow y límites

El motor probablemente envuelve el texto por caja. Traducciones más largas →
desbordes. Reglas:
- Respetar `max_len` por `id` (medido en F6/F7).
- Preferir sinónimos cortos; permitir 2 líneas si la caja lo admite.
- Validar con `tools/validate_translation.py` antes de publicar.

### 9.5 Glifos / fuente

- Si el atlas cubre latino extendido → usar acentos normales.
- Si no → **F3-b**: extender el `AIF` (añadir celdas de glifos) y actualizar el
  mapa de celdas. Alternativa conservadora: castellano sin acentos (no
  recomendable).
- Los **iconos de botón** dentro del texto (A/B/X/Y de Xbox) no se traducen; se
  preservan.

### 9.6 Interruptor y recarga

- `REXCVAR_DEFINE_BOOL(translation, true, "Translation", "…)`.
- Ruta del catálogo: `<portable_root>\translation\es.json` (p. ej.
  `USA\translation\es.json`) o junto al EXE.
- Recarga en caliente por tecla de depuración (reutilizar el patrón de binds de
  `infinite_undiscovery_app.h`).

---

## 10. QA y validación

1. **Unitario (pipeline):** decodificación de `RMD-`, parseo de `es.json`,
   validador de glifos/longitud.
2. **Integración:** el hook recibe cada `id` del volcado y devuelve la cadena
   esperada (test fuera del juego).
3. **En juego:** checklist por zonas (menús, tienda, combate, cinemáticas,
   tutoriales, nombre de personaje en caja).
4. **Regresión:** recompilar tras cambios del upstream; revalidar.
5. **Cifras:** registrar qué se probó, con **comando + fecha** (convención del
   ecosistema: toda afirmación, con su ancla).

---

## 11. Empaquetado, distribución y legal

- **Contenido del mod:** código del fork + `translation/es.json` + documentación.
  **Sin** assets del juego.
- **Requisitos del usuario:** su copia legítima del juego, VC++ Redist 2015-2022
  x64, GPU D3D12.
- **Licencia:** respetar **BSD-3-Clause** del recomp y las licencias de ReXGlue
  (incluye componentes LGPL): conservar avisos.
- **Aviso:** proyecto no oficial, sin afiliación con Square Enix / tri-Ace /
  Microsoft; no se distribuyen contenidos con copyright.

---

## 12. Matriz de riesgos

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | Formato de mensaje = índices a glifos | Media | Alto | F1 con Plan B (mapeo a índices); restringir a glifos existentes |
| R2 | Faltan glifos acentuados | Media | Alto | F3-b (extender `AIF`) o Plan C sin acentos |
| R3 | Toolchain ReXGlue difícil de reproducir | Media | Alto | Seguir `RELEASE-BUILD.md` al pie; versiones fijadas |
| R4 | Texto compuesto en runtime no interceptable | Baja-Media | Medio | H3/H4; más puntos de hook |
| R5 | Reflow/desbordes por longitud | Alta | Medio | Validador + `max_len` + sinónimos |
| R6 | Divergencia con el upstream | Media | Bajo | Parches pequeños y aislados; seguimiento de releases |
| R7 | Validación de assets bloquea algo necesario | Baja | Medio | Preferir hook; no parchear BINs |
| R8 | Legal | Baja | Alto | Nunca versionar assets; solo código/tablas propias |

---

## 13. Anexos

### 13.1 Offsets de contenedores (edición **EUROPE/PAL**)

| Disco | Contenedor | Offset | Longitud |
|---|---|---|---|
| 1 | `ud1.bin` | `0x6589E800` | `2207584256` |
| 1 | `ud2.bin` | `0xE99D0000` | `2800330752` |
| 2 | `ud1.bin` | `0x28ACC000` | `3217651712` |
| 2 | `ud2.bin` | `0xE99D0000` | `3289788416` |

(Tomados del censo de RE; verificar con `xdvdfs.py info`/`list` para tu edición.)

### 13.2 Perfiles XEX de Disco 1 admitidos (SHA-256)

```
22893bb8d96a1440ecbdbcae543baeaf89d26588c89c99a2c96fecf611475325  EUROPE (PAL)
9523b45e6a724d4988ce9cf70d55b672e461b89303b02dc2f0f9c84329c25555  USA
42dfaa90814f5b78592bb637ac371df20c30acfa897f922fff96d3251553473b  USA-UNDUB
cbb789e5e8842398253839b2e320874b3851bd10aaa2392aadf5cdeed438cc91  JAPAN
fd063de17d98ab1201795efab4ffd06d76e85eeb4da0ce751926792deeeccd33  ASIA
```

### 13.3 Referencias de código del recomp (para el hook)

| Ruta | Qué aporta |
|---|---|
| `src/infinite_undiscovery_app.h` | Ciclo de vida e instalación de hooks (`…Install(runtime())`). |
| `src/disc_swap.h` | `SetFunction`/`GetFunction`, `PatchIAT`, registro de VFS/mounts. Ejemplo: `SetFunction(0x829687EC, Hook_XamSwapDisc)`. |
| `src/disc2_io_trace.h` | Hooks a `__imp__NtCreateFile` (`0x8296853C`) y otros; observa `game:\ud1.bin`. |
| `src/save_anywhere.h` | `DECLARE_REX_FUNC(sub_82475670)`; llamada a funciones invitadas y estado. |
| `src/asset_setup.cpp` | `CanLaunch`, `ExpectedBinHash`, `Ready` (validación de assets). |
| `src/community_debug_dialog.h` | UI in-game (patrón de binds y bilingüe). |
| `functions.toml` | Entradas respaldadas por binario (sin parches de instrucciones). |
| `main.cpp` | `REXCVAR_DEFINE_BOOL` y `REX_DEFINE_APP`. |
| `CMakeLists.txt` | Fuentes y targets. |
| `docs/RELEASE-BUILD.md` | Build reproducible y hashes de DLL. |

### 13.4 Herramientas de análisis (comandos rápidos)

```bash
# Filesystem
python tools/xdvdfs.py info  "D1.iso"
python tools/xdvdfs.py list  "D1.iso" --csv d1.csv

# Contenedor → RMD-
python tools/mron.py extract "D1.iso" --offset 0x6589E800 --length 2207584256 \
       --tag RMD- --decompress extract/d1_ud1

# Atlas de fuente
python tools/aif.py png extract/.../*.aif atlas.png

# Ejecutable
python tools/xex.py extract default.xex default.exe

# Xrefs / desensamblado (requiere capstone)
python tools/disasm.py strings default.exe "MessageConvertLib" --base 0x82000000
python tools/disasm.py xref    default.exe 0x82XXXXXX --base 0x82000000
python tools/disasm.py dis     default.exe 0x82XXXXXX --base 0x82000000
```

### 13.5 Glosario

- **ASKA:** motor de tri-Ace del juego.
- **NORM/MRON:** contenedor de recursos (`ud1.bin`/`ud2.bin`).
- **SLZ/XCompress:** compresión de payloads.
- **AIF:** textura/imagen (el atlas de fuente es un `AIF`).
- **RMD-:** recurso de mensaje = atlas `AIF` + datos de texto (**a decodificar**).
- **ReXGlue / XenonRecomp:** toolchain de recompilación y runtime.
- **Hook:** interceptación de una función invitada por dirección
  (`function_dispatcher`).
- **REXCVAR:** variable de configuración del runtime.

### 13.6 Enlaces

- Recomp: <https://github.com/doc-haz/infinite-undiscovery-recomp>
- RE / formato ASKA: <https://github.com/vs-sr-dev/pc-infiniteundiscovery>
- Editor de saves: <https://github.com/doc-haz/iu-save-bridge>
- Referencia Lost Odyssey Recomp: <https://github.com/freefrank/LostOdysseyRecomp>

---

## 14. Checklist de arranque (primera sesión)

```
[x] Crear directorio del proyecto (§7.3)
[x] Copiar este plan a <proyecto>/PLAN-TRADUCCION-INFINITE-UNDISCOVERY-ES.md
[x] .gitignore con exclusión de assets y volcados
[x] pip install capstone
[x] Clonar pc-infiniteundiscovery en tools/vendor/   (submódulo git)
[x] Indicar la ruta del ISO/carpeta del Disco 1 (y Disco 2)   (roms/, ambos discos)
[x] Ejecutar F0: extraer los RMD-   (81 RMD-, atlas PNG, manifest.csv)
[~] Abrir docs/re/rmd-format.md y empezar F1   (estructura sí; mapeo código→glifo pendiente)
```

**Primer prompt sugerido para la sesión nueva:**

> «Lee `PLAN-TRADUCCION-INFINITE-UNDISCOVERY-ES.md`. Ejecuta **F0**. Mi disco está
> en `<ruta>`. Déjame los `RMD-` extraídos y el atlas en PNG, y abre
> `docs/re/rmd-format.md` con las primeras observaciones para F1.»

---

*Fin del plan.*
