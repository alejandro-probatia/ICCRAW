#!/usr/bin/env bash
set -euo pipefail

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

if [ "${PROBRAW_BOOTSTRAP:-0}" = "1" ] || ! .venv/bin/python - <<'PY' >/dev/null 2>&1
import PySide6  # noqa: F401
import rawpy  # noqa: F401
import probraw  # noqa: F401
PY
then
  .venv/bin/python -m pip install -q -e ".[gui]"
fi

exec .venv/bin/probraw-ui
