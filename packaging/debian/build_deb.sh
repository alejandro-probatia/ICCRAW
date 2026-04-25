#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
DEB_VERSION="${NEXORAW_DEB_VERSION:-${ICCRAW_DEB_VERSION:-0.1.0~beta4}}"
APP_VERSION="${NEXORAW_APP_VERSION:-${ICCRAW_APP_VERSION:-0.1.0b4}}"
ARCH="${NEXORAW_DEB_ARCH:-${ICCRAW_DEB_ARCH:-$(dpkg --print-architecture)}}"
PKG_NAME="nexoraw"
BUILD_ROOT="$ROOT/build/deb/${PKG_NAME}_${DEB_VERSION}_${ARCH}"
DIST_DIR="$ROOT/dist"
DEB_PATH="$DIST_DIR/${PKG_NAME}_${DEB_VERSION}_${ARCH}.deb"
VENV_DIR="$BUILD_ROOT/opt/nexoraw/venv"
VENV_INSTALL_DIR="/opt/nexoraw/venv"

rm -rf "$BUILD_ROOT"
mkdir -p \
  "$BUILD_ROOT/DEBIAN" \
  "$BUILD_ROOT/opt/nexoraw" \
  "$BUILD_ROOT/usr/bin" \
  "$BUILD_ROOT/usr/share/applications" \
  "$BUILD_ROOT/usr/share/icons/hicolor/scalable/apps" \
  "$BUILD_ROOT/usr/share/doc/nexoraw" \
  "$DIST_DIR"

"$PYTHON" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install "$ROOT[gui]"
SITE_PACKAGES="$("$VENV_DIR/bin/python" - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)"
"$VENV_DIR/bin/python" -m compileall -q "$SITE_PACKAGES/iccraw"

for entry in "$VENV_DIR/bin/"*; do
  [ -f "$entry" ] || continue
  grep -Iq . "$entry" || continue
  first_line="$(head -n 1 "$entry" || true)"
  case "$first_line" in
    "#!$VENV_DIR/bin/python"*)
      sed -i "1s|^#!.*|#!$VENV_INSTALL_DIR/bin/python|" "$entry"
      ;;
  esac
done
sed -i "s|$VENV_DIR|$VENV_INSTALL_DIR|g" "$VENV_DIR/pyvenv.cfg"

cat > "$BUILD_ROOT/usr/bin/nexoraw" <<'SH'
#!/usr/bin/env sh
exec /opt/nexoraw/venv/bin/nexoraw "$@"
SH

cat > "$BUILD_ROOT/usr/bin/nexoraw-ui" <<'SH'
#!/usr/bin/env sh
exec /opt/nexoraw/venv/bin/nexoraw-ui "$@"
SH

cat > "$BUILD_ROOT/usr/bin/iccraw" <<'SH'
#!/usr/bin/env sh
exec /opt/nexoraw/venv/bin/iccraw "$@"
SH

cat > "$BUILD_ROOT/usr/bin/iccraw-ui" <<'SH'
#!/usr/bin/env sh
exec /opt/nexoraw/venv/bin/iccraw-ui "$@"
SH

chmod 0755 \
  "$BUILD_ROOT/usr/bin/nexoraw" \
  "$BUILD_ROOT/usr/bin/nexoraw-ui" \
  "$BUILD_ROOT/usr/bin/iccraw" \
  "$BUILD_ROOT/usr/bin/iccraw-ui"

cat > "$BUILD_ROOT/usr/share/applications/nexoraw.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=NexoRAW
GenericName=RAW color profiling
Comment=Pipeline reproducible RAW -> carta -> perfil ICC de sesion
Exec=nexoraw-ui
Icon=nexoraw
Terminal=false
Categories=Graphics;Photography;Science;
DESKTOP

install -m 0644 "$ROOT/src/iccraw/resources/icons/nexoraw-icon.svg" "$BUILD_ROOT/usr/share/icons/hicolor/scalable/apps/nexoraw.svg"
install -m 0644 "$ROOT/README.md" "$BUILD_ROOT/usr/share/doc/nexoraw/README.md"
install -m 0644 "$ROOT/CHANGELOG.md" "$BUILD_ROOT/usr/share/doc/nexoraw/CHANGELOG.md"
install -m 0644 "$ROOT/LICENSE" "$BUILD_ROOT/usr/share/doc/nexoraw/LICENSE"
install -m 0644 "$ROOT/docs/THIRD_PARTY_LICENSES.md" "$BUILD_ROOT/usr/share/doc/nexoraw/THIRD_PARTY_LICENSES.md"
install -m 0644 "$ROOT/docs/LEGAL_COMPLIANCE.md" "$BUILD_ROOT/usr/share/doc/nexoraw/LEGAL_COMPLIANCE.md"
install -m 0644 "$ROOT/docs/AMAZE_GPL3.md" "$BUILD_ROOT/usr/share/doc/nexoraw/AMAZE_GPL3.md"
install -m 0644 "$ROOT/docs/DEBIAN_PACKAGE.md" "$BUILD_ROOT/usr/share/doc/nexoraw/DEBIAN_PACKAGE.md"
install -m 0755 "$ROOT/scripts/check_amaze_support.py" "$BUILD_ROOT/usr/share/doc/nexoraw/check_amaze_support.py"

INSTALLED_SIZE="$(du -sk "$BUILD_ROOT" | awk '{print $1}')"
cat > "$BUILD_ROOT/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $DEB_VERSION
Section: graphics
Priority: optional
Architecture: $ARCH
Maintainer: Comunidad AEICF <release@nexoraw.local>
Installed-Size: $INSTALLED_SIZE
Depends: python3 (>= 3.11), argyll, liblcms2-utils, exiftool, libgl1, libegl1, libxkbcommon0, libxcb-cursor0, libxcb-xinerama0
Homepage: https://github.com/alejandro-probatia/ICCRAW
Description: NexoRAW beta $APP_VERSION reproducible RAW and ICC session profiling
 NexoRAW is a technical/scientific RAW workflow for controlled development,
 color chart sampling, session development profiles and ICC camera profiles.
 This beta package installs a bundled Python environment under /opt/nexoraw
 and command launchers under /usr/bin.
EOF

cat > "$BUILD_ROOT/DEBIAN/postinst" <<'SH'
#!/usr/bin/env sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
exit 0
SH

chmod 0755 "$BUILD_ROOT/DEBIAN/postinst"

dpkg-deb --build --root-owner-group "$BUILD_ROOT" "$DEB_PATH"
dpkg-deb --info "$DEB_PATH"

echo
echo "Paquete generado: $DEB_PATH"
