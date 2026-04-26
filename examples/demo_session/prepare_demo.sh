#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEMO_DIR="$ROOT_DIR/examples/demo_session"
DATA_DIR="$DEMO_DIR/data"

mkdir -p "$DATA_DIR/batch_images" "$DATA_DIR/references"

cp "$ROOT_DIR/testdata/batch_images/session_001.tiff" "$DATA_DIR/batch_images/session_001.tiff"
cp "$ROOT_DIR/testdata/batch_images/session_002.tiff" "$DATA_DIR/batch_images/session_002.tiff"
cp "$ROOT_DIR/testdata/references/colorchecker24_colorchecker2005_d50.json" \
  "$DATA_DIR/references/colorchecker24_colorchecker2005_d50.json"

cat > "$DATA_DIR/MANIFEST.sha256" <<'MANIFEST'
9e8f73d43e9288713fc17634af77abea82dbb23ed87bc8e203332c22e93a23cc  batch_images/session_001.tiff
9e8f73d43e9288713fc17634af77abea82dbb23ed87bc8e203332c22e93a23cc  batch_images/session_002.tiff
b1f1934b40fef8bbb231495a6b9a757a044a84c5082d400c20843e5828022817  references/colorchecker24_colorchecker2005_d50.json
MANIFEST

if command -v sha256sum >/dev/null 2>&1; then
  (cd "$DATA_DIR" && sha256sum -c MANIFEST.sha256)
elif command -v shasum >/dev/null 2>&1; then
  (cd "$DATA_DIR" && shasum -a 256 -c MANIFEST.sha256)
else
  echo "WARNING: sha256sum/shasum no disponible; no se valida checksum automaticamente." >&2
fi

echo "Dataset demo preparado en: $DATA_DIR"
