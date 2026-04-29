_English version: [README.md](README.md)_

<p align="center">
  <img src="assets/nexoraw-logo.svg" alt="Logo de NexoRAW" width="560">
</p>

# NexoRAW

Revelado RAW/TIFF reproducible y auditable para fotografía científica, forense y
patrimonial, con perfilado ICC por sesión, ajustes paramétricos por archivo y
trazabilidad abierta AGPL.

![Licencia AGPL-3.0-or-later](https://img.shields.io/badge/licencia-AGPL--3.0--or--later-blue) ![CI](https://img.shields.io/badge/CI-pendiente-lightgrey) ![Versión](https://img.shields.io/badge/version-v0.2.5-brightgreen) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![Plataformas](https://img.shields.io/badge/plataformas-Linux%20%7C%20macOS%20%7C%20Windows-informational)

![Interfaz principal de NexoRAW](docs/assets/screenshots/nexoraw-portada.png)

## Qué Es NexoRAW

NexoRAW no es un editor creativo generalista. Su objetivo es más estrecho: hacer
que el revelado RAW sea explicable, repetible y revisable cuando importan la
precisión colorimétrica, la procedencia y la auditoría.

El flujo actual está centrado de forma deliberada en ICC:

- con una carta de color válida, NexoRAW crea un perfil de ajuste calibrado y un
  perfil ICC de entrada propio de la sesión;
- sin carta, NexoRAW usa un perfil de ajuste manual y un ICC estándar real de
  salida (`sRGB`, `Adobe RGB (1998)` o `ProPhoto RGB`);
- la gestión ICC del monitor afecta solo a la previsualización en pantalla;
- el soporte DCP no es un objetivo activo de implementación en la línea 0.2.

## Estado Actual

NexoRAW 0.2.5 es adecuado para pruebas controladas, revisión metodológica y
validación de candidata a release. Todavía no es un sistema certificado para
producción científica o forense.

La última validación de empaquetado pasó con:

```text
203 passed, 1 warning
```

## Documentación

- [Manual de usuario](docs/MANUAL_USUARIO.es.md)
- [Metodología RAW e ICC](docs/METODOLOGIA_COLOR_RAW.es.md)
- [Pipeline de color](docs/COLOR_PIPELINE.es.md)
- [Arquitectura](docs/ARCHITECTURE.es.md)
- [Roadmap](docs/ROADMAP.es.md)
- [Rendimiento](docs/PERFORMANCE.es.md)
- [Reproducibilidad](docs/REPRODUCIBILITY.es.md)
- [NexoRAW Proof](docs/NEXORAW_PROOF.es.md)
- [C2PA/CAI](docs/C2PA_CAI.es.md)
- [Integración LibRaw + ArgyllCMS](docs/INTEGRACION_LIBRAW_ARGYLL.es.md)
- [Paquete Debian](docs/DEBIAN_PACKAGE.es.md)
- [Instalación en macOS](docs/MACOS_INSTALL.es.md)
- [Instalador Windows](docs/WINDOWS_INSTALLER.es.md)
- [Cumplimiento legal](docs/LEGAL_COMPLIANCE.es.md)
- [Licencias de terceros](docs/THIRD_PARTY_LICENSES.es.md)
- [Changelog](CHANGELOG.md)

## Arranque Rápido Desde Código

Los usuarios finales deberían preferir los instaladores publicados. Para
desarrollo:

```bash
git clone https://github.com/alejandro-probatia/NexoRAW.git
cd NexoRAW
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[gui]
nexoraw check-tools --out tools_report.json
nexoraw-ui
```

Herramientas externas opcionales para flujos completos de perfilado/exportación:

```bash
# Debian/Ubuntu
sudo apt-get install argyll exiftool

# macOS/Homebrew
brew install argyll-cms exiftool
```

## Paquete Debian

Construcción e instalación local:

```bash
bash packaging/debian/build_deb.sh
sudo apt install ./dist/nexoraw_<version>_amd64.deb
```

El paquete Debian instala NexoRAW en `/opt/nexoraw` y expone solo los lanzadores
canónicos:

- `nexoraw`
- `nexoraw-ui`

Los lanzadores heredados `iccraw` y los scripts internos de compatibilidad ya no
se instalan en 0.2.5. Si existe una beta antigua instalada, conviene retirarla
antes de probar el paquete actual.

## Flujo GUI

La aplicación gráfica se organiza en tres pestañas:

| Pestaña | Función |
| --- | --- |
| `1. Sesión` | Crear/abrir un proyecto y guardar notas de captura. |
| `2. Ajustar / Aplicar` | Navegar RAW, previsualizar, ajustar, perfilar, copiar ajustes y preparar exportaciones. |
| `3. Cola de Revelado` | Revelar lotes conservando el perfil asignado a cada archivo. |

Carpetas de sesión:

```text
00_configuraciones/   estado, recetas, perfiles, ICC, reportes y caché
01_ORG/               RAW/DNG/TIFF originales y capturas de carta
02_DRV/               TIFF derivados, manifiestos y salidas finales
```

La lista completa de controles y flujos está en el
[Manual de usuario](docs/MANUAL_USUARIO.es.md).

## Ejemplos CLI

Inspeccionar herramientas y metadatos RAW:

```bash
nexoraw check-tools --strict --out tools_report.json
nexoraw raw-info input.raw
nexoraw metadata input.raw --out metadata.json
```

Revelar un RAW con receta:

```bash
nexoraw develop input.raw \
  --recipe recipe.yml \
  --out output.tiff \
  --audit-linear output_linear.tiff
```

Crear un perfil con carta:

```bash
nexoraw detect-chart chart.tiff \
  --out detection.json \
  --preview overlay.png \
  --chart-type colorchecker24

nexoraw sample-chart chart.tiff \
  --detection detection.json \
  --reference testdata/references/colorchecker24_colorchecker2005_d50.json \
  --out samples.json

nexoraw build-develop-profile samples.json \
  --recipe recipe.yml \
  --out development_profile.json \
  --calibrated-recipe recipe_calibrated.yml

nexoraw build-profile samples.json \
  --recipe recipe_calibrated.yml \
  --out camera_profile.icc \
  --report profile_report.json
```

Revelado por lote:

```bash
nexoraw batch-develop ./01_ORG \
  --recipe recipe_calibrated.yml \
  --profile camera_profile.icc \
  --out ./02_DRV \
  --workers 0 \
  --cache-dir ./00_configuraciones/cache
```

Verificar procedencia:

```bash
nexoraw verify-proof ./02_DRV/captura.tiff.nexoraw.proof.json \
  --tiff ./02_DRV/captura.tiff \
  --raw ./01_ORG/captura.NEF

nexoraw verify-c2pa ./02_DRV/captura.tiff \
  --raw ./01_ORG/captura.NEF \
  --manifest ./02_DRV/batch_manifest.json
```

## Principios de Color y Trazabilidad

- Un perfil ICC de sesión es contextual, no universal.
- Un perfil solo es válido para condiciones comparables de cámara, óptica,
  iluminante, receta RAW y versión de software.
- Los flujos con carta separan decisiones de medición y decisiones visuales.
- Las salidas TIFF no se sobrescriben; NexoRAW crea `_v002`, `_v003`, etc.
- NexoRAW Proof vincula RAW, TIFF, receta, ICC, ajustes y hashes.
- C2PA/CAI está disponible como capa interoperable de procedencia cuando se
  configura.

## Licencia y Gobernanza

- Licencia del proyecto: `AGPL-3.0-or-later`.
- NexoRAW se mantiene como proyecto comunitario gratuito, abierto y auditable.
- La AGPL es una licencia libre y no prohíbe el uso comercial por terceros; la
  orientación no comercial es un objetivo de gobernanza, no una restricción
  adicional de licencia.
- La redistribución debe respetar las licencias de dependencias directas e
  indirectas, incluidas LibRaw/rawpy, rawpy-demosaic, ArgyllCMS, ExifTool,
  Qt/PySide6 y herramientas C2PA.

Iniciativa de **Probatia Forensics SL**, con la comunidad de la
**Asociación Española de Imagen Científica y Forense**.
