from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any
import warnings

import numpy as np

warnings.filterwarnings(
    "ignore",
    message='.*"Matplotlib" related API features are not available.*',
)

try:
    from colour.utilities import ColourUsageWarning

    warnings.filterwarnings("ignore", category=ColourUsageWarning)
except Exception:
    pass

from .core.models import Recipe
from .core.recipe import save_recipe
from .gui_config import *  # noqa: F403
from .gui_config import (
    APP_NAME,
    ORG_NAME,
    PREVIEW_INTERACTIVE_BYPASS_DISPLAY_ICC_ENV,
    _app_icon_path,
    _env_flag,
)
from .raw.preview import apply_render_adjustments
from .ui.widgets import (
    CollapsibleToolPanel,
    Gamut3DWidget,
    ImagePanel,
    PersistentSideTabWidget,
    RGBHistogramWidget,
    ToneCurveEditor,
)
from .ui.window import (
    BatchWorkflowMixin,
    BrowserMetadataMixin,
    ControlPanelsMixin,
    DisplayControlsMixin,
    LayoutMixin,
    PreviewWorkflowMixin,
    ProfileWorkflowMixin,
    SessionWorkflowMixin,
    SettingsMixin,
    TaskStatusMixin,
)
from .ui.window._imports import (
    ReferenceCatalog,
    apply_adjustments,
    auto_generate_profile_from_charts,
    build_gamut_diagnostics,
    build_gamut_pair_diagnostics,
    detect_system_display_profile,
    develop_image_array,
    extract_embedded_preview,
    load_image_for_preview,
    read_image,
    write_raw_sidecar,
    write_signed_profiled_tiff,
)
from .ui.window.core import (
    TaskThread,
    app_icon as _app_icon,
    make_app_settings as _make_app_settings,
)
from .version import __version__

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:  # pragma: no cover - entorno sin GUI
    QtCore = None
    QtGui = None
    QtWidgets = None


