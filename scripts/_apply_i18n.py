"""
_apply_i18n.py — Envuelve cadenas visibles de gui.py en self.tr()

Uso:
    python scripts/_apply_i18n.py src/probraw/gui.py [--dry-run]

Principios de seguridad:
- Solo transforma cadenas literales simples (no f-strings, no raw, no bytes)
- No transforma cadenas ya envueltas en .tr(
- No transforma cadenas que son claves internas (paths de settings, IDs técnicos)
- Crea copia de seguridad .bak antes de modificar
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Patrón para una cadena simple (no f-string, no raw, no bytes, no tr() ya)
# Captura el contenido entre comillas simples o dobles (sin saltos de línea en
# el literal).  No hace backtrack dentro de secuencias de escape básicas.
# ---------------------------------------------------------------------------
# Solo excluye el prefijo de f/r/b/u (un carácter) para no capturar f-strings,
# raw strings ni bytes. La comprobación de "ya envuelta" se hace en already_wrapped().
STR_SIMPLE = r"""(?<![frbuFRBU])(?<![frbuFRBU]{2})\"(?:[^\"\\]|\\.)*\"|(?<![frbuFRBU])(?<![frbuFRBU]{2})'(?:[^'\\]|\\.)*'"""

# ---------------------------------------------------------------------------
# Construye regex que detecta si ya hay .tr( antes del argumento
# ---------------------------------------------------------------------------
def already_wrapped(text: str, pos: int) -> bool:
    """True si la cadena que empieza en `pos` ya está dentro de .tr("""
    # Mira los 10 caracteres anteriores
    prefix = text[max(0, pos - 10):pos]
    return ".tr(" in prefix or "self.tr(" in prefix


def wrap(s: str) -> str:
    """Envuelve la cadena en self.tr(…) si no está ya envuelta."""
    return f"self.tr({s})"


# ---------------------------------------------------------------------------
# Transformaciones sencillas: patrón fijo → sustitución
# Cada regla es (patrón regex, función de sustitución o string de reemplazo)
# ---------------------------------------------------------------------------

def make_arg_wrapper(call_prefix: str) -> tuple[re.Pattern, callable]:
    """
    Genera una regla que transforma el PRIMER argumento string de una llamada.
    call_prefix: el texto que precede a la cadena, ej. r'QLabel\('
    """
    pattern = re.compile(
        r'(' + call_prefix + r')(' + STR_SIMPLE + r')',
        re.DOTALL,
    )

    def replacer(m: re.Match) -> str:
        prefix = m.group(1)
        s = m.group(2)
        # Skip si ya tiene .tr( justo antes
        if already_wrapped(m.string, m.start(2)):
            return m.group(0)
        return f"{prefix}{wrap(s)}"

    return pattern, replacer


# ---------------------------------------------------------------------------
# Reglas que envuelven el PRIMER argumento string (el texto visible)
# ---------------------------------------------------------------------------
SINGLE_ARG_RULES: list[tuple[re.Pattern, callable]] = [
    # QLabel("texto")
    make_arg_wrapper(r'QtWidgets\.QLabel\('),
    # QGroupBox("texto")
    make_arg_wrapper(r'QtWidgets\.QGroupBox\('),
    # QCheckBox("texto")
    make_arg_wrapper(r'QtWidgets\.QCheckBox\('),
    # QPushButton("texto")  — solo cuando se construye directamente
    make_arg_wrapper(r'QtWidgets\.QPushButton\('),
    # ImagePanel("texto")
    make_arg_wrapper(r'ImagePanel\('),
    # addMenu("texto")
    make_arg_wrapper(r'\.addMenu\('),
    # showMessage("texto")  — solo literal simple
    make_arg_wrapper(r'\.showMessage\('),
    # setWindowTitle("texto")  — solo literal simple
    make_arg_wrapper(r'\.setWindowTitle\('),
    # setPlaceholderText("texto")
    make_arg_wrapper(r'\.setPlaceholderText\('),
    # QFileDialog.getExistingDirectory(self, "título", ...)
    # QFileDialog.getSaveFileName(self, "título", ...)
    # QFileDialog.getOpenFileName(self, "título", ...)
]


