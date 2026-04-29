#!/usr/bin/env bash
set -euo pipefail

REQUIRE_AMAZE="${PROBRAW_REQUIRE_AMAZE:-1}"

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

dpkg-query -W -f='${Package} ${Status} ${Version}\n' probraw | grep -q 'install ok installed' \
  || fail "probraw no esta instalado correctamente"
if dpkg-query -W -f='${Status}\n' iccraw 2>/dev/null | grep -q 'install ok installed'; then
  fail "iccraw sigue instalado"
fi

command -v probraw >/dev/null 2>&1 || fail "probraw no esta en PATH"
command -v probraw-ui >/dev/null 2>&1 || fail "probraw-ui no esta en PATH"
command -v colormgr >/dev/null 2>&1 || fail "colormgr/colord no esta instalado para detectar perfiles ICC de monitor"
if command -v iccraw >/dev/null 2>&1 || command -v iccraw-ui >/dev/null 2>&1; then
  fail "hay comandos iccraw heredados en PATH"
fi
[[ ! -e /opt/probraw/venv/bin/iccraw ]] || fail "queda /opt/probraw/venv/bin/iccraw"
[[ ! -e /opt/probraw/venv/bin/iccraw-ui ]] || fail "queda /opt/probraw/venv/bin/iccraw-ui"

desktop=/usr/share/applications/probraw.desktop
[[ -f "$desktop" ]] || fail "falta $desktop"
grep -Fxq "Name=ProbRAW" "$desktop" || fail "desktop Name no es ProbRAW"
grep -Fxq "Exec=probraw-ui" "$desktop" || fail "desktop Exec no usa probraw-ui"
grep -Fxq "Icon=probraw" "$desktop" || fail "desktop Icon no usa probraw"
grep -Eq '^Categories=.*Graphics.*Photography.*;$' "$desktop" || fail "desktop Categories no incluye Graphics y Photography"

for size in 16 32 48 64 128 256 512; do
  [[ -f "/usr/share/icons/hicolor/${size}x${size}/apps/probraw.png" ]] \
    || fail "falta icono hicolor ${size}x${size}"
done
[[ -f /usr/share/icons/hicolor/scalable/apps/probraw.svg ]] || fail "falta icono SVG"
[[ -f /usr/share/pixmaps/probraw.png ]] || fail "falta fallback /usr/share/pixmaps/probraw.png"

probraw --version >/dev/null
probraw check-tools --strict >/dev/null
probraw check-c2pa >/dev/null
probraw check-display-profile >/dev/null
if is_true "$REQUIRE_AMAZE"; then
  probraw check-amaze >/dev/null
fi

QT_QPA_PLATFORM=offscreen /opt/probraw/venv/bin/python - <<'PY'
from PySide6 import QtWidgets
from probraw.gui import _app_icon, _app_icon_path

app = QtWidgets.QApplication([])
icon = _app_icon()
if icon.isNull():
    raise SystemExit(f"icono Qt no cargado: {_app_icon_path()}")
print(_app_icon_path())
PY

echo "OK: instalacion Linux validada"
