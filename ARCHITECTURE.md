# Architecture

## Objetivo

Pipeline científico reproducible:

`RAW -> develop controlado -> detect-chart -> sample-chart -> build-profile -> batch-develop -> validate-profile`

## Módulos Python

- `icc_entrada.raw`: ingesta RAW y metadatos (rawpy + exiftool).
- `icc_entrada.pipeline`: revelado controlado por `recipe`.
- `icc_entrada.chart_detection`: localización de carta + homografía + patch geometry.
- `icc_entrada.sampling`: muestreo robusto por parche y enlace con referencia.
- `icc_entrada.profiling`: ajuste de perfil, DeltaE, generación ICC.
- `icc_entrada.export`: aplicación de perfil a lotes y export TIFF 16-bit.
- `icc_entrada.reporting`: contexto de ejecución y trazabilidad.
- `icc_entrada.cli`: interfaz de línea de comandos.

## Perfil ICC

- Motor preferente: `ArgyllCMS (colprof)`.
- Fallback: perfil matrix/shaper interno.
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