# ---------------------------------------------------------------------------
# Reglas que envuelven el SEGUNDO argumento string (self como primer arg)
# ---------------------------------------------------------------------------
def make_second_arg_wrapper(call_prefix: str) -> tuple[re.Pattern, callable]:
    """El primer arg es `self` o similar, el segundo es el string visible."""
    pattern = re.compile(
        r'(' + call_prefix + r'self,\s*)(' + STR_SIMPLE + r')',
        re.DOTALL,
    )

    def replacer(m: re.Match) -> str:
        prefix = m.group(1)
        s = m.group(2)
        if already_wrapped(m.string, m.start(2)):
            return m.group(0)
        return f"{prefix}{wrap(s)}"

    return pattern, replacer


SECOND_ARG_RULES: list[tuple[re.Pattern, callable]] = [
    # QFileDialog.getExistingDirectory(self, "titulo", ...)
    make_second_arg_wrapper(r'QFileDialog\.getExistingDirectory\('),
    make_second_arg_wrapper(r'QFileDialog\.getSaveFileName\('),
    make_second_arg_wrapper(r'QFileDialog\.getOpenFileName\('),
]


# ---------------------------------------------------------------------------
# Regla especial: _button("texto", callback)
# La función _button(text, callback) tiene el texto como primer arg
# ---------------------------------------------------------------------------
BUTTON_PATTERN = re.compile(
    r'(self\._button\()(' + STR_SIMPLE + r')(,)',
)

def button_replacer(m: re.Match) -> str:
    prefix = m.group(1)
    s = m.group(2)
    comma = m.group(3)
    if already_wrapped(m.string, m.start(2)):
        return m.group(0)
    return f"{prefix}{wrap(s)}{comma}"


# ---------------------------------------------------------------------------
# Regla especial: _action("texto", callback)
# ---------------------------------------------------------------------------
ACTION_PATTERN = re.compile(
    r'(self\._action\()(' + STR_SIMPLE + r')(,)',
)

def action_replacer(m: re.Match) -> str:
    prefix = m.group(1)
    s = m.group(2)
    comma = m.group(3)
    if already_wrapped(m.string, m.start(2)):
        return m.group(0)
    return f"{prefix}{wrap(s)}{comma}"


# ---------------------------------------------------------------------------
# Regla especial: addTab(widget, "texto")  — segundo argumento
# ---------------------------------------------------------------------------
ADD_TAB_PATTERN = re.compile(
    r'(\.addTab\([^,]+,\s*)(' + STR_SIMPLE + r')(\))',
)

def add_tab_replacer(m: re.Match) -> str:
    prefix = m.group(1)
    s = m.group(2)
    closing = m.group(3)
    if already_wrapped(m.string, m.start(2)):
        return m.group(0)
    return f"{prefix}{wrap(s)}{closing}"


# Variante con expanded=... (CollapsibleToolPanel.addItem)
ADD_ITEM_PANEL_PATTERN = re.compile(
    r'(\.addItem\([^,]+,\s*)(' + STR_SIMPLE + r')(,\s*expanded=)',
)

def add_item_panel_replacer(m: re.Match) -> str:
    prefix = m.group(1)
    s = m.group(2)
    suffix = m.group(3)
    if already_wrapped(m.string, m.start(2)):
        return m.group(0)
    return f"{prefix}{wrap(s)}{suffix}"


# ---------------------------------------------------------------------------
# Regla especial: _add_path_row(grid, row, "etiqueta", widget, ...)
# Tercer argumento es el string visible
# ---------------------------------------------------------------------------
ADD_PATH_ROW_PATTERN = re.compile(
    r'(self\._add_path_row\([^,]+,\s*[^,]+,\s*)(' + STR_SIMPLE + r')(,)',
)

