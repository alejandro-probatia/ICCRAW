# Manual de Usuario NexoRAW

## 1. ¿Qué hace NexoRAW?

NexoRAW implementa un flujo reproducible para:

1. revelar RAW con control técnico,
2. detectar automáticamente carta ColorChecker,
3. muestrear parches,
4. crear un perfil de revelado científico y un perfil ICC de cámara con ArgyllCMS,
5. aplicar ese paquete de sesión a RAW/TIFF seleccionados,
6. generar trazabilidad (JSON, hashes y manifiestos).

## Estado actual (importante)

La version actual esta en desarrollo. Existe funcionalidad base para ejecutar flujo tecnico y GUI, pero **todavia no puede considerarse una herramienta plenamente funcional ni validada para uso cientifico/forense en produccion**.

## 2. Requisitos

### 2.1 Dependencias del sistema

```bash
sudo apt-get update
sudo apt-get install -y argyll liblcms2-utils exiftool
```

Comprobación:

```bash
bash scripts/check_tools.sh
```

### 2.2 Entorno Python

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
# Opcional para GUI Qt:
pip install -e .[gui]
```

### 2.3 Licencia y uso legal

- NexoRAW se distribuye bajo `AGPL-3.0-or-later`.
- Proyecto mantenido por la comunidad de la **Asociacion Espanola de Imagen Cientifica y Forense**.
- Antes de redistribuir o desplegar como servicio, revisar:
  - `docs/LEGAL_COMPLIANCE.md`

### 2.4 Registro de cambios

- El historial oficial del proyecto se mantiene en `CHANGELOG.md`.
- Cada cambio funcional, legal o de reproducibilidad debe quedar documentado allí.

## 3. Flujo recomendado (CLI)

## 3.1 Obtener metadatos RAW

```bash
nexoraw raw-info captura.raw
```

Salida: JSON con cámara, lente, ISO, exposición, hash, etc.

## 3.2 Revelado controlado

```bash
nexoraw develop captura.raw \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out /tmp/captura_revelada.tiff \
  --audit-linear /tmp/captura_linear.tiff
```

## 3.3 Detectar carta y muestrear

```bash
nexoraw detect-chart /tmp/captura_revelada.tiff \
  --out /tmp/detection.json \
  --preview /tmp/overlay.png \
  --chart-type colorchecker24

# Fallback manual/asistido si el overlay automatico no encaja:
nexoraw detect-chart /tmp/captura_revelada.tiff \
  --out /tmp/detection.json \
  --preview /tmp/overlay.png \
  --chart-type colorchecker24 \
  --manual-corners 2193,1717 3045,1686 3070,2256 2211,2288

nexoraw sample-chart /tmp/captura_revelada.tiff \
  --detection /tmp/detection.json \
  --reference testdata/references/colorchecker24_colorchecker2005_d50.json \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out /tmp/samples.json

nexoraw export-cgats /tmp/samples.json \
  --out /tmp/samples.ti3
```

## 3.4 Calibrar sesión: perfil de revelado + ICC

```bash
nexoraw build-develop-profile /tmp/samples.json \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out /tmp/development_profile.json \
  --calibrated-recipe /tmp/recipe_calibrated.yml

nexoraw build-profile /tmp/samples.json \
  --recipe /tmp/recipe_calibrated.yml \
  --out /tmp/camera_profile.icc \
  --report /tmp/profile_report.json

nexoraw validate-profile /tmp/samples.json \
  --profile /tmp/camera_profile.icc \
  --out /tmp/validation.json
```

## 3.5 Aplicar perfil de sesión a lote

```bash
nexoraw batch-develop ./raws \
  --recipe /tmp/recipe_calibrated.yml \
  --profile /tmp/camera_profile.icc \
  --out /tmp/tiffs
