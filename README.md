# ICCRAW

Aplicación open source para fotografía técnico-científica:

1. revelado RAW controlado y reproducible,
2. detección automática de carta de color,
3. muestreo robusto por parche,
4. generación de perfil ICC específico de sesión,
5. aplicación del mismo flujo + perfil a lotes RAW,
6. trazabilidad y auditoría (JSON sidecars + hashes + manifiestos).

## Stack actual

- Lenguaje principal: **Python**.
- Decodificación RAW: `rawpy` (LibRaw).
- Detección geométrica: `OpenCV`.
- Colorimetría y DeltaE: `colour-science`.
- Export TIFF 16-bit: `tifffile`.
- Motor de perfil recomendado: **ArgyllCMS (`colprof`)** cuando está disponible.
- Fallback explícito: perfil matrix/shaper interno con sidecar reproducible.

## Instalación

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Opcional pero recomendado para perfilado con ArgyllCMS:

```bash
# Debian/Ubuntu
sudo apt-get install argyll
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
- `black_level_mode`
- `white_balance_mode`
- `wb_multipliers`
- `output_linear`
- `tone_curve`
- `profiling_mode`
- `profile_engine` (`argyll` recomendado)

## Reproducibilidad y límites

- El perfil ICC **no es universal**.
- Válido para condiciones comparables de cámara + óptica + iluminante + recipe.
- Cambios de demosaicing/WB/tone mapping pueden invalidar la validez colorimétrica.

## Documentación

- [Architecture](/home/alejandro/Repositorios/ICC-entrada/ARCHITECTURE.md)
- [Roadmap](/home/alejandro/Repositorios/ICC-entrada/ROADMAP.md)
- [Color Pipeline](/home/alejandro/Repositorios/ICC-entrada/COLOR_PIPELINE.md)
- [Decisiones](/home/alejandro/Repositorios/ICC-entrada/docs/DECISIONS.md)
- [Backlog priorizado](/home/alejandro/Repositorios/ICC-entrada/docs/ISSUES.md)