def add_path_row_replacer(m: re.Match) -> str:
    prefix = m.group(1)
    s = m.group(2)
    comma = m.group(3)
    if already_wrapped(m.string, m.start(2)):
        return m.group(0)
    return f"{prefix}{wrap(s)}{comma}"


# ---------------------------------------------------------------------------
# Regla especial: QMessageBox.xxx(self, "titulo", "mensaje"...)
# Transforma TÍTULO (tercer arg) y MENSAJE (cuarto arg, si es literal)
# ---------------------------------------------------------------------------
MSGBOX_TITLE_PATTERN = re.compile(
    r'(QMessageBox\.\w+\(\s*self,\s*)(' + STR_SIMPLE + r')(,)',
    re.DOTALL,
)

def msgbox_title_replacer(m: re.Match) -> str:
    prefix = m.group(1)
    s = m.group(2)
    comma = m.group(3)
    if already_wrapped(m.string, m.start(2)):
        return m.group(0)
    return f"{prefix}{wrap(s)}{comma}"


MSGBOX_MSG_PATTERN = re.compile(
    r'(QMessageBox\.\w+\(\s*self,\s*(?:self\.tr\()?' + STR_SIMPLE + r'\)?,\s*)(' + STR_SIMPLE + r')(,|\))',
    re.DOTALL,
)

def msgbox_msg_replacer(m: re.Match) -> str:
    prefix = m.group(1)
    s = m.group(2)
    end = m.group(3)
    if already_wrapped(m.string, m.start(2)):
        return m.group(0)
    return f"{prefix}{wrap(s)}{end}"


# ---------------------------------------------------------------------------
# Regla especial: setHorizontalHeaderLabels / setHeaderLabels
# Envuelve cada string dentro de la lista
# ---------------------------------------------------------------------------
HEADER_LABELS_PATTERN = re.compile(
    r'((?:setHorizontalHeaderLabels|setHeaderLabels)\(\[)([^\]]+)(\]\))',
)

def header_labels_replacer(m: re.Match) -> str:
    prefix = m.group(1)
    items_str = m.group(2)
    closing = m.group(3)

    str_pattern = re.compile(STR_SIMPLE)

    def wrap_str(sm: re.Match) -> str:
        s = sm.group(0)
        if already_wrapped(items_str, sm.start()):
            return s
        return wrap(s)

    new_items = str_pattern.sub(wrap_str, items_str)
    return f"{prefix}{new_items}{closing}"


# ---------------------------------------------------------------------------
# Regla especial: formatter=lambda v: f"LABEL: {expr}"
# → formatter=lambda v: self.tr("LABEL") + f": {expr}"
# ---------------------------------------------------------------------------
FORMATTER_LAMBDA_PATTERN = re.compile(
    r'(formatter=lambda v: )f("([^":{]+):\s*\{([^}]+)\}([^"]*)")',
)

def formatter_lambda_replacer(m: re.Match) -> str:
    prefix = m.group(1)  # "formatter=lambda v: "
    # group(3) = label text, group(4) = expr, group(5) = suffix
    label = m.group(3).strip()
    expr = m.group(4)
    suffix = m.group(5)  # anything after the closing brace
    rest_after_brace = suffix  # e.g. " EV" or ""
    fmt_part = f"{{" + expr + f"}}"
    result = f'{prefix}self.tr("{label}") + f": {fmt_part}{rest_after_brace}"'
    return result


# También manejar comillas simples en formatter
FORMATTER_LAMBDA_SQ_PATTERN = re.compile(
    r"(formatter=lambda v: )f('([^':{]+):\s*\{([^}]+)\}([^']*)')",
)

def formatter_lambda_sq_replacer(m: re.Match) -> str:
    prefix = m.group(1)
    label = m.group(3).strip()
    expr = m.group(4)
    suffix = m.group(5)
    fmt_part = f"{{" + expr + f"}}"
    result = f'{prefix}self.tr("{label}") + f": {fmt_part}{suffix}"'
    return result