```

## 3.6 Flujo automático de extremo a extremo

```bash
nexoraw auto-profile-batch \
  --charts ./charts_raw \
  --targets ./raws_objetivo \
  --recipe testdata/recipes/scientific_recipe.yml \
  --reference testdata/references/colorchecker24_colorchecker2005_d50.json \
  --development-profile-out /tmp/development_profile.json \
  --calibrated-recipe-out /tmp/recipe_calibrated.yml \
  --profile-out /tmp/camera_profile.icc \
  --profile-report /tmp/profile_report.json \
  --validation-report /tmp/qa_session_report.json \
  --validation-holdout-count 1 \
  --profile-validity-days 30 \
  --out /tmp/tiffs \
  --workdir /tmp/work_auto
```

Con `--validation-holdout-count 1`, la última captura de carta se reserva para
validación independiente y no se usa para construir el perfil.
El resultado incluye `profile_status.status`: `draft` sin validación
independiente, `validated` si supera QA, `rejected` si falla los umbrales
DeltaE y `expired` cuando se supera la vigencia declarada.

Para comparar sesiones ya generadas:

```bash
nexoraw compare-qa-reports \
  /ruta/sesion_a/qa_session_report.json \
  /ruta/sesion_b/qa_session_report.json \
  --out /tmp/qa_comparison.json
