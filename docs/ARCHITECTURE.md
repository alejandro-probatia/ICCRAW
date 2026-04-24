# Architecture

## Objetivo

Pipeline científico reproducible:

`RAW -> develop base -> detect-chart -> sample-chart -> perfil de revelado -> receta calibrada -> sample-chart calibrado -> build-profile ICC -> batch-develop -> validate-profile`

Gobernanza y licencia:

- proyecto mantenido por la comunidad de la **Asociacion Espanola de Imagen Cientifica y Forense**.
- licencia del repositorio: `AGPL-3.0-or-later`.

## Layout del paquete

El código vive en `src/iccraw/`, organizado por dominio para permitir crecer sin archivos flat de tamaño desbordante:

```text
src/iccraw/
  __init__.py, __main__.py, version.py
  cli.py                       # interfaz de línea de comandos
  gui.py                       # interfaz gráfica Qt/PySide6
  workflow.py                  # orquestación end-to-end
  session.py                   # modelo y persistencia de sesiones
  reporting.py                 # contexto de ejecución y trazabilidad

  core/                        # dominio compartido, sin deps cruzadas al resto
    models.py                  # dataclasses + I/O JSON
    recipe.py                  # carga de receta + scientific_guard
    color.py                   # DeltaE 76/2000
    utils.py                   # I/O imagen, hashes, TIFF 16-bit

  raw/                         # ingesta y revelado RAW
    metadata.py                # raw_info (exiftool + rawpy opcional)
    pipeline.py                # develop_controlled con backend dcraw
    preview.py                 # preview rápido + ajustes técnicos

  chart/                       # cartas de color
    detection.py               # localización + homografía + parches
    sampling.py                # muestreo robusto + ReferenceCatalog

  profile/                     # perfil ICC y export
    development.py             # perfil de revelado cientifico: WB + densidad + EV
    builder.py                 # build_profile / validate_profile (ArgyllCMS)
    export.py                  # batch_develop + export ICC/CMM + matriz diagnostica
```

## Reglas de dependencia

- `core/` no importa del resto del paquete.
- `raw/` y `chart/` dependen sólo de `core/`.
- `profile/` depende de `core/` y `raw/`.
- `workflow.py`, `cli.py`, `gui.py` orquestan — pueden importar de cualquier subpaquete, nunca al revés.
- `session.py` y `reporting.py` son standalone.

## Perfil ICC

- Motor único: `ArgyllCMS (colprof)`.
- Siempre se guarda sidecar `.profile.json` con matriz, recipe y métricas para reproducibilidad.

## Reproducibilidad

Se registra:

- versión software,
- commit hash (si aplica),
- recipe exacta,
- metadatos RAW,
- detección de carta,
- muestras por parche,
- DeltaE 76/2000,
- hashes de entradas/salidas,
- manifiesto de lote.

## Principio clave

El perfil es condicional (cámara + óptica + iluminante + recipe + versión). No se considera universal.
