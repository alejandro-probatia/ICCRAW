# Manual de Usuario ICCRAW

## 1. ¿Qué hace ICCRAW?

ICCRAW implementa un flujo reproducible para:

1. revelar RAW con control técnico,
2. detectar automáticamente carta ColorChecker,
3. muestrear parches,
4. crear perfil ICC de cámara con ArgyllCMS,
5. aplicar el mismo flujo + perfil a lotes RAW/TIFF,
6. generar trazabilidad (JSON, hashes y manifiestos).

## Estado actual (importante)

La version actual esta en desarrollo. Existe funcionalidad base para ejecutar flujo tecnico y GUI, pero **todavia no puede considerarse una herramienta plenamente funcional ni validada para uso cientifico/forense en produccion**.

## 2. Requisitos

### 2.1 Dependencias del sistema

```bash
sudo apt-get update
sudo apt-get install -y dcraw argyll exiftool
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
# Opcional para metadatos RAW enriquecidos:
pip install -e .[raw_metadata]
# Opcional para GUI Qt:
pip install -e .[gui]
```

### 2.3 Licencia y uso legal

- ICCRAW se distribuye bajo `AGPL-3.0-or-later`.
- Proyecto mantenido por la comunidad de la **Asociacion Espanola de Imagen Cientifica y Forense**.
- Antes de redistribuir o desplegar como servicio, revisar:
  - `docs/LEGAL_COMPLIANCE.md`

### 2.4 Registro de cambios

- El historial oficial del proyecto se mantiene en `CHANGELOG.md`.
- Cada cambio funcional, legal o de reproducibilidad debe quedar documentado allí.

## 3. Flujo recomendado (CLI)

## 3.1 Obtener metadatos RAW

```bash
app raw-info captura.raw
```

Salida: JSON con cámara, lente, ISO, exposición, hash, etc.

## 3.2 Revelado controlado

```bash
app develop captura.raw \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out /tmp/captura_revelada.tiff \
  --audit-linear /tmp/captura_linear.tiff
```

## 3.3 Detectar carta y muestrear

```bash
app detect-chart /tmp/captura_revelada.tiff \
  --out /tmp/detection.json \
  --preview /tmp/overlay.png \
  --chart-type colorchecker24

app sample-chart /tmp/captura_revelada.tiff \
  --detection /tmp/detection.json \
  --reference testdata/references/colorchecker24_reference.json \
  --out /tmp/samples.json
```

## 3.4 Construir y validar perfil ICC

```bash
app build-profile /tmp/samples.json \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out /tmp/camera_profile.icc \
  --report /tmp/profile_report.json

app validate-profile /tmp/samples.json \
  --profile /tmp/camera_profile.icc \
  --out /tmp/validation.json
```

## 3.5 Aplicar a lote

```bash
app batch-develop ./raws \
  --recipe testdata/recipes/scientific_recipe.yml \
  --profile /tmp/camera_profile.icc \
  --out /tmp/tiffs
```

## 3.6 Flujo automático de extremo a extremo

```bash
app auto-profile-batch \
  --charts ./charts_raw \
  --targets ./raws_objetivo \
  --recipe testdata/recipes/scientific_recipe.yml \
  --reference testdata/references/colorchecker24_reference.json \
  --profile-out /tmp/camera_profile.icc \
  --profile-report /tmp/profile_report.json \
  --out /tmp/tiffs \
  --workdir /tmp/work_auto
```

## 4. Flujo con interfaz grafica Qt

Arranque:

```bash
app-ui
# o:
app-ui-qt
```

o:

```bash
bash scripts/run_ui.sh
# o:
bash scripts/run_ui_qt.sh
```

Estructura de la interfaz:

Pestañas principales:

1. `Generación Perfil ICC`
   - genera perfil ICC a partir de capturas de carta,
   - guarda perfil y reporte para reutilización en sesiones posteriores.
2. `Revelado RAW`
   - navegación completa de unidades y directorios,
   - selección visual por miniaturas,
   - preview RAW rápida,
   - ajustes de nitidez y ruido,
   - revelado individual y por lotes,
   - aplicación opcional de perfil ICC en preview/export.
3. `Monitoreo Flujo`
   - estado de tareas,
   - tabla de ejecución,
   - log de eventos del pipeline.

Flujo recomendado en GUI:

1. Navegar a la carpeta de trabajo en el panel izquierdo.
2. Ir a `Generación Perfil ICC`, asignar carpeta de cartas y generar el perfil.
3. Guardar y activar el perfil generado para sesiones posteriores.
4. Ir a `Revelado RAW`, seleccionar visualmente RAW objetivo y cargar preview.
5. Ajustar nitidez y ruido (luminancia/color) en panel derecho.
6. Ejecutar revelado individual o por lote y exportar TIFF 16-bit.
7. Revisar `Monitoreo Flujo` para estado de tareas, incidencias y trazas.

Notas de uso de preview:

- El checkbox `Aplicar perfil ICC en resultado` se inicia desactivado para evitar dominantes si el perfil activo no corresponde al flujo actual.
- Si el perfil activo no tiene sidecar `.profile.json` válido o genera clipping extremo en preview, la aplicación muestra la vista sin perfil y registra aviso.
- `Vista -> Pantalla completa` (`F11`) y `Vista -> Restablecer distribución` permiten adaptar la interfaz a cualquier tamaño de pantalla.

## 5. Artefactos que genera el sistema

Durante el proceso, ICCRAW produce:

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

- Error `dcraw`:
  - comprobar que la ruta es RAW real y no fichero de ejemplo truncado.
- Error `colprof`:
  - revisar que Argyll esté instalado y que la referencia de carta sea correcta.
- Detección con baja confianza:
  - mejorar encuadre de carta, iluminación y foco.

## 9. C2PA/CAI (propuesta)

Es posible integrar C2PA/CAI para añadir cadena de custodia criptográfica del proceso.

Recomendación de implantación:

1. generar manifiesto C2PA con hashes, recipe, perfil y métricas,
2. firmar con certificado del laboratorio,
3. embebido en TIFF o sidecar `.c2pa`.

Ver detalles técnicos en:

- `docs/INTEGRACION_DCRAW_ARGYLL.md`
