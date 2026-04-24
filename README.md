# ICCRAW

Aplicación open source para fotografía técnico-científica:

1. revelado RAW controlado y reproducible,
2. detección automática de carta de color,
3. muestreo robusto por parche,
4. generación de perfil ICC específico de sesión,
5. aplicación del mismo flujo + perfil a lotes RAW,
6. trazabilidad y auditoría (JSON sidecars + hashes + manifiestos).

Mantenimiento comunitario:

- Comunidad de la **Asociacion Espanola de Imagen Cientifica y Forense**.

## Estado actual (importante)

ICCRAW esta en fase activa de desarrollo. Aunque ya hay CLI y GUI operativas para pruebas, la aplicacion **todavia no es plenamente funcional ni esta validada para produccion cientifica/forense**.

Usar por ahora como entorno de prototipado, evaluacion tecnica y pruebas controladas.

## Stack actual

- Lenguaje: **Python** (única toolchain del proyecto).
- Revelado RAW: `dcraw` (CLI, modo determinista).
- Metadatos RAW enriquecidos (opcional): `rawpy` (LibRaw) + `exiftool`.
- Detección geométrica: `OpenCV`.
- Colorimetría y DeltaE: `colour-science`.
- Export TIFF 16-bit: `tifffile`.
- Motor de perfil ICC: **ArgyllCMS (`colprof`)**.
- Conversion ICC de salida: **LittleCMS (`tificc`)**.
- GUI (opcional): **Qt for Python (`PySide6`)**.

## Instalación

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
# Opcional (metadatos RAW enriquecidos con rawpy/LibRaw):
# pip install -e .[raw_metadata]
# Opcional (interfaz grafica Qt):
# pip install -e .[gui]
```

Opcional pero recomendado para perfilado con ArgyllCMS y conversion ICC real:

```bash
# Debian/Ubuntu
sudo apt-get install dcraw argyll liblcms2-utils exiftool
bash scripts/check_tools.sh
```

## CLI

El entry point es `iccraw` (también invocable como `python -m iccraw`):

```bash
iccraw raw-info input.raw

iccraw develop input.raw --recipe recipe.yml --out output.tiff --audit-linear output_linear.tiff

iccraw detect-chart chart.tiff --out detection.json --preview overlay.png --chart-type colorchecker24

# Si la deteccion automatica falla, marcar cuatro esquinas de la carta:
iccraw detect-chart chart.tiff \
  --out detection.json \
  --preview overlay.png \
  --chart-type colorchecker24 \
  --manual-corners 2193,1717 3045,1686 3070,2256 2211,2288

iccraw sample-chart chart.tiff --detection detection.json --reference target.json --out samples.json

# Referencia ColorChecker 24 operativa incluida:
# testdata/references/colorchecker24_colorchecker2005_d50.json

iccraw build-develop-profile samples.json \
  --recipe recipe.yml \
  --out development_profile.json \
  --calibrated-recipe recipe_calibrated.yml

iccraw export-cgats samples.json --out samples.ti3

iccraw build-profile samples.json --recipe recipe_calibrated.yml --out camera_profile.icc --report report.json

iccraw batch-develop ./raws --recipe recipe_calibrated.yml --profile camera_profile.icc --out ./tiffs

iccraw validate-profile samples.json --profile camera_profile.icc --out validation.json

# Flujo completo automático:
# 1) develop de capturas de carta
# 2) detección automática de carta
# 3) muestreo y agregación multi-captura
# 4) perfil de revelado: neutralidad + densidad/exposicion desde carta
# 5) segunda medicion con receta calibrada
# 6) build-profile ICC
# 7) batch-develop con receta calibrada y perfil ICC embebido en TIFF 16-bit
iccraw auto-profile-batch \
  --charts ./charts_raw \
  --targets ./raws \
  --recipe recipe.yml \
  --reference target.json \
  --development-profile-out development_profile.json \
  --calibrated-recipe-out recipe_calibrated.yml \
  --profile-out camera_profile.icc \
  --profile-report profile_report.json \
  --out ./tiffs \
  --workdir ./work_auto