if QtWidgets is not None:
    class ProbRawMainWindow(
        LayoutMixin,
        ControlPanelsMixin,
        SettingsMixin,
        DisplayControlsMixin,
        SessionWorkflowMixin,
        BrowserMetadataMixin,
        PreviewWorkflowMixin,
        ProfileWorkflowMixin,
        BatchWorkflowMixin,
        TaskStatusMixin,
        QtWidgets.QMainWindow,
    ):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(f"{APP_NAME} - " + self.tr("Ajuste paramétrico RAW"))
            icon = _app_icon()
            if not icon.isNull():
                self.setWindowIcon(icon)
            self.resize(1800, 1020)
            self._settings = _make_app_settings()

            self._threads: list[TaskThread] = []
            self._thumb_cache: dict[str, QtGui.QIcon] = {}
            self._image_thumb_cache: dict[str, QtGui.QIcon] = {}
            self._file_items_by_key: dict[str, QtWidgets.QListWidgetItem] = {}
            self._thumbnail_generation = 0
            self._metadata_generation = 0
            self._thumbnail_disk_writes_since_prune = 0
            self._pending_thumbnail_paths: list[Path] = []
            self._thumbnail_scan_index = 0
            self._thumbnail_task_active = False
            self._metadata_task_active = False
            self._metadata_pending_request: tuple[Path, bool] | None = None
            self._queued_metadata_include_c2pa = True
            self._preview_load_task_active = False
            self._preview_load_inflight_key: str | None = None
            self._preview_load_pending_request: tuple[Path, Recipe, bool, int, str] | None = None
            self._loaded_preview_base_signature: str | None = None
            self._loaded_preview_fast_raw: bool | None = None
            self._loaded_preview_source_max_side: int = 0
            self._preview_cache: dict[str, np.ndarray] = {}
            self._preview_cache_order: list[str] = []
            self._profile_preview_cache: dict[str, np.ndarray] = {}
            self._profile_preview_cache_order: list[str] = []
            self._profile_preview_task_active = False
            self._profile_preview_inflight_key: str | None = None
            self._profile_preview_pending_request: tuple[str, Path, np.ndarray, tuple[int, int]] | None = None
            self._profile_preview_expected_key: str | None = None
            self._profile_preview_error_key: str | None = None
            self._interactive_preview_task_active = False
            self._interactive_preview_inflight_key: str | None = None
            self._interactive_preview_pending_request: tuple[
                str,
                str | None,
                np.ndarray,
                dict[str, float],
                dict[str, Any],
                bool,
                bool,
                int,
                bool,
                bool,
            ] | None = None
            self._interactive_preview_expected_key: str | None = None
            self._interactive_preview_last_ms: float | None = None
            self._interactive_preview_request_seq = 0
            self._display_color_error_key: str | None = None
            self._manual_chart_marking = False
            self._manual_chart_points: list[tuple[float, float]] = []
            self._manual_chart_points_source: Path | None = None
            self._manual_chart_marking_after_reload = False
            self._neutral_picker_active = False
            self._current_dir = self._startup_directory_from_settings()
            self._selected_file: Path | None = None
            self._storage_roots: list[Path] = []
            self._task_counter = 0
            self._active_tasks = 0
            self._active_session_root: Path | None = None
            self._active_session_payload: dict[str, Any] | None = None
            self._develop_queue: list[dict[str, str]] = []
            self._icc_profiles: list[dict[str, Any]] = []
            self._active_icc_profile_id = ""
            self._development_profiles: list[dict[str, Any]] = []
            self._active_development_profile_id = ""
            self._development_settings_clipboard: dict[str, Any] | None = None
            self._selected_chart_files: list[Path] = []
            self._manual_chart_detections: dict[str, dict[str, Any]] = {}
            self._update_check_last: dict[str, Any] | None = None

            self._original_linear: np.ndarray | None = None
            self._adjusted_linear: np.ndarray | None = None
            self._preview_srgb: np.ndarray | None = None
            self._last_loaded_preview_key: str | None = None
            self._tone_curve_histogram_key: str | None = None
            self._detail_adjusted_linear: np.ndarray | None = None
            self._detail_adjustment_cache_key: str | None = None
            self._original_srgb_cache: np.ndarray | None = None
            self._original_srgb_cache_key: str | None = None
            self._original_display_u8_cache: np.ndarray | None = None
            self._original_display_u8_cache_key: str | None = None
            self._original_compare_panel_key: str | None = None
            self._interactive_bypass_display_icc = _env_flag(
                PREVIEW_INTERACTIVE_BYPASS_DISPLAY_ICC_ENV,
                default=True,
            )
            self._viewer_zoom = 1.0
            self._viewer_rotation = 0
            self._selection_load_timer = QtCore.QTimer(self)
            self._selection_load_timer.setSingleShot(True)
            self._selection_load_timer.timeout.connect(self._load_selected_from_timer)
            self._preview_refresh_timer = QtCore.QTimer(self)
            self._preview_refresh_timer.setSingleShot(True)
            self._preview_refresh_timer.timeout.connect(self._refresh_preview)
            self._thumbnail_timer = QtCore.QTimer(self)
            self._thumbnail_timer.setSingleShot(True)
            self._thumbnail_timer.timeout.connect(self._start_pending_thumbnail_generation)
            self._metadata_timer = QtCore.QTimer(self)
            self._metadata_timer.setSingleShot(True)
            self._metadata_timer.timeout.connect(self._load_metadata_from_timer)
            self._session_root_update_timer = QtCore.QTimer(self)
            self._session_root_update_timer.setSingleShot(True)
            self._session_root_update_timer.timeout.connect(self._on_session_root_edited)

            self._build_ui()
            self._setup_interactive_preview_status_widgets()
            self._build_menu_bar()
            self._init_fs_model()
            self._refresh_storage_roots()
            self._apply_recipe_to_controls(Recipe())
            layout_restored = self._restore_window_settings()
            if not layout_restored:
                self._reset_layout_splitters()
            self._initialize_session_tab_defaults()
            if not self._restore_startup_context():
                self._set_current_directory(self._current_dir)
            self._refresh_queue_table()
            self.statusBar().showMessage(self.tr("Listo"))

    ICCRawMainWindow = ProbRawMainWindow

def main(argv: list[str] | None = None) -> int:
    if QtWidgets is None:
        print(
            "ERROR: Dependencia de GUI no disponible. Instala PySide6 con: pip install -e .[gui]",
            file=sys.stderr,
        )
        return 2

    app = QtWidgets.QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setDesktopFileName("probraw")
    icon = _app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    # Cargar traductor antes de crear la ventana, para que todos los widgets
    # reciban las cadenas traducidas desde el primer paint.
    from .i18n import AUTO_LANG, install_translator, resolve_language
    _lang_settings = _make_app_settings()
    # Default "auto": instalaciones nuevas siguen al idioma del SO. No migramos
    # usuarios existentes con "es" guardado: respetan la elección previa.
    _lang_pref = str(_lang_settings.value("app/language", AUTO_LANG) or AUTO_LANG).strip()
    install_translator(app, resolve_language(_lang_pref))

    win = ProbRawMainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