# ---------------------------------------------------------------------------
# Regla especial: tooltip multilínea con concatenación de strings
# .setToolTip("linea1 " "linea2") o .setToolTip("...")  — solo una línea
# ---------------------------------------------------------------------------
TOOLTIP_PATTERN = re.compile(
    r'(\.setToolTip\()(' + STR_SIMPLE + r')(\))',
)

def tooltip_replacer(m: re.Match) -> str:
    prefix = m.group(1)
    s = m.group(2)
    closing = m.group(3)
    if already_wrapped(m.string, m.start(2)):
        return m.group(0)
    return f"{prefix}{wrap(s)}{closing}"


# ---------------------------------------------------------------------------
# Regla: "Antes" / "Despues" como QLabel standalone
# ---------------------------------------------------------------------------
BEFORE_AFTER_PATTERN = re.compile(
    r'(= QtWidgets\.QLabel\()("Antes"|"Despues"|"Resultado")(\))',
)

def before_after_replacer(m: re.Match) -> str:
    prefix = m.group(1)
    s = m.group(2)
    closing = m.group(3)
    if already_wrapped(m.string, m.start(2)):
        return m.group(0)
    return f"{prefix}{wrap(s)}{closing}"


# ---------------------------------------------------------------------------
# Aplicar todas las reglas
# ---------------------------------------------------------------------------
ALL_RULES: list[tuple[re.Pattern, callable]] = [
    *SINGLE_ARG_RULES,
    *SECOND_ARG_RULES,
    (BUTTON_PATTERN, button_replacer),
    (ACTION_PATTERN, action_replacer),
    (ADD_TAB_PATTERN, add_tab_replacer),
    (ADD_ITEM_PANEL_PATTERN, add_item_panel_replacer),
    (ADD_PATH_ROW_PATTERN, add_path_row_replacer),
    (MSGBOX_TITLE_PATTERN, msgbox_title_replacer),
    (MSGBOX_MSG_PATTERN, msgbox_msg_replacer),
    (HEADER_LABELS_PATTERN, header_labels_replacer),
    (FORMATTER_LAMBDA_PATTERN, formatter_lambda_replacer),
    (FORMATTER_LAMBDA_SQ_PATTERN, formatter_lambda_sq_replacer),
    (TOOLTIP_PATTERN, tooltip_replacer),
]


def transform(source: str) -> str:
    for pattern, replacer in ALL_RULES:
        source = pattern.sub(replacer, source)
    return source


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    files = [a for a in args if not a.startswith("--")]

    if not files:
        print("Uso: python scripts/_apply_i18n.py src/probraw/gui.py [--dry-run]")
        sys.exit(1)

    for file_path in files:
        path = Path(file_path)
        original = path.read_text(encoding="utf-8")
        transformed = transform(original)

        if dry_run:
            # Mostrar cuántas sustituciones se harían
            orig_lines = original.splitlines()
            new_lines = transformed.splitlines()
            changes = sum(1 for a, b in zip(orig_lines, new_lines) if a != b)
            print(f"{file_path}: {changes} línea(s) modificadas (dry-run)")
            # Mostrar las primeras diferencias
            shown = 0
            for i, (a, b) in enumerate(zip(orig_lines, new_lines), 1):
                if a != b and shown < 20:
                    print(f"  L{i}: {a.strip()!r}")
                    print(f"    → {b.strip()!r}")
                    shown += 1
        else:
            bak = path.with_suffix(path.suffix + ".bak")
            bak.write_text(original, encoding="utf-8")
            path.write_text(transformed, encoding="utf-8")
            orig_lines = original.splitlines()
            new_lines = transformed.splitlines()
            changes = sum(1 for a, b in zip(orig_lines, new_lines) if a != b)
            print(f"{file_path}: {changes} línea(s) modificadas. Backup en {bak}")


if __name__ == "__main__":
    main()