```

## Interfaz Gráfica Qt

La aplicación incluye una GUI basada en **Qt/PySide6** optimizada para flujo de revelado técnico:

```bash
iccraw-ui
```

O directamente:

```bash
bash scripts/run_ui.sh
```

Diseño de trabajo:

La interfaz principal se organiza en 3 pestañas:

- `1. Sesión`:
  - crear o abrir sesión de trabajo,
  - guardar metadatos de iluminación y toma,
  - definir un directorio raíz y crear automáticamente estructura persistente:
    - `charts/`, `raw/`, `profiles/`, `exports/`, `config/`, `work/`,
  - persistir estado de la sesión (`config/session.json`) con configuración y cola.
- `2. Revelado y Perfil ICC`:
  - explorador visual completo del sistema (unidades + árbol + miniaturas),
  - preview rápido RAW/DNG (miniatura embebida / half-size) y resolución configurable,
  - configuración de revelado y perfil ICC por sesión,
  - generación de perfil ICC desde cartas dentro del mismo flujo de trabajo,
  - revelado individual y por lotes a TIFF 16-bit,
  - aplicación opcional de perfil ICC activo (desactivada por defecto en preview para evitar dominantes por perfil no válido).
- `3. Cola de Revelado`:
  - cola de imágenes para revelar (añadir/quitar/limpiar),
  - ejecución de cola con estado por archivo (pendiente/ok/error),
  - monitoreo de tareas y log técnico centralizado del pipeline.

Menú superior:

- `Archivo`, `Configuracion`, `Perfil ICC`, `Vista`, `Ayuda`.
- Acceso rápido a carga/guardado de receta, perfil activo y acciones de revelado.
- `Vista` incluye pantalla completa (`F11`) y restablecer distribución de paneles.

Compatibilidad prevista de GUI:

- Linux, macOS y Windows (Qt/PySide6, selector de raíces/unidades por plataforma).

La GUI usa los mismos módulos de la CLI y escribe los mismos artefactos JSON/TIFF/ICC, manteniendo trazabilidad.
Además, conserva tamaño/estado de ventana y splitters entre sesiones.

## Receta reproducible

Ver ejemplo en [testdata/recipes/scientific_recipe.yml](testdata/recipes/scientific_recipe.yml).

Campos clave:

- `demosaic_algorithm`
- `raw_developer` (`dcraw`)
- `black_level_mode`
- `white_balance_mode`
- `wb_multipliers`
- `output_linear`
- `tone_curve`
- `profiling_mode`
- `profile_engine` (`argyll`, único motor soportado)

## Reproducibilidad y límites

- El perfil ICC **no es universal**.
- Válido para condiciones comparables de cámara + óptica + iluminante + recipe.
- Cambios de demosaicing/WB/tone mapping pueden invalidar la validez colorimétrica.

## Licencia

- Licencia del proyecto: `AGPL-3.0-or-later`.
- Objetivo del proyecto: científico, forense y comunitario sin finalidad comercial.
- Nota legal importante: la AGPL es una licencia libre y **no** restringe el uso comercial por terceros; el objetivo no comercial se expresa como gobernanza del proyecto, no como cláusula restrictiva.
- Para despliegues y redistribución, seguir:
  - [Cumplimiento Legal y Licencias](docs/LEGAL_COMPLIANCE.md)
  - [Licencias de Terceros](docs/THIRD_PARTY_LICENSES.md)

## Documentación

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Color Pipeline](docs/COLOR_PIPELINE.md)
- [Revision operativa y plan de profesionalizacion](docs/OPERATIVE_REVIEW_PLAN.md)
- [Changelog](CHANGELOG.md)
- [Manual de Usuario](docs/MANUAL_USUARIO.md)
- [Integración dcraw + ArgyllCMS](docs/INTEGRACION_DCRAW_ARGYLL.md)
- [Cumplimiento Legal y Licencias](docs/LEGAL_COMPLIANCE.md)
- [Licencias de Terceros](docs/THIRD_PARTY_LICENSES.md)
- [Decisiones](docs/DECISIONS.md)
- [Backlog priorizado](docs/ISSUES.md)
