#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '==> %s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

bool_enabled() {
  case "${1:-0}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

resolve_bootstrap_python() {
  if command -v python3.12 >/dev/null 2>&1; then
    command -v python3.12
    return
  fi
  if command -v python3.11 >/dev/null 2>&1; then
    command -v python3.11
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  fail "python3.12 or python3.11 is required. Install it with Homebrew first."
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$script_dir/../.." && pwd)"
cd "$root"

if [[ "$(uname -s)" != "Darwin" ]]; then
  fail "macOS builds must run on macOS. Use this script from a Mac build host."
fi

python_bin="${PROBRAW_MACOS_PYTHON:-$root/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  bootstrap_python="$(resolve_bootstrap_python)"
  log "Create virtual environment"
  "$bootstrap_python" -m venv "$root/.venv"
  python_bin="$root/.venv/bin/python"
fi

python_minor="$("$python_bin" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
case "$python_minor" in
  3.11|3.12) ;;
  *)
    if ! bool_enabled "${PROBRAW_MACOS_ALLOW_UNTESTED_PYTHON:-0}"; then
      fail "macOS packaging is validated with Python 3.11/3.12; got $python_minor. Set PROBRAW_MACOS_PYTHON to python3.12 or use PROBRAW_MACOS_ALLOW_UNTESTED_PYTHON=1."
    fi
    log "Using untested Python $python_minor"
    ;;
esac

output_root="${PROBRAW_MACOS_OUTPUT_ROOT:-$root/dist/macos}"
build_root="${PROBRAW_MACOS_BUILD_ROOT:-$root/build/macos}"
pyinstaller_work="$build_root/pyinstaller"
spec_path="$root/packaging/macos/probraw.spec"
strict_tools="${PROBRAW_MACOS_STRICT_TOOLS:-0}"
skip_tests="${PROBRAW_MACOS_SKIP_TESTS:-0}"
skip_tool_check="${PROBRAW_MACOS_SKIP_TOOL_CHECK:-0}"
skip_c2pa_check="${PROBRAW_MACOS_SKIP_C2PA_CHECK:-0}"
create_zip="${PROBRAW_MACOS_CREATE_ZIP:-1}"
install_extras="${PROBRAW_MACOS_EXTRAS:-.[dev,macos]}"
codesign_identity="${PROBRAW_MACOS_CODESIGN_IDENTITY:-}"
bundle_identifier="${PROBRAW_MACOS_BUNDLE_IDENTIFIER:-org.aeicf.probraw}"

log "Install build dependencies"
"$python_bin" -m pip install --upgrade pip
"$python_bin" -m pip install -e "$install_extras"

if [[ -n "${PROBRAW_RAWPY_DEMOSAIC_WHEEL:-}" || -n "${PROBRAW_RAWPY_DEMOSAIC_SOURCE:-}" ]] || bool_enabled "${PROBRAW_MACOS_AMAZE:-0}" || bool_enabled "${PROBRAW_REQUIRE_AMAZE:-0}"; then
  amaze_args=("scripts/install_amaze_backend.py")
  if [[ -n "${PROBRAW_RAWPY_DEMOSAIC_WHEEL:-}" ]]; then
    [[ -f "$PROBRAW_RAWPY_DEMOSAIC_WHEEL" ]] || fail "Missing rawpy-demosaic wheel: $PROBRAW_RAWPY_DEMOSAIC_WHEEL"
    amaze_args+=("--wheel" "$PROBRAW_RAWPY_DEMOSAIC_WHEEL")
  elif [[ -n "${PROBRAW_RAWPY_DEMOSAIC_SOURCE:-}" ]]; then
    amaze_args+=("--source" "$PROBRAW_RAWPY_DEMOSAIC_SOURCE")
  else
    amaze_args+=("--pypi")
  fi
  log "Install AMaZE backend"
  "$python_bin" "${amaze_args[@]}"
