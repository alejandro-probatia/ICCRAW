from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import shlex
import sys
import tempfile
import traceback
from typing import Any
import warnings

import cv2
import numpy as np
import yaml

warnings.filterwarnings(
    "ignore",
    message='.*"Matplotlib" related API features are not available.*',
)

try:
    from colour.utilities import ColourUsageWarning

    warnings.filterwarnings("ignore", category=ColourUsageWarning)
except Exception:
    pass

from .chart.detection import detect_chart_from_corners, draw_detection_overlay
from .chart.sampling import ReferenceCatalog
from .core.models import Recipe, to_json_dict, write_json
from .core.recipe import load_recipe
from .core.utils import RAW_EXTENSIONS, read_image
from .profile.export import write_profiled_tiff
from .raw.pipeline import develop_controlled
from .raw.preview import (
    apply_adjustments,
    apply_profile_preview,
    extract_embedded_preview,
    linear_to_srgb_display,
    load_image_for_preview,
    preview_analysis_text,
)
from .session import create_session, ensure_session_structure, load_session, save_session, session_file_path
from .workflow import auto_generate_profile_from_charts

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:  # pragma: no cover - entorno sin GUI
    QtCore = None
    QtGui = None
    QtWidgets = None


IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}
BROWSABLE_EXTENSIONS = RAW_EXTENSIONS.union(IMAGE_EXTENSIONS)

LAYOUT_VERSION = 2

DEMOSAIC_OPTIONS = [
    "linear",
    "vng",
    "ppg",
    "ahd",
]

WB_MODE_OPTIONS = [
    ("Fijo (multiplicadores manuales)", "fixed"),
    ("Desde metadatos de camara", "camera_metadata"),
]

BLACK_MODE_OPTIONS = [
    ("Metadata", "metadata"),
    ("Fijo", "fixed"),
    ("White level", "white"),
]

TONE_OPTIONS = [
    ("Lineal", "linear"),
    ("sRGB", "srgb"),
    ("Gamma", "gamma"),
]

SPACE_OPTIONS = [
    "scene_linear_camera_rgb",
    "srgb",
    "camera_rgb",
]

SAMPLE_OPTIONS = [
    "trimmed_mean",
    "median",
]

FILTER_MODE_OPTIONS = [
    "off",
    "mild",
    "medium",
    "strong",
]

PROFILE_ALGO_OPTIONS = [
    ("shaper+matrix (-as)", "-as"),
    ("gamma+matrix (-ag)", "-ag"),
    ("matrix only (-am)", "-am"),
    ("Lab cLUT (-al)", "-al"),
    ("XYZ cLUT (-ax)", "-ax"),
]

PROFILE_QUALITY_OPTIONS = [
    ("Low", "l"),
    ("Medium", "m"),
    ("High", "h"),
    ("Ultra", "u"),
]

PROFILE_FORMAT_OPTIONS = [".icc", ".icm"]


