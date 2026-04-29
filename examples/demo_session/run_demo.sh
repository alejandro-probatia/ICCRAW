#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEMO_DIR="$ROOT_DIR/examples/demo_session"
DATA_DIR="$DEMO_DIR/data"
OUTPUT_DIR="$DEMO_DIR/output"

bash "$DEMO_DIR/prepare_demo.sh"

if command -v probraw >/dev/null 2>&1; then
  PROBRAW_CMD=(probraw)
  USING_WINDOWS_PYTHON=0
elif [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PROBRAW_CMD=("$ROOT_DIR/.venv/bin/python" -m probraw)
  USING_WINDOWS_PYTHON=0
elif [ -x "$ROOT_DIR/.venv/Scripts/python.exe" ]; then
  PROBRAW_CMD=("$ROOT_DIR/.venv/Scripts/python.exe" -m probraw)
  USING_WINDOWS_PYTHON=1
else
  echo "ERROR: no se encontro comando probraw ni entorno .venv listo." >&2
  exit 1
fi

to_native_path() {
  local p="$1"
  if [[ "$USING_WINDOWS_PYTHON" -eq 1 ]] && command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$p"
  elif [[ "$USING_WINDOWS_PYTHON" -eq 1 ]] && command -v wslpath >/dev/null 2>&1; then
    wslpath -w "$p"
  else
    printf '%s' "$p"
  fi
}

CHARTS_ARG="$(to_native_path "$DATA_DIR/batch_images")"
TARGETS_ARG="$(to_native_path "$DATA_DIR/batch_images")"
RECIPE_ARG="$(to_native_path "$DEMO_DIR/recipe.yml")"
REFERENCE_ARG="$(to_native_path "$DATA_DIR/references/colorchecker24_colorchecker2005_d50.json")"
OUTPUT_ARG="$(to_native_path "$OUTPUT_DIR")"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

"${PROBRAW_CMD[@]}" auto-profile-batch \
  --charts "$CHARTS_ARG" \
  --targets "$TARGETS_ARG" \
  --recipe "$RECIPE_ARG" \
  --reference "$REFERENCE_ARG" \
  --development-profile-out "$OUTPUT_ARG/development_profile.json" \
  --calibrated-recipe-out "$OUTPUT_ARG/recipe_calibrated.yml" \
  --profile-out "$OUTPUT_ARG/camera_profile.icc" \
  --profile-report "$OUTPUT_ARG/profile_report.json" \
  --validation-report "$OUTPUT_ARG/qa_session_report.json" \
  --validation-holdout-count 1 \
  --qa-mean-deltae2000-max 100 \
  --qa-max-deltae2000-max 100 \
  --profile-validity-days 30 \
  --allow-fallback-detection \
  --min-confidence 0.0 \
  --out "$OUTPUT_ARG/tiffs" \
  --workdir "$OUTPUT_ARG/work_auto" >/dev/null

PYTHON_BIN="python3"
if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif [ -x "$ROOT_DIR/.venv/Scripts/python.exe" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/Scripts/python.exe"
fi

readarray -t METRICS < <("$PYTHON_BIN" - <<'PY' "$OUTPUT_ARG"
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
qa = json.loads((out / "qa_session_report.json").read_text(encoding="utf-8"))
manifest_path = out / "tiffs" / "batch_manifest.json"
profile_path = out / "camera_profile.icc"
summary = qa.get("validation_error_summary", {})
status = qa.get("status", "unknown")
print(str(profile_path))
print(summary.get("mean_delta_e76", "n/a"))
print(summary.get("mean_delta_e2000", "n/a"))
print(status)
print(str(manifest_path))
PY
)

echo "ICC generado: ${METRICS[0]}"
echo "DeltaE76 medio: ${METRICS[1]}"
echo "DeltaE2000 medio: ${METRICS[2]}"
echo "Estado operacional del perfil: ${METRICS[3]}"
echo "Manifiesto: ${METRICS[4]}"
