#!/usr/bin/env bash
set -euo pipefail

check_cmd() {
  local name="$1"
  local version_cmd="$2"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "[MISSING] $name"
    return 1
  fi
  local version
  version="$(
    set +e
    eval "$version_cmd" 2>&1 | awk 'NF { print; exit }'
    exit 0
  )"
  echo "[OK] $name -> ${version:-version desconocida}"
  return 0
}

missing=0

check_cmd "dcraw" "dcraw" || missing=1
check_cmd "colprof" "colprof -? " || missing=1
check_cmd "exiftool" "exiftool -ver" || missing=1

if [[ "$missing" -ne 0 ]]; then
  echo
  echo "Faltan dependencias del sistema. Instala (Debian/Ubuntu):"
  echo "  sudo apt-get install dcraw argyll exiftool"
  exit 2
fi

echo
echo "Herramientas externas listas para pruebas."