fi

if bool_enabled "${PROBRAW_REQUIRE_AMAZE:-0}"; then
  log "Verify AMaZE backend"
  "$python_bin" scripts/check_amaze_support.py >/dev/null
fi

if ! bool_enabled "$skip_tests"; then
  log "Run tests"
  "$python_bin" -m pytest
fi

if ! bool_enabled "$skip_tool_check"; then
  tool_args=("-m" "probraw" "check-tools")
  if bool_enabled "$strict_tools"; then
    tool_args+=("--strict")
  fi
  log "Check external tools"
  "$python_bin" "${tool_args[@]}"
fi

version="$(PROBRAW_LANG=C "$python_bin" -c 'from probraw.version import __version__; print(__version__)')"
[[ -n "$version" ]] || fail "Could not read ProbRAW version"

mkdir -p "$output_root" "$build_root"

icon_png="$root/src/probraw/resources/icons/probraw-icon.png"
icon_icns="$build_root/probraw-icon.icns"
if [[ -f "$icon_png" && ! -f "$icon_icns" ]]; then
  if command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
    log "Build macOS icon"
    iconset="$build_root/probraw.iconset"
    rm -rf "$iconset"
    mkdir -p "$iconset"
    for size in 16 32 128 256 512; do
      sips -z "$size" "$size" "$icon_png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
      double=$((size * 2))
      sips -z "$double" "$double" "$icon_png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
    done
    iconutil -c icns "$iconset" -o "$icon_icns"
    rm -rf "$iconset"
  else
    log "sips/iconutil not found; PyInstaller will use its default app icon"
  fi
fi

log "Build ProbRAW.app and CLI with PyInstaller"
PROBRAW_MACOS_VERSION="$version" \
PROBRAW_MACOS_BUNDLE_IDENTIFIER="$bundle_identifier" \
PROBRAW_MACOS_PYINSTALLER_CODESIGN_IDENTITY="${PROBRAW_MACOS_PYINSTALLER_CODESIGN_IDENTITY:-}" \
"$python_bin" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$output_root" \
  --workpath "$pyinstaller_work" \
  "$spec_path"

app_path="$output_root/ProbRAW.app"
cli_path="$output_root/probraw/probraw"
[[ -d "$app_path" ]] || fail "Missing app bundle: $app_path"
[[ -x "$cli_path" ]] || fail "Missing packaged CLI: $cli_path"

log "Smoke packaged CLI"
"$cli_path" --version
"$cli_path" --help >/dev/null
if ! bool_enabled "$skip_tool_check" && bool_enabled "$strict_tools"; then
  "$cli_path" check-tools --strict
fi
if ! bool_enabled "$skip_c2pa_check"; then
  "$cli_path" check-c2pa
fi
if bool_enabled "${PROBRAW_REQUIRE_AMAZE:-0}"; then
  "$cli_path" check-amaze
fi

if [[ -n "$codesign_identity" ]]; then
  log "Codesign app bundle"
  codesign_args=(--force --deep --options runtime --sign "$codesign_identity")
  if [[ -n "${PROBRAW_MACOS_ENTITLEMENTS:-}" ]]; then
    codesign_args+=(--entitlements "$PROBRAW_MACOS_ENTITLEMENTS")
  fi
  codesign "${codesign_args[@]}" "$app_path"
  codesign --verify --deep --strict "$app_path"
fi

if bool_enabled "$create_zip"; then
  arch="$(uname -m)"
  zip_path="$output_root/ProbRAW-${version}-macos-${arch}.zip"
  log "Create distributable zip"
  rm -f "$zip_path" "$zip_path.sha256"
  (
    cd "$output_root"
    ditto -c -k --sequesterRsrc --keepParent "ProbRAW.app" "$zip_path"
  )
  shasum -a 256 "$zip_path" > "$zip_path.sha256"
fi

log "macOS build ready: $app_path"
