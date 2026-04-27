# Architecture

## Objetivo

Pipeline científico reproducible:

`RAW -> ajuste parametrico por archivo -> mochila -> perfil avanzado con carta o perfil basico manual -> ICC de entrada o ICC generico -> cola -> TIFF 16-bit -> proof/manifiesto`

El flujo con carta mantiene la cadena tecnica completa:

`RAW carta -> develop base -> detect-chart -> sample-chart -> perfil de ajuste avanzado -> receta calibrada -> sample-chart calibrado -> build-profile ICC -> asignar perfil al RAW -> copiar/pegar a RAW equivalentes -> batch-develop`

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
```

## Estructura de proyecto

Una sesion NexoRAW 0.2 usa tres carpetas principales:

```text
proyecto/
  00_configuraciones/          # session.json, perfiles, ICC, reportes, cache
    cache/                     # cache numerica persistente por sesion
  01_ORG/                      # originales RAW y cartas
  02_DRV/                      # TIFF, previews, manifiestos y proof
```

Las sesiones heredadas con `charts/`, `raw/`, `profiles/`, `exports/`,
`config/` y `work/` se abren por compatibilidad. La GUI resuelve rutas antiguas
como `raw/captura.NEF` contra `01_ORG/captura.NEF` cuando existe el archivo.

## Reglas de dependencia

- `core/` no importa del resto del paquete.
- `raw/` y `chart/` dependen sólo de `core/`.
- `profile/` depende de `core/` y `raw/`.
- `workflow.py`, `cli.py`, `gui.py` orquestan — pueden importar de cualquier subpaquete, nunca al revés.
- `session.py` y `reporting.py` son standalone.

## Perfil ICC

- Motor único: `ArgyllCMS (colprof)`.
- Siempre se guarda sidecar `.profile.json` con matriz, recipe y métricas para reproducibilidad.
- Si hay carta, el ICC se trata como perfil de entrada de sesion y se incrusta
  en el TIFF maestro sin convertir a un espacio generico.
- Si no hay carta, NexoRAW genera o selecciona un ICC generico de salida
  (`sRGB`, `Adobe RGB (1998)` o `ProPhoto RGB`) y lo declara como
  `generic_output_icc`.

## Perfiles de ajuste

- El perfil avanzado nace de carta de color, queda marcado en azul y puede
  llevar ICC de entrada de sesion asociado.
- El perfil basico nace de ajustes manuales, queda marcado en verde y puede usar
  ICC generico.
- Ambos se asignan a RAW concretos mediante mochilas y se pueden copiar/pegar
  entre miniaturas.

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

## Rendimiento y cache

- `batch-develop` y la fase batch de `auto-profile-batch` paralelizan a nivel
  de imagen con procesos cuando `workers > 1`. El manifiesto se ordena por el
  plan de entrada, no por orden de finalizacion.
- La cache de demosaico RAW es opt-in (`use_cache: true` en receta o control
  equivalente) y guarda arrays `.npy` en `00_configuraciones/cache/demosaic/`
  cuando se puede inferir la sesion. El modo canonico de regresion usa
  `use_cache: false`.
- La clave de cache incluye nombre, tamano, SHA-256 completo del RAW,
  parametros LibRaw que afectan al demosaico/WB/negro y firma del backend
  rawpy/LibRaw. Cambiar algoritmo de demosaico invalida la entrada.
- La cache aplica poda LRU por tamano maximo. Por defecto usa 5 GiB,
  configurable con `NEXORAW_DEMOSAIC_CACHE_MAX_GB`.

## Principio clave

El perfil es condicional (cámara + óptica + iluminante + recipe + versión). No se considera universal.
