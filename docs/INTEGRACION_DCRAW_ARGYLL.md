# Integración de `dcraw`, ArgyllCMS y LittleCMS en ICCRAW

## Objetivo

Este documento describe cómo ICCRAW integra:

- `dcraw` como motor único de revelado RAW.
- `ArgyllCMS` (`colprof`) como motor único de generación de perfiles ICC.
- `LittleCMS` (`tificc`) como CMM para conversiones ICC de salida.

La meta es mantener un flujo científico reproducible y auditable.

Marco legal:

- Licencia del proyecto: `AGPL-3.0-or-later`.
- Referencia operativa de cumplimiento: `docs/LEGAL_COMPLIANCE.md`.

## Instalación del sistema

### Opción recomendada (global, con `sudo`)

```bash
sudo apt-get update
sudo apt-get install -y dcraw argyll liblcms2-utils exiftool
```

### Verificación rápida

```bash
bash scripts/check_tools.sh
iccraw check-tools --strict --out tools_report.json
```

`iccraw check-tools` genera un JSON auditable con disponibilidad, ruta,
comando de versión y primera línea de versión detectada para `dcraw`,
`colprof`, `xicclu`/`icclu`, `tificc` y `exiftool`. La misma comprobación está
disponible en la GUI desde `Ayuda -> Diagnóstico herramientas...`.

El paquete Debian beta declara estas herramientas como dependencias de sistema,
pero sigue siendo recomendable ejecutar `iccraw check-tools --strict` tras la
instalacion para dejar registro auditable del entorno real.

## Integración `dcraw` (módulo `raw.pipeline`)

Archivo clave:

- `src/iccraw/raw/pipeline.py`

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
- `demosaic_algorithm`: debe ser uno de `linear`, `vng`, `ppg`, `ahd`.
- `white_balance_mode` + `wb_multipliers`: `-w` o `-r`.
- `black_level_mode`: opcional `-k` o `-S`.

Nota sobre calidad de interpolación: en `dcraw` el rango disponible es `-q 0..3`.
ICCRAW expone AHD (`ahd`, `-q 3`) como preset de máxima calidad para este
backend. AMaZE no está disponible en `dcraw`, por lo que no se ofrece como valor
de receta mientras el backend activo sea `dcraw`.

Regla operativa:

- no se permiten mapeos silenciosos de algoritmos no soportados; una receta que
  pida un demosaicing que `dcraw` no puede ejecutar debe fallar antes de procesar.

## Integración `ArgyllCMS` (módulo `profile.builder`)

Archivo clave:

- `src/iccraw/profile/builder.py`

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

Validacion:

- `validate-profile` usa `xicclu` (o `icclu` como fallback) para consultar el
  perfil ICC real en modo forward hacia Lab PCS.
- La matriz `matrix_camera_to_xyz` del sidecar ya no se usa para calcular DeltaE
  en validacion.

Interoperabilidad:

- `export-cgats` escribe las muestras en formato CGATS/CTI3 (`LAB_RGB`) para
  auditoria externa o uso con herramientas compatibles.

## Integración `LittleCMS` (módulo `profile.export`)

Archivo clave:

- `src/iccraw/profile/export.py`

ICCRAW separa dos modos de salida:

1. `camera_rgb_with_input_icc`:
   - mantiene los pixeles en RGB de camara,
   - incrusta el perfil ICC de entrada generado para la sesion,
   - no realiza conversion colorimetrica.
2. `converted_srgb`:
   - usa `tificc` como CMM real,
   - transforma desde el perfil ICC de entrada a un perfil sRGB generado con
     LittleCMS/Pillow,
   - incrusta el perfil sRGB resultante en el TIFF de salida.

Regla operativa:

- la matriz `matrix_camera_to_xyz` del sidecar se conserva como diagnostico y
  compatibilidad interna, pero no se usa como sustituto de una conversion ICC en
  la exportacion de lote.

## Validación de integración en local

Las referencias de carta cargadas desde JSON se validan en modo estricto:

- `reference_source`/`source` obligatorio,
- `illuminant: D50`,
- `observer: 2`,
- ids de parche únicos,
- `reference_lab` numerico de tres componentes por parche,
- 24 parches para ColorChecker.

### Prueba de revelado RAW real (`dcraw`)

```bash
iccraw develop /ruta/a/captura.dng \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out /tmp/dev_out.tiff \
  --audit-linear /tmp/dev_linear.tiff
```

### Prueba de perfilado (`colprof`)

```bash
iccraw auto-profile-batch \
  --charts testdata/batch_images \
  --targets testdata/batch_images \
  --recipe testdata/recipes/scientific_recipe.yml \
  --reference testdata/references/colorchecker24_colorchecker2005_d50.json \
  --profile-out /tmp/camera_profile.icc \
  --profile-report /tmp/profile_report.json \
  --out /tmp/batch_out \
  --workdir /tmp/work_auto \
  --min-confidence 0.0
```

Por defecto, una deteccion de carta por fallback no se acepta para construir
perfil. Para pruebas controladas con imagenes sinteticas se puede activar de
forma explicita:

```bash
iccraw auto-profile-batch ... --allow-fallback-detection
```

Para rescatar una captura real cuando la geometria automatica no encaja, se
puede crear la deteccion con cuatro esquinas manuales y revisar el overlay:

```bash
iccraw detect-chart chart.tiff \
  --out detection.json \
  --preview overlay.png \
  --chart-type colorchecker24 \
  --manual-corners 2193,1717 3045,1686 3070,2256 2211,2288
```

## Errores comunes

- `No se puede revelar RAW: 'dcraw' no esta disponible en PATH.`
  - Solución: instalar `dcraw` o ajustar `PATH`.

- `colprof no esta en PATH`
  - Solución: instalar `argyll`.

- `No se puede convertir ICC: 'tificc' no esta disponible en PATH.`
  - Solución: instalar `liblcms2-utils` o equivalente de LittleCMS.

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
