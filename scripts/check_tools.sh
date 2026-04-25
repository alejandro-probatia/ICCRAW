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

check_python_module() {
  local module="$1"
  local py="python3"
  if [[ -x ".venv/bin/python" ]]; then
    py=".venv/bin/python"
  fi
  if ! "$py" -c "import ${module}" >/dev/null 2>&1; then
    echo "[MISSING] python module ${module}"
    return 1
  fi
  local version
  version="$("$py" -c "import ${module}; print(getattr(${module}, '__version__', 'version desconocida'))")"
  echo "[OK] python module ${module} -> ${version}"
  return 0
}

missing=0

check_python_module "rawpy" || missing=1
if [[ "$missing" -eq 0 ]]; then
  py="python3"
  if [[ -x ".venv/bin/python" ]]; then
    py=".venv/bin/python"
  fi
  if "$py" scripts/check_amaze_support.py >/tmp/nexoraw_amaze_check.json 2>/dev/null; then
    echo "[OK] LibRaw GPL3 demosaic pack -> AMaZE disponible"
  else
    echo "[WARN] LibRaw GPL3 demosaic pack no disponible; AMaZE requiere rawpy-demosaic o LibRaw compilado con GPL3"
  fi
fi
check_cmd "colprof" "colprof -? " || missing=1
if command -v xicclu >/dev/null 2>&1; then
  check_cmd "xicclu" "xicclu" || missing=1
else
  check_cmd "icclu" "icclu" || missing=1
fi
check_cmd "tificc" "tificc -v" || missing=1
check_cmd "exiftool" "exiftool -ver" || missing=1

if [[ "$missing" -ne 0 ]]; then
  echo
  echo "Faltan dependencias del sistema. Instala (Debian/Ubuntu):"
  echo "  sudo apt-get install argyll liblcms2-utils exiftool"
  echo "Y dependencias Python del proyecto:"
  echo "  pip install -e ."
  exit 2
fi

echo
echo "Herramientas externas listas para pruebas."
