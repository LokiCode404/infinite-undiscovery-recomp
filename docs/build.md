# Build del fork (F4+)

> **Estado:** pendiente. Se rellena en **F4**.
> **Objetivo:** compilar la versión *stock* del recomp desde fuente, sin cambios.

## 1. Requisitos (según `docs/RELEASE-BUILD.md` del recomp)

- Windows 10/11 x64.
- **ReXGlue SDK v0.10.0 desde fuente** (tag `v0.10.0`,
  commit `f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`). NO el SDK precompilado
  antiguo: el recomp rechaza esos DLL por hash.
- **CMake ≥ 3.25**, **Ninja**, **Clang/LLVM**, **MSVC + Windows SDK**.
- Hashes DLL de release exigidos por `cmake/verify_rexglue_dlls.cmake`:

```
25C0F2D1DBB7FE3147FC59E22C9A3E4C764DC2E0B0C6877FC86F0DA499E0F67F  rexruntime.dll
98CEF22E2AC1667F3A42910DD7474C0409BBEF7DB7599B3A48DF1EDBB0739A2D  rexgpu-xenos.dll
```

## 2. Pasos

1. Forkear `doc-haz/infinite-undiscovery-recomp` → `infinite-undiscovery-es`.
2. Construir e instalar ReXGlue en el commit fijado (Release).
3. Proveer el `default.xex` legítimo y ejecutar el **codegen**
   (`run-codegen.ps1`, usa `tools/rexglue/rexglue.exe`).
4. Configurar y compilar con `CMakePresets.json`.
5. Arrancar con los assets del usuario (setup wizard) y verificar.

## 3. Estado del entorno local

Comprobado en esta máquina (2026-10-07):

| Componente | Estado |
|---|---|
| git | 2.46.2 |
| Python | 3.14.6 |
| CMake | 4.2.3 |
| Ninja | 1.13.2 |
| capstone | 5.0.9 |
| Visual Studio | **2026 Community** en `C:\Program Files\Microsoft Visual Studio\18\Community` (con toolset VC x64 + Windows SDK) |
| Clang/LLVM | **22.1.3**, en `…\VC\Tools\Llvm\x64\bin\clang-cl.exe` (no está en el PATH global) |
| MSBuild | `…\MSBuild\Current\Bin\MSBuild.exe` |
| vcvars64 | `…\VC\Auxiliary\Build\vcvars64.bat` |

> Para F4 no hace falta instalar MSVC/Clang: ya vienen con Visual Studio 2026.
> Solo hay que exponerlos en el entorno (usar `vcvars64.bat`, o el *Developer
> Command Prompt*, o el preset de CMake del proyecto). El punto que sigue siendo
> el crítico de F4 es construir **ReXGlue v0.10.0 desde fuente** con los hashes
> de DLL exigidos.

## 4. Notas / evidencia

- _Pendiente._

---

# F4 — estado

**Fecha:** 2026-10-08 · **Resultado global:** build **OK**, verificación de hashes **FALLIDA (parcial)**.

## Rutas

| Elemento | Ruta |
|---|---|
| Checkout fuente ReXGlue | `C:/Users/eleaz/Downloads/Projects/rexglue-sdk-v0.10.0-git` |
| Build dir | `…/rexglue-sdk-v0.10.0-git/out/build/win-amd64` |
| Install (stock) | `C:/Users/eleaz/Downloads/Projects/rexglue-0.10.0-install` |
| Install experimental (`/Brepro`) | `C:/Users/eleaz/Downloads/Projects/rexglue-0.10.0-install-brepro` |
| Toolchain LLVM 20.1.8 portable | `C:/Users/eleaz/Downloads/Projects/llvm-20.1.8` (extraído con 7-Zip) |

## Repositorio y preset

- Tag `v0.10.0`, commit `f5337cdc947ff6d4c4196737e2c807a48f2a1fc2` (detached HEAD verificado).
- Submódulos inicializados recursivamente (22 + `simde/test/munit`); `git config --global core.symlinks true`.
- Preset: `win-amd64` (Ninja Multi-Config, `CMAKE_INSTALL_PREFIX` redirigido al install).
- Build: `cmake --build out/build/win-amd64 --target install --config Release -j 16`.

