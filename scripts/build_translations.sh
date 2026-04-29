#!/usr/bin/env bash
# build_translations.sh — Actualizar y compilar las traducciones de NexoRAW
#
# Uso:
#   ./scripts/build_translations.sh            # actualiza + compila todos los idiomas
#   ./scripts/build_translations.sh extract    # solo extrae cadenas nuevas del código
#   ./scripts/build_translations.sh compile    # solo compila .ts → .qm
#
# Requisitos: entorno virtual activado con PySide6 instalado.
#   source .venv/bin/activate

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCALES_SRC="$REPO_ROOT/locales"
LOCALES_BIN="$REPO_ROOT/src/nexoraw/resources/locales"

# Ficheros Python de los que se extraen cadenas
PY_SOURCES=(
    "$REPO_ROOT/src/nexoraw/gui.py"
    "$REPO_ROOT/src/nexoraw/gui_config.py"
    "$REPO_ROOT/src/nexoraw/ui/widgets.py"
    "$REPO_ROOT/src/nexoraw/ui/window/"*.py
    "$REPO_ROOT/src/nexoraw/cli.py"
    "$REPO_ROOT/src/nexoraw/workflow.py"
    "$REPO_ROOT/src/nexoraw/reporting.py"
)

# Idiomas gestionados (uno por fichero .ts en locales/)
LANGUAGES=(en)

extract() {
    echo "[i18n] Extrayendo cadenas del código fuente..."
    for lang in "${LANGUAGES[@]}"; do
        ts_file="$LOCALES_SRC/${lang}.ts"
        pyside6-lupdate "${PY_SOURCES[@]}" -ts "$ts_file"
        echo "  → $ts_file actualizado"
    done
}

compile() {
    echo "[i18n] Compilando .ts → .qm..."
    mkdir -p "$LOCALES_BIN"
    for lang in "${LANGUAGES[@]}"; do
        ts_file="$LOCALES_SRC/${lang}.ts"
        qm_file="$LOCALES_BIN/${lang}.qm"
        if [ ! -f "$ts_file" ]; then
            echo "  ✗ No existe $ts_file — omitido"
            continue
        fi
        pyside6-lrelease "$ts_file" -qm "$qm_file"
        echo "  → $qm_file generado"
    done
}

case "${1:-all}" in
    extract)  extract ;;
    compile)  compile ;;
    all)      extract; compile ;;
    *)
        echo "Uso: $0 [extract|compile|all]"
        exit 1
        ;;
esac

echo "[i18n] Listo."