```

Para comprobar que el entorno externo está listo antes de calibrar:

```bash
nexoraw check-tools --strict --out config/nexoraw_tools.json
```

## 4. Flujo con interfaz grafica Qt

Arranque:

```bash
nexoraw-ui
```

o:

```bash
bash scripts/run_ui.sh
```

Instalacion beta con paquete Debian:

```bash
sudo apt install ./dist/nexoraw_0.1.0~beta4_amd64.deb
nexoraw check-tools --strict
nexoraw-ui
```

Para rescatar una carta no detectada automaticamente desde la GUI:

1. Cargar la captura de carta en el visor.
2. En `1. Calibrar sesión`, usar `Marcar en visor` y hacer clic en cuatro esquinas.
3. Guardar la deteccion manual y revisar el PNG de overlay generado.

Estructura de la interfaz:

Pestañas principales:

1. `Sesión`
   - crear o abrir sesión,
   - guardar metadatos de iluminación y toma,
   - crear estructura persistente en el directorio raíz:
     - `charts/`, `raw/`, `profiles/`, `exports/`, `config/`, `work/`,
   - persistir configuración y cola en `config/session.json`.
2. `Calibrar / Aplicar`
   - navegación completa de unidades y directorios,
   - selección visual por miniaturas,
   - carga automática en visor al seleccionar una miniatura RAW/TIFF compatible,
   - preview RAW rápida,
   - comparación original/resultado,
   - zoom, rotación y reencuadre por arrastre en el visor,
   - paneles verticales de procesado: calibración con criterios RAW,
     corrección básica, detalle, perfil activo y aplicación de sesión,
   - `Calibrar sesión`: usar la selección de miniaturas o una carpeta de cartas,
     ajustar criterios RAW globales y generar perfil de revelado + ICC,
   - `Corrección básica`: iluminante final, temperatura, matiz, brillo, niveles,
     contraste y curva de medios,
   - `Detalle`: eliminación de ruido de luminancia/color, nitidez y corrección
     de aberración cromática lateral,
   - `Aplicar sesión`: revelar selección o carpeta con receta calibrada + ICC.
3. `Cola de Revelado`
   - cola de archivos para revelar,
   - estado por archivo (pendiente/completado/error),
   - monitoreo de tareas,
   - log de eventos del pipeline.

Flujo recomendado en GUI:

1. Ir a `Sesión` y crear/abrir sesión con su directorio raíz.
2. Registrar iluminación y toma para esa sesión.
3. En `Calibrar / Aplicar`, seleccionar una o varias capturas RAW/DNG con carta y ejecutar `Generar perfil de sesión`.
4. Ajustar `Corrección básica` y `Detalle` si el criterio de salida lo requiere.
5. En `Aplicar sesión`, revelar RAW individuales, una selección de miniaturas o una carpeta.
6. En `Cola de Revelado`, añadir archivos y ejecutar cola cuando se necesite procesado diferido.
7. Revisar estado, artefactos JSON y monitoreo para trazabilidad e incidencias.

Notas de uso de preview:

- El checkbox `Aplicar perfil ICC en resultado` se inicia desactivado para evitar dominantes si el perfil activo no corresponde al flujo actual.
- La exposición, densidad, balance de blancos y base colorimétrica se derivan de la carta; no se editan como ajustes creativos.
- Si el perfil activo no tiene sidecar `.profile.json` válido o genera clipping extremo en preview, la aplicación muestra la vista sin perfil y registra aviso.
- La barra superior muestra progreso indeterminado durante carga, generación de
  perfil y revelado por lote.
- LibRaw/rawpy es el unico motor RAW; DCB es el valor por defecto instalable.
  AMaZE requiere `rawpy-demosaic` o una build de `rawpy`/LibRaw con demosaic
  pack GPL3 y `DEMOSAIC_PACK_GPL3=True`.
- `Vista -> Pantalla completa` (`F11`) y `Vista -> Restablecer distribución` permiten adaptar la interfaz a cualquier tamaño de pantalla.
- Al abrir una sesión, las salidas operativas se fuerzan al árbol de sesión:
  `profiles/` para ICC, `config/` para reportes/recetas, `work/` para
  intermedios y `exports/` para TIFF/preview. Los temporales internos siguen
  usándose solo como scratch transitorio.
- `Ayuda -> Diagnóstico herramientas...` muestra versiones/rutas de ArgyllCMS,
  LittleCMS y `exiftool`; `rawpy`/LibRaw queda registrado en el contexto de
  ejecución.

## 5. Artefactos que genera el sistema

Durante el proceso, NexoRAW produce:

- TIFF 16-bit,
- perfil ICC,
- sidecar de perfil (`.profile.json`),
- detección de carta (`detection.json`),
- muestras (`samples.json`),
- reporte y validación DeltaE,
- manifiesto de lote (`batch_manifest.json`).

## 6. Buenas prácticas de captura

- iluminación uniforme y estable,
- carta limpia y en foco,
- exposición sin clipping,
- bloquear configuración de cámara entre carta y lote,
- usar exactamente la misma `recipe` del perfilado para el batch.

## 7. Advertencias científicas

- El perfil ICC de cámara no es universal.
- Es válido para condiciones comparables:
  - cámara,
  - óptica,
  - iluminante,
  - recipe de revelado.
- Cambios en WB, demosaicing o tone-curve pueden degradar la validez.

## 8. Problemas frecuentes

- Error LibRaw/rawpy:
  - comprobar que la ruta es RAW real y no fichero de ejemplo truncado,
  - reinstalar dependencias Python con `pip install -e .`,
  - si se usa AMaZE, ejecutar `python scripts/check_amaze_support.py` y revisar
    `docs/AMAZE_GPL3.md`.
- Error `colprof`:
  - revisar que Argyll esté instalado y que la referencia de carta sea correcta.
- Detección con baja confianza:
  - mejorar encuadre de carta, iluminación y foco.
- Detección por fallback:
  - el flujo automático la rechaza por defecto para evitar perfiles inválidos,
  - usar `--allow-fallback-detection` solo en pruebas controladas o con revisión
    manual del overlay.
- Referencia de carta inválida:
  - comprobar que declara `reference_source`, `illuminant: D50`, `observer: 2`
    y valores `reference_lab` para todos los parches.

## 9. C2PA/CAI (propuesta)

Es posible integrar C2PA/CAI para añadir cadena de custodia criptográfica del proceso.

Recomendación de implantación:

1. generar manifiesto C2PA con hashes, recipe, perfil y métricas,
2. firmar con certificado del laboratorio,
3. embebido en TIFF o sidecar `.c2pa`.

Ver detalles técnicos en:

- `docs/INTEGRACION_LIBRAW_ARGYLL.md`
