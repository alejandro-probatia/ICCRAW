#!/usr/bin/env bash
set -euo pipefail

run_app() {
  if [ -x ".venv/bin/probraw" ]; then
    .venv/bin/probraw "$@"
  elif command -v probraw >/dev/null 2>&1; then
    probraw "$@"
  else
    python -m probraw "$@"
  fi
}

run_app raw-info testdata/raw/mock_capture.nef
run_app develop testdata/charts/synthetic_colorchecker.tiff \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out /tmp/session_chart.tiff \
  --audit-linear /tmp/session_chart_linear.tiff

run_app detect-chart /tmp/session_chart.tiff \
  --out /tmp/detection.json \
  --preview /tmp/overlay.png

run_app sample-chart /tmp/session_chart.tiff \
  --detection /tmp/detection.json \
  --reference testdata/references/colorchecker24_colorchecker2005_d50.json \
  --out /tmp/samples.json

run_app build-profile /tmp/samples.json \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out /tmp/camera_profile.icc \
  --report /tmp/profile_report.json

run_app batch-develop testdata/batch_images \
  --recipe testdata/recipes/scientific_recipe.yml \
  --profile /tmp/camera_profile.icc \
  --out /tmp/batch_tiffs
