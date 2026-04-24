# Architecture

## Objetivo

Pipeline científico reproducible:

`RAW -> develop controlado -> detect-chart -> sample-chart -> build-profile -> batch-develop -> validate-profile`

Gobernanza y licencia:

- proyecto mantenido por la comunidad de la **Asociacion Espanola de Imagen Cientifica y Forense**.
- licencia del repositorio: `AGPL-3.0-or-later`.

## Módulos Python

- `icc_entrada.raw`: ingesta RAW y metadatos (exiftool + rawpy opcional).
- `icc_entrada.pipeline`: revelado controlado por `recipe` con backend `dcraw`.
- `icc_entrada.chart_detection`: localización de carta + homografía + patch geometry.
- `icc_entrada.sampling`: muestreo robusto por parche y enlace con referencia.
- `icc_entrada.profiling`: ajuste de perfil, DeltaE, generación ICC.
- `icc_entrada.export`: aplicación de perfil a lotes y export TIFF 16-bit.
- `icc_entrada.reporting`: contexto de ejecución y trazabilidad.
- `icc_entrada.cli`: interfaz de línea de comandos.
- `icc_entrada.preview`: utilidades de previsualización técnica, análisis lineal y ajustes (nitidez + ruido luminancia/color).
- `icc_entrada.session`: modelo y persistencia de sesiones (estructura de directorios, estado de sesión y cola de revelado).
- `icc_entrada.gui`: interfaz gráfica Qt/PySide6 con:
  - pestaña `Sesión` (crear/abrir/guardar sesión + metadatos + estructura persistente),
  - pestaña `Revelado y Perfil ICC` (explorador multiunidad, visor, receta, perfil y lote),
  - pestaña `Cola de Revelado` (cola por archivo + monitoreo y logs).
- `icc_entrada.workflow`: orquestación automática de pipeline completo (chart captures -> perfil -> batch TIFF ICC).

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