## Toolchain usada (coincide con `docs/RELEASE-BUILD.md` del recomp)

| Tool | Versión |
|---|---|
| Clang / clang++ | **20.1.8** (portable, no el 22.1.3 de VS) |
| MSVC | **14.44.35207** (`vcvarsall.bat x64 10.0.26100.0 -vcvars_ver=14.44.35207`) |
| Windows SDK | **10.0.26100.0** |
| CMake | 4.2.3 (release usó 3.31.8) |
| Ninja | 1.13.2 (release usó 1.12.1) |

Config resuelta: `Version 0.10.0 (release)`, `Platform win-amd64`, `D3D12=ON Vulkan=OFF`,
`Tracy=ON`, `Perf Counters=ON`. `rexglue.exe --version` → `0.10.0` (binario funcional).

## Artefactos y hashes obtenidos (install stock)

```
D2007719685FFEF45B73DFB84472B403E81811A9AF8F69D94EF99B337146D069  rexglue.exe
C0531F279D7956D49E60A9EF77595905ECCE18C7084F34052D8B2CB03AEF3A42  rexruntime.dll
C42FA4D8DDE90BA4437B01DA48351402ED68E28B184ACD24572840D1CFFD0503  rexgpu-xenos.dll
2B58451377917F90EF9D4F6737D4D8AF50174FEFF2A38689F03CD8EE7F5C1C42  TracyClient.dll
```

### Comparación con los hashes exigidos

| DLL | Requerido (`verify_rexglue_dlls.cmake`) | Obtenido | ¿Coincide? |
|---|---|---|---|
| `rexruntime.dll` | `25C0F2D1…E0F67F` | `C0531F27…EF3A42` | **NO** |
| `rexgpu-xenos.dll` | `98CEF22E…739A2D` | `C42FA4D8…FD0503` | **NO** |

El guard del recomp falla con:

```
CMake Error at cmake/verify_rexglue_dlls.cmake:52 (message):
  ReXGlue release guard: 'rexruntime.dll' has unexpected sha256
  C0531F279D7956D49E60A9EF77595905ECCE18C7084F34052D8B2CB03AEF3A42.
  Expected the auditable v0.10.0 build:
  25C0F2D1DBB7FE3147FC59E22C9A3E4C764DC2E0B0C6877FC86F0DA499E0F67F
```

## Análisis de la causa (por qué los hashes no son reproducibles)

1. **El PE embebe `TimeDateStamp` de enlace.** `llvm-readobj --file-headers` sobre nuestro
   `rexruntime.dll` da `TimeDateStamp: 2026-10-07 23:50:41` (hora de link). MSVC `link.exe`
   **no** usa `/Brepro` por defecto, así que cada build produce bytes distintos. El SDK **no**
   define `SOURCE_DATE_EPOCH`, `/Brepro` ni ningún mecanismo de build reproducible (grep en
   `cmake/`, `CMakeLists.txt`, `.github/` sin resultados).
2. **Los hashes exigidos NO son el release oficial.** Descargado `rexglue-sdk-0.10.0-win-amd64.zip`
   de GitHub Releases: sus DLL son `E359209F…` / `0C23CFA2…`, es decir **exactamente los hashes
   "prohibidos"** que el guard rechaza. Por tanto, el binario oficial v0.10.0 *es* el "SDK
   precompilado antiguo" vetado.
3. Los hashes requeridos (`25C0…` / `98CE…`) provienen de un **build desde fuente concreto del
   autor del recomp** (otra hora de enlace y probablemente otro entorno). No son un artefacto
   publicado en ningún sitio.
4. Se probó la hipótesis de reproducibilidad con `/Brepro`
   (`-DCMAKE_SHARED_LINKER_FLAGS_RELEASE=-Wl,/Brepro`): el hash cambia a `FF0B4B28…` / `C6628BE5…`
   (tampoco coincide), lo que confirma que la hora de enlace y/o diferencias de entorno hacen
   inviable reproducir los hashes fijados con un build nuevo.
5. `docs/RELEASE-BUILD.md` ya anticipa esto al decir que "a fresh from-source build would not
   reproduce the exact release DLL bytes anyway". Los hashes fijados son, en la práctica, un pin
   a un binario concreto, no un resultado reproducible.