if QtWidgets is not None:
    class TaskThread(QtCore.QThread):
        succeeded = QtCore.Signal(object)
        failed = QtCore.Signal(str)

        def __init__(self, task):
            super().__init__()
            self._task = task

        def run(self) -> None:
            try:
                payload = self._task()
                self.succeeded.emit(payload)
            except Exception:
                self.failed.emit(traceback.format_exc())


    class ImagePanel(QtWidgets.QLabel):
        imageClicked = QtCore.Signal(float, float)

        def __init__(self, title: str) -> None:
            super().__init__()
            self._base_pixmap: QtGui.QPixmap | None = None
            self._image_size: tuple[int, int] | None = None
            self._overlay_points: list[tuple[float, float]] = []
            self.setAlignment(QtCore.Qt.AlignCenter)
            self.setMinimumSize(220, 160)
            self.setText(title)
            self.setStyleSheet(
                "QLabel {"
                "border: 1px solid #4b5563;"
                "background-color: #111827;"
                "color: #e5e7eb;"
                "font-size: 13px;"
                "}"
            )

        def set_rgb_float_image(self, image_rgb: np.ndarray) -> None:
            rgb = np.clip(image_rgb, 0.0, 1.0)
            u8 = np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)
            h, w, _ = u8.shape
            self._image_size = (w, h)
            qimg = QtGui.QImage(u8.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()
            self._base_pixmap = QtGui.QPixmap.fromImage(qimg)
            self._refresh_scaled_pixmap()

        def set_overlay_points(self, points: list[tuple[float, float]]) -> None:
            self._overlay_points = list(points)
            self._refresh_scaled_pixmap()

        def mousePressEvent(self, event) -> None:  # noqa: N802
            mapped = self._map_widget_to_image(event.position())
            if mapped is not None and event.button() == QtCore.Qt.LeftButton:
                self.imageClicked.emit(float(mapped[0]), float(mapped[1]))
                return
            super().mousePressEvent(event)

        def resizeEvent(self, event) -> None:  # noqa: N802
            super().resizeEvent(event)
            self._refresh_scaled_pixmap()

        def _refresh_scaled_pixmap(self) -> None:
            if self._base_pixmap is None:
                return
            scaled = self._base_pixmap.scaled(
                self.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            if self._overlay_points and self._image_size is not None:
                scaled = QtGui.QPixmap(scaled)
                painter = QtGui.QPainter(scaled)
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                painter.setPen(QtGui.QPen(QtGui.QColor("#22c55e"), 2))
                painter.setBrush(QtGui.QBrush(QtGui.QColor(34, 197, 94, 96)))
                image_w, image_h = self._image_size
                sx = scaled.width() / max(1, image_w)
                sy = scaled.height() / max(1, image_h)
                qpoints = [QtCore.QPointF(x * sx, y * sy) for x, y in self._overlay_points]
                if len(qpoints) >= 2:
                    painter.drawPolyline(QtGui.QPolygonF(qpoints))
                if len(qpoints) == 4:
                    painter.drawLine(qpoints[-1], qpoints[0])
                for idx, point in enumerate(qpoints, start=1):
                    painter.drawEllipse(point, 6, 6)
                    painter.drawText(point + QtCore.QPointF(8, -8), str(idx))
                painter.end()
            self.setPixmap(scaled)

        def _map_widget_to_image(self, pos: QtCore.QPointF) -> tuple[float, float] | None:
            if self._base_pixmap is None or self._image_size is None or self.pixmap() is None:
                return None
            displayed = self.pixmap()
            offset_x = (self.width() - displayed.width()) / 2.0
            offset_y = (self.height() - displayed.height()) / 2.0
            x = float(pos.x()) - offset_x
            y = float(pos.y()) - offset_y
            if x < 0 or y < 0 or x > displayed.width() or y > displayed.height():
                return None
            image_w, image_h = self._image_size
            return x * image_w / max(1, displayed.width()), y * image_h / max(1, displayed.height())


    class ICCRawMainWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("ICCRAW - Calibración científica de sesión")
            self.resize(1800, 1020)
            self._settings = QtCore.QSettings("ICCRAW", "ICCRAW")

            self._threads: list[TaskThread] = []
            self._thumb_cache: dict[str, QtGui.QIcon] = {}
            self._preview_cache: dict[str, np.ndarray] = {}
            self._preview_cache_order: list[str] = []
            self._manual_chart_marking = False
            self._manual_chart_points: list[tuple[float, float]] = []
            self._current_dir = Path.home()
            self._selected_file: Path | None = None
            self._storage_roots: list[Path] = []
            self._task_counter = 0
            self._active_tasks = 0
            self._active_session_root: Path | None = None
            self._active_session_payload: dict[str, Any] | None = None
            self._develop_queue: list[dict[str, str]] = []
            self._selected_chart_files: list[Path] = []
            self._manual_chart_detections: dict[str, dict[str, Any]] = {}

            self._original_linear: np.ndarray | None = None
            self._adjusted_linear: np.ndarray | None = None
            self._preview_srgb: np.ndarray | None = None

            self._build_ui()
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
            self.statusBar().showMessage("Listo")

        def _build_ui(self) -> None:
            root = QtWidgets.QWidget()
            root_layout = QtWidgets.QVBoxLayout(root)
            root_layout.setContentsMargins(6, 6, 6, 6)
            root_layout.setSpacing(6)

            header = QtWidgets.QHBoxLayout()
            title = QtWidgets.QLabel("ICCRAW")
            title.setStyleSheet("font-size: 22px; font-weight: 700;")
            subtitle = QtWidgets.QLabel("Flujo tecnico reproducible: RAW -> carta -> perfil de revelado + ICC -> TIFF 16-bit")
            subtitle.setStyleSheet("font-size: 12px; color: #4b5563;")
            header.addWidget(title)
            header.addWidget(subtitle)
            header.addStretch(1)
            header.addWidget(self._button("Abrir carpeta...", self._pick_directory))
            header.addWidget(self._button("Recargar", self._reload_current_directory))
            header.addWidget(self._button("Pantalla completa", self._menu_toggle_fullscreen))
            root_layout.addLayout(header)

            self.main_tabs = QtWidgets.QTabWidget()
            session_tab = self._build_tab_session()
            raw_tab = self._build_tab_raw_develop()
            queue_tab = self._build_tab_queue()

            self.main_tabs.addTab(session_tab, "1. Sesión")
            self.main_tabs.addTab(raw_tab, "2. Calibrar / Aplicar")
            self.main_tabs.addTab(queue_tab, "3. Cola de Revelado")

            root_layout.addWidget(self.main_tabs, 1)

            self.setCentralWidget(root)

        def _build_menu_bar(self) -> None:
            mb = self.menuBar()

            menu_file = mb.addMenu("Archivo")
            menu_file.addAction(self._action("Crear sesión...", self._on_create_session))
            menu_file.addAction(self._action("Abrir sesión...", self._on_open_session))
            menu_file.addAction(self._action("Guardar sesión", self._on_save_session, "Ctrl+Shift+S"))
            menu_file.addSeparator()
            menu_file.addAction(self._action("Abrir carpeta...", self._pick_directory, "Ctrl+O"))
            menu_file.addAction(self._action("Cargar seleccion", self._on_load_selected, "Ctrl+L"))
            menu_file.addAction(self._action("Guardar preview PNG", self._on_save_preview, "Ctrl+S"))
            menu_file.addAction(self._action("Aplicar sesión a selección", self._on_batch_develop_selected, "Ctrl+R"))
            menu_file.addSeparator()
            menu_file.addAction(self._action("Salir", self.close, "Ctrl+Q"))

            menu_cfg = mb.addMenu("Configuracion")
            menu_cfg.addAction(self._action("Cargar receta...", self._menu_load_recipe))
            menu_cfg.addAction(self._action("Guardar receta...", self._menu_save_recipe))
            menu_cfg.addAction(self._action("Receta por defecto", self._menu_reset_recipe))
            menu_cfg.addSeparator()
            menu_cfg.addAction(self._action("Ir a pestaña Sesión", lambda: self.main_tabs.setCurrentIndex(0)))
            menu_cfg.addAction(self._action("Ir a pestaña Revelado", lambda: self.main_tabs.setCurrentIndex(1)))
            menu_cfg.addAction(self._action("Ir a pestaña Cola", lambda: self.main_tabs.setCurrentIndex(2)))

            menu_profile = mb.addMenu("Perfil ICC")
            menu_profile.addAction(self._action("Cargar perfil activo...", self._menu_load_profile))
            menu_profile.addAction(self._action("Usar perfil generado", self._use_generated_profile_as_active))

            menu_view = mb.addMenu("Vista")
            a_compare = self._action("Comparar original/resultado", self._menu_toggle_compare)
            a_compare.setCheckable(True)
            a_compare.setChecked(False)
            self._action_compare = a_compare
            menu_view.addAction(a_compare)
            menu_view.addAction(self._action("Ir a Nitidez", lambda: self._go_to_nitidez_tab()))
            menu_view.addAction(self._action("Pantalla completa", self._menu_toggle_fullscreen, "F11"))
            menu_view.addAction(self._action("Restablecer distribución", self._reset_layout_splitters))

            menu_help = mb.addMenu("Ayuda")
            menu_help.addAction(self._action("Acerca de ICCRAW", self._menu_about))

        def _go_to_nitidez_tab(self) -> None:
            self.main_tabs.setCurrentIndex(1)
            self.config_tabs.setCurrentIndex(1)

        def _menu_toggle_fullscreen(self, _checked: bool = False) -> None:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()

        def _reset_layout_splitters(self) -> None:
            if hasattr(self, "raw_splitter"):
                w = max(1200, int(self.width() * 0.98))
                left = max(220, int(w * 0.15))
                right = max(320, int(w * 0.25))
                center = max(520, w - left - right)
                self.raw_splitter.setSizes([left, center, right])

            if hasattr(self, "compare_splitter"):
                cw = max(600, int(self.width() * 0.55))
                self.compare_splitter.setSizes([cw // 2, cw // 2])

            if hasattr(self, "viewer_splitter"):
                h = max(700, int(self.height() * 0.85))
                self.viewer_splitter.setSizes([
                    int(h * 0.55),
                    int(h * 0.30),
                    int(h * 0.15),
                ])

        def _restore_window_settings(self) -> bool:
            restored_layout = False
            geometry = self._settings_to_bytearray(self._settings.value("window/geometry"))
            if geometry is not None:
                self.restoreGeometry(geometry)

            state = self._settings_to_bytearray(self._settings.value("window/state"))
            if state is not None:
                self.restoreState(state)

            layout_version = self._settings.value("layout/version")
            try:
                layout_version = int(layout_version) if layout_version is not None else 0
            except (TypeError, ValueError):
                layout_version = 0
            if layout_version != LAYOUT_VERSION:
                return False

            raw_splitter_state = self._settings_to_bytearray(self._settings.value("layout/raw_splitter"))
            if raw_splitter_state is not None and hasattr(self, "raw_splitter"):
                self.raw_splitter.restoreState(raw_splitter_state)
                restored_layout = True

            viewer_splitter_state = self._settings_to_bytearray(self._settings.value("layout/viewer_splitter"))
            if viewer_splitter_state is not None and hasattr(self, "viewer_splitter"):
                self.viewer_splitter.restoreState(viewer_splitter_state)
                restored_layout = True

            compare_splitter_state = self._settings_to_bytearray(self._settings.value("layout/compare_splitter"))
            if compare_splitter_state is not None and hasattr(self, "compare_splitter"):
                self.compare_splitter.restoreState(compare_splitter_state)
                restored_layout = True
            return restored_layout

        def _save_window_settings(self) -> None:
            self._settings.setValue("window/geometry", self.saveGeometry())
            self._settings.setValue("window/state", self.saveState())
            self._settings.setValue("layout/version", LAYOUT_VERSION)
            if hasattr(self, "raw_splitter"):
                self._settings.setValue("layout/raw_splitter", self.raw_splitter.saveState())
            if hasattr(self, "viewer_splitter"):
                self._settings.setValue("layout/viewer_splitter", self.viewer_splitter.saveState())
            if hasattr(self, "compare_splitter"):
                self._settings.setValue("layout/compare_splitter", self.compare_splitter.saveState())

        def _settings_to_bytearray(self, value):
            if value is None:
                return None
            if isinstance(value, QtCore.QByteArray):
                return value
            if isinstance(value, (bytes, bytearray)):
                return QtCore.QByteArray(bytes(value))
            return None

        def _restore_startup_context(self) -> bool:
            last_session = str(self._settings.value("session/last_root") or "").strip()
            if last_session:
                root = Path(last_session).expanduser()
                try:
                    if session_file_path(root).exists():
                        self._activate_session(root, load_session(root))
                        return True
                except Exception as exc:
                    self._set_status(f"No se pudo restaurar la última sesión: {exc}")

            last_dir = str(self._settings.value("browser/last_dir") or "").strip()
            if last_dir:
                folder = Path(last_dir).expanduser()
                if folder.exists() and folder.is_dir():
                    self._set_current_directory(folder)
                    return True
            return False

        def closeEvent(self, event) -> None:  # noqa: N802
            self._save_window_settings()
            super().closeEvent(event)

        def _build_tab_session(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            outer = QtWidgets.QVBoxLayout(tab)
            outer.setContentsMargins(8, 8, 8, 8)
            outer.setSpacing(8)

            session_box = QtWidgets.QGroupBox("Gestión de sesión")
            grid = QtWidgets.QGridLayout(session_box)

            self.session_root_path = QtWidgets.QLineEdit(str(self._current_dir / "iccraw_session"))
            self._add_path_row(grid, 0, "Directorio raíz de sesión", self.session_root_path, file_mode=False, save_mode=False, dir_mode=True)
            self.session_root_path.editingFinished.connect(self._on_session_root_edited)

            grid.addWidget(QtWidgets.QLabel("Nombre de sesión"), 1, 0)
            self.session_name_edit = QtWidgets.QLineEdit("")
            grid.addWidget(self.session_name_edit, 1, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Condiciones de iluminación"), 2, 0)
            self.session_illumination_edit = QtWidgets.QLineEdit("")
            grid.addWidget(self.session_illumination_edit, 2, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Notas de toma"), 3, 0)
            self.session_capture_edit = QtWidgets.QLineEdit("")
            grid.addWidget(self.session_capture_edit, 3, 1, 1, 2)

            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("Usar carpeta actual", self._use_current_dir_as_session_root))
            row.addWidget(self._button("Crear sesión", self._on_create_session))
            row.addWidget(self._button("Abrir sesión", self._on_open_session))
            row.addWidget(self._button("Guardar sesión", self._on_save_session))
            grid.addLayout(row, 4, 0, 1, 3)

            self.session_active_label = QtWidgets.QLabel("Sin sesión activa")
            self.session_active_label.setWordWrap(True)
            self.session_active_label.setStyleSheet("font-size: 12px; color: #1f2937;")
            grid.addWidget(self.session_active_label, 5, 0, 1, 3)

            outer.addWidget(session_box)

            dirs_box = QtWidgets.QGroupBox("Estructura persistente de la sesión")
            dirs_grid = QtWidgets.QGridLayout(dirs_box)

            self.session_dir_charts = QtWidgets.QLineEdit("")
            self.session_dir_charts.setReadOnly(True)
            self.session_dir_raw = QtWidgets.QLineEdit("")
            self.session_dir_raw.setReadOnly(True)
            self.session_dir_profiles = QtWidgets.QLineEdit("")
            self.session_dir_profiles.setReadOnly(True)
            self.session_dir_exports = QtWidgets.QLineEdit("")
            self.session_dir_exports.setReadOnly(True)
            self.session_dir_config = QtWidgets.QLineEdit("")
            self.session_dir_config.setReadOnly(True)
            self.session_dir_work = QtWidgets.QLineEdit("")
            self.session_dir_work.setReadOnly(True)

            dirs_grid.addWidget(QtWidgets.QLabel("Cartas de color"), 0, 0)
            dirs_grid.addWidget(self.session_dir_charts, 0, 1)
            dirs_grid.addWidget(QtWidgets.QLabel("RAW de sesión"), 1, 0)
            dirs_grid.addWidget(self.session_dir_raw, 1, 1)
            dirs_grid.addWidget(QtWidgets.QLabel("Perfiles ICC"), 2, 0)
            dirs_grid.addWidget(self.session_dir_profiles, 2, 1)
            dirs_grid.addWidget(QtWidgets.QLabel("Exportaciones"), 3, 0)
            dirs_grid.addWidget(self.session_dir_exports, 3, 1)
            dirs_grid.addWidget(QtWidgets.QLabel("Configuración"), 4, 0)
            dirs_grid.addWidget(self.session_dir_config, 4, 1)
            dirs_grid.addWidget(QtWidgets.QLabel("Artefactos/work"), 5, 0)
            dirs_grid.addWidget(self.session_dir_work, 5, 1)

            outer.addWidget(dirs_box)
            outer.addStretch(1)
            return tab

        def _build_tab_raw_develop(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(tab)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            self.raw_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            self.raw_splitter.setChildrenCollapsible(True)
            self.raw_splitter.setHandleWidth(9)
            self.raw_splitter.addWidget(self._build_left_pane())
            self.raw_splitter.addWidget(self._build_center_pane())
            self.raw_splitter.addWidget(self._build_right_pane())
            self.raw_splitter.setSizes([260, 1180, 460])
            self.raw_splitter.setStretchFactor(0, 0)
            self.raw_splitter.setStretchFactor(1, 1)
            self.raw_splitter.setStretchFactor(2, 0)
            layout.addWidget(self.raw_splitter, 1)
            return tab

        def _build_tab_profile_generation(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            outer = QtWidgets.QVBoxLayout(tab)
            outer.setContentsMargins(8, 8, 8, 8)
            outer.setSpacing(8)

            box = QtWidgets.QGroupBox("Generación científica desde carta: revelado + ICC")
            grid = QtWidgets.QGridLayout(box)

            self.profile_charts_dir = QtWidgets.QLineEdit(str(self._current_dir))
            self._add_path_row(grid, 0, "Carpeta de cartas", self.profile_charts_dir, file_mode=False, save_mode=False, dir_mode=True)

            self.profile_chart_selection_label = QtWidgets.QLabel("Cartas: todas las compatibles de la carpeta indicada")
            self.profile_chart_selection_label.setWordWrap(True)
            self.profile_chart_selection_label.setStyleSheet("font-size: 12px; color: #374151;")
            grid.addWidget(self.profile_chart_selection_label, 1, 0, 1, 3)

            self.path_reference = QtWidgets.QLineEdit("testdata/references/colorchecker24_colorchecker2005_d50.json")
            self._add_path_row(grid, 2, "Referencia carta JSON", self.path_reference, file_mode=True, save_mode=False, dir_mode=False)

            self.profile_out_path_edit = QtWidgets.QLineEdit("/tmp/camera_profile_gui.icc")
            self._hide_row_widgets(self._add_path_row(grid, 3, "Perfil ICC de salida", self.profile_out_path_edit, file_mode=False, save_mode=True, dir_mode=False))

            self.profile_report_out = QtWidgets.QLineEdit("/tmp/profile_report_gui.json")
            self._hide_row_widgets(self._add_path_row(grid, 4, "Reporte perfil JSON", self.profile_report_out, file_mode=False, save_mode=True, dir_mode=False))

            self.profile_workdir = QtWidgets.QLineEdit("/tmp/iccraw_profile_work")
            self._hide_row_widgets(self._add_path_row(grid, 5, "Directorio artefactos", self.profile_workdir, file_mode=False, save_mode=False, dir_mode=True))

            self.develop_profile_out = QtWidgets.QLineEdit("/tmp/development_profile_gui.json")
            self._hide_row_widgets(self._add_path_row(grid, 6, "Perfil de revelado JSON", self.develop_profile_out, file_mode=False, save_mode=True, dir_mode=False))

            self.calibrated_recipe_out = QtWidgets.QLineEdit("/tmp/recipe_calibrated_gui.yml")
            self._hide_row_widgets(self._add_path_row(grid, 7, "Receta calibrada", self.calibrated_recipe_out, file_mode=False, save_mode=True, dir_mode=False))

            grid.addWidget(QtWidgets.QLabel("Tipo de carta"), 8, 0)
            self.profile_chart_type = QtWidgets.QComboBox()
            self.profile_chart_type.addItems(["colorchecker24", "it8"])
            grid.addWidget(self.profile_chart_type, 8, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Confianza mínima"), 9, 0)
            self.profile_min_conf = QtWidgets.QDoubleSpinBox()
            self.profile_min_conf.setRange(0.0, 1.0)
            self.profile_min_conf.setSingleStep(0.05)
            self.profile_min_conf.setDecimals(2)
            self.profile_min_conf.setValue(0.35)
            grid.addWidget(self.profile_min_conf, 9, 1, 1, 2)

            self.profile_allow_fallback = QtWidgets.QCheckBox("Permitir fallback")
            self.profile_allow_fallback.setChecked(False)
            grid.addWidget(self.profile_allow_fallback, 10, 1, 1, 2)

            label_camera = QtWidgets.QLabel("Cámara (opcional)")
            grid.addWidget(label_camera, 11, 0)
            self.profile_camera = QtWidgets.QLineEdit("")
            grid.addWidget(self.profile_camera, 11, 1, 1, 2)
            label_camera.hide()
            self.profile_camera.hide()

            label_lens = QtWidgets.QLabel("Lente (opcional)")
            grid.addWidget(label_lens, 12, 0)
            self.profile_lens = QtWidgets.QLineEdit("")
            grid.addWidget(self.profile_lens, 12, 1, 1, 2)
            label_lens.hide()
            self.profile_lens.hide()

            row_generate = QtWidgets.QHBoxLayout()
            row_generate.addWidget(self._button("Generar perfil de sesión", self._on_generate_profile))
            grid.addLayout(row_generate, 13, 0, 1, 3)

            outer.addWidget(box)

            manual_box = QtWidgets.QGroupBox("Marcado manual de carta")
            manual_layout = QtWidgets.QVBoxLayout(manual_box)
            manual_buttons = QtWidgets.QHBoxLayout()
            manual_buttons.addWidget(self._button("Marcar en visor", self._start_manual_chart_marking))
            manual_buttons.addWidget(self._button("Limpiar puntos", self._clear_manual_chart_points))
            manual_buttons.addWidget(self._button("Guardar detección", self._save_manual_chart_detection))
            manual_layout.addLayout(manual_buttons)
            self.manual_chart_points_label = QtWidgets.QLabel("Puntos: 0/4")
            self.manual_chart_points_label.setWordWrap(True)
            self.manual_chart_points_label.setStyleSheet("font-size: 12px; color: #374151;")
            manual_layout.addWidget(self.manual_chart_points_label)
            outer.addWidget(manual_box)

            self.profile_summary_label = QtWidgets.QLabel("Sin perfil de sesión generado")
            self.profile_summary_label.setWordWrap(True)
            self.profile_summary_label.setStyleSheet("font-size: 12px; color: #d1d5db;")
            outer.addWidget(self.profile_summary_label)

            self.profile_output = QtWidgets.QPlainTextEdit()
            self.profile_output.setReadOnly(True)
            self.profile_output.setPlaceholderText("Resultado JSON de la generación de perfil")
            self.profile_output.setMaximumHeight(170)
            outer.addWidget(self.profile_output, 1)
            return tab

        def _build_tab_queue(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            outer = QtWidgets.QVBoxLayout(tab)
            outer.setContentsMargins(8, 8, 8, 8)
            outer.setSpacing(8)

            queue_box = QtWidgets.QGroupBox("Cola de imágenes para revelado")
            queue_layout = QtWidgets.QVBoxLayout(queue_box)

            queue_actions = QtWidgets.QHBoxLayout()
            queue_actions.addWidget(self._button("Añadir selección", self._queue_add_selected))
            queue_actions.addWidget(self._button("Añadir RAW de sesión", self._queue_add_session_raws))
            queue_actions.addWidget(self._button("Quitar seleccionados", self._queue_remove_selected))
            queue_actions.addWidget(self._button("Limpiar cola", self._queue_clear))
            queue_actions.addWidget(self._button("Revelar cola", self._queue_process))
            queue_layout.addLayout(queue_actions)

            self.queue_status_label = QtWidgets.QLabel("Cola vacía")
            self.queue_status_label.setStyleSheet("font-size: 12px; color: #374151;")
            queue_layout.addWidget(self.queue_status_label)

            self.queue_table = QtWidgets.QTableWidget(0, 4)
            self.queue_table.setHorizontalHeaderLabels(["Archivo", "Estado", "TIFF salida", "Mensaje"])
            self.queue_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            self.queue_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
            self.queue_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
            self.queue_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.queue_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            queue_layout.addWidget(self.queue_table, 1)

            outer.addWidget(queue_box, 2)

            monitor_box = QtWidgets.QGroupBox("Monitoreo de ejecución")
            monitor_layout = QtWidgets.QVBoxLayout(monitor_box)

            top = QtWidgets.QHBoxLayout()
            self.monitor_status_label = QtWidgets.QLabel("Sin tareas en ejecución")
            self.monitor_progress = QtWidgets.QProgressBar()
            self.monitor_progress.setRange(0, 1)
            self.monitor_progress.setValue(0)
            top.addWidget(self.monitor_status_label, 1)
            top.addWidget(self.monitor_progress, 1)
            monitor_layout.addLayout(top)

            self.monitor_tasks = QtWidgets.QTableWidget(0, 4)
            self.monitor_tasks.setHorizontalHeaderLabels(["ID", "Tarea", "Estado", "Detalle"])
            self.monitor_tasks.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            self.monitor_tasks.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
            self.monitor_tasks.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.monitor_tasks.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            monitor_layout.addWidget(self.monitor_tasks, 1)

            self.monitor_log = QtWidgets.QPlainTextEdit()
            self.monitor_log.setReadOnly(True)
            self.monitor_log.setPlaceholderText("Eventos y trazas de flujo")
            monitor_layout.addWidget(self.monitor_log, 1)

            outer.addWidget(monitor_box, 2)
            return tab

        def _build_left_pane(self) -> QtWidgets.QWidget:
            pane = QtWidgets.QWidget()
            pane.setMinimumWidth(220)
            layout = QtWidgets.QVBoxLayout(pane)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            box = QtWidgets.QGroupBox("Explorador de unidades y carpetas")
            box_layout = QtWidgets.QVBoxLayout(box)

            root_row = QtWidgets.QHBoxLayout()
            root_row.addWidget(QtWidgets.QLabel("Unidad / raiz"))
            self.storage_root_combo = QtWidgets.QComboBox()
            self.storage_root_combo.currentIndexChanged.connect(self._on_storage_root_changed)
            root_row.addWidget(self.storage_root_combo, 1)
            root_row.addWidget(self._button("Actualizar", self._refresh_storage_roots))
            box_layout.addLayout(root_row)

            self.current_dir_label = QtWidgets.QLabel("")
            self.current_dir_label.setWordWrap(True)
            self.current_dir_label.setStyleSheet("font-size: 12px; color: #374151;")
            box_layout.addWidget(self.current_dir_label)

            self.dir_tree = QtWidgets.QTreeView()
            self.dir_tree.setHeaderHidden(True)
            self.dir_tree.setMinimumHeight(260)
            self.dir_tree.clicked.connect(self._on_tree_clicked)
            box_layout.addWidget(self.dir_tree, 1)

            layout.addWidget(box, 1)
            return pane

        def _build_thumbnails_pane(self) -> QtWidgets.QWidget:
            pane = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(pane)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            self.file_list = QtWidgets.QListWidget()
            self.file_list.setViewMode(QtWidgets.QListView.IconMode)
            self.file_list.setIconSize(QtCore.QSize(132, 132))
            self.file_list.setResizeMode(QtWidgets.QListView.Adjust)
            self.file_list.setMovement(QtWidgets.QListView.Static)
            self.file_list.setSpacing(8)
            self.file_list.setWordWrap(True)
            self.file_list.setUniformItemSizes(False)
            self.file_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            self.file_list.itemSelectionChanged.connect(self._on_file_selection_changed)
            self.file_list.itemDoubleClicked.connect(self._on_file_double_clicked)
            layout.addWidget(self.file_list, 1)

            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("Cargar seleccion", self._on_load_selected))
            row.addWidget(self._button("Usar selección como cartas", self._use_selected_files_as_profile_charts))
            row.addWidget(self._button("Añadir selección a cola", self._queue_add_selected))
            layout.addLayout(row)
            return pane

        def _build_center_pane(self) -> QtWidgets.QWidget:
            pane = QtWidgets.QWidget()
            pane.setMinimumWidth(420)
            layout = QtWidgets.QVBoxLayout(pane)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            controls = QtWidgets.QGroupBox("Visor principal")
            g = QtWidgets.QGridLayout(controls)

            g.addWidget(QtWidgets.QLabel("Archivo actual"), 0, 0)
            self.selected_file_label = QtWidgets.QLabel("Sin archivo seleccionado")
            self.selected_file_label.setWordWrap(True)
            self.selected_file_label.setStyleSheet("font-size: 12px; color: #1f2937;")
            g.addWidget(self.selected_file_label, 0, 1, 1, 4)

            self.chk_compare = QtWidgets.QCheckBox("Comparar original / resultado")
            self.chk_compare.toggled.connect(self._toggle_compare)
            g.addWidget(self.chk_compare, 1, 0, 1, 2)

            self.chk_apply_profile = QtWidgets.QCheckBox("Aplicar perfil ICC en resultado")
            self.chk_apply_profile.setChecked(False)
            self.chk_apply_profile.setToolTip(
                "Desactivado por defecto para evitar dominantes si el perfil no corresponde "
                "a camara + iluminacion + receta actuales."
            )
            self.chk_apply_profile.toggled.connect(lambda _v: self._refresh_preview())
            g.addWidget(self.chk_apply_profile, 1, 2, 1, 2)

            g.addWidget(self._button("Cargar seleccion", self._on_load_selected), 2, 0, 1, 2)
            g.addWidget(self._button("Recargar directorio", self._reload_current_directory), 2, 2, 1, 2)

            layout.addWidget(controls)

            self.viewer_stack = QtWidgets.QStackedWidget()

            self.image_result_single = ImagePanel("Resultado")
            self.image_result_single.imageClicked.connect(self._on_manual_chart_click)
            single_page = QtWidgets.QWidget()
            single_layout = QtWidgets.QVBoxLayout(single_page)
            single_layout.setContentsMargins(0, 0, 0, 0)
            single_layout.addWidget(self.image_result_single, 1)
            self.viewer_stack.addWidget(single_page)

            self.image_original_compare = ImagePanel("Original")
            self.image_result_compare = ImagePanel("Resultado")
            self.image_result_compare.imageClicked.connect(self._on_manual_chart_click)
            self.compare_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            self.compare_splitter.setChildrenCollapsible(True)
            self.compare_splitter.setHandleWidth(8)
            self.compare_splitter.addWidget(self.image_original_compare)
            self.compare_splitter.addWidget(self.image_result_compare)
            self.compare_splitter.setSizes([560, 560])
            self.viewer_stack.addWidget(self.compare_splitter)
            self.viewer_stack.setCurrentIndex(0)

            tabs = QtWidgets.QTabWidget()
            self.preview_analysis = QtWidgets.QPlainTextEdit()
            self.preview_analysis.setReadOnly(True)
            self.preview_analysis.setPlaceholderText("Analisis tecnico lineal")
            tabs.addTab(self.preview_analysis, "Analisis")

            self.preview_log = QtWidgets.QPlainTextEdit()
            self.preview_log.setReadOnly(True)
            self.preview_log.setPlaceholderText("Eventos y trazas de ejecucion")
            tabs.addTab(self.preview_log, "Log")

            self.viewer_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
            self.viewer_splitter.setChildrenCollapsible(True)
            self.viewer_splitter.setHandleWidth(8)
            self.viewer_splitter.addWidget(self.viewer_stack)
            self.viewer_splitter.addWidget(self._build_thumbnails_pane())
            self.viewer_splitter.addWidget(tabs)
            self.viewer_splitter.setStretchFactor(0, 3)
            self.viewer_splitter.setStretchFactor(1, 2)
            self.viewer_splitter.setStretchFactor(2, 0)
            self.viewer_splitter.setSizes([680, 280, 150])
            layout.addWidget(self.viewer_splitter, 1)
            return pane

        def _build_right_pane(self) -> QtWidgets.QWidget:
            pane = QtWidgets.QWidget()
            pane.setMinimumWidth(280)
            layout = QtWidgets.QVBoxLayout(pane)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            self.config_tabs = QtWidgets.QTabWidget()
            self.config_tabs.addTab(self._build_tab_profile_generation(), "1. Calibrar sesión")
            self.config_tabs.addTab(self._build_tab_preview_settings(), "Nitidez")
            self.config_tabs.addTab(self._build_tab_batch_config(), "2. Aplicar sesión")
            self._advanced_raw_config = self._build_tab_raw_config()
            self._advanced_profile_config = self._build_tab_profile_config()
            layout.addWidget(self.config_tabs, 1)

            return pane

        def _build_tab_preview_settings(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(tab)

            self.slider_sharpen, self.label_sharpen = self._slider(
                minimum=0,
                maximum=300,
                value=0,
                on_change=self._on_slider_change,
                formatter=lambda v: f"Nitidez (amount): {v / 100:.2f}",
            )
            grid.addWidget(self.label_sharpen, 0, 0, 1, 3)
            grid.addWidget(self.slider_sharpen, 1, 0, 1, 3)

            self.slider_radius, self.label_radius = self._slider(
                minimum=1,
                maximum=80,
                value=10,
                on_change=self._on_slider_change,
                formatter=lambda v: f"Radio nitidez: {v / 10:.1f}",
            )
            grid.addWidget(self.label_radius, 2, 0, 1, 3)
            grid.addWidget(self.slider_radius, 3, 0, 1, 3)

            self.slider_noise_luma, self.label_noise_luma = self._slider(
                minimum=0,
                maximum=100,
                value=0,
                on_change=self._on_slider_change,
                formatter=lambda v: f"Ruido luminancia: {v / 100:.2f}",
            )
            grid.addWidget(self.label_noise_luma, 4, 0, 1, 3)
            grid.addWidget(self.slider_noise_luma, 5, 0, 1, 3)

            self.slider_noise_color, self.label_noise_color = self._slider(
                minimum=0,
                maximum=100,
                value=0,
                on_change=self._on_slider_change,
                formatter=lambda v: f"Ruido color: {v / 100:.2f}",
            )
            grid.addWidget(self.label_noise_color, 6, 0, 1, 3)
            grid.addWidget(self.slider_noise_color, 7, 0, 1, 3)
            self.label_noise_luma.hide()
            self.slider_noise_luma.hide()
            self.label_noise_color.hide()
            self.slider_noise_color.hide()

            self.check_fast_raw_preview = QtWidgets.QCheckBox("Preview RAW rapida (recomendado)")
            self.check_fast_raw_preview.setChecked(True)
            self.check_fast_raw_preview.setToolTip(
                "Usa miniatura embebida o revelado RAW half-size para acelerar carga y previsualizacion."
            )
            grid.addWidget(self.check_fast_raw_preview, 8, 0, 1, 3)

            grid.addWidget(QtWidgets.QLabel("Lado maximo preview (px)"), 9, 0)
            self.spin_preview_max_side = QtWidgets.QSpinBox()
            self.spin_preview_max_side.setRange(900, 6000)
            self.spin_preview_max_side.setSingleStep(100)
            self.spin_preview_max_side.setValue(2600)
            grid.addWidget(self.spin_preview_max_side, 9, 1, 1, 2)

            self.path_preview_png = QtWidgets.QLineEdit("/tmp/iccraw_preview.png")
            self._add_path_row(grid, 10, "Guardar preview PNG", self.path_preview_png, file_mode=False, save_mode=True, dir_mode=False)
            grid.addWidget(self._button("Restablecer nitidez", self._reset_adjustments), 11, 0, 1, 3)
            return tab

        def _build_tab_raw_config(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(tab)

            self.path_recipe = QtWidgets.QLineEdit("testdata/recipes/scientific_recipe.yml")
            self._add_path_row(grid, 0, "Receta YAML/JSON", self.path_recipe, file_mode=True, save_mode=False, dir_mode=False)

            row_recipe = QtWidgets.QHBoxLayout()
            row_recipe.addWidget(self._button("Cargar receta", self._menu_load_recipe))
            row_recipe.addWidget(self._button("Guardar receta", self._menu_save_recipe))
            row_recipe.addWidget(self._button("Receta por defecto", self._menu_reset_recipe))
            grid.addLayout(row_recipe, 1, 0, 1, 3)

            grid.addWidget(QtWidgets.QLabel("Motor RAW"), 2, 0)
            self.combo_raw_developer = QtWidgets.QComboBox()
            self.combo_raw_developer.addItem("dcraw")
            self.combo_raw_developer.setEnabled(False)
            grid.addWidget(self.combo_raw_developer, 2, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Demosaic/interpolacion"), 3, 0)
            self.combo_demosaic = QtWidgets.QComboBox()
            for opt in DEMOSAIC_OPTIONS:
                self.combo_demosaic.addItem(opt, opt)
            grid.addWidget(self.combo_demosaic, 3, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Balance de blancos"), 4, 0)
            self.combo_wb_mode = QtWidgets.QComboBox()
            for label, val in WB_MODE_OPTIONS:
                self.combo_wb_mode.addItem(label, val)
            grid.addWidget(self.combo_wb_mode, 4, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("WB multiplicadores"), 5, 0)
            self.edit_wb_multipliers = QtWidgets.QLineEdit("1,1,1,1")
            self.edit_wb_multipliers.setToolTip("Formato: R,G,B,G (o R,G,B)")
            grid.addWidget(self.edit_wb_multipliers, 5, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Black level mode"), 6, 0)
            self.combo_black_mode = QtWidgets.QComboBox()
            for label, val in BLACK_MODE_OPTIONS:
                self.combo_black_mode.addItem(label, val)
            grid.addWidget(self.combo_black_mode, 6, 1)
            self.spin_black_value = QtWidgets.QSpinBox()
            self.spin_black_value.setRange(0, 65535)
            self.spin_black_value.setValue(0)
            grid.addWidget(self.spin_black_value, 6, 2)

            grid.addWidget(QtWidgets.QLabel("Exposure compensation (EV)"), 7, 0)
            self.spin_exposure = QtWidgets.QDoubleSpinBox()
            self.spin_exposure.setRange(-8.0, 8.0)
            self.spin_exposure.setDecimals(2)
            self.spin_exposure.setSingleStep(0.1)
            grid.addWidget(self.spin_exposure, 7, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Tone curve"), 8, 0)
            self.combo_tone_curve = QtWidgets.QComboBox()
            for label, val in TONE_OPTIONS:
                self.combo_tone_curve.addItem(label, val)
            grid.addWidget(self.combo_tone_curve, 8, 1)
            self.spin_gamma = QtWidgets.QDoubleSpinBox()
            self.spin_gamma.setRange(0.8, 4.0)
            self.spin_gamma.setDecimals(2)
            self.spin_gamma.setValue(2.2)
            grid.addWidget(self.spin_gamma, 8, 2)

            self.check_output_linear = QtWidgets.QCheckBox("Salida lineal")
            self.check_output_linear.setChecked(True)
            grid.addWidget(self.check_output_linear, 9, 0, 1, 3)

            grid.addWidget(QtWidgets.QLabel("Denoise modo receta"), 10, 0)
            self.combo_recipe_denoise = QtWidgets.QComboBox()
            self.combo_recipe_denoise.addItems(FILTER_MODE_OPTIONS)
            grid.addWidget(self.combo_recipe_denoise, 10, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Sharpen modo receta"), 11, 0)
            self.combo_recipe_sharpen = QtWidgets.QComboBox()
            self.combo_recipe_sharpen.addItems(FILTER_MODE_OPTIONS)
            grid.addWidget(self.combo_recipe_sharpen, 11, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Working space"), 12, 0)
            self.combo_working_space = QtWidgets.QComboBox()
            self.combo_working_space.addItems(SPACE_OPTIONS)
            grid.addWidget(self.combo_working_space, 12, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Output space"), 13, 0)
            self.combo_output_space = QtWidgets.QComboBox()
            self.combo_output_space.addItems(SPACE_OPTIONS)
            grid.addWidget(self.combo_output_space, 13, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Sampling strategy"), 14, 0)
            self.combo_sampling = QtWidgets.QComboBox()
            self.combo_sampling.addItems(SAMPLE_OPTIONS)
            grid.addWidget(self.combo_sampling, 14, 1, 1, 2)

            self.check_profiling_mode = QtWidgets.QCheckBox("Profiling mode")
            self.check_profiling_mode.setChecked(True)
            grid.addWidget(self.check_profiling_mode, 15, 0, 1, 3)

            grid.addWidget(QtWidgets.QLabel("Input color assumption"), 16, 0)
            self.edit_input_color = QtWidgets.QLineEdit("camera_native")
            grid.addWidget(self.edit_input_color, 16, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Illuminant metadata"), 17, 0)
            self.edit_illuminant = QtWidgets.QLineEdit("")
            grid.addWidget(self.edit_illuminant, 17, 1, 1, 2)
            return tab

        def _build_tab_profile_config(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(tab)

            self.path_profile_active = QtWidgets.QLineEdit("/tmp/camera_profile.icc")
            self._add_path_row(grid, 0, "Perfil ICC activo (preview/export)", self.path_profile_active, file_mode=True, save_mode=False, dir_mode=False)

            self.path_profile_out = QtWidgets.QLineEdit("/tmp/camera_profile_gui.icc")
            self._add_path_row(grid, 1, "Perfil ICC salida (workflow)", self.path_profile_out, file_mode=False, save_mode=True, dir_mode=False)

            grid.addWidget(QtWidgets.QLabel("Formato archivo"), 2, 0)
            self.combo_profile_format = QtWidgets.QComboBox()
            self.combo_profile_format.addItems(PROFILE_FORMAT_OPTIONS)
            grid.addWidget(self.combo_profile_format, 2, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Tipo de perfil ICC"), 3, 0)
            self.combo_profile_algo = QtWidgets.QComboBox()
            for label, flag in PROFILE_ALGO_OPTIONS:
                self.combo_profile_algo.addItem(label, flag)
            grid.addWidget(self.combo_profile_algo, 3, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Calidad perfil"), 4, 0)
            self.combo_profile_quality = QtWidgets.QComboBox()
            for label, q in PROFILE_QUALITY_OPTIONS:
                self.combo_profile_quality.addItem(label, q)
            self.combo_profile_quality.setCurrentIndex(1)
            grid.addWidget(self.combo_profile_quality, 4, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Args extra colprof"), 5, 0)
            self.edit_colprof_args = QtWidgets.QLineEdit("")
            self.edit_colprof_args.setPlaceholderText("Ejemplo: -D \"Perfil Camara Museo\"")
            grid.addWidget(self.edit_colprof_args, 5, 1, 1, 2)

            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("Cargar perfil activo", self._menu_load_profile))
            row.addWidget(self._button("Usar perfil generado", self._use_generated_profile_as_active))
            grid.addLayout(row, 6, 0, 1, 3)
            return tab

        def _build_tab_batch_config(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(tab)
            grid = QtWidgets.QGridLayout()

            self.batch_input_dir = QtWidgets.QLineEdit(str(self._current_dir))
            self._add_path_row(grid, 0, "RAW a revelar (carpeta)", self.batch_input_dir, file_mode=False, save_mode=False, dir_mode=True)

            self.batch_out_dir = QtWidgets.QLineEdit("/tmp/iccraw_batch_tiffs")
            self._add_path_row(grid, 1, "Salida TIFF de sesión", self.batch_out_dir, file_mode=False, save_mode=False, dir_mode=True)

            self.batch_embed_profile = QtWidgets.QCheckBox("Aplicar perfil de sesión (ICC) en TIFF")
            self.batch_embed_profile.setChecked(True)
            self.batch_embed_profile.setEnabled(False)
            grid.addWidget(self.batch_embed_profile, 2, 0, 1, 3)

            self.batch_apply_adjustments = QtWidgets.QCheckBox("Aplicar nitidez del panel")
            self.batch_apply_adjustments.setChecked(True)
            grid.addWidget(self.batch_apply_adjustments, 3, 0, 1, 3)

            row_1 = QtWidgets.QHBoxLayout()
            row_1.addWidget(self._button("Usar carpeta actual", self._use_current_dir_as_batch_input))
            row_1.addWidget(self._button("Aplicar a selección", self._on_batch_develop_selected))
            row_1.addWidget(self._button("Aplicar a carpeta", self._on_batch_develop_directory))

            self.batch_output = QtWidgets.QPlainTextEdit()
            self.batch_output.setReadOnly(True)
            self.batch_output.setPlaceholderText("Salida JSON de aplicación de sesión")

            layout.addLayout(grid)
            layout.addLayout(row_1)
            layout.addWidget(self.batch_output, 1)
            return tab

        def _init_fs_model(self) -> None:
            self._dir_model = QtWidgets.QFileSystemModel(self)
            self._dir_model.setFilter(QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot)
            root_path = "" if sys.platform.startswith("win") else "/"
            self._dir_model.setRootPath(root_path)
            index = self._dir_model.index(root_path)
            self.dir_tree.setModel(self._dir_model)
            self.dir_tree.setRootIndex(index)
            for c in (1, 2, 3):
                self.dir_tree.hideColumn(c)

        def _action(self, text: str, callback, shortcut: str | None = None) -> QtGui.QAction:
            a = QtGui.QAction(text, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(callback)
            return a

        def _button(self, text: str, callback) -> QtWidgets.QPushButton:
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(callback)
            return b

        def _slider(self, minimum: int, maximum: int, value: int, on_change, formatter):
            label = QtWidgets.QLabel(formatter(value))
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setRange(minimum, maximum)
            slider.setValue(value)
            slider.valueChanged.connect(lambda v: label.setText(formatter(v)))
            slider.valueChanged.connect(on_change)
            return slider, label

        def _add_path_row(
            self,
            grid: QtWidgets.QGridLayout,
            row: int,
            label_text: str,
            line_edit: QtWidgets.QLineEdit,
            *,
            file_mode: bool,
            save_mode: bool,
            dir_mode: bool,
        ) -> tuple[QtWidgets.QWidget, QtWidgets.QWidget, QtWidgets.QWidget]:
            label = QtWidgets.QLabel(label_text)
            grid.addWidget(label, row, 0)
            grid.addWidget(line_edit, row, 1)
            browse = QtWidgets.QPushButton("...")
            browse.setMaximumWidth(36)
            browse.clicked.connect(
                lambda: self._browse_for_path(
                    target=line_edit,
                    file_mode=file_mode,
                    save_mode=save_mode,
                    dir_mode=dir_mode,
                )
            )
            grid.addWidget(browse, row, 2)
            return label, line_edit, browse

        def _hide_row_widgets(self, widgets: tuple[QtWidgets.QWidget, ...]) -> None:
            for widget in widgets:
                widget.hide()

        def _browse_for_path(self, target, *, file_mode: bool, save_mode: bool, dir_mode: bool) -> None:
            if dir_mode:
                path = QtWidgets.QFileDialog.getExistingDirectory(self, "Selecciona directorio")
                if path:
                    target.setText(path)
                return
            if save_mode:
                path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar como")
                if path:
                    target.setText(path)
                return
            if file_mode:
                path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Selecciona archivo")
                if path:
                    target.setText(path)

        def _initialize_session_tab_defaults(self) -> None:
            suggested = (self._current_dir / "iccraw_session").resolve()
            self.session_root_path.setText(str(suggested))
            self.session_name_edit.setText(suggested.name)
            self._populate_session_directory_fields(self._session_paths_from_root(suggested))

        def _session_paths_from_root(self, root: Path) -> dict[str, Path]:
            absolute = root.expanduser().resolve()
            return {
                "root": absolute,
                "charts": absolute / "charts",
                "raw": absolute / "raw",
                "profiles": absolute / "profiles",
                "exports": absolute / "exports",
                "config": absolute / "config",
                "work": absolute / "work",
            }

        def _populate_session_directory_fields(self, paths: dict[str, Path]) -> None:
            self.session_dir_charts.setText(str(paths["charts"]))
            self.session_dir_raw.setText(str(paths["raw"]))
            self.session_dir_profiles.setText(str(paths["profiles"]))
            self.session_dir_exports.setText(str(paths["exports"]))
            self.session_dir_config.setText(str(paths["config"]))
            self.session_dir_work.setText(str(paths["work"]))

        def _path_is_inside(self, path: Path, root: Path) -> bool:
            try:
                path.expanduser().resolve(strict=False).relative_to(root.expanduser().resolve(strict=False))
                return True
            except Exception:
                return False

        def _folder_has_browsable_files(self, folder: Path) -> bool:
            try:
                return any(
                    p.is_file() and p.suffix.lower() in BROWSABLE_EXTENSIONS
                    for p in folder.iterdir()
                )
            except OSError:
                return False

        def _session_state_path_or_default(self, value: Any, default: Path) -> Path:
            text = str(value or "").strip()
            default = default.expanduser()
            if not text:
                return default

            candidate = Path(text).expanduser()
            try:
                if candidate.resolve(strict=False) == Path.home().resolve(strict=False):
                    return default
            except Exception:
                return default

            if not candidate.exists() and default.exists():
                return default
            return candidate

        def _preferred_session_start_directory(self, directories: dict[str, Any], state: dict[str, Any]) -> Path:
            root = self._active_session_root or Path.cwd()
            paths = {
                k: Path(str(v)).expanduser()
                for k, v in directories.items()
                if isinstance(v, (str, Path)) and str(v).strip()
            }

            charts_default = paths.get("charts", root)
            raw_default = paths.get("raw", root)
            charts_state = self._session_state_path_or_default(state.get("profile_charts_dir"), charts_default)
            raw_state = self._session_state_path_or_default(state.get("batch_input_dir"), raw_default)

            candidates: list[Path] = []
            for chart_file in self._selected_chart_files:
                if chart_file.exists() and chart_file.is_file():
                    candidates.append(chart_file.parent)
                    break
            candidates.extend([charts_state, raw_state, charts_default, raw_default, root])

            seen: set[str] = set()
            unique_candidates: list[Path] = []
            for candidate in candidates:
                try:
                    key = str(candidate.expanduser().resolve(strict=False))
                except Exception:
                    key = str(candidate.expanduser())
                if key not in seen:
                    seen.add(key)
                    unique_candidates.append(candidate)

            for candidate in unique_candidates:
                if candidate.exists() and candidate.is_dir() and self._folder_has_browsable_files(candidate):
                    return candidate
            for candidate in unique_candidates:
                if candidate.exists() and candidate.is_dir():
                    return candidate
            return root

        def _should_replace_operational_dir(self, current_value: str, new_folder: Path) -> bool:
            text = current_value.strip()
            if not text:
                return True

            current = Path(text).expanduser()
            try:
                if current.resolve(strict=False) == Path.home().resolve(strict=False):
                    return True
            except Exception:
                return True

            if not current.exists():
                return True

            if self._active_session_root is not None:
                inside_current_session = self._path_is_inside(current, self._active_session_root)
                inside_new_session = self._path_is_inside(new_folder, self._active_session_root)
                if inside_new_session and not inside_current_session:
                    return True
            return False

        def _sync_operational_dirs_from_browser(self, folder: Path) -> None:
            if not self._folder_has_browsable_files(folder):
                return
            if self._should_replace_operational_dir(self.profile_charts_dir.text(), folder):
                self.profile_charts_dir.setText(str(folder))
            if self._should_replace_operational_dir(self.batch_input_dir.text(), folder):
                self.batch_input_dir.setText(str(folder))

        def _use_current_dir_as_session_root(self) -> None:
            self.session_root_path.setText(str(self._current_dir))
            self.session_name_edit.setText(self._current_dir.name)
            self._populate_session_directory_fields(self._session_paths_from_root(self._current_dir))
            self._set_status(f"Raíz de sesión: {self._current_dir}")

        def _on_session_root_edited(self) -> None:
            text = self.session_root_path.text().strip()
            if not text:
                return
            root = Path(text).expanduser()
            self._populate_session_directory_fields(self._session_paths_from_root(root))

        def _session_state_snapshot(self) -> dict[str, Any]:
            return {
                "profile_charts_dir": self.profile_charts_dir.text().strip(),
                "profile_chart_files": [str(p) for p in self._selected_chart_files],
                "reference_path": self.path_reference.text().strip(),
                "profile_output_path": self.profile_out_path_edit.text().strip(),
                "profile_report_path": self.profile_report_out.text().strip(),
                "profile_workdir": self.profile_workdir.text().strip(),
                "development_profile_path": self.develop_profile_out.text().strip(),
                "calibrated_recipe_path": self.calibrated_recipe_out.text().strip(),
                "profile_chart_type": self.profile_chart_type.currentText().strip(),
                "profile_min_confidence": float(self.profile_min_conf.value()),
                "profile_allow_fallback_detection": bool(self.profile_allow_fallback.isChecked()),
                "profile_camera": self.profile_camera.text().strip(),
                "profile_lens": self.profile_lens.text().strip(),
                "recipe_path": self.path_recipe.text().strip(),
                "profile_active_path": self.path_profile_active.text().strip(),
                "batch_input_dir": self.batch_input_dir.text().strip(),
                "batch_output_dir": self.batch_out_dir.text().strip(),
                "preview_png_path": self.path_preview_png.text().strip(),
                "preview_apply_profile": bool(self.chk_apply_profile.isChecked()),
                "batch_embed_profile": True,
                "batch_apply_adjustments": bool(self.batch_apply_adjustments.isChecked()),
                "fast_raw_preview": bool(self.check_fast_raw_preview.isChecked()),
                "preview_max_side": int(self.spin_preview_max_side.value()),
                "adjustments": {
                    "sharpen": int(self.slider_sharpen.value()),
                    "radius": int(self.slider_radius.value()),
                    "noise_luma": int(self.slider_noise_luma.value()),
                    "noise_color": int(self.slider_noise_color.value()),
                },
                "recipe": asdict(self._build_effective_recipe()),
            }

        def _apply_state_to_ui_from_session(
            self,
            *,
            state: dict[str, Any],
            directories: dict[str, str],
            session_name: str,
        ) -> None:
            paths = {k: Path(v) for k, v in directories.items() if isinstance(v, str)}
            charts_dir = self._session_state_path_or_default(
                state.get("profile_charts_dir"),
                paths.get("charts", Path.cwd()),
            )
            raw_dir = self._session_state_path_or_default(
                state.get("batch_input_dir"),
                paths.get("raw", Path.cwd()),
            )
            exports_dir = paths.get("exports", Path.cwd())
            profiles_dir = paths.get("profiles", Path.cwd())
            config_dir = paths.get("config", Path.cwd())
            work_dir = paths.get("work", Path.cwd())

            safe_name = session_name.strip() or "session"
            default_profile_out = profiles_dir / f"{safe_name}.icc"
            default_report = config_dir / "profile_report.json"
            default_workdir = work_dir / "profile_generation"
            default_development_profile = config_dir / "development_profile.json"
            default_calibrated_recipe = config_dir / "recipe_calibrated.yml"
            default_recipe = config_dir / "recipe.yml"
            default_preview = exports_dir / "preview" / "preview.png"
            default_tiff_out = exports_dir / "tiff"

            self.profile_charts_dir.setText(str(charts_dir))
            chart_files_state = state.get("profile_chart_files")
            if isinstance(chart_files_state, list):
                self._selected_chart_files = [
                    Path(str(p)).expanduser()
                    for p in chart_files_state
                    if str(p).strip() and Path(str(p)).expanduser().exists()
                ]
            else:
                self._selected_chart_files = []
            self._sync_profile_chart_selection_label()
            self.path_reference.setText(str(state.get("reference_path") or self.path_reference.text().strip()))
            self.profile_out_path_edit.setText(str(state.get("profile_output_path") or default_profile_out))
            self.path_profile_out.setText(self.profile_out_path_edit.text().strip())
            self.profile_report_out.setText(str(state.get("profile_report_path") or default_report))
            self.profile_workdir.setText(str(state.get("profile_workdir") or default_workdir))
            self.develop_profile_out.setText(str(state.get("development_profile_path") or default_development_profile))
            self.calibrated_recipe_out.setText(str(state.get("calibrated_recipe_path") or default_calibrated_recipe))
            self.batch_input_dir.setText(str(raw_dir))
            self.batch_out_dir.setText(str(state.get("batch_output_dir") or default_tiff_out))
            self.path_preview_png.setText(str(state.get("preview_png_path") or default_preview))
            self.path_recipe.setText(str(state.get("recipe_path") or default_recipe))

            profile_active = str(state.get("profile_active_path") or "").strip()
            if profile_active:
                self.path_profile_active.setText(profile_active)

            chart_type = str(state.get("profile_chart_type") or "colorchecker24")
            self._set_combo_text(self.profile_chart_type, chart_type)
            try:
                self.profile_min_conf.setValue(float(state.get("profile_min_confidence", 0.35)))
            except Exception:
                self.profile_min_conf.setValue(0.35)
            self.profile_allow_fallback.setChecked(bool(state.get("profile_allow_fallback_detection", False)))

            self.profile_camera.setText(str(state.get("profile_camera") or ""))
            self.profile_lens.setText(str(state.get("profile_lens") or ""))

            self.chk_apply_profile.setChecked(bool(state.get("preview_apply_profile", self.chk_apply_profile.isChecked())))
            self.batch_embed_profile.setChecked(True)
            self.batch_apply_adjustments.setChecked(bool(state.get("batch_apply_adjustments", self.batch_apply_adjustments.isChecked())))
            self.check_fast_raw_preview.setChecked(bool(state.get("fast_raw_preview", self.check_fast_raw_preview.isChecked())))

            try:
                self.spin_preview_max_side.setValue(int(state.get("preview_max_side", self.spin_preview_max_side.value())))
            except Exception:
                pass

            adjustments = state.get("adjustments") if isinstance(state.get("adjustments"), dict) else {}
            try:
                self.slider_sharpen.setValue(int(adjustments.get("sharpen", self.slider_sharpen.value())))
                self.slider_radius.setValue(int(adjustments.get("radius", self.slider_radius.value())))
                self.slider_noise_luma.setValue(int(adjustments.get("noise_luma", self.slider_noise_luma.value())))
                self.slider_noise_color.setValue(int(adjustments.get("noise_color", self.slider_noise_color.value())))
            except Exception:
                pass

            recipe_payload = state.get("recipe")
            if isinstance(recipe_payload, dict):
                try:
                    allowed_keys = set(Recipe.__dataclass_fields__.keys())
                    filtered = {k: v for k, v in recipe_payload.items() if k in allowed_keys}
                    self._apply_recipe_to_controls(Recipe(**filtered))
                except Exception:
                    pass

        def _activate_session(self, root: Path, payload: dict[str, Any]) -> None:
            self._active_session_root = root.expanduser().resolve()
            self._active_session_payload = payload

            metadata = payload.get("metadata", {})
            directories = payload.get("directories", {})
            state = payload.get("state", {})
            queue = payload.get("queue", [])

            session_name = str(metadata.get("name") or self._active_session_root.name)
            self.session_root_path.setText(str(self._active_session_root))
            self.session_name_edit.setText(session_name)
            self.session_illumination_edit.setText(str(metadata.get("illumination_notes") or ""))
            self.session_capture_edit.setText(str(metadata.get("capture_notes") or ""))

            if isinstance(directories, dict) and directories:
                self.session_dir_charts.setText(str(directories.get("charts") or ""))
                self.session_dir_raw.setText(str(directories.get("raw") or ""))
                self.session_dir_profiles.setText(str(directories.get("profiles") or ""))
                self.session_dir_exports.setText(str(directories.get("exports") or ""))
                self.session_dir_config.setText(str(directories.get("config") or ""))
                self.session_dir_work.setText(str(directories.get("work") or ""))
            else:
                self._populate_session_directory_fields(self._session_paths_from_root(self._active_session_root))

            self._apply_state_to_ui_from_session(
                state=state if isinstance(state, dict) else {},
                directories=directories if isinstance(directories, dict) else {},
                session_name=session_name,
            )
            self._settings.setValue("session/last_root", str(self._active_session_root))

            self._develop_queue = [
                {
                    "source": str(item.get("source") or ""),
                    "status": str(item.get("status") or "pending"),
                    "output_tiff": str(item.get("output_tiff") or ""),
                    "message": str(item.get("message") or ""),
                }
                for item in queue
                if isinstance(item, dict) and str(item.get("source") or "").strip()
            ]
            self._refresh_queue_table()

            start_dir = self._preferred_session_start_directory(
                directories if isinstance(directories, dict) else {},
                state if isinstance(state, dict) else {},
            )
            self._set_current_directory(start_dir)

            self.session_active_label.setText(
                f"Sesión activa: {session_name}\n"
                f"Raíz: {self._active_session_root}\n"
                f"Configuración: {session_file_path(self._active_session_root)}"
            )
            self._set_status(f"Sesión activa: {session_name}")

        def _on_create_session(self) -> None:
            root_text = self.session_root_path.text().strip()
            if not root_text:
                QtWidgets.QMessageBox.information(self, "Info", "Indica un directorio raíz para la sesión.")
                return

            root = Path(root_text).expanduser()
            existing_session = session_file_path(root)
            if existing_session.exists():
                resp = QtWidgets.QMessageBox.question(
                    self,
                    "Sesión existente",
                    "Ya existe una sesión en ese directorio. ¿Sobrescribir configuración?",
                )
                if resp != QtWidgets.QMessageBox.Yes:
                    return
            name = self.session_name_edit.text().strip() or root.name
            illumination = self.session_illumination_edit.text().strip()
            capture = self.session_capture_edit.text().strip()
            payload = create_session(
                root,
                name=name,
                illumination_notes=illumination,
                capture_notes=capture,
                state=self._session_state_snapshot(),
                queue=self._develop_queue,
            )
            self._activate_session(root, payload)

        def _on_open_session(self) -> None:
            start = self.session_root_path.text().strip() or str(self._current_dir)
            selected = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Abrir sesión (directorio raíz)",
                start,
            )
            if not selected:
                return
            root = Path(selected)
            try:
                payload = load_session(root)
            except FileNotFoundError:
                QtWidgets.QMessageBox.information(
                    self,
                    "Info",
                    f"No se encontró configuración de sesión en:\n{session_file_path(root)}",
                )
                return
            self._activate_session(root, payload)

        def _save_active_session(self, *, silent: bool) -> bool:
            if self._active_session_root is None and silent:
                return False

            root_text = self.session_root_path.text().strip()
            if not root_text:
                if not silent:
                    QtWidgets.QMessageBox.information(self, "Info", "Define un directorio de sesión.")
                return False

            root = Path(root_text).expanduser()
            ensure_session_structure(root)

            metadata_existing = {}
            directories_existing = {}
            if isinstance(self._active_session_payload, dict):
                metadata_existing = self._active_session_payload.get("metadata", {})
                directories_existing = self._active_session_payload.get("directories", {})
            if isinstance(directories_existing, dict):
                current_root = str(directories_existing.get("root") or "")
                if current_root and Path(current_root).expanduser().resolve() != root.resolve():
                    directories_existing = {}

            payload = {
                "version": 1,
                "metadata": {
                    "name": self.session_name_edit.text().strip() or root.name,
                    "illumination_notes": self.session_illumination_edit.text().strip(),
                    "capture_notes": self.session_capture_edit.text().strip(),
                    "created_at": metadata_existing.get("created_at", ""),
                    "updated_at": metadata_existing.get("updated_at", ""),
                },
                "directories": directories_existing if isinstance(directories_existing, dict) else {},
                "state": self._session_state_snapshot(),
                "queue": self._develop_queue,
            }
            saved = save_session(root, payload)
            self._active_session_payload = saved
            self._active_session_root = root.resolve()
            self._settings.setValue("session/last_root", str(self._active_session_root))
            self.session_active_label.setText(
                f"Sesión activa: {saved['metadata']['name']}\n"
                f"Raíz: {self._active_session_root}\n"
                f"Configuración: {session_file_path(self._active_session_root)}"
            )
            if not silent:
                self._set_status(f"Sesión guardada: {session_file_path(self._active_session_root)}")
            return True

        def _on_save_session(self) -> None:
            if self._active_session_root is None:
                self._on_create_session()
                return
            self._save_active_session(silent=False)

        def _queue_add_files(self, files: list[Path]) -> int:
            existing = {item["source"] for item in self._develop_queue if item.get("source")}
            added = 0
            for src in files:
                source = str(src)
                if source in existing:
                    continue
                self._develop_queue.append(
                    {
                        "source": source,
                        "status": "pending",
                        "output_tiff": "",
                        "message": "",
                    }
                )
                existing.add(source)
                added += 1

            if added:
                self._refresh_queue_table()
                self._save_active_session(silent=True)
            return added

        def _queue_add_selected(self) -> None:
            files = self._collect_selected_file_paths()
            if not files:
                QtWidgets.QMessageBox.information(self, "Info", "No hay selección para añadir a la cola.")
                return
            added = self._queue_add_files(files)
            self._set_status(f"Cola actualizada: {added} elementos añadidos")

        def _queue_add_session_raws(self) -> None:
            source_dir = Path(self.batch_input_dir.text().strip() or self._current_dir)
            if not source_dir.exists() or not source_dir.is_dir():
                QtWidgets.QMessageBox.information(self, "Info", f"Directorio inválido: {source_dir}")
                return
            files = [
                p for p in sorted(source_dir.iterdir())
                if p.is_file() and p.suffix.lower() in BROWSABLE_EXTENSIONS
            ]
            if not files:
                QtWidgets.QMessageBox.information(self, "Info", "No hay RAW/imágenes compatibles en el directorio.")
                return
            added = self._queue_add_files(files)
            self._set_status(f"Cola actualizada: {added} archivos añadidos desde {source_dir}")

        def _queue_remove_selected(self) -> None:
            if not self._develop_queue:
                return
            rows = sorted({i.row() for i in self.queue_table.selectionModel().selectedRows()}, reverse=True)
            if not rows:
                QtWidgets.QMessageBox.information(self, "Info", "Selecciona filas de la cola para quitar.")
                return
            for row in rows:
                if 0 <= row < len(self._develop_queue):
                    self._develop_queue.pop(row)
            self._refresh_queue_table()
            self._save_active_session(silent=True)

        def _queue_clear(self) -> None:
            self._develop_queue = []
            self._refresh_queue_table()
            self._save_active_session(silent=True)
            self._set_status("Cola vaciada")

        def _refresh_queue_table(self) -> None:
            if not hasattr(self, "queue_table"):
                return

            self.queue_table.setRowCount(0)
            pending = 0
            done = 0
            errors = 0

            for item in self._develop_queue:
                status = str(item.get("status") or "pending")
                if status == "done":
                    done += 1
                elif status == "error":
                    errors += 1
                else:
                    pending += 1

                row = self.queue_table.rowCount()
                self.queue_table.insertRow(row)
                self.queue_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(item.get("source") or "")))
                self.queue_table.setItem(row, 1, QtWidgets.QTableWidgetItem(status))
                self.queue_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(item.get("output_tiff") or "")))
                self.queue_table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(item.get("message") or "")))

            self.queue_status_label.setText(
                f"Elementos: {len(self._develop_queue)} | Pendientes: {pending} | OK: {done} | Error: {errors}"
            )

        def _queue_process(self) -> None:
            if not self._develop_queue:
                QtWidgets.QMessageBox.information(self, "Info", "No hay elementos en cola.")
                return

            files: list[Path] = []
            for item in self._develop_queue:
                src = Path(str(item.get("source") or ""))
                if src.exists() and src.is_file() and src.suffix.lower() in BROWSABLE_EXTENSIONS:
                    files.append(src)
                else:
                    item["status"] = "error"
                    item["message"] = "Archivo no encontrado o extensión incompatible"
                    item["output_tiff"] = ""

            if not files:
                self._refresh_queue_table()
                self._save_active_session(silent=True)
                QtWidgets.QMessageBox.information(self, "Info", "No hay archivos válidos para procesar en la cola.")
                return

            valid_sources = {str(p) for p in files}
            for item in self._develop_queue:
                source = str(item.get("source") or "")
                if source and source in valid_sources:
                    item["status"] = "pending"
                    item["message"] = ""
                    item["output_tiff"] = ""
            self._refresh_queue_table()

            out_dir = Path(self.batch_out_dir.text().strip())
            recipe = self._build_effective_recipe()
            apply_adjust = bool(self.batch_apply_adjustments.isChecked())
            use_profile = bool(self.batch_embed_profile.isChecked()) and self.path_profile_active.text().strip() != ""
            profile_path = Path(self.path_profile_active.text().strip()) if use_profile else None

            nl = 0.0
            nc = 0.0
            sharpen = self.slider_sharpen.value() / 100.0
            radius = self.slider_radius.value() / 10.0

            def task():
                payload = self._process_batch_files(
                    files=files,
                    out_dir=out_dir,
                    recipe=recipe,
                    apply_adjust=apply_adjust,
                    use_profile=use_profile,
                    profile_path=profile_path,
                    denoise_luma=nl,
                    denoise_color=nc,
                    sharpen_amount=sharpen,
                    sharpen_radius=radius,
                )
                payload["task"] = "Cola de revelado"
                return payload

            def on_success(payload) -> None:
                ok_by_source = {str(o["source"]): str(o["output"]) for o in payload.get("outputs", [])}
                err_by_source = {str(e["source"]): str(e["error"]) for e in payload.get("errors", [])}

                for item in self._develop_queue:
                    source = str(item.get("source") or "")
                    if source in ok_by_source:
                        item["status"] = "done"
                        item["output_tiff"] = ok_by_source[source]
                        item["message"] = "OK"
                    elif source in err_by_source:
                        item["status"] = "error"
                        item["output_tiff"] = ""
                        item["message"] = err_by_source[source]

                self._refresh_queue_table()
                self._save_active_session(silent=True)
                self._set_status(
                    f"Cola procesada: {len(payload.get('outputs', []))} OK / {len(payload.get('errors', []))} errores"
                )

            self._start_background_task("Procesar cola de revelado", task, on_success)

        def _pick_directory(self) -> None:
            p = QtWidgets.QFileDialog.getExistingDirectory(self, "Selecciona directorio")
            if not p:
                return
            selected = Path(p)
            self.dir_tree.setCurrentIndex(self._dir_model.index(str(selected)))
            self._set_current_directory(selected)

        def _detect_storage_roots(self) -> list[Path]:
            roots: list[Path] = []
            if sys.platform.startswith("win"):
                for fi in QtCore.QDir.drives():
                    p = Path(fi.absoluteFilePath())
                    if p not in roots:
                        roots.append(p)
            else:
                roots.append(Path("/"))

            if hasattr(QtCore, "QStorageInfo"):
                for vol in QtCore.QStorageInfo.mountedVolumes():
                    try:
                        if not vol.isValid() or not vol.isReady():
                            continue
                        p = Path(vol.rootPath())
                        if p not in roots:
                            roots.append(p)
                    except Exception:
                        continue

            roots = sorted(roots, key=lambda p: str(p))
            return roots

        def _refresh_storage_roots(self) -> None:
            roots = self._detect_storage_roots()
            self._storage_roots = roots
            current_dir = self._current_dir

            self.storage_root_combo.blockSignals(True)
            self.storage_root_combo.clear()
            best_idx = -1
            best_len = -1

            for idx, root in enumerate(roots):
                label = str(root)
                self.storage_root_combo.addItem(label, str(root))
                if str(current_dir).startswith(str(root)) and len(str(root)) > best_len:
                    best_idx = idx
                    best_len = len(str(root))

            if best_idx >= 0:
                self.storage_root_combo.setCurrentIndex(best_idx)
            self.storage_root_combo.blockSignals(False)

        def _on_storage_root_changed(self, idx: int) -> None:
            if idx < 0:
                return
            data = self.storage_root_combo.itemData(idx)
            if not data:
                return
            root = Path(str(data))
            self.dir_tree.setCurrentIndex(self._dir_model.index(str(root)))
            self._set_current_directory(root)

        def _on_tree_clicked(self, index) -> None:
            p = Path(self._dir_model.filePath(index))
            self._set_current_directory(p)

        def _set_current_directory(self, folder: Path) -> None:
            if not folder.exists() or not folder.is_dir():
                return
            folder = folder.expanduser().resolve()
            self._current_dir = folder
            self.current_dir_label.setText(str(folder))
            self._settings.setValue("browser/last_dir", str(folder))
            self._refresh_storage_roots()
            index = self._dir_model.index(str(folder))
            if index.isValid():
                self.dir_tree.blockSignals(True)
                self.dir_tree.setCurrentIndex(index)
                self.dir_tree.scrollTo(index)
                self.dir_tree.blockSignals(False)
            self._sync_operational_dirs_from_browser(folder)
            self._populate_file_list(folder)
            self._set_status(f"Directorio actual: {folder}")

        def _reload_current_directory(self) -> None:
            self._populate_file_list(self._current_dir)

        def _populate_file_list(self, folder: Path) -> None:
            self.file_list.clear()
            self._selected_file = None
            self.selected_file_label.setText("Sin archivo seleccionado")

            files = [
                p for p in sorted(folder.iterdir())
                if p.is_file() and p.suffix.lower() in BROWSABLE_EXTENSIONS
            ]
            max_items = 500
            shown = files[:max_items]

            for p in shown:
                item = QtWidgets.QListWidgetItem(p.name)
                item.setData(QtCore.Qt.UserRole, str(p))
                item.setTextAlignment(QtCore.Qt.AlignHCenter)
                item.setToolTip(str(p))
                item.setIcon(self._icon_for_file(p))
                self.file_list.addItem(item)

            if len(files) > max_items:
                rest = len(files) - max_items
                i = QtWidgets.QListWidgetItem(f"... {rest} archivos mas")
                i.setFlags(QtCore.Qt.NoItemFlags)
                self.file_list.addItem(i)

        def _icon_for_file(self, path: Path) -> QtGui.QIcon:
            try:
                st = path.stat()
                key = f"{path}:{st.st_mtime_ns}"
            except Exception:
                key = str(path)

            cached = self._thumb_cache.get(key)
            if cached is not None:
                return cached

            if path.suffix.lower() in RAW_EXTENSIONS:
                preview = extract_embedded_preview(path)
                if preview is not None:
                    icon = self._icon_from_linear_image(preview)
                else:
                    icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
                self._thumb_cache[key] = icon
                return icon

            try:
                rgb = read_image(path)
                icon = self._icon_from_linear_image(rgb)
                self._thumb_cache[key] = icon
                return icon
            except Exception:
                icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
                self._thumb_cache[key] = icon
                return icon

        def _icon_from_linear_image(self, rgb: np.ndarray) -> QtGui.QIcon:
            h, w, _ = rgb.shape
            max_side = max(h, w)
            if max_side > 280:
                scale = 280.0 / max_side
                rgb = cv2.resize(
                    rgb,
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    interpolation=cv2.INTER_AREA,
                )
            srgb = linear_to_srgb_display(rgb)
            u8 = np.clip(np.round(srgb * 255.0), 0, 255).astype(np.uint8)
            hh, ww, _ = u8.shape
            qimg = QtGui.QImage(u8.data, ww, hh, 3 * ww, QtGui.QImage.Format_RGB888).copy()
            pix = QtGui.QPixmap.fromImage(qimg).scaled(
                132,
                132,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            return QtGui.QIcon(pix)

        def _on_file_selection_changed(self) -> None:
            item = self.file_list.currentItem()
            if item is None:
                self._selected_file = None
                self.selected_file_label.setText("Sin archivo seleccionado")
                return
            raw_path = item.data(QtCore.Qt.UserRole)
            if not raw_path:
                self._selected_file = None
                return
            self._selected_file = Path(raw_path)
            self.selected_file_label.setText(str(self._selected_file))

        def _on_file_double_clicked(self, _item) -> None:
            self._on_load_selected()

        def _toggle_compare(self, enabled: bool) -> None:
            self.viewer_stack.setCurrentIndex(1 if enabled else 0)
            if hasattr(self, "_action_compare"):
                self._action_compare.blockSignals(True)
                self._action_compare.setChecked(enabled)
                self._action_compare.blockSignals(False)

        def _menu_toggle_compare(self, checked: bool) -> None:
            self.chk_compare.setChecked(checked)
            self._toggle_compare(checked)

        def _menu_about(self) -> None:
            QtWidgets.QMessageBox.information(
                self,
                "Acerca de ICCRAW",
                "ICCRAW\n\nRevelado RAW tecnico y perfilado ICC reproducible.\n"
                "Backend: dcraw + ArgyllCMS.\nGUI: Qt/PySide6.",
            )

        def _menu_load_profile(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Selecciona perfil ICC",
                self.path_profile_active.text().strip(),
                "ICC Profiles (*.icc *.icm);;Todos (*)",
            )
            if not path:
                return
            self.path_profile_active.setText(path)
            self._set_status(f"Perfil activo: {path}")
            self._refresh_preview()
            self._save_active_session(silent=True)

        def _menu_load_recipe(self) -> None:
            start = self.path_recipe.text().strip() or str(Path.cwd())
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Selecciona receta",
                start,
                "Recetas (*.yml *.yaml *.json);;Todos (*)",
            )
            if not path:
                return
            recipe_path = Path(path)
            recipe = load_recipe(recipe_path)
            self.path_recipe.setText(str(recipe_path))
            self._apply_recipe_to_controls(recipe)
            self._set_status(f"Receta cargada: {recipe_path}")
            self._save_active_session(silent=True)

        def _menu_save_recipe(self) -> None:
            start = self.path_recipe.text().strip() or str(Path.cwd() / "recipe.yml")
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Guardar receta",
                start,
                "YAML (*.yml *.yaml);;JSON (*.json)",
            )
            if not path:
                return
            out = Path(path)
            recipe = self._build_effective_recipe()
            payload = asdict(recipe)
            out.parent.mkdir(parents=True, exist_ok=True)

            if out.suffix.lower() in {".yaml", ".yml"}:
                out.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            else:
                out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            self.path_recipe.setText(str(out))
            self._set_status(f"Receta guardada: {out}")
            self._save_active_session(silent=True)

        def _menu_reset_recipe(self) -> None:
            self._apply_recipe_to_controls(Recipe())
            self._set_status("Receta restablecida a valores por defecto")
            self._save_active_session(silent=True)

        def _apply_recipe_to_controls(self, recipe: Recipe) -> None:
            self._set_combo_data(self.combo_demosaic, recipe.demosaic_algorithm)
            self._set_combo_data(self.combo_wb_mode, recipe.white_balance_mode)
            self.edit_wb_multipliers.setText(",".join(f"{float(v):.6g}" for v in recipe.wb_multipliers))

            mode, value = self._split_black_mode(recipe.black_level_mode)
            self._set_combo_data(self.combo_black_mode, mode)
            self.spin_black_value.setValue(value)

            self.spin_exposure.setValue(float(recipe.exposure_compensation))

            tone_mode, gamma = self._split_tone_curve(recipe.tone_curve)
            self._set_combo_data(self.combo_tone_curve, tone_mode)
            self.spin_gamma.setValue(gamma)

            self.check_output_linear.setChecked(bool(recipe.output_linear))
            self._set_combo_text(self.combo_recipe_denoise, recipe.denoise)
            self._set_combo_text(self.combo_recipe_sharpen, recipe.sharpen)
            self._set_combo_text(self.combo_working_space, recipe.working_space)
            self._set_combo_text(self.combo_output_space, recipe.output_space)
            self._set_combo_text(self.combo_sampling, recipe.sampling_strategy)
            self.check_profiling_mode.setChecked(bool(recipe.profiling_mode))
            self.edit_input_color.setText(recipe.input_color_assumption)
            self.edit_illuminant.setText(recipe.illuminant_metadata or "")

            if recipe.argyll_colprof_args:
                self._apply_argyll_args_to_controls(recipe.argyll_colprof_args)
            else:
                self._set_combo_data(self.combo_profile_quality, "m")
                self._set_combo_data(self.combo_profile_algo, "-as")
                self.edit_colprof_args.setText("")

        def _split_black_mode(self, value: str) -> tuple[str, int]:
            txt = (value or "metadata").strip().lower()
            if txt.startswith("fixed:"):
                try:
                    return "fixed", int(txt.split(":", 1)[1])
                except Exception:
                    return "fixed", 0
            if txt.startswith("white:"):
                try:
                    return "white", int(txt.split(":", 1)[1])
                except Exception:
                    return "white", 0
            return "metadata", 0

        def _split_tone_curve(self, value: str) -> tuple[str, float]:
            txt = (value or "linear").strip().lower()
            if txt.startswith("gamma:"):
                try:
                    return "gamma", float(txt.split(":", 1)[1])
                except Exception:
                    return "gamma", 2.2
            if txt == "srgb":
                return "srgb", 2.2
            return "linear", 2.2

        def _apply_argyll_args_to_controls(self, args: list[str]) -> None:
            quality = None
            algo = None
            extra: list[str] = []
            for a in args:
                if a.startswith("-q") and len(a) == 3:
                    quality = a[-1]
                elif a in {"-as", "-ag", "-am", "-al", "-ax"}:
                    algo = a
                else:
                    extra.append(a)
            if quality is not None:
                self._set_combo_data(self.combo_profile_quality, quality)
            if algo is not None:
                self._set_combo_data(self.combo_profile_algo, algo)
            self.edit_colprof_args.setText(" ".join(extra))

        def _set_combo_data(self, combo: QtWidgets.QComboBox, data_value: str) -> None:
            for i in range(combo.count()):
                if str(combo.itemData(i)) == str(data_value):
                    combo.setCurrentIndex(i)
                    return
            self._set_combo_text(combo, str(data_value))

        def _set_combo_text(self, combo: QtWidgets.QComboBox, text: str) -> None:
            idx = combo.findText(str(text), QtCore.Qt.MatchFixedString)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        def _build_effective_recipe(self) -> Recipe:
            recipe = Recipe()
            path_text = self.path_recipe.text().strip()
            if path_text:
                p = Path(path_text)
                if p.exists():
                    recipe = load_recipe(p)

            recipe.raw_developer = "dcraw"
            recipe.demosaic_algorithm = str(self.combo_demosaic.currentData() or self.combo_demosaic.currentText())
            recipe.white_balance_mode = str(self.combo_wb_mode.currentData() or self.combo_wb_mode.currentText())
            recipe.wb_multipliers = self._parse_wb_multipliers(self.edit_wb_multipliers.text(), recipe.wb_multipliers)

            black_mode = str(self.combo_black_mode.currentData() or "metadata")
            black_value = int(self.spin_black_value.value())
            if black_mode == "fixed":
                recipe.black_level_mode = f"fixed:{black_value}"
            elif black_mode == "white":
                recipe.black_level_mode = f"white:{black_value}"
            else:
                recipe.black_level_mode = "metadata"

            recipe.exposure_compensation = float(self.spin_exposure.value())
            tone_mode = str(self.combo_tone_curve.currentData() or "linear")
            if tone_mode == "gamma":
                recipe.tone_curve = f"gamma:{float(self.spin_gamma.value()):.3g}"
            else:
                recipe.tone_curve = tone_mode

            recipe.output_linear = bool(self.check_output_linear.isChecked())
            recipe.denoise = self.combo_recipe_denoise.currentText().strip().lower()
            recipe.sharpen = self.combo_recipe_sharpen.currentText().strip().lower()
            recipe.working_space = self.combo_working_space.currentText().strip()
            recipe.output_space = self.combo_output_space.currentText().strip()
            recipe.sampling_strategy = self.combo_sampling.currentText().strip()
            recipe.profiling_mode = bool(self.check_profiling_mode.isChecked())
            recipe.input_color_assumption = self.edit_input_color.text().strip() or "camera_native"
            recipe.illuminant_metadata = self.edit_illuminant.text().strip() or None
            recipe.chart_reference = self.path_reference.text().strip() or None
            recipe.profile_engine = "argyll"
            recipe.argyll_colprof_args = self._build_colprof_args()
            return recipe

        def _build_colprof_args(self) -> list[str]:
            quality = str(self.combo_profile_quality.currentData() or "m")
            algo = str(self.combo_profile_algo.currentData() or "-as")
            args = [f"-q{quality}", algo]
            custom = self.edit_colprof_args.text().strip()
            if custom:
                try:
                    args.extend(shlex.split(custom))
                except Exception:
                    self._log_preview("No se pudieron parsear args extra colprof; se ignoran.")
            return args

        def _parse_wb_multipliers(self, text: str, fallback: list[float]) -> list[float]:
            raw = [p.strip() for p in text.split(",") if p.strip()]
            vals: list[float] = []
            for p in raw:
                try:
                    vals.append(float(p))
                except Exception:
                    continue
            if len(vals) >= 3:
                return vals
            return list(fallback)

        def _normalized_profile_out_path(self) -> Path:
            current = self.path_profile_out.text().strip() or "/tmp/camera_profile_gui.icc"
            ext = self.combo_profile_format.currentText().strip().lower() or ".icc"
            p = Path(current)
            if p.suffix.lower() != ext:
                p = p.with_suffix(ext)
            self.path_profile_out.setText(str(p))
            if hasattr(self, "profile_out_path_edit"):
                self.profile_out_path_edit.setText(str(p))
            return p

        def _preview_cache_key(
            self,
            *,
            selected: Path,
            recipe: Recipe,
            fast_raw: bool,
            max_preview_side: int,
        ) -> str:
            try:
                st = selected.stat()
                stamp = f"{st.st_mtime_ns}:{st.st_size}"
            except Exception:
                stamp = "nostat"

            wb = ",".join(f"{float(v):.6g}" for v in recipe.wb_multipliers)
            recipe_sig = "|".join(
                [
                    recipe.raw_developer,
                    recipe.demosaic_algorithm,
                    recipe.white_balance_mode,
                    recipe.black_level_mode,
                    recipe.tone_curve,
                    f"{float(recipe.exposure_compensation):.3g}",
                    recipe.output_space,
                    wb,
                ]
            )
            return f"{selected}|{stamp}|{int(fast_raw)}|{max_preview_side}|{recipe_sig}"

        def _cache_preview_image(self, key: str, image: np.ndarray) -> None:
            self._preview_cache[key] = image.copy()
            self._preview_cache_order.append(key)
            max_entries = 12
            while len(self._preview_cache_order) > max_entries:
                old = self._preview_cache_order.pop(0)
                self._preview_cache.pop(old, None)

        def _on_load_selected(self) -> None:
            if self._selected_file is None:
                QtWidgets.QMessageBox.information(self, "Info", "Selecciona primero un archivo.")
                return

            selected = self._selected_file
            recipe = self._build_effective_recipe()
            fast_raw = bool(self.check_fast_raw_preview.isChecked())
            max_preview_side = int(self.spin_preview_max_side.value())
            cache_key = self._preview_cache_key(
                selected=selected,
                recipe=recipe,
                fast_raw=fast_raw,
                max_preview_side=max_preview_side,
            )

            cached = self._preview_cache.get(cache_key)
            if cached is not None:
                self._original_linear = cached.copy()
                self._adjusted_linear = self._original_linear.copy()
                self._refresh_preview()
                self._log_preview(f"Preview cargada desde cache: {selected.name}")
                self._set_status(f"Preview en cache: {selected.name}")
                return

            def task():
                return load_image_for_preview(
                    selected,
                    recipe=recipe,
                    fast_raw=fast_raw,
                    max_preview_side=max_preview_side,
                )

            def on_success(payload) -> None:
                image_linear, msg = payload
                self._original_linear = np.asarray(image_linear, dtype=np.float32)
                self._adjusted_linear = self._original_linear.copy()
                self._cache_preview_image(cache_key, self._original_linear)
                self._refresh_preview()
                self._log_preview(msg)

            self._start_background_task("Carga de imagen para preview", task, on_success)

        def _on_slider_change(self) -> None:
            if self._original_linear is not None:
                self._refresh_preview()

        def _reset_adjustments(self) -> None:
            self.slider_sharpen.setValue(0)
            self.slider_radius.setValue(10)
            self.slider_noise_luma.setValue(0)
            self.slider_noise_color.setValue(0)
            if self._original_linear is not None:
                self._refresh_preview()

        def _refresh_preview(self) -> None:
            if self._original_linear is None:
                return
            try:
                nl = 0.0
                nc = 0.0
                sharpen = self.slider_sharpen.value() / 100.0
                radius = self.slider_radius.value() / 10.0

                adjusted = apply_adjustments(
                    self._original_linear,
                    denoise_luminance=nl,
                    denoise_color=nc,
                    sharpen_amount=sharpen,
                    sharpen_radius=radius,
                )
                self._adjusted_linear = adjusted

                original_srgb = linear_to_srgb_display(self._original_linear)
                self.image_original_compare.set_rgb_float_image(original_srgb)

                result_srgb = linear_to_srgb_display(adjusted)
                if self.chk_apply_profile.isChecked() and self.path_profile_active.text().strip():
                    p = Path(self.path_profile_active.text().strip())
                    if p.exists() and p.with_suffix(".profile.json").exists():
                        candidate = apply_profile_preview(adjusted, p)
                        if self._looks_broken_profile_preview(candidate):
                            self._log_preview(
                                "Aviso: preview del perfil ICC parece no fiable "
                                "(dominante/clipping extremo). Se muestra vista sin perfil."
                            )
                        else:
                            result_srgb = candidate
                    else:
                        self._log_preview(
                            f"Aviso: perfil activo sin sidecar valido ({p}). Se muestra vista sin perfil."
                        )

                self._preview_srgb = np.asarray(result_srgb, dtype=np.float32)
                self.image_result_single.set_rgb_float_image(self._preview_srgb)
                self.image_result_compare.set_rgb_float_image(self._preview_srgb)
                self.preview_analysis.setPlainText(preview_analysis_text(self._original_linear, adjusted))
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Aviso", str(exc))

        def _looks_broken_profile_preview(self, image_srgb: np.ndarray) -> bool:
            x = np.clip(np.asarray(image_srgb, dtype=np.float32), 0.0, 1.0)
            if x.ndim != 3 or x.shape[2] < 3:
                return True
            if not np.isfinite(x).all():
                return True

            means = np.mean(x[..., :3], axis=(0, 1))
            clipped_hi = np.mean(x[..., :3] >= 0.995, axis=(0, 1))
            clipped_channels = int(np.count_nonzero(clipped_hi > 0.80))
            chroma_ratio = float((np.max(means) + 1e-6) / (np.min(means) + 1e-6))

            # Heuristic safeguard for clearly wrong matrix/profile assignments.
            return clipped_channels >= 2 and chroma_ratio > 3.5

        def _on_save_preview(self) -> None:
            if self._preview_srgb is None:
                QtWidgets.QMessageBox.information(self, "Info", "No hay preview para guardar.")
                return
            out = Path(self.path_preview_png.text().strip() or "/tmp/iccraw_preview.png")
            out.parent.mkdir(parents=True, exist_ok=True)
            bgr = np.clip(np.round(self._preview_srgb[..., ::-1] * 255.0), 0, 255).astype(np.uint8)
            ok = cv2.imwrite(str(out), bgr)
            if not ok:
                QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo guardar: {out}")
                return
            self._log_preview(f"Preview guardada en: {out}")
            self._set_status(f"Preview guardada: {out}")
            self._save_active_session(silent=True)

        def _on_develop_selected(self) -> None:
            if self._selected_file is None:
                QtWidgets.QMessageBox.information(self, "Info", "Selecciona un archivo para revelar.")
                return

            in_path = self._selected_file
            default_out = str(in_path.with_suffix(".tiff"))
            out_text, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Guardar TIFF revelado",
                default_out,
                "TIFF (*.tif *.tiff)",
            )
            if not out_text:
                return
            out_path = Path(out_text)

            recipe = self._build_effective_recipe()
            use_profile = self.chk_apply_profile.isChecked() and self.path_profile_active.text().strip() != ""
            profile_path = Path(self.path_profile_active.text().strip()) if use_profile else None

            def task():
                with tempfile.TemporaryDirectory(prefix="iccraw_gui_develop_") as tmp:
                    temp_linear = Path(tmp) / "develop_linear.tiff"
                    develop_controlled(in_path, recipe, temp_linear, None)
                    image = read_image(temp_linear)
                    write_profiled_tiff(out_path, image, recipe=recipe, profile_path=profile_path)
                return {"output_tiff": str(out_path)}

            def on_success(payload) -> None:
                self._log_preview(f"TIFF revelado: {payload['output_tiff']}")
                self._set_status(f"Revelado completado: {payload['output_tiff']}")
                self._save_active_session(silent=True)

            self._start_background_task("Revelado a TIFF", task, on_success)

        def _use_current_dir_as_profile_charts(self) -> None:
            self.profile_charts_dir.setText(str(self._current_dir))
            self._selected_chart_files = []
            self._sync_profile_chart_selection_label()
            self._set_status(f"Directorio cartas: {self._current_dir}")
            self._save_active_session(silent=True)

        def _use_selected_files_as_profile_charts(self) -> None:
            files = [
                p for p in self._collect_selected_file_paths()
                if p.suffix.lower() in BROWSABLE_EXTENSIONS
            ]
            if not files:
                QtWidgets.QMessageBox.information(
                    self,
                    "Info",
                    "Selecciona una o más capturas RAW/DNG/TIFF con carta ColorChecker.",
                )
                return
            self._selected_chart_files = sorted(set(files), key=lambda p: str(p))
            parents = {p.parent for p in self._selected_chart_files}
            if len(parents) == 1:
                self.profile_charts_dir.setText(str(next(iter(parents))))
            self._sync_profile_chart_selection_label()
            self._set_status(f"Cartas seleccionadas: {len(self._selected_chart_files)}")
            self._save_active_session(silent=True)

        def _sync_profile_chart_selection_label(self) -> None:
            if not hasattr(self, "profile_chart_selection_label"):
                return
            if not self._selected_chart_files:
                self.profile_chart_selection_label.setText("Cartas: todas las compatibles de la carpeta indicada")
                return
            preview = ", ".join(p.name for p in self._selected_chart_files[:4])
            if len(self._selected_chart_files) > 4:
                preview += f" (+{len(self._selected_chart_files) - 4} más)"
            self.profile_chart_selection_label.setText(
                f"Cartas seleccionadas: {len(self._selected_chart_files)} - {preview}"
            )

        def _profile_chart_files_or_none(self) -> list[Path] | None:
            return list(self._selected_chart_files) if self._selected_chart_files else None

        def _infer_profile_chart_files(self) -> list[Path] | None:
            files = self._profile_chart_files_or_none()
            if files:
                return files

            selected = [
                p for p in self._collect_selected_file_paths()
                if p.suffix.lower() in BROWSABLE_EXTENSIONS
            ]
            if selected:
                self._selected_chart_files = sorted(set(selected), key=lambda p: str(p))
                self._sync_profile_chart_selection_label()
                parents = {p.parent for p in self._selected_chart_files}
                if len(parents) == 1:
                    self.profile_charts_dir.setText(str(next(iter(parents))))
                self._set_status(f"Cartas tomadas de la selección: {len(self._selected_chart_files)}")
                return list(self._selected_chart_files)

            if self._selected_file is not None and self._selected_file.suffix.lower() in BROWSABLE_EXTENSIONS:
                self._selected_chart_files = [self._selected_file]
                self.profile_charts_dir.setText(str(self._selected_file.parent))
                self._sync_profile_chart_selection_label()
                self._set_status(f"Carta tomada del archivo cargado: {self._selected_file.name}")
                return list(self._selected_chart_files)

            return None

        def _manual_detections_for_profile(self, chart_files: list[Path] | None) -> dict[Path, Any] | None:
            if not self._manual_chart_detections:
                return None
            if chart_files:
                selected_keys = {str(p.expanduser().resolve()) for p in chart_files}
                matches = {
                    Path(path): detection
                    for path, detection in self._manual_chart_detections.items()
                    if path in selected_keys
                }
            else:
                matches = {Path(path): detection for path, detection in self._manual_chart_detections.items()}
            return matches or None

        def _directory_has_chart_captures(self, folder: Path) -> bool:
            try:
                return folder.exists() and folder.is_dir() and any(
                    p.is_file() and p.suffix.lower() in BROWSABLE_EXTENSIONS
                    for p in folder.iterdir()
                )
            except Exception:
                return False

        def _use_current_dir_as_batch_input(self) -> None:
            self.batch_input_dir.setText(str(self._current_dir))
            self._set_status(f"Directorio lote: {self._current_dir}")
            self._save_active_session(silent=True)

        def _on_generate_profile(self) -> None:
            charts = Path(self.profile_charts_dir.text().strip())
            chart_capture_files = self._infer_profile_chart_files()
            if chart_capture_files is None and not self._directory_has_chart_captures(charts):
                if self._directory_has_chart_captures(self._current_dir):
                    charts = self._current_dir
                    self.profile_charts_dir.setText(str(charts))
                else:
                    QtWidgets.QMessageBox.information(
                        self,
                        "Sin capturas de carta",
                        "Selecciona una o más miniaturas con carta, carga una carta en el visor o abre una carpeta con capturas RAW/DNG/TIFF.",
                    )
                    return
            manual_detections = self._manual_detections_for_profile(chart_capture_files)
            reference_path = Path(self.path_reference.text().strip())
            profile_out = Path(self.profile_out_path_edit.text().strip())
            ext = self.combo_profile_format.currentText().strip().lower() or ".icc"
            if profile_out.suffix.lower() != ext:
                profile_out = profile_out.with_suffix(ext)
                self.profile_out_path_edit.setText(str(profile_out))
            profile_report = Path(self.profile_report_out.text().strip())
            workdir = Path(self.profile_workdir.text().strip())
            development_profile_out = Path(self.develop_profile_out.text().strip())
            calibrated_recipe_out = Path(self.calibrated_recipe_out.text().strip())
            validation_report_out = profile_report.with_name("qa_session_report.json")
            validation_holdout_count = 1 if self._profile_chart_candidate_count(charts, chart_capture_files) >= 2 else 0
            chart_type = self.profile_chart_type.currentText()
            min_confidence = float(self.profile_min_conf.value())
            allow_fallback_detection = bool(self.profile_allow_fallback.isChecked())
            camera = self.profile_camera.text().strip() or None
            lens = self.profile_lens.text().strip() or None
            recipe = self._build_effective_recipe()

            # Sync profile output path with RAW tab profile controls.
            self.path_profile_out.setText(str(profile_out))

            def task():
                reference = ReferenceCatalog.from_path(reference_path)
                return auto_generate_profile_from_charts(
                    chart_captures_dir=charts,
                    chart_capture_files=chart_capture_files,
                    recipe=recipe,
                    reference=reference,
                    profile_out=profile_out,
                    profile_report_out=profile_report,
                    validation_report_out=validation_report_out,
                    work_dir=workdir,
                    development_profile_out=development_profile_out,
                    calibrated_recipe_out=calibrated_recipe_out,
                    calibrate_development=True,
                    chart_type=chart_type,
                    min_confidence=min_confidence,
                    allow_fallback_detection=allow_fallback_detection,
                    camera_model=camera,
                    lens_model=lens,
                    manual_detections=manual_detections,
                    validation_holdout_count=validation_holdout_count,
                )

            def on_success(payload) -> None:
                self.profile_output.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
                profile_status = payload.get("profile_status") if isinstance(payload.get("profile_status"), dict) else {}
                status = str(profile_status.get("status") or "draft")
                if status not in {"rejected", "expired"}:
                    self.path_profile_active.setText(str(profile_out))
                else:
                    self.path_profile_active.clear()
                    self._log_preview(f"Perfil no activado por estado: {status}")
                if payload.get("calibrated_recipe_path"):
                    calibrated_recipe_path = Path(str(payload["calibrated_recipe_path"]))
                    self.path_recipe.setText(str(calibrated_recipe_path))
                    try:
                        self._apply_recipe_to_controls(load_recipe(calibrated_recipe_path))
                    except Exception as exc:
                        self._log_preview(f"No se pudo cargar receta calibrada en la GUI: {exc}")
                if hasattr(self, "profile_summary_label"):
                    self.profile_summary_label.setText(self._profile_success_summary(payload, profile_out))
                self._log_preview(f"Perfil de revelado: {payload.get('development_profile_path')}")
                self._log_preview(f"Perfil ICC generado: {profile_out}")
                self._set_status(f"Revelado calibrado + ICC generado: {profile_out}")
                self._save_active_session(silent=True)

            self._start_background_task("Generación de perfil de revelado + ICC", task, on_success)

        def _profile_chart_candidate_count(self, charts: Path, chart_capture_files: list[Path] | None) -> int:
            if chart_capture_files is not None:
                return len(chart_capture_files)
            try:
                return sum(
                    1
                    for p in charts.iterdir()
                    if p.is_file() and p.suffix.lower() in BROWSABLE_EXTENSIONS
                )
            except Exception:
                return 0

        def _profile_success_summary(self, payload: dict[str, Any], profile_out: Path) -> str:
            profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
            error_summary = profile.get("error_summary") if isinstance(profile.get("error_summary"), dict) else {}
            de00 = error_summary.get("mean_delta_e2000")
            max_de00 = error_summary.get("max_delta_e2000")
            profile_status = payload.get("profile_status") if isinstance(payload.get("profile_status"), dict) else {}
            status = str(profile_status.get("status") or "draft")
            parts = [
                f"Estado perfil: {status}",
                f"Perfil generado: {profile_out}",
                f"Entrenamiento: {payload.get('chart_captures_used', 0)}/{payload.get('training_captures_total', payload.get('chart_captures_total', 0))}",
                f"Receta calibrada: {payload.get('calibrated_recipe_path') or 'no generada'}",
            ]
            if isinstance(de00, (int, float)) and isinstance(max_de00, (int, float)):
                parts.append(f"DeltaE2000 entrenamiento: media {float(de00):.2f}, max {float(max_de00):.2f}")
            validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else None
            if validation:
                qa = validation.get("qa_report") if isinstance(validation.get("qa_report"), dict) else {}
                v_error = qa.get("validation_error_summary") if isinstance(qa.get("validation_error_summary"), dict) else {}
                status = qa.get("status", "sin_estado")
                parts.append(
                    f"Validación: {validation.get('validation_captures_used', 0)}/"
                    f"{validation.get('validation_captures_total', 0)} ({status})"
                )
                mean_val = v_error.get("mean_delta_e2000")
                max_val = v_error.get("max_delta_e2000")
                if isinstance(mean_val, (int, float)) and isinstance(max_val, (int, float)):
                    parts.append(f"DeltaE2000 validación: media {float(mean_val):.2f}, max {float(max_val):.2f}")
                checks = qa.get("checks") if isinstance(qa.get("checks"), list) else []
                failed_warnings = [
                    str(check.get("id"))
                    for check in checks
                    if isinstance(check, dict)
                    and check.get("severity") == "warning"
                    and check.get("passed") is False
                ]
                if failed_warnings:
                    parts.append(f"QA captura: {len(failed_warnings)} avisos ({', '.join(failed_warnings[:3])})")
            skipped = payload.get("chart_captures_skipped")
            if isinstance(skipped, list) and skipped:
                parts.append(f"Avisos/omisiones: {len(skipped)}")
            return "\n".join(parts)

        def _start_manual_chart_marking(self) -> None:
            if self._original_linear is None:
                QtWidgets.QMessageBox.information(self, "Info", "Carga primero la captura de carta en el visor.")
                return
            self._manual_chart_marking = True
            self._manual_chart_points = []
            self._sync_manual_chart_overlay()
            self._set_status("Marcado manual activo: selecciona 4 esquinas en el visor")

        def _clear_manual_chart_points(self) -> None:
            self._manual_chart_marking = False
            self._manual_chart_points = []
            self._sync_manual_chart_overlay()
            self._set_status("Marcado manual limpiado")

        def _on_manual_chart_click(self, x: float, y: float) -> None:
            if not self._manual_chart_marking:
                return
            if len(self._manual_chart_points) >= 4:
                self._manual_chart_points = []
            self._manual_chart_points.append((float(x), float(y)))
            if len(self._manual_chart_points) == 4:
                self._manual_chart_marking = False
                self._set_status("Cuatro esquinas marcadas; revisa y guarda la detección")
            else:
                self._set_status(f"Punto {len(self._manual_chart_points)}/4 marcado")
            self._sync_manual_chart_overlay()

        def _sync_manual_chart_overlay(self) -> None:
            if hasattr(self, "manual_chart_points_label"):
                if self._manual_chart_points:
                    coords = " | ".join(f"{idx}:{x:.0f},{y:.0f}" for idx, (x, y) in enumerate(self._manual_chart_points, start=1))
                    self.manual_chart_points_label.setText(f"Puntos: {len(self._manual_chart_points)}/4 - {coords}")
                else:
                    self.manual_chart_points_label.setText("Puntos: 0/4")
            if hasattr(self, "image_result_single"):
                self.image_result_single.set_overlay_points(self._manual_chart_points)
            if hasattr(self, "image_result_compare"):
                self.image_result_compare.set_overlay_points(self._manual_chart_points)

        def _save_manual_chart_detection(self) -> None:
            if self._selected_file is None:
                QtWidgets.QMessageBox.information(self, "Info", "Selecciona primero una captura de carta.")
                return
            if self._original_linear is None:
                QtWidgets.QMessageBox.information(self, "Info", "Carga primero la captura de carta en el visor.")
                return
            if len(self._manual_chart_points) != 4:
                QtWidgets.QMessageBox.information(self, "Info", "Marca exactamente 4 esquinas antes de guardar.")
                return

            workdir = Path(self.profile_workdir.text().strip() or "/tmp/iccraw_profile_work")
            default_dir = workdir / "manual_detections"
            default_dir.mkdir(parents=True, exist_ok=True)
            default_path = default_dir / f"{self._selected_file.stem}.manual_detection.json"
            out_text, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Guardar detección manual",
                str(default_path),
                "JSON (*.json)",
            )
            if not out_text:
                return

            selected = self._selected_file
            points_preview = list(self._manual_chart_points)
            preview_h, preview_w = self._original_linear.shape[:2]
            out_json = Path(out_text)
            chart_type = self.profile_chart_type.currentText()
            recipe = self._build_effective_recipe()

            def task():
                out_json.parent.mkdir(parents=True, exist_ok=True)
                overlay_path = out_json.with_name(f"{out_json.stem}.overlay.png")
                if selected.suffix.lower() in RAW_EXTENSIONS:
                    target_image = out_json.with_name(f"{out_json.stem}.developed.tiff")
                    develop_controlled(selected, recipe, target_image, None)
                else:
                    target_image = selected

                full_image = read_image(target_image)
                full_h, full_w = full_image.shape[:2]
                sx = full_w / max(1, preview_w)
                sy = full_h / max(1, preview_h)
                corners = [(x * sx, y * sy) for x, y in points_preview]
                detection = detect_chart_from_corners(target_image, corners=corners, chart_type=chart_type)
                write_json(out_json, detection)
                draw_detection_overlay(target_image, detection, overlay_path)
                return {
                    "detection_json": str(out_json),
                    "overlay": str(overlay_path),
                    "image": str(target_image),
                    "corners": corners,
                    "source_raw": str(selected),
                    "detection": to_json_dict(detection),
                }

            def on_success(payload) -> None:
                self.profile_output.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
                source = Path(str(payload["source_raw"])).expanduser().resolve()
                self._manual_chart_detections[str(source)] = payload["detection"]
                if source not in {p.expanduser().resolve() for p in self._selected_chart_files}:
                    self._selected_chart_files.append(source)
                    self._selected_chart_files = sorted(set(self._selected_chart_files), key=lambda p: str(p))
                    self._sync_profile_chart_selection_label()
                self.profile_charts_dir.setText(str(source.parent))
                self._log_preview(f"Detección manual guardada: {payload['detection_json']}")
                self._set_status(f"Detección manual asociada a carta: {source.name}")

            self._start_background_task("Detección manual de carta", task, on_success)

        def _collect_selected_file_paths(self) -> list[Path]:
            files: list[Path] = []
            for item in self.file_list.selectedItems():
                value = item.data(QtCore.Qt.UserRole)
                if not value:
                    continue
                p = Path(str(value))
                if p.exists() and p.is_file() and p.suffix.lower() in BROWSABLE_EXTENSIONS:
                    files.append(p)
            files.sort()
            return files

        def _on_batch_develop_selected(self) -> None:
            files = self._collect_selected_file_paths()
            if not files:
                QtWidgets.QMessageBox.information(self, "Info", "Selecciona uno o más archivos para el lote.")
                return
            self._start_batch_develop(files, "Lote desde selección")

        def _on_batch_develop_directory(self) -> None:
            folder = Path(self.batch_input_dir.text().strip())
            if not folder.exists() or not folder.is_dir():
                QtWidgets.QMessageBox.information(self, "Info", f"Directorio inválido: {folder}")
                return
            files = [
                p for p in sorted(folder.iterdir())
                if p.is_file() and p.suffix.lower() in BROWSABLE_EXTENSIONS
            ]
            if not files:
                QtWidgets.QMessageBox.information(self, "Info", "No hay RAW/imagenes compatibles en el directorio.")
                return
            self._start_batch_develop(files, "Lote desde directorio")

        def _process_batch_files(
            self,
            *,
            files: list[Path],
            out_dir: Path,
            recipe: Recipe,
            apply_adjust: bool,
            use_profile: bool,
            profile_path: Path | None,
            denoise_luma: float,
            denoise_color: float,
            sharpen_amount: float,
            sharpen_radius: float,
        ) -> dict[str, Any]:
            out_dir.mkdir(parents=True, exist_ok=True)
            outputs: list[dict[str, str]] = []
            errors: list[dict[str, str]] = []

            with tempfile.TemporaryDirectory(prefix="iccraw_gui_batch_") as tmp:
                tmpdir = Path(tmp)
                if profile_path is not None and not profile_path.exists():
                    raise RuntimeError(f"No existe perfil ICC activo: {profile_path}")

                for idx, src in enumerate(files, start=1):
                    try:
                        if src.suffix.lower() in RAW_EXTENSIONS:
                            temp_linear = tmpdir / f"{idx:04d}_{src.stem}.tiff"
                            develop_controlled(src, recipe, temp_linear, None)
                            image = read_image(temp_linear)
                        else:
                            image = read_image(src)

                        if apply_adjust:
                            image = apply_adjustments(
                                image,
                                denoise_luminance=denoise_luma,
                                denoise_color=denoise_color,
                                sharpen_amount=sharpen_amount,
                                sharpen_radius=sharpen_radius,
                            )

                        out_path = out_dir / f"{src.stem}.tiff"
                        write_profiled_tiff(
                            out_path,
                            image,
                            recipe=recipe,
                            profile_path=profile_path if use_profile else None,
                        )
                        outputs.append({"source": str(src), "output": str(out_path)})
                    except Exception as exc:
                        errors.append({"source": str(src), "error": str(exc)})

            return {
                "input_files": len(files),
                "output_dir": str(out_dir),
                "outputs": outputs,
                "errors": errors,
            }

        def _start_batch_develop(self, files: list[Path], task_label: str) -> None:
            out_dir = Path(self.batch_out_dir.text().strip())
            recipe = self._build_effective_recipe()
            apply_adjust = bool(self.batch_apply_adjustments.isChecked())
            use_profile = bool(self.batch_embed_profile.isChecked()) and self.path_profile_active.text().strip() != ""
            profile_path = Path(self.path_profile_active.text().strip()) if use_profile else None

            nl = 0.0
            nc = 0.0
            sharpen = self.slider_sharpen.value() / 100.0
            radius = self.slider_radius.value() / 10.0

            def task():
                payload = self._process_batch_files(
                    files=files,
                    out_dir=out_dir,
                    recipe=recipe,
                    apply_adjust=apply_adjust,
                    use_profile=use_profile,
                    profile_path=profile_path,
                    denoise_luma=nl,
                    denoise_color=nc,
                    sharpen_amount=sharpen,
                    sharpen_radius=radius,
                )
                payload["task"] = task_label
                return payload

            def on_success(payload) -> None:
                self.batch_output.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
                ok_count = len(payload.get("outputs", []))
                error_count = len(payload.get("errors", []))
                self._log_preview(
                    f"Lote finalizado: {ok_count}/{payload['input_files']} completados "
                    f"({error_count} errores)"
                )
                self._set_status(
                    f"Lote finalizado en {payload['output_dir']} "
                    f"(OK={ok_count}, errores={error_count})"
                )
                self._save_active_session(silent=True)

            self._start_background_task(task_label, task, on_success)

        def _use_generated_profile_as_active(self) -> None:
            p = self._normalized_profile_out_path()
            if not p.exists():
                QtWidgets.QMessageBox.information(self, "Info", "El perfil de salida aun no existe.")
                return
            self.path_profile_active.setText(str(p))
            recipe_path = Path(self.calibrated_recipe_out.text().strip())
            if recipe_path.exists():
                self.path_recipe.setText(str(recipe_path))
                try:
                    self._apply_recipe_to_controls(load_recipe(recipe_path))
                except Exception as exc:
                    self._log_preview(f"No se pudo activar receta calibrada: {exc}")
            self._set_status(f"Perfil activo: {p}")
            self._save_active_session(silent=True)

        def _start_background_task(self, label: str, task, on_success) -> None:
            self._set_status(f"Ejecutando: {label}")
            task_row = self._monitor_task_start(label)
            thread = TaskThread(task)
            self._threads.append(thread)

            def cleanup() -> None:
                if thread in self._threads:
                    self._threads.remove(thread)
                thread.deleteLater()

            def ok(payload) -> None:
                try:
                    on_success(payload)
                    self._set_status(f"Completado: {label}")
                    self._monitor_task_finish(task_row, "Completado", "OK")
                finally:
                    cleanup()

            def fail(trace: str) -> None:
                cleanup()
                self._log_preview(trace[-1200:])
                self._set_status(f"Error en: {label}")
                self._monitor_task_finish(task_row, "Error", trace.strip().splitlines()[-1] if trace.strip() else "Error")
                QtWidgets.QMessageBox.critical(self, "Error", trace[-4000:])

            thread.succeeded.connect(ok)
            thread.failed.connect(fail)
            thread.start()

        def _log_preview(self, text: str) -> None:
            self.preview_log.appendPlainText(text)
            self.monitor_log.appendPlainText(text)

        def _monitor_task_start(self, label: str) -> int:
            self._task_counter += 1
            self._active_tasks += 1

            row = self.monitor_tasks.rowCount()
            self.monitor_tasks.insertRow(row)
            self.monitor_tasks.setItem(row, 0, QtWidgets.QTableWidgetItem(str(self._task_counter)))
            self.monitor_tasks.setItem(row, 1, QtWidgets.QTableWidgetItem(label))
            self.monitor_tasks.setItem(row, 2, QtWidgets.QTableWidgetItem("En curso"))
            self.monitor_tasks.setItem(row, 3, QtWidgets.QTableWidgetItem(""))
            self.monitor_tasks.scrollToBottom()

            self.monitor_status_label.setText(f"Ejecutando: {label}")
            self.monitor_progress.setRange(0, 0)
            return row

        def _monitor_task_finish(self, row: int, status: str, detail: str) -> None:
            self._active_tasks = max(0, self._active_tasks - 1)
            self.monitor_tasks.setItem(row, 2, QtWidgets.QTableWidgetItem(status))
            self.monitor_tasks.setItem(row, 3, QtWidgets.QTableWidgetItem(detail))
            self.monitor_tasks.scrollToBottom()

            if self._active_tasks == 0:
                self.monitor_progress.setRange(0, 1)
                self.monitor_progress.setValue(1 if status == "Completado" else 0)
                self.monitor_status_label.setText("Sin tareas en ejecución")

        def _set_status(self, text: str) -> None:
            self.statusBar().showMessage(text, 8000)


def main(argv: list[str] | None = None) -> int:
    if QtWidgets is None:
        print(
            "ERROR: Dependencia de GUI no disponible. Instala PySide6 con: pip install -e .[gui]",
            file=sys.stderr,
        )
        return 2

    app = QtWidgets.QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("ICCRAW")
    app.setOrganizationName("ICCRAW")
    win = ICCRawMainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
