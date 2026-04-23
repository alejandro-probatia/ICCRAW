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

## Stack actual

- Lenguaje principal: **Python**.
- Revelado RAW: `dcraw` (CLI, modo determinista).
- Metadatos RAW enriquecidos (opcional): `rawpy` (LibRaw) + `exiftool`.
- Detección geométrica: `OpenCV`.
- Colorimetría y DeltaE: `colour-science`.
- Export TIFF 16-bit: `tifffile`.
- Motor de perfil ICC: **ArgyllCMS (`colprof`)**.

## Instalación

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
# Opcional (metadatos RAW enriquecidos con rawpy/LibRaw):
# pip install -e .[raw_metadata]
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

## Interfaz Gráfica Ligera

La aplicación incluye una GUI simple basada en `tkinter` para operar el flujo sin comandos manuales:

```bash
app-ui
```

o directamente:

```bash
bash scripts/run_ui.sh
```

Pestañas disponibles:

- `Información RAW`
- `Revelado`
- `Detectar + Muestrear`
- `Crear + Validar Perfil`
- `Revelado por Lotes`
- `Flujo Automático` (capturas de carta -> perfil ICC -> lote TIFF 16-bit con ICC)

La GUI escribe los mismos artefactos JSON/TIFF/ICC que la CLI, manteniendo trazabilidad.

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
- Para despliegues y redistribucion, seguir:
  - [Cumplimiento Legal y Licencias](/home/alejandro/Repositorios/ICC-entrada/docs/LEGAL_COMPLIANCE.md)

## Documentación

- [Architecture](/home/alejandro/Repositorios/ICC-entrada/ARCHITECTURE.md)
- [Roadmap](/home/alejandro/Repositorios/ICC-entrada/ROADMAP.md)
- [Color Pipeline](/home/alejandro/Repositorios/ICC-entrada/COLOR_PIPELINE.md)
- [Changelog](/home/alejandro/Repositorios/ICC-entrada/CHANGELOG.md)
- [Manual de Usuario](/home/alejandro/Repositorios/ICC-entrada/docs/MANUAL_USUARIO.md)
- [Integración dcraw + ArgyllCMS](/home/alejandro/Repositorios/ICC-entrada/docs/INTEGRACION_DCRAW_ARGYLL.md)
- [Cumplimiento Legal y Licencias](/home/alejandro/Repositorios/ICC-entrada/docs/LEGAL_COMPLIANCE.md)
- [Decisiones](/home/alejandro/Repositorios/ICC-entrada/docs/DECISIONS.md)
- [Backlog priorizado](/home/alejandro/Repositorios/ICC-entrada/docs/ISSUES.md)
