_Spanish version: [ARCHITECTURE.es.md](ARCHITECTURE.es.md)_

# Architecture

## Objective

Reproducible scientific pipeline:

`RAW -> ajuste parametrico por archivo -> mochila -> perfil avanzado con carta o perfil basico manual -> ICC de entrada o ICC generico -> cola -> TIFF 16-bit -> proof/manifiesto`

The letter flow maintains the complete technical chain:

`RAW carta -> develop base -> detect-chart -> sample-chart -> perfil de ajuste avanzado -> receta calibrada -> sample-chart calibrado -> build-profile ICC -> asignar perfil al RAW -> copiar/pegar a RAW equivalentes -> batch-develop`

Governance and licensing:

- project maintained by the community of the **Spanish Association of Scientific and Forensic Image**.
- repository license: `AGPL-3.0-or-later`.

## Package layout

The code lives in `src/nexoraw/`, organized by domain to allow it to grow without oversized flat files:
```text
src/nexoraw/
  __init__.py, __main__.py, version.py
  cli.py                       # interfaz de línea de comandos
  gui.py                       # Qt/PySide6 main window and UI orchestration
  gui_config.py                # GUI visual, cache and compatibility constants
  workflow.py                  # orquestación end-to-end
  session.py                   # modelo y persistencia de sesiones
  sidecar.py                   # mochilas RAW.nexoraw.json por imagen
  display_color.py             # perfil ICC de monitor por plataforma
  reporting.py                 # contexto de ejecución y trazabilidad

  core/                        # dominio compartido, sin deps cruzadas al resto
    models.py                  # dataclasses + I/O JSON
    recipe.py                  # carga de receta + scientific_guard
    color.py                   # DeltaE 76/2000
    utils.py                   # I/O imagen, hashes, TIFF 16-bit

  raw/                         # ingesta y revelado RAW
    metadata.py                # raw_info (exiftool + rawpy/LibRaw)
    pipeline.py                # develop_controlled con backend LibRaw
    preview.py                 # preview rápido + ajustes técnicos

  chart/                       # cartas de color
    detection.py               # localización + homografía + parches
    sampling.py                # muestreo robusto + ReferenceCatalog

  profile/                     # perfil ICC y export
    development.py             # perfil de revelado cientifico: WB + densidad + EV
    builder.py                 # build_profile / validate_profile (ArgyllCMS)
    generic.py                 # perfiles ICC genericos para flujos sin carta
    export.py                  # batch_develop + export ICC/CMM + matriz diagnostica

  ui/                          # reusable Qt widgets, without session logic
    widgets.py                 # image viewer, histogram and tone curve controls
    window/                    # NexoRawMainWindow behavior by domain
      layout.py                # menus, tabs and main panes
      control_panels.py        # development/export control tabs
      settings.py              # global dialog, language, signatures and display color
      display.py               # visual utilities, adjustments and display color
      session.py               # session facade
      session_paths.py         # project paths, references and outputs
      session_development.py   # adjustment profiles and RAW sidecars
      session_state.py         # snapshot, activation, creation and save
      session_queue.py         # queue table and processing
      browser.py               # browser, thumbnails, caches and metadata
      preview.py               # preview facade
      preview_menu.py          # menu actions, about, QA and recipes
      preview_recipe.py        # recipe controls, histogram and tone curve
      preview_cache.py         # preview keys and cache
      preview_load.py          # image loading and visible precache
      preview_render.py        # interactive preview, ICC and final refresh
      preview_export.py        # save preview and single develop
      profile.py               # chart selection, ICC profiling and manual marking
      batch.py                 # batch develop and signed export
      tasks.py                 # background tasks, monitor and global status
```
## Project structure

A NexoRAW 0.2 session uses three main folders:
```text
proyecto/
  00_configuraciones/          # session.json, perfiles, ICC, reportes, cache
    cache/                     # cache numerica persistente por sesion
  01_ORG/                      # originales RAW y cartas
  02_DRV/                      # TIFF, previews, manifiestos y proof
```
Sessions inherited with `charts/`, `raw/`, `profiles/`, `exports/`,
`config/` and `work/` are opened for compatibility. GUI resolves old routes
such as `raw/captura.NEF` versus `01_ORG/captura.NEF` when the file exists.

## Dependency rules

- `core/` does not matter from the rest of the package.
- `raw/` and `chart/` depend only on `core/`.
- `profile/` depends on `core/` and `raw/`.
- `workflow.py`, `cli.py`, `gui.py` orchestrate — can import from any subpackage, never the other way around.
- `ui/` only contains reusable widgets and controls; it should not know session paths or run RAW processes.
- `ui/window/` splits the main window into responsibility-oriented mixins; each module may depend on the domain, but new behavior should not be added directly to `gui.py`.
- `session.py` and `reporting.py` are standalone.

## ICC Profile

- Single motor: `ArgyllCMS (colprof)`.
- `.profile.json` sidecar with matrix, recipe and metrics is always saved for reproducibility.
- If there is a letter, the ICC is treated as a session entry profile and is embedded
  in the master TIFF without converting to generic space.
- If there is no card, NexoRAW reveals the RAW in a real standard RGB space
  (`sRGB`, `Adobe RGB (1998)` or `ProPhoto RGB`), copy/embed the standard ICC
  from the system or ArgyllCMS and declares it as `generic_output_icc`.

## Fit profiles

- The advanced profile is based on a color chart, is marked in blue and can be
  carry associated session input ICC.
- The basic profile comes from manual settings, is marked in green and can use
  Generic CCI.
- Both are assigned to specific RAWs via backpacks and can be copied/pasted
  between miniatures.

## Reproducibility

It registers:

- software version,
- commit hash (if applicable),
- exact recipe,
- RAW metadata,
- letter detection,
- samples per patch,
- DeltaE 76/2000,
- input/output hashes,
- batch manifest.

## Performance and cache- `batch-develop` and the batch phase of `auto-profile-batch` parallelize at the
  image with processes when `workers > 1`. The manifesto is ordered by
  entry plan, not in order of completion.
- The RAW demo cache is opt-in (`use_cache: true` in recipe or control
  equivalent) and save `.npy` arrays to `00_configuraciones/cache/demosaic/`
  when the session can be inferred. The canonical regression mode uses
  `use_cache: false`.
- The cache key includes name, size, full RAW SHA-256,
  LibRaw parameters affecting demosaic/WB/black and backend signature
  rawpy/LibRaw. Changing demosaic algorithm invalidates the entry.
- The cache applies LRU pruning by maximum size. By default it uses 5 GiB,
  configurable with `NEXORAW_DEMOSAIC_CACHE_MAX_GB`.

## Key principle

The profile is conditional (camera + optics + illuminant + recipe + version). It is not considered universal.
