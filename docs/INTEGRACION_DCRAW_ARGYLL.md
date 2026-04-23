# Integración de `dcraw` y `ArgyllCMS` en ICCRAW

## Objetivo

Este documento describe cómo ICCRAW integra:

- `dcraw` como motor único de revelado RAW.
- `ArgyllCMS` (`colprof`) como motor único de generación de perfiles ICC.

La meta es mantener un flujo científico reproducible y auditable.

## Instalación del sistema

### Opción recomendada (global, con `sudo`)

```bash
sudo apt-get update
sudo apt-get install -y dcraw argyll exiftool
```

### Verificación rápida

```bash
bash scripts/check_tools.sh
```

## Integración `dcraw` (módulo `pipeline`)

Archivo clave:

- `src/icc_entrada/pipeline.py`

Para entradas RAW, ICCRAW construye un comando `dcraw` determinista:

- `-T`: salida TIFF.
- `-4`: 16-bit lineal.
- `-W`: sin auto-bright.
- `-H 0`: clipping de altas luces.
- `-t 0`: sin rotación automática.
- `-o 0`: espacio de color cámara nativo.
- `-q <0|1|2|3>`: algoritmo de demosaicing.
- `-w` o `-r ...`: balance de blancos (metadatos o fijo).
- `-k` / `-S`: overrides de black/white level cuando la `recipe` lo pide.
- `-c`: TIFF por stdout (capturado por el pipeline).

Mapeo de `recipe`:

- `raw_developer`: debe ser `dcraw`.
- `demosaic_algorithm`: mapea a `-q`.
- `white_balance_mode` + `wb_multipliers`: `-w` o `-r`.
- `black_level_mode`: opcional `-k` o `-S`.

## Integración `ArgyllCMS` (módulo `profiling`)

Archivo clave:

- `src/icc_entrada/profiling.py`

Flujo:

1. Se construye un `.ti3` temporal con muestras y referencia.
2. Formato usado:
   - `DEVICE_CLASS "INPUT"`
   - `COLOR_REP "LAB_RGB"`
   - campos `LAB_L LAB_A LAB_B RGB_R RGB_G RGB_B`
3. Se ejecuta `colprof` para generar el `.icc`.

Comando base:

```bash
colprof -v -D "<descripcion>" -qm -as <base_ti3>
```

Personalización:

- `recipe.argyll_colprof_args` tiene prioridad.
- Si no existe, se usa `ICC_ARGYLL_COLPROF_ARGS` (variable de entorno).
- Si tampoco existe, se usan `-qm -as`.

## Validación de integración en local

### Prueba de revelado RAW real (`dcraw`)

```bash
app develop /ruta/a/captura.dng \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out /tmp/dev_out.tiff \
  --audit-linear /tmp/dev_linear.tiff
```

### Prueba de perfilado (`colprof`)

```bash
app auto-profile-batch \
  --charts testdata/batch_images \
  --targets testdata/batch_images \
  --recipe testdata/recipes/scientific_recipe.yml \
  --reference testdata/references/colorchecker24_reference.json \
  --profile-out /tmp/camera_profile.icc \
  --profile-report /tmp/profile_report.json \
  --out /tmp/batch_out \
  --workdir /tmp/work_auto \
  --min-confidence 0.0
```

## Errores comunes

- `No se puede revelar RAW: 'dcraw' no esta disponible en PATH.`
  - Solución: instalar `dcraw` o ajustar `PATH`.

- `colprof no esta en PATH`
  - Solución: instalar `argyll`.

- `colprof retorno ...`
  - Revisar `argyll_colprof_args` y consistencia de muestras/carta/referencia.

## Integración futura C2PA/CAI (propuesta)

Sí, es viable y recomendable para este proyecto.

Propuesta de integración:

1. Generar un manifiesto C2PA por salida TIFF/ICC con:
   - hash de entrada/salida,
   - `recipe`,
   - versión software + commit,
   - perfil ICC aplicado,
   - métricas DeltaE.
2. Firmar usando `c2patool`/biblioteca C2PA con certificado del laboratorio.
3. Guardar:
   - manifest embebido (si el contenedor lo permite) o
   - sidecar `.c2pa`.

Estado actual: no implementado aún en código, pero completamente compatible con la arquitectura de sidecars y manifiestos.
