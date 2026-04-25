# Integración de LibRaw, ArgyllCMS y LittleCMS en NexoRAW

## Objetivo

NexoRAW usa un único motor de revelado RAW:

- **LibRaw**, mediante la dependencia Python `rawpy`, para decodificación e
  interpolación RAW.
- **ArgyllCMS** (`colprof`) como motor de generación de perfiles ICC.
- **LittleCMS** (`tificc`) como CMM para conversiones ICC de salida.

La meta es mantener un flujo científico reproducible y auditable con menos
ramas de código y sin mapeos implícitos entre motores RAW distintos.

## Instalación del sistema

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[gui]
sudo apt-get install -y argyll liblcms2-utils exiftool
```

`rawpy`/LibRaw se instala como dependencia Python del proyecto. Para AMaZE se
requiere una build GPL3 con `DEMOSAIC_PACK_GPL3=True`; ver
`docs/AMAZE_GPL3.md`.

Verificación:

```bash
bash scripts/check_tools.sh
nexoraw check-tools --strict --out tools_report.json
```

`nexoraw check-tools` registra disponibilidad de ArgyllCMS, LittleCMS y
`exiftool`. Las versiones de `rawpy` y LibRaw quedan registradas en el contexto
de ejecución (`run_context`).

## Integración LibRaw/rawpy

Archivo clave:

- `src/iccraw/raw/pipeline.py`

Para entradas RAW, NexoRAW ejecuta `rawpy.imread(...).postprocess(...)` con un
contrato explícito:

- salida de 16 bit,
- `gamma=(1, 1)` para mantener salida lineal,
- `no_auto_bright=True`,
- `highlight_mode=Clip`,
- `user_flip=0`,
- `output_color=raw` para conservar RGB de cámara,
- balance de blancos desde metadatos o multiplicadores fijos según receta,
- black/white level manual solo si la receta lo declara.

Mapeo de `recipe`:

- `raw_developer`: debe ser `libraw`.
- `demosaic_algorithm`: valores soportados por `rawpy`, entre ellos `dcb`,
  `dht`, `ahd`, `vng`, `ppg`, `linear` y, si la build lo incluye, `amaze`.
- `white_balance_mode` + `wb_multipliers`: `camera_metadata` o `fixed`.
- `black_level_mode`: opcional `fixed:<valor>` o `white:<valor>`.

DCB (`demosaic_algorithm: dcb`) es el valor por defecto porque ofrece alta
calidad y funciona con los wheels estándar de `rawpy`. AMaZE puede usarse con
una build de `rawpy`/LibRaw compilada con el demosaic pack GPL3; si la build no
lo incluye, LibRaw devuelve un error explícito.

Regla operativa:

- no se permiten motores RAW alternativos ni mapeos silenciosos; una receta que
  pida un `raw_developer` distinto de `libraw` falla antes de procesar.
- AMaZE requiere `rawpy.flags["DEMOSAIC_PACK_GPL3"] == True`. Si no esta
  disponible, la CLI/backend fallan con error explicito y la GUI degrada la
  receta interactiva a `dcb` para no bloquear la calibracion.

## Integración ArgyllCMS

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

Validación:

- `validate-profile` usa `xicclu` o `icclu` para consultar el perfil ICC real
  en modo forward hacia Lab PCS.
- La matriz `matrix_camera_to_xyz` del sidecar queda como diagnóstico, no como
  sustituto de una conversión ICC real.

## Integración LittleCMS

Archivo clave:

- `src/iccraw/profile/export.py`

Modos de salida:

1. `camera_rgb_with_input_icc`: mantiene píxeles en RGB de cámara e incrusta el
   perfil ICC de entrada generado para la sesión.
2. `converted_srgb`: usa `tificc` como CMM para transformar desde el perfil ICC
   de entrada a sRGB.

## Validación local

```bash
nexoraw develop /ruta/a/captura.dng \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out /tmp/dev_out.tiff \
  --audit-linear /tmp/dev_linear.tiff
```

```bash
nexoraw auto-profile-batch \
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

## Errores comunes

- `No se puede revelar RAW: dependencia 'rawpy'/'LibRaw' no disponible.`
  - Solución: reinstalar el paquete o ejecutar `pip install -e .`.
- `colprof no esta en PATH`
  - Solución: instalar `argyll`.
- `No se puede convertir ICC: 'tificc' no esta disponible en PATH.`
  - Solución: instalar `liblcms2-utils`.

## Integración futura C2PA/CAI

La arquitectura de sidecars y manifiestos permite añadir C2PA/CAI más adelante:

1. hash de entrada/salida,
2. receta,
3. versión software + commit,
4. perfil ICC aplicado,
5. métricas DeltaE,
6. firma del laboratorio o entidad responsable.
