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

- Lenguaje principal: **Python**.
- Revelado RAW: `dcraw` (CLI, modo determinista).
- Metadatos RAW enriquecidos (opcional): `rawpy` (LibRaw) + `exiftool`.
- Detección geométrica: `OpenCV`.
- Colorimetría y DeltaE: `colour-science`.
- Export TIFF 16-bit: `tifffile`.
- Motor de perfil ICC: **ArgyllCMS (`colprof`)**.
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

Opcional pero recomendado para perfilado con ArgyllCMS:

```bash
# Debian/Ubuntu
sudo apt-get install dcraw argyll exiftool
bash scripts/check_tools.sh
```

## CLI

```bash
app raw-info input.raw

app develop input.raw --recipe recipe.yml --out output.tiff --audit-linear output_linear.tiff

app detect-chart chart.tiff --out detection.json --preview overlay.png --chart-type colorchecker24

app sample-chart chart.tiff --detection detection.json --reference target.json --out samples.json

app build-profile samples.json --recipe recipe.yml --out camera_profile.icc --report report.json

app batch-develop ./raws --recipe recipe.yml --profile camera_profile.icc --out ./tiffs

app validate-profile samples.json --profile camera_profile.icc --out validation.json

# Flujo completo automático:
# 1) develop de capturas de carta
# 2) detección automática de carta
# 3) muestreo y agregación multi-captura
# 4) build-profile
# 5) batch-develop con perfil ICC embebido en TIFF 16-bit
app auto-profile-batch \
  --charts ./charts_raw \
  --targets ./raws \
  --recipe recipe.yml \
  --reference target.json \
  --profile-out camera_profile.icc \
  --profile-report profile_report.json \
  --out ./tiffs \
  --workdir ./work_auto
```

## Interfaz Grafica Qt

La aplicacion incluye una GUI basada en **Qt/PySide6** optimizada para flujo de revelado técnico:

```bash
app-ui
# o:
app-ui-qt
```

o directamente:

```bash
bash scripts/run_ui.sh
# o:
bash scripts/run_ui_qt.sh
```

Diseño de trabajo:

La interfaz principal se organiza en 3 pestañas:

- `1. Generación Perfil ICC`:
  - selecciona directorio de cartas,
  - genera perfil ICC y reporte para guardar/reutilizar más adelante,
  - usa configuración RAW compartida para mantener consistencia científica.
- `2. Revelado RAW`:
  - explorador visual completo del sistema (unidades + árbol + miniaturas),
  - preview rápido RAW/DNG (miniatura embebida / half-size) y resolución configurable,
  - pestaña `Nitidez` con nitidez + ruido luminancia/color,
  - revelado individual y por lotes (selección o directorio completo),
  - aplicación opcional de perfil ICC activo (desactivada por defecto en preview para evitar dominantes por perfil no válido).
- `3. Monitoreo Flujo`:
  - estado de tareas en ejecución,
  - tabla de operaciones (en curso/completadas/error),
  - log técnico centralizado del pipeline.

Menu superior:

- `Archivo`, `Configuracion`, `Perfil ICC`, `Vista`, `Ayuda`.
- Acceso rapido a carga/guardado de receta, perfil activo y acciones de revelado.
- `Vista` incluye pantalla completa (`F11`) y restablecer distribución de paneles.

Compatibilidad prevista de GUI:

- Linux, macOS y Windows (Qt/PySide6, selector de raices/unidades por plataforma).

La GUI usa los mismos modulos de la CLI y escribe los mismos artefactos JSON/TIFF/ICC, manteniendo trazabilidad.
Además, conserva tamaño/estado de ventana y splitters entre sesiones.

## Receta reproducible

Ver ejemplo en [testdata/recipes/scientific_recipe.yml](/home/alejandro/Repositorios/ICC-entrada/testdata/recipes/scientific_recipe.yml).

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
- Objetivo del proyecto: cientifico, forense y comunitario sin finalidad comercial.
- Nota legal importante: la AGPL es una licencia libre y **no** restringe el uso comercial por terceros; el objetivo no comercial se expresa como gobernanza del proyecto, no como clausula restrictiva.
- Para despliegues y redistribucion, seguir:
  - [Cumplimiento Legal y Licencias](/home/alejandro/Repositorios/ICC-entrada/docs/LEGAL_COMPLIANCE.md)
  - [Licencias de Terceros](/home/alejandro/Repositorios/ICC-entrada/docs/THIRD_PARTY_LICENSES.md)

## Documentación

- [Architecture](/home/alejandro/Repositorios/ICC-entrada/ARCHITECTURE.md)
- [Roadmap](/home/alejandro/Repositorios/ICC-entrada/ROADMAP.md)
- [Color Pipeline](/home/alejandro/Repositorios/ICC-entrada/COLOR_PIPELINE.md)
- [Changelog](/home/alejandro/Repositorios/ICC-entrada/CHANGELOG.md)
- [Manual de Usuario](/home/alejandro/Repositorios/ICC-entrada/docs/MANUAL_USUARIO.md)
- [Integración dcraw + ArgyllCMS](/home/alejandro/Repositorios/ICC-entrada/docs/INTEGRACION_DCRAW_ARGYLL.md)
- [Cumplimiento Legal y Licencias](/home/alejandro/Repositorios/ICC-entrada/docs/LEGAL_COMPLIANCE.md)
- [Licencias de Terceros](/home/alejandro/Repositorios/ICC-entrada/docs/THIRD_PARTY_LICENSES.md)
- [Decisiones](/home/alejandro/Repositorios/ICC-entrada/docs/DECISIONS.md)
- [Backlog priorizado](/home/alejandro/Repositorios/ICC-entrada/docs/ISSUES.md)