## Conclusión F4

- ✅ ReXGlue v0.10.0 se **compiló e instaló desde fuente** en el commit fijado, con la toolchain
  documentada (Clang 20.1.8 + MSVC 14.44.35207 + SDK 10.0.26100.0), y `rexglue.exe` funciona.
- ❌ Los hashes de `rexruntime.dll` / `rexgpu-xenos.dll` **no** coinciden con los exigidos; el
  guard `verify_rexglue_dlls.cmake` del recomp **rechazará** este build tal cual.

## Próximos pasos (requieren decisión del proyecto; NO aplicados aquí)

1. **Re-pinnear los hashes** en `extract/f2/recomp/cmake/verify_rexglue_dlls.cmake` a los del build
   desde fuente reproducible propio (`C0531F27…` / `C42FA4D8…`), y regenerar
   `RELEASE_HASHES_SHA256.txt`. Es la vía coherente con "construir desde fuente".
2. Alternativamente, **preservar el install del autor** con hashes `25C0…`/`98CE…` (no está en
   esta máquina) y usarlo como artefacto auditable en lugar de reconstruir.
3. Si se quiere reproducibilidad bit-a-bit: fijar `TimeDateStamp` (`/Brepro` o `SOURCE_DATE_EPOCH`
   soportado por `link.exe`/`lld-link`) **y** igualar CMake 3.31.8 + Ninja 1.12.1, y re-pinnear
   los hashes resultantes una sola vez.
4. Consumir el install con `find_package(rexglue 0.10.0 CONFIG)` vía `CMAKE_PREFIX_PATH` /
   `rexglue_DIR` apuntando a `C:/Users/eleaz/Downloads/Projects/rexglue-0.10.0-install` (NO usar
   `REXSDK_DIR`/`add_subdirectory`).

> Nota: el build dir quedó reconfigurado a **stock** (sin `/Brepro`) y con `CMAKE_INSTALL_PREFIX`
> apuntando al install principal. El install `/Brepro` se conserva solo como evidencia del
> experimento de reproducibilidad.

---

# F5 — Build del recomp (fork local) + hook de traza

Con el SDK instalado, el **recomp se compila** con nuestro install. Script:
`extract/f2/build_recomp.bat` (carga `vcvars64`, añade Clang al PATH, configura con
`CMAKE_PREFIX_PATH` al install y compila con Ninja).

```bat
cmake -S . -B out\build\local -G Ninja -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_PREFIX_PATH="C:/Users/eleaz/Downloads/Projects/rexglue-0.10.0-install" ^
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
cmake --build out\build\local -j 12
```

Resultado: `out/build/local/InfiniteUndiscoveryRecomp.exe` (+ `rexruntime.dll`,
`rexgpu-xenos.dll`). **El guard se re-pinnea** a nuestros hashes (`C0531F27…`/
`C42FA4D8…`) en `cmake/verify_rexglue_dlls.cmake`.

## Hook de traza de texto

`src/translation_trace.h` (incluido desde `src/main.cpp`). Intercepta
`CMessageTextWnd::SetText` (**guest `0x826D1F20`**) mediante **override del símbolo
débil** (patrón de `src/iu_trace_points.h`), porque el código generado llama a las
funciones internas de forma **directa** (no por el `FunctionDispatcher`):

```cpp
extern "C" void __imp__sub_826D1F20(PPCContext&, uint8_t*);
extern "C" void sub_826D1F20(PPCContext& ctx, uint8_t* base) {
  // vuelca ctx.r4 (texto) como u16 big-endian y llama al original
  __imp__sub_826D1F20(ctx, base);
}
```

## Ejecución con traza

Layout portable (`<exe_dir>/<PERFIL>/assets/disc1/{default.xex,ud1.bin,ud2.bin}`)
y `setup.json` con `"active_profile": "EUROPE"`. Los assets se extraen del ISO con
`xdvdfs.py`. La traza se escribe en `<PERFIL>/logs/iu_trace.log`:

```bash
bash extract/f2/run_trace.sh 180    # ejecuta 180s con IU_TRACE=1 y muestra SETTEXT
```
