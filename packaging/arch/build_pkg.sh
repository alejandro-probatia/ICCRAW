#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="${PROBRAW_ARCH_BUILD_DIR:-$ROOT/build/arch}"
SYNCDEPS="${PROBRAW_ARCH_SYNCDEPS:-0}"

is_true() {
  case "${1,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

mkdir -p "$BUILD_DIR"
cp "$ROOT/packaging/arch/PKGBUILD" "$BUILD_DIR/PKGBUILD"
cp "$ROOT/packaging/arch/probraw.install" "$BUILD_DIR/probraw.install"

args=(--force)
if is_true "$SYNCDEPS"; then
  args+=(--syncdeps --needed)
fi
if [[ -n "${PROBRAW_MAKEPKG_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  extra_args=(${PROBRAW_MAKEPKG_ARGS})
  args+=("${extra_args[@]}")
fi

export PROBRAW_SOURCE_DIR="$ROOT"
export PROBRAW_ARCH_NATIVE="${PROBRAW_ARCH_NATIVE:-1}"
export PROBRAW_BUILD_AMAZE="${PROBRAW_BUILD_AMAZE:-1}"

(
  cd "$BUILD_DIR"
  makepkg "${args[@]}"
)

echo "Paquetes generados en $BUILD_DIR"
