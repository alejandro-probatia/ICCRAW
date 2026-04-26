#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEB_PATH="${1:-$ROOT/dist/nexoraw_0.1.0~beta5_$(dpkg --print-architecture).deb}"
REQUIRE_AMAZE="${NEXORAW_REQUIRE_AMAZE:-1}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

is_true() {
  case "${1,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "falta archivo: ${path#$EXTRACT_ROOT/}"
}

require_executable() {
  local path="$1"
  [[ -x "$path" ]] || fail "falta ejecutable: ${path#$EXTRACT_ROOT/}"
}

png_size() {
  python3 - "$1" <<'PY'
from pathlib import Path
import struct
import sys

path = Path(sys.argv[1])
data = path.read_bytes()
if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
    raise SystemExit("not-png")
width, height = struct.unpack(">II", data[16:24])
print(f"{width}x{height}")
PY
}

[[ -f "$DEB_PATH" ]] || fail "no existe el paquete: $DEB_PATH"

package="$(dpkg-deb --field "$DEB_PATH" Package)"
[[ "$package" == "nexoraw" ]] || fail "Package debe ser nexoraw, es: $package"

dpkg-deb --field "$DEB_PATH" Replaces | grep -qw iccraw || fail "falta Replaces: iccraw"
dpkg-deb --field "$DEB_PATH" Conflicts | grep -qw iccraw || fail "falta Conflicts: iccraw"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
EXTRACT_ROOT="$tmp/root"
mkdir -p "$EXTRACT_ROOT"
dpkg-deb -x "$DEB_PATH" "$EXTRACT_ROOT"
dpkg-deb -e "$DEB_PATH" "$tmp/DEBIAN"

contents="$tmp/contents.txt"
dpkg-deb --contents "$DEB_PATH" > "$contents"

grep -qE '\./usr/bin/nexoraw$' "$contents" || fail "falta /usr/bin/nexoraw"
grep -qE '\./usr/bin/nexoraw-ui$' "$contents" || fail "falta /usr/bin/nexoraw-ui"
if grep -qE '\./usr/bin/iccraw($|-ui$)' "$contents"; then
  fail "el paquete no puede instalar lanzadores /usr/bin/iccraw heredados"
fi
if grep -qE '\./opt/nexoraw/venv/bin/iccraw($|-ui$)' "$contents"; then
  fail "el venv empaquetado no puede contener scripts iccraw heredados"
fi

require_executable "$EXTRACT_ROOT/usr/bin/nexoraw"
require_executable "$EXTRACT_ROOT/usr/bin/nexoraw-ui"
require_file "$EXTRACT_ROOT/usr/share/applications/nexoraw.desktop"
require_file "$EXTRACT_ROOT/usr/share/icons/hicolor/scalable/apps/nexoraw.svg"
require_file "$EXTRACT_ROOT/usr/share/pixmaps/nexoraw.png"

desktop="$EXTRACT_ROOT/usr/share/applications/nexoraw.desktop"
grep -Fxq "Name=NexoRAW" "$desktop" || fail "desktop Name no es NexoRAW"
grep -Fxq "Exec=nexoraw-ui" "$desktop" || fail "desktop Exec no usa nexoraw-ui"
grep -Fxq "Icon=nexoraw" "$desktop" || fail "desktop Icon no usa nexoraw"
grep -Eq '^Categories=.*Graphics.*Photography.*;$' "$desktop" || fail "desktop Categories no incluye Graphics y Photography"
if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "$desktop"
fi

for size in 16 32 48 64 128 256 512; do
  icon="$EXTRACT_ROOT/usr/share/icons/hicolor/${size}x${size}/apps/nexoraw.png"
  require_file "$icon"
  actual="$(png_size "$icon")"
  [[ "$actual" == "${size}x${size}" ]] || fail "icono ${size}x${size} tiene tamano $actual"
done
actual_pixmap="$(png_size "$EXTRACT_ROOT/usr/share/pixmaps/nexoraw.png")"
[[ "$actual_pixmap" == "512x512" ]] || fail "pixmap nexoraw.png debe ser 512x512, es $actual_pixmap"

if is_true "$REQUIRE_AMAZE"; then
  depends="$(dpkg-deb --field "$DEB_PATH" Depends)"
  for dep in libgomp1 liblcms2-2 libjpeg-turbo8 libstdc++6; do
    echo "$depends" | grep -qw "$dep" || fail "falta dependencia runtime AMaZE: $dep"
  done
  amaze_json="$EXTRACT_ROOT/usr/share/doc/nexoraw/third_party/rawpy-demosaic/check-amaze.json"
  amaze_metadata="$EXTRACT_ROOT/usr/share/doc/nexoraw/third_party/rawpy-demosaic/build-metadata.json"
  require_file "$amaze_json"
  require_file "$amaze_metadata"
  python3 - "$amaze_json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("amaze_supported") is not True:
    raise SystemExit("AMaZE no aparece como soportado en check-amaze.json")
PY
fi

echo "OK: paquete Linux validado: $DEB_PATH"
