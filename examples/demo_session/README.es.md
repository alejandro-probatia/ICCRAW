# Demo de sesion reproducible

Este directorio ejecuta un flujo completo de `auto-profile-batch` en menos de
5 minutos con artefactos incluidos en el repositorio.

## Que demuestra

- Pipeline reproducible de calibracion por carta + perfil ICC de sesion.
- Generacion de sidecars, reporte QA y manifiesto de lote.
- Ejecucion sin dataset externo ni configuracion manual de rutas.

## Origen de los datos demo

Se reutilizan fixtures incluidos en el repositorio:

- `testdata/batch_images/session_001.tiff`
- `testdata/batch_images/session_002.tiff`
- `testdata/references/colorchecker24_colorchecker2005_d50.json`

`prepare_demo.sh` copia esos archivos a `examples/demo_session/data/` y valida
SHA-256 contra `data/MANIFEST.sha256`.

## Ejecucion

```bash
bash examples/demo_session/run_demo.sh
```

## Artefactos generados

En `examples/demo_session/output/`:

- `camera_profile.icc`
- `development_profile.json`
- `recipe_calibrated.yml`
- `profile_report.json`
- `qa_session_report.json`
- `tiffs/batch_manifest.json`

`run_demo.sh` imprime al final:

- ruta del ICC generado,
- DeltaE76 medio,
- DeltaE2000 medio,
- estado operacional del perfil,
- ruta del manifiesto.

## Limitaciones conocidas

- Este demo usa imagenes TIFF de fixture, no RAW de camara real.
- El proyecto mantiene pendiente incorporar un dataset RAW real con licencia
  explicita para regresion (ver `docs/ISSUES.md`, item P0.6).
- Placeholder para mantenedor: `[PENDIENTE: dataset CC-BY propio de Probatia/AEICF para demo RAW real]`.
