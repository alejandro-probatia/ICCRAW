from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
import time
import traceback
from typing import Any
import warnings

import cv2
import numpy as np
from PIL import Image, ImageOps
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

from .chart.detection import detect_chart_from_corners_array, draw_detection_overlay_array
from .chart.sampling import ReferenceCatalog
from .core.models import Recipe, to_json_dict, write_json
from .core.recipe import load_recipe, save_recipe
from .core.utils import RAW_EXTENSIONS, read_image, versioned_output_path, write_tiff16
from .display_color import (
    detect_system_display_profile,
    display_profile_label,
    srgb_to_display_u8,
    srgb_u8_to_display_u8,
)
from .metadata_viewer import inspect_file_metadata, metadata_display_sections, metadata_sections_text
from .profile.export import (
    _resolve_batch_workers as resolve_batch_workers,
    profile_path_for_render_settings,
    write_signed_profiled_tiff,
)
from .profile.generic import ensure_generic_output_profile, generic_output_profile, is_generic_output_space
from .provenance.c2pa import C2PASignConfig, DEFAULT_TIMESTAMP_URL, auto_c2pa_config
from .provenance.nexoraw_proof import (
    NexoRawProofConfig,
    generate_ed25519_identity,
    proof_config_from_environment,
)
from .qa_compare import compare_qa_reports
from .raw.pipeline import (
    develop_image_array,
    is_libraw_demosaic_supported,
    rawpy_feature_flags,
    unavailable_demosaic_reason,
)
from .raw.preview import (
    apply_adjustments,
    apply_render_adjustments,
    apply_profile_preview,
    estimate_temperature_tint_from_neutral_sample,
    extract_embedded_preview,
    linear_to_srgb_display,
    load_image_for_preview,
    normalize_tone_curve_points,
    preview_analysis_text,
    tone_curve_lut,
)
from .reporting import check_amaze_backend, check_external_tools
from .session import create_session, ensure_session_structure, load_session, save_session, session_file_path
from .sidecar import load_raw_sidecar, raw_sidecar_path, write_raw_sidecar
from .update import auto_update, check_latest_release
from .version import __version__
from .workflow import auto_generate_profile_from_charts

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:  # pragma: no cover - entorno sin GUI
    QtCore = None
    QtGui = None
    QtWidgets = None


IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}
BROWSABLE_EXTENSIONS = RAW_EXTENSIONS.union(IMAGE_EXTENSIONS)
PROFILE_CHART_EXTENSIONS = RAW_EXTENSIONS.union({".tif", ".tiff"})
PROFILE_REFERENCE_FORBIDDEN_DIRS = {
    "exports": "exportaciones TIFF",
    "work": "intermedios de trabajo",
    "profiles": "perfiles ICC",
    "config": "configuracion",
}

LAYOUT_VERSION = 4
APP_NAME = "NexoRAW"
ORG_NAME = "NexoRAW"
APP_ICON_RESOURCE = "icons/nexoraw-icon.png"
PROJECT_DIRECTOR_NAME = os.environ.get("NEXORAW_PROJECT_DIRECTOR", "Alejandro Probatia").strip() or "Alejandro Probatia"
DEFAULT_THUMBNAIL_SIZE = 132
MIN_THUMBNAIL_SIZE = 72
MAX_THUMBNAIL_SIZE = 220
PREVIEW_CACHE_MAX_ENTRIES = 8
PREVIEW_CACHE_MAX_BYTES = 384 * 1024 * 1024
PREVIEW_DISK_CACHE_MAX_ENTRIES = 48
PREVIEW_DISK_CACHE_MAX_BYTES = 2 * 1024 * 1024 * 1024
THUMBNAIL_CACHE_MAX_ENTRIES = 512
THUMBNAIL_DISK_CACHE_MAX_ENTRIES = 4096
THUMBNAIL_DISK_CACHE_MAX_BYTES = 512 * 1024 * 1024
THUMBNAIL_DISK_PRUNE_INTERVAL_WRITES = 512
THUMBNAIL_BATCH_SIZE = 48
THUMBNAIL_PREFETCH_MARGIN_PAGES = 2
PREVIEW_REFRESH_DEBOUNCE_MS = 120
PREVIEW_REFRESH_THROTTLE_MS = 65
PREVIEW_AUTO_BASE_MAX_SIDE = 2600
PREVIEW_INTERACTIVE_MAX_SIDE = 1200
PREVIEW_INTERACTIVE_DRAG_MAX_SIDE = 720
PREVIEW_INTERACTIVE_TONAL_MAX_SIDE = 560
PREVIEW_PRECISION_MIN_MAX_SIDE = 6000
PREVIEW_PROFILE_CACHE_MAX_ENTRIES = 8
PREVIEW_PROFILE_APPLY_MAX_SIDE = 1400
PREVIEW_INTERACTIVE_BYPASS_DISPLAY_ICC_ENV = "NEXORAW_PREVIEW_INTERACTIVE_BYPASS_DISPLAY_ICC"
LEGACY_PREVIEW_INTERACTIVE_BYPASS_DISPLAY_ICC_ENV = "ICCRAW_PREVIEW_INTERACTIVE_BYPASS_DISPLAY_ICC"
IMAGE_PANEL_BACKGROUND = "#2b2b2b"
IMAGE_PANEL_BORDER = "#5a5a5a"
IMAGE_PANEL_TEXT = "#e6e6e6"
VIEWER_HISTOGRAM_MAX_SAMPLE_PIXELS = 320000
VIEWER_HISTOGRAM_SHADOW_CLIP_U8 = 1
VIEWER_HISTOGRAM_HIGHLIGHT_CLIP_U8 = 254
VIEWER_HISTOGRAM_CLIP_ALERT_RATIO = 5e-4
LEGACY_PROJECT_DIR_RENAMES = {
    "charts": Path("01_ORG"),
    "raw": Path("01_ORG"),
    "exports": Path("02_DRV"),
    "config": Path("00_configuraciones"),
    "profiles": Path("00_configuraciones") / "profiles",
    "work": Path("00_configuraciones") / "work",
}


def _app_icon_path() -> Path | None:
    try:
        path = resources.files("iccraw.resources").joinpath(APP_ICON_RESOURCE)
    except Exception:
        return None
    if not path.is_file():
        return None
    return Path(str(path))


def _app_icon() -> QtGui.QIcon:
    if QtGui is None:
        raise RuntimeError("PySide6 no esta disponible")
    path = _app_icon_path()
    if path is None:
        return QtGui.QIcon()
    return QtGui.QIcon(str(path))


def _env_flag(primary: str, legacy: str, *, default: bool) -> bool:
    raw = str(
        (os.environ.get(primary, "").strip() or os.environ.get(legacy, "").strip())
    ).strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)

DEMOSAIC_OPTIONS = [
    ("DCB (LibRaw, alta calidad)", "dcb"),
    ("DHT", "dht"),
    ("AHD", "ahd"),
    ("AAHD", "aahd"),
    ("VNG", "vng"),
    ("PPG", "ppg"),
    ("Lineal", "linear"),
    ("AMaZE (GPL3)", "amaze"),
]
PREVIEW_BALANCED_DEMOSAIC_ORDER = ("dcb", "ahd", "dht", "aahd", "ppg", "vng", "linear")

ILLUMINANT_OPTIONS = [
    ("A / tungsteno (2856 K)", 2856, 0),
    ("D50 (5003 K)", 5003, 0),
    ("D55 (5503 K)", 5503, 0),
    ("Flash / D55 (5500 K)", 5500, 0),
    ("D60 (6000 K)", 6000, 0),
    ("D65 (6504 K)", 6504, 0),
    ("D75 (7504 K)", 7504, 0),
    ("Personalizado", None, None),
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

TONE_CURVE_PRESETS: list[tuple[str, str, list[tuple[float, float]]]] = [
    ("Lineal", "linear", [(0.0, 0.0), (1.0, 1.0)]),
    ("Contraste suave", "soft_contrast", [(0.0, 0.0), (0.24, 0.18), (0.50, 0.50), (0.76, 0.84), (1.0, 1.0)]),
    ("Similar a película", "film_like", [(0.0, 0.0), (0.06, 0.015), (0.22, 0.18), (0.52, 0.66), (0.82, 0.92), (1.0, 1.0)]),
    ("Sombras levantadas", "lift_shadows", [(0.0, 0.0), (0.14, 0.20), (0.45, 0.50), (0.78, 0.82), (1.0, 1.0)]),
    ("Alto contraste", "high_contrast", [(0.0, 0.0), (0.18, 0.09), (0.50, 0.50), (0.82, 0.93), (1.0, 1.0)]),
    ("Personalizada", "custom", [(0.0, 0.0), (1.0, 1.0)]),
]

SPACE_OPTIONS = [
    "scene_linear_camera_rgb",
    "srgb",
    "adobe_rgb",
    "prophoto_rgb",
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

LEGACY_TEMP_OUTPUT_NAMES = {
    "camera_profile.icc",
    "camera_profile_gui.icc",
    "profile_report_gui.json",
    "iccraw_profile_work",
    "nexoraw_profile_work",
    "development_profile_gui.json",
    "recipe_calibrated_gui.yml",
    "iccraw_preview.png",
    "nexoraw_preview.png",
    "iccraw_batch_tiffs",
    "nexoraw_batch_tiffs",
}

SETTINGS_DIR_ENV = "NEXORAW_SETTINGS_DIR"
LEGACY_SETTINGS_DIR_ENV = "ICCRAW_SETTINGS_DIR"


if QtWidgets is not None:
    def _make_app_settings() -> QtCore.QSettings:
        settings_dir = os.environ.get(SETTINGS_DIR_ENV, "").strip() or os.environ.get(
            LEGACY_SETTINGS_DIR_ENV, ""
        ).strip()
        if settings_dir:
            base = Path(settings_dir).expanduser()
            base.mkdir(parents=True, exist_ok=True)
            QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, str(base))
            return QtCore.QSettings(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, ORG_NAME, APP_NAME)
        return QtCore.QSettings(ORG_NAME, APP_NAME)


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


    class CollapsibleToolPanel(QtWidgets.QScrollArea):
        def __init__(self) -> None:
            super().__init__()
            self.setWidgetResizable(True)
            self.setFrameShape(QtWidgets.QFrame.NoFrame)
            self._items: list[dict[str, Any]] = []

            self._content = QtWidgets.QWidget()
            self._layout = QtWidgets.QVBoxLayout(self._content)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(6)
            self._layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
            self._layout.addStretch(1)
            self.setWidget(self._content)

        def addItem(self, widget: QtWidgets.QWidget, title: str, expanded: bool = True) -> int:  # noqa: N802
            section = QtWidgets.QFrame()
            section.setFrameShape(QtWidgets.QFrame.StyledPanel)
            section.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

            section_layout = QtWidgets.QVBoxLayout(section)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(0)
            section_layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)

            header = QtWidgets.QToolButton()
            header.setText(title)
            header.setCheckable(True)
            header.setChecked(bool(expanded))
            header.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            header.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
            header.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            header.setStyleSheet(
                "QToolButton {"
                "text-align: left;"
                "font-weight: 600;"
                "padding: 5px 6px;"
                "border: 0;"
                "}"
            )

            body = QtWidgets.QWidget()
            body_layout = QtWidgets.QVBoxLayout(body)
            body_layout.setContentsMargins(8, 8, 8, 8)
            body_layout.setSpacing(6)
            body_layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
            body_layout.addWidget(widget)
            body.setVisible(bool(expanded))
            body.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

            def toggle(
                checked: bool,
                *,
                section_widget=section,
                body_widget=body,
                button=header,
            ) -> None:
                button.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
                self._set_section_expanded(section_widget, body_widget, button, bool(checked))

            header.toggled.connect(toggle)
            section_layout.addWidget(header)
            section_layout.addWidget(body)

            self._layout.insertWidget(max(0, self._layout.count() - 1), section)
            self._items.append({"title": title, "header": header, "body": body, "widget": widget, "section": section})
            self._set_section_expanded(section, body, header, bool(expanded))
            return len(self._items) - 1

        def count(self) -> int:
            return len(self._items)

        def itemText(self, index: int) -> str:  # noqa: N802
            if index < 0 or index >= len(self._items):
                return ""
            return str(self._items[index]["title"])

        def indexOf(self, title: str) -> int:  # noqa: N802
            for index, item in enumerate(self._items):
                if str(item["title"]) == title:
                    return index
            return -1

        def setCurrentIndex(self, index: int) -> None:  # noqa: N802
            self.setItemExpanded(index, True)

        def setItemExpanded(self, index: int, expanded: bool) -> None:  # noqa: N802
            if index < 0 or index >= len(self._items):
                return
            header = self._items[index]["header"]
            header.setChecked(bool(expanded))
            if expanded:
                section = self._items[index]["section"]
                QtCore.QTimer.singleShot(0, lambda: self.ensureWidgetVisible(section, 0, 24))

        def isItemExpanded(self, index: int) -> bool:  # noqa: N802
            if index < 0 or index >= len(self._items):
                return False
            return bool(self._items[index]["header"].isChecked())

        def _set_section_expanded(
            self,
            section: QtWidgets.QFrame,
            body: QtWidgets.QWidget,
            header: QtWidgets.QToolButton,
            expanded: bool,
        ) -> None:
            body.setVisible(expanded)
            if expanded:
                section.setMinimumHeight(0)
                section.setMaximumHeight(16777215)
            else:
                collapsed_height = header.sizeHint().height() + 2 * section.frameWidth()
                section.setMinimumHeight(collapsed_height)
                section.setMaximumHeight(collapsed_height)
            body.updateGeometry()
            section.updateGeometry()
            self._content.updateGeometry()
            QtCore.QTimer.singleShot(0, self._content.adjustSize)


    class ToneCurveEditor(QtWidgets.QWidget):
        pointsChanged = QtCore.Signal(object)
        interactionFinished = QtCore.Signal()

        def __init__(self) -> None:
            super().__init__()
            self._points = normalize_tone_curve_points([(0.0, 0.0), (1.0, 1.0)])
            self._drag_index: int | None = None
            self._histogram: np.ndarray | None = None
            self._black_point = 0.0
            self._white_point = 1.0
            self.setMinimumHeight(320)
            self.setMouseTracking(True)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        def hasHeightForWidth(self) -> bool:  # noqa: N802
            return True

        def heightForWidth(self, width: int) -> int:  # noqa: N802
            return int(np.clip(width, 300, 460))

        def sizeHint(self) -> QtCore.QSize:  # noqa: N802
            return QtCore.QSize(340, 340)

        def points(self) -> list[tuple[float, float]]:
            return list(self._points)

        def set_points(self, points: list[tuple[float, float]], *, emit: bool = True) -> None:
            self._points = normalize_tone_curve_points(points)
            self._drag_index = None
            self.update()
            if emit:
                self.pointsChanged.emit(self.points())

        def set_input_range(self, black_point: float, white_point: float) -> None:
            black = float(np.clip(black_point, 0.0, 0.95))
            white = float(np.clip(white_point, black + 0.01, 1.0))
            self._black_point = black
            self._white_point = white
            self.update()

        def set_histogram_from_image(self, image_linear_rgb: np.ndarray | None) -> None:
            if image_linear_rgb is None:
                self._histogram = None
                self.update()
                return
            rgb = np.clip(np.asarray(image_linear_rgb, dtype=np.float32), 0.0, 1.0)
            if rgb.ndim != 3 or rgb.shape[2] < 3:
                self._histogram = None
                self.update()
                return
            weights = np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
            luminance = np.sum(rgb[..., :3] * weights.reshape((1, 1, 3)), axis=2)
            hist, _ = np.histogram(luminance, bins=64, range=(0.0, 1.0))
            hist = hist.astype(np.float32)
            maxv = float(np.max(hist)) if hist.size else 0.0
            self._histogram = hist / maxv if maxv > 0.0 else None
            self.update()

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            rect = self._plot_rect()
            painter.fillRect(self.rect(), QtGui.QColor("#2b2b2b"))
            painter.fillRect(rect, QtGui.QColor("#242424"))

            grid_pen = QtGui.QPen(QtGui.QColor("#505050"), 1)
            painter.setPen(grid_pen)
            for i in range(6):
                x = rect.left() + rect.width() * i / 5.0
                y = rect.top() + rect.height() * i / 5.0
                painter.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
                painter.drawLine(QtCore.QPointF(rect.left(), y), QtCore.QPointF(rect.right(), y))

            if self._histogram is not None:
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(QtGui.QColor(110, 110, 110, 110))
                bin_w = rect.width() / max(1, len(self._histogram))
                for idx, value in enumerate(self._histogram):
                    h = rect.height() * float(value)
                    painter.drawRect(QtCore.QRectF(rect.left() + idx * bin_w, rect.bottom() - h, bin_w + 1, h))

            diagonal_pen = QtGui.QPen(QtGui.QColor("#8a8a8a"), 1, QtCore.Qt.DashLine)
            painter.setPen(diagonal_pen)
            painter.drawLine(self._domain_point_to_widget(0.0, 0.0), self._domain_point_to_widget(1.0, 1.0))

            range_pen = QtGui.QPen(QtGui.QColor("#bdbdbd"), 1, QtCore.Qt.DotLine)
            painter.setPen(range_pen)
            painter.drawLine(
                self._domain_point_to_widget(self._black_point, 0.0),
                self._domain_point_to_widget(self._black_point, 1.0),
            )
            painter.drawLine(
                self._domain_point_to_widget(self._white_point, 0.0),
                self._domain_point_to_widget(self._white_point, 1.0),
            )

            curve_pen = QtGui.QPen(QtGui.QColor("#d9d9d9"), 2)
            painter.setPen(curve_pen)
            curve_x, curve_y = tone_curve_lut(
                self._points,
                lut_size=256,
                black_point=self._black_point,
                white_point=self._white_point,
            )
            path = QtGui.QPainterPath(self._domain_point_to_widget(float(curve_x[0]), float(curve_y[0])))
            for x, y in zip(curve_x[1:], curve_y[1:]):
                path.lineTo(self._domain_point_to_widget(float(x), float(y)))
            painter.drawPath(path)

            painter.setBrush(QtGui.QBrush(QtGui.QColor("#d9d9d9")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#101010"), 1))
            for idx, point in enumerate(self._points):
                radius = 5 if idx == self._drag_index else 4
                pos = self._point_to_widget(point)
                painter.drawEllipse(pos, radius, radius)

        def mousePressEvent(self, event) -> None:  # noqa: N802
            pos = event.position()
            nearest = self._nearest_point_index(pos)
            if event.button() == QtCore.Qt.RightButton and nearest not in (None, 0, len(self._points) - 1):
                self._points.pop(int(nearest))
                self.update()
                self.pointsChanged.emit(self.points())
                self.interactionFinished.emit()
                return
            if event.button() != QtCore.Qt.LeftButton:
                return super().mousePressEvent(event)
            if nearest is None:
                self._points.append(self._widget_to_point(pos))
                self._points = normalize_tone_curve_points(self._points)
                nearest = self._nearest_point_index(pos)
                self.pointsChanged.emit(self.points())
            self._drag_index = nearest

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            if self._drag_index is None:
                return super().mouseMoveEvent(event)
            idx = int(self._drag_index)
            if idx == 0 or idx == len(self._points) - 1:
                return
            x, y = self._widget_to_point(event.position())
            left = self._points[idx - 1][0] + 0.01
            right = self._points[idx + 1][0] - 0.01
            lower_y = self._points[idx - 1][1]
            upper_y = self._points[idx + 1][1]
            self._points[idx] = (
                float(np.clip(x, left, right)),
                float(np.clip(y, lower_y, upper_y)),
            )
            self.update()
            self.pointsChanged.emit(self.points())

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            had_drag = self._drag_index is not None
            self._drag_index = None
            self._points = normalize_tone_curve_points(self._points)
            self.update()
            if had_drag:
                self.interactionFinished.emit()
            return super().mouseReleaseEvent(event)

        def is_dragging(self) -> bool:
            return self._drag_index is not None

        def _plot_rect(self) -> QtCore.QRectF:
            available_w = max(20.0, float(self.width() - 24))
            available_h = max(20.0, float(self.height() - 24))
            side = min(available_w, available_h)
            left = (float(self.width()) - side) / 2.0
            top = (float(self.height()) - side) / 2.0
            return QtCore.QRectF(left, top, side, side)

        def _point_to_widget(self, point: tuple[float, float]) -> QtCore.QPointF:
            domain_x = self._black_point + float(point[0]) * max(1e-4, self._white_point - self._black_point)
            return self._domain_point_to_widget(domain_x, float(point[1]))

        def _domain_point_to_widget(self, x_value: float, y_value: float) -> QtCore.QPointF:
            rect = self._plot_rect()
            x = rect.left() + float(np.clip(x_value, 0.0, 1.0)) * rect.width()
            y = rect.bottom() - float(np.clip(y_value, 0.0, 1.0)) * rect.height()
            return QtCore.QPointF(x, y)

        def _widget_to_point(self, pos: QtCore.QPointF) -> tuple[float, float]:
            rect = self._plot_rect()
            domain_x = (pos.x() - rect.left()) / max(1.0, rect.width())
            x = (domain_x - self._black_point) / max(1e-4, self._white_point - self._black_point)
            y = (rect.bottom() - pos.y()) / max(1.0, rect.height())
            return float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0))

        def _nearest_point_index(self, pos: QtCore.QPointF) -> int | None:
            best_idx = None
            best_dist = 14.0
            for idx, point in enumerate(self._points):
                p = self._point_to_widget(point)
                dist = float(np.hypot(p.x() - pos.x(), p.y() - pos.y()))
                if dist < best_dist:
                    best_dist = dist
                    best_idx = idx
            return best_idx


    class RGBHistogramWidget(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self._hist_r: np.ndarray | None = None
            self._hist_g: np.ndarray | None = None
            self._hist_b: np.ndarray | None = None
            self._clip_shadow = np.zeros(3, dtype=np.float32)
            self._clip_highlight = np.zeros(3, dtype=np.float32)
            self._clip_markers_enabled = True
            self.setMinimumHeight(130)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        def sizeHint(self) -> QtCore.QSize:  # noqa: N802
            return QtCore.QSize(340, 150)

        def clear(self) -> None:
            self._hist_r = None
            self._hist_g = None
            self._hist_b = None
            self._clip_shadow = np.zeros(3, dtype=np.float32)
            self._clip_highlight = np.zeros(3, dtype=np.float32)
            self.setToolTip("")
            self.update()

        def set_clip_markers_enabled(self, enabled: bool) -> None:
            self._clip_markers_enabled = bool(enabled)
            self.update()

        def clip_metrics(self) -> dict[str, float]:
            return {
                "shadow_r": float(self._clip_shadow[0]),
                "shadow_g": float(self._clip_shadow[1]),
                "shadow_b": float(self._clip_shadow[2]),
                "highlight_r": float(self._clip_highlight[0]),
                "highlight_g": float(self._clip_highlight[1]),
                "highlight_b": float(self._clip_highlight[2]),
                "shadow_any": float(np.max(self._clip_shadow)),
                "highlight_any": float(np.max(self._clip_highlight)),
            }

        def set_image_u8(self, image_rgb_u8: np.ndarray | None) -> None:
            if image_rgb_u8 is None:
                self.clear()
                return
            rgb = np.asarray(image_rgb_u8)
            if rgb.ndim == 2:
                rgb = np.repeat(rgb[..., None], 3, axis=2)
            if rgb.ndim != 3 or rgb.shape[2] < 3:
                self.clear()
                return
            rgb = np.ascontiguousarray(rgb[..., :3])
            if rgb.dtype != np.uint8:
                rgb = np.clip(np.round(rgb.astype(np.float32)), 0, 255).astype(np.uint8)

            pixels = rgb.reshape((-1, 3))
            if pixels.size == 0:
                self.clear()
                return

            count = int(pixels.shape[0])
            if count > VIEWER_HISTOGRAM_MAX_SAMPLE_PIXELS:
                stride = int(np.ceil(count / VIEWER_HISTOGRAM_MAX_SAMPLE_PIXELS))
                pixels = pixels[::max(1, stride)]
                count = int(pixels.shape[0])

            hist_r = np.bincount(pixels[:, 0], minlength=256).astype(np.float32)
            hist_g = np.bincount(pixels[:, 1], minlength=256).astype(np.float32)
            hist_b = np.bincount(pixels[:, 2], minlength=256).astype(np.float32)
            maxv = float(max(np.max(hist_r), np.max(hist_g), np.max(hist_b), 1.0))
            self._hist_r = hist_r / maxv
            self._hist_g = hist_g / maxv
            self._hist_b = hist_b / maxv

            self._clip_shadow = np.mean(
                pixels <= int(VIEWER_HISTOGRAM_SHADOW_CLIP_U8), axis=0
            ).astype(np.float32)
            self._clip_highlight = np.mean(
                pixels >= int(VIEWER_HISTOGRAM_HIGHLIGHT_CLIP_U8), axis=0
            ).astype(np.float32)

            metrics = self.clip_metrics()
            self.setToolTip(
                "Clipping sombras: "
                f"R {metrics['shadow_r'] * 100.0:.2f}%  "
                f"G {metrics['shadow_g'] * 100.0:.2f}%  "
                f"B {metrics['shadow_b'] * 100.0:.2f}%\n"
                "Clipping luces: "
                f"R {metrics['highlight_r'] * 100.0:.2f}%  "
                f"G {metrics['highlight_g'] * 100.0:.2f}%  "
                f"B {metrics['highlight_b'] * 100.0:.2f}%"
            )
            self.update()

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.fillRect(self.rect(), QtGui.QColor("#1c1f24"))

            plot_rect = self.rect().adjusted(8, 8, -8, -24)
            if plot_rect.width() <= 4 or plot_rect.height() <= 4:
                return

            bg_grad = QtGui.QLinearGradient(plot_rect.topLeft(), plot_rect.bottomLeft())
            bg_grad.setColorAt(0.0, QtGui.QColor("#2b2f35"))
            bg_grad.setColorAt(1.0, QtGui.QColor("#1d2025"))
            painter.fillRect(plot_rect, bg_grad)

            painter.setPen(QtGui.QPen(QtGui.QColor("#3b4048"), 1))
            for idx in range(1, 4):
                x = plot_rect.left() + (plot_rect.width() * idx / 4.0)
                painter.drawLine(QtCore.QPointF(x, plot_rect.top()), QtCore.QPointF(x, plot_rect.bottom()))
            for idx in range(1, 3):
                y = plot_rect.top() + (plot_rect.height() * idx / 3.0)
                painter.drawLine(QtCore.QPointF(plot_rect.left(), y), QtCore.QPointF(plot_rect.right(), y))

            self._draw_hist_channel(painter, plot_rect, self._hist_r, QtGui.QColor(248, 113, 113, 170), QtGui.QColor(248, 113, 113, 245))
            self._draw_hist_channel(painter, plot_rect, self._hist_g, QtGui.QColor(134, 239, 172, 150), QtGui.QColor(134, 239, 172, 245))
            self._draw_hist_channel(painter, plot_rect, self._hist_b, QtGui.QColor(96, 165, 250, 150), QtGui.QColor(96, 165, 250, 245))

            painter.setPen(QtGui.QPen(QtGui.QColor("#4b515b"), 1))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(plot_rect)

            metrics = self.clip_metrics()
            self._draw_clip_marker(
                painter,
                left_side=True,
                active=bool(metrics["shadow_any"] > VIEWER_HISTOGRAM_CLIP_ALERT_RATIO),
                color=QtGui.QColor("#60a5fa"),
            )
            self._draw_clip_marker(
                painter,
                left_side=False,
                active=bool(metrics["highlight_any"] > VIEWER_HISTOGRAM_CLIP_ALERT_RATIO),
                color=QtGui.QColor("#f87171"),
            )

            painter.setPen(QtGui.QColor("#aeb5bf"))
            painter.drawText(
                self.rect().adjusted(8, 0, -8, -4),
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom,
                f"S {metrics['shadow_any'] * 100.0:.2f}%",
            )
            painter.drawText(
                self.rect().adjusted(8, 0, -8, -4),
                QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom,
                f"L {metrics['highlight_any'] * 100.0:.2f}%",
            )

        def _draw_hist_channel(
            self,
            painter: QtGui.QPainter,
            rect: QtCore.QRect,
            hist: np.ndarray | None,
            fill_color: QtGui.QColor,
            line_color: QtGui.QColor,
        ) -> None:
            if hist is None or hist.size == 0:
                return
            n = int(hist.size)
            if n <= 1:
                return
            path = QtGui.QPainterPath()
            path.moveTo(rect.left(), rect.bottom())
            for idx, value in enumerate(hist):
                x = rect.left() + rect.width() * (idx / float(n - 1))
                y = rect.bottom() - rect.height() * float(np.clip(value, 0.0, 1.0))
                path.lineTo(float(x), float(y))
            path.lineTo(rect.right(), rect.bottom())
            path.closeSubpath()
            painter.fillPath(path, fill_color)

            line_path = QtGui.QPainterPath()
            for idx, value in enumerate(hist):
                x = rect.left() + rect.width() * (idx / float(n - 1))
                y = rect.bottom() - rect.height() * float(np.clip(value, 0.0, 1.0))
                if idx == 0:
                    line_path.moveTo(float(x), float(y))
                else:
                    line_path.lineTo(float(x), float(y))
            painter.setPen(QtGui.QPen(line_color, 1.15))
            painter.drawPath(line_path)

        def _draw_clip_marker(
            self,
            painter: QtGui.QPainter,
            *,
            left_side: bool,
            active: bool,
            color: QtGui.QColor,
        ) -> None:
            size = 12
            margin = 3
            if left_side:
                x = margin
            else:
                x = max(margin, self.width() - margin - size)
            y = margin
            points = QtGui.QPolygonF(
                [
                    QtCore.QPointF(x, y + size),
                    QtCore.QPointF(x + size * 0.5, y),
                    QtCore.QPointF(x + size, y + size),
                ]
            )
            marker_on = bool(self._clip_markers_enabled and active)
            painter.setPen(QtGui.QPen(QtGui.QColor("#0f1115"), 1))
            painter.setBrush(QtGui.QBrush(color if marker_on else QtGui.QColor("#323842")))
            painter.drawPolygon(points)


    class ImagePanel(QtWidgets.QLabel):
        imageClicked = QtCore.Signal(float, float)

        def __init__(
            self,
            title: str,
            *,
            framed: bool = True,
            background: str = IMAGE_PANEL_BACKGROUND,
        ) -> None:
            super().__init__()
            self._base_pixmap: QtGui.QPixmap | None = None
            self._image_size: tuple[int, int] | None = None
            self._overlay_points: list[tuple[float, float]] = []
            self._view_zoom = 1.0
            self._view_rotation = 0
            self._framed = bool(framed)
            self._background = str(background or IMAGE_PANEL_BACKGROUND)
            self._clip_overlay_pixmap: QtGui.QPixmap | None = None
            self._clip_overlay_enabled = False
            self._pan = QtCore.QPointF(0.0, 0.0)
            self._drag_start: QtCore.QPointF | None = None
            self._drag_last: QtCore.QPointF | None = None
            self._drag_moved = False
            self.setAlignment(QtCore.Qt.AlignCenter)
            self.setMinimumSize(220, 160)
            self.setMouseTracking(True)
            self.setText(title)
            border_style = f"1px solid {IMAGE_PANEL_BORDER}" if self._framed else "1px solid transparent"
            self.setStyleSheet(
                "QLabel {"
                f"border: {border_style};"
                f"background-color: {self._background};"
                f"color: {IMAGE_PANEL_TEXT};"
                "font-size: 13px;"
                "}"
            )

        def set_rgb_float_image(self, image_rgb: np.ndarray) -> None:
            rgb = np.clip(image_rgb, 0.0, 1.0)
            u8 = np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)
            self.set_rgb_u8_image(u8)

        def set_rgb_u8_image(self, image_rgb_u8: np.ndarray) -> None:
            u8 = np.ascontiguousarray(image_rgb_u8.astype(np.uint8))
            if u8.ndim == 2:
                u8 = np.repeat(u8[..., None], 3, axis=2)
            if u8.ndim != 3 or u8.shape[2] < 3:
                raise RuntimeError(f"Imagen RGB inesperada para visor: shape={u8.shape}")
            u8 = np.ascontiguousarray(u8[..., :3])
            h, w, _ = u8.shape
            self._image_size = (w, h)
            qimg = QtGui.QImage(u8.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()
            self._base_pixmap = QtGui.QPixmap.fromImage(qimg)
            self._clip_overlay_pixmap = None
            self._refresh_scaled_pixmap()

        def set_overlay_points(self, points: list[tuple[float, float]]) -> None:
            self._overlay_points = list(points)
            self._refresh_scaled_pixmap()

        def set_clip_overlay_enabled(self, enabled: bool) -> None:
            self._clip_overlay_enabled = bool(enabled)
            self._refresh_scaled_pixmap()

        def clear_clip_overlay(self) -> None:
            self._clip_overlay_pixmap = None
            self._refresh_scaled_pixmap()

        def set_clip_overlay_classes(self, classes_u8: np.ndarray | None) -> None:
            if classes_u8 is None:
                self._clip_overlay_pixmap = None
                self._refresh_scaled_pixmap()
                return
            classes = np.ascontiguousarray(np.asarray(classes_u8, dtype=np.uint8))
            if classes.ndim != 2:
                self._clip_overlay_pixmap = None
                self._refresh_scaled_pixmap()
                return
            h, w = int(classes.shape[0]), int(classes.shape[1])
            if h <= 0 or w <= 0:
                self._clip_overlay_pixmap = None
                self._refresh_scaled_pixmap()
                return
            qimg = QtGui.QImage(classes.data, w, h, w, QtGui.QImage.Format_Indexed8).copy()
            qimg.setColorCount(4)
            qimg.setColor(0, QtGui.qRgba(0, 0, 0, 0))
            qimg.setColor(1, QtGui.qRgba(44, 156, 255, 110))
            qimg.setColor(2, QtGui.qRgba(255, 68, 68, 120))
            qimg.setColor(3, QtGui.qRgba(196, 65, 255, 140))
            self._clip_overlay_pixmap = QtGui.QPixmap.fromImage(qimg)
            self._refresh_scaled_pixmap()

        def set_view_transform(self, *, zoom: float, rotation: int) -> None:
            self._view_zoom = float(np.clip(zoom, 0.2, 8.0))
            self._view_rotation = int(rotation) % 360
            if self._view_zoom <= 1.0:
                self._pan = QtCore.QPointF(0.0, 0.0)
            self._refresh_scaled_pixmap()

        def mousePressEvent(self, event) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.LeftButton and self._base_pixmap is not None:
                self._drag_start = event.position()
                self._drag_last = event.position()
                self._drag_moved = False
                self.setCursor(QtCore.Qt.ClosedHandCursor)
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            if self._drag_last is not None and self._drag_start is not None:
                delta = event.position() - self._drag_last
                distance = event.position() - self._drag_start
                if self._view_zoom > 1.0 and (abs(distance.x()) > 3.0 or abs(distance.y()) > 3.0):
                    self._pan += delta
                    self._drag_moved = True
                    self._refresh_scaled_pixmap()
                self._drag_last = event.position()
                return
            if self._view_zoom > 1.0:
                self.setCursor(QtCore.Qt.OpenHandCursor)
            else:
                self.unsetCursor()
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.LeftButton and self._drag_start is not None:
                mapped = self._map_widget_to_image(event.position())
                if mapped is not None and not self._drag_moved:
                    self.imageClicked.emit(float(mapped[0]), float(mapped[1]))
                self._drag_start = None
                self._drag_last = None
                self._drag_moved = False
                self.setCursor(QtCore.Qt.OpenHandCursor if self._view_zoom > 1.0 else QtCore.Qt.ArrowCursor)
                return
            super().mouseReleaseEvent(event)

        def wheelEvent(self, event) -> None:  # noqa: N802
            if self._base_pixmap is None:
                return super().wheelEvent(event)
            factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
            self.set_view_transform(zoom=self._view_zoom * factor, rotation=self._view_rotation)
            event.accept()

        def resizeEvent(self, event) -> None:  # noqa: N802
            super().resizeEvent(event)
            self._refresh_scaled_pixmap()

        def paintEvent(self, event) -> None:  # noqa: N802
            if self._base_pixmap is None:
                return super().paintEvent(event)

            geometry = self._display_geometry()
            if geometry is None:
                return super().paintEvent(event)

            pixmap, rect, scale, transform, bounds = geometry
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
            painter.fillRect(self.rect(), QtGui.QColor(self._background))
            painter.drawPixmap(rect, pixmap, QtCore.QRectF(pixmap.rect()))
            if self._clip_overlay_enabled and self._clip_overlay_pixmap is not None:
                painter.drawPixmap(rect, self._clip_overlay_pixmap, QtCore.QRectF(self._clip_overlay_pixmap.rect()))

            if self._overlay_points and self._image_size is not None:
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                painter.setPen(QtGui.QPen(QtGui.QColor("#f59e0b"), 2))
                painter.setBrush(QtCore.Qt.NoBrush)
                qpoints = [
                    self._map_image_to_widget(x, y, rect, scale, transform, bounds)
                    for x, y in self._overlay_points
                ]
                if len(qpoints) >= 2:
                    painter.drawPolyline(QtGui.QPolygonF(qpoints))
                if len(qpoints) == 4:
                    painter.drawLine(qpoints[-1], qpoints[0])
                painter.setBrush(QtGui.QBrush(QtGui.QColor(245, 158, 11, 160)))
                for idx, point in enumerate(qpoints, start=1):
                    painter.drawEllipse(point, 6, 6)
                    painter.drawText(point + QtCore.QPointF(8, -8), str(idx))

            if self._framed:
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.setPen(QtGui.QPen(QtGui.QColor("#4b5563"), 1))
                painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            painter.end()

        def _refresh_scaled_pixmap(self) -> None:
            self.update()

        def _map_widget_to_image(self, pos: QtCore.QPointF) -> tuple[float, float] | None:
            if self._base_pixmap is None or self._image_size is None:
                return None
            geometry = self._display_geometry()
            if geometry is None:
                return None
            _pixmap, rect, scale, transform, bounds = geometry
            if not rect.contains(pos):
                return None
            tx = (float(pos.x()) - rect.left()) / max(1e-6, scale)
            ty = (float(pos.y()) - rect.top()) / max(1e-6, scale)
            inv, ok = transform.inverted()
            if not ok:
                return None
            mapped = inv.map(QtCore.QPointF(tx + bounds.left(), ty + bounds.top()))
            image_w, image_h = self._image_size
            if mapped.x() < 0 or mapped.y() < 0 or mapped.x() > image_w or mapped.y() > image_h:
                return None
            return float(mapped.x()), float(mapped.y())

        def _display_geometry(self):
            if self._base_pixmap is None:
                return None
            transform = QtGui.QTransform()
            transform.rotate(self._view_rotation)
            bounds = transform.mapRect(
                QtCore.QRectF(
                    0.0,
                    0.0,
                    float(self._base_pixmap.width()),
                    float(self._base_pixmap.height()),
                )
            )
            pixmap = (
                self._base_pixmap
                if self._view_rotation == 0
                else self._base_pixmap.transformed(transform, QtCore.Qt.SmoothTransformation)
            )
            pw = max(1.0, float(pixmap.width()))
            ph = max(1.0, float(pixmap.height()))
            fit = min(max(1.0, self.width()) / pw, max(1.0, self.height()) / ph)
            scale = fit * self._view_zoom
            draw_w = pw * scale
            draw_h = ph * scale
            max_pan_x = max(0.0, (draw_w - self.width()) / 2.0)
            max_pan_y = max(0.0, (draw_h - self.height()) / 2.0)
            pan_x = float(np.clip(self._pan.x(), -max_pan_x, max_pan_x))
            pan_y = float(np.clip(self._pan.y(), -max_pan_y, max_pan_y))
            self._pan = QtCore.QPointF(pan_x, pan_y)
            rect = QtCore.QRectF(
                (self.width() - draw_w) / 2.0 + pan_x,
                (self.height() - draw_h) / 2.0 + pan_y,
                draw_w,
                draw_h,
            )
            return pixmap, rect, scale, transform, bounds

        def _map_image_to_widget(
            self,
            x: float,
            y: float,
            rect: QtCore.QRectF,
            scale: float,
            transform: QtGui.QTransform,
            bounds: QtCore.QRectF,
        ) -> QtCore.QPointF:
            mapped = transform.map(QtCore.QPointF(float(x), float(y)))
            tx = mapped.x() - bounds.left()
            ty = mapped.y() - bounds.top()
            return QtCore.QPointF(rect.left() + tx * scale, rect.top() + ty * scale)


    class NexoRawMainWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle(f"{APP_NAME} - Ajuste paramétrico RAW")
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
                LEGACY_PREVIEW_INTERACTIVE_BYPASS_DISPLAY_ICC_ENV,
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
            self.statusBar().showMessage("Listo")

        def _build_ui(self) -> None:
            root = QtWidgets.QWidget()
            root_layout = QtWidgets.QVBoxLayout(root)
            root_layout.setContentsMargins(4, 4, 4, 4)
            root_layout.setSpacing(4)

            header = QtWidgets.QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(6)
            header.addStretch(1)
            header.addWidget(self._button("Inicio", self._go_home_directory))
            header.addWidget(self._button("Abrir carpeta...", self._pick_directory))
            header.addWidget(self._button("Recargar", self._reload_current_directory))
            header.addWidget(self._button("Pantalla completa", self._menu_toggle_fullscreen))
            root_layout.addLayout(header)

            task_bar = QtWidgets.QHBoxLayout()
            self.global_status_label = QtWidgets.QLabel("Listo")
            self.global_status_label.setStyleSheet("font-size: 12px; color: #374151;")
            self.global_progress = QtWidgets.QProgressBar()
            self.global_progress.setRange(0, 1)
            self.global_progress.setValue(0)
            self.global_progress.setTextVisible(False)
            self.global_progress.setMaximumHeight(8)
            task_bar.addWidget(self.global_status_label, 1)
            task_bar.addWidget(self.global_progress, 2)
            root_layout.addLayout(task_bar)

            self.main_tabs = QtWidgets.QTabWidget()
            session_tab = self._build_tab_session()
            raw_tab = self._build_tab_raw_develop()
            queue_tab = self._build_tab_queue()

            self.main_tabs.addTab(session_tab, "1. Sesión")
            self.main_tabs.addTab(raw_tab, "2. Ajustar / Aplicar")
            self.main_tabs.addTab(queue_tab, "3. Cola de Revelado")

            root_layout.addWidget(self.main_tabs, 1)

            self.setCentralWidget(root)
            self._build_global_settings_dialog()

        def _build_menu_bar(self) -> None:
            mb = self.menuBar()

            menu_file = mb.addMenu("Archivo")
            menu_file.addAction(self._action("Crear sesión...", self._on_create_session))
            menu_file.addAction(self._action("Abrir sesión...", self._on_open_session))
            menu_file.addAction(self._action("Guardar sesión", self._on_save_session, "Ctrl+Shift+S"))
            menu_file.addSeparator()
            menu_file.addAction(self._action("Abrir carpeta...", self._pick_directory, "Ctrl+O"))
            menu_file.addAction(self._action("Guardar preview PNG", self._on_save_preview, "Ctrl+S"))
            menu_file.addAction(self._action("Aplicar ajustes a selección", self._on_batch_develop_selected, "Ctrl+R"))
            menu_file.addSeparator()
            menu_file.addAction(self._action("Salir", self.close, "Ctrl+Q"))

            menu_cfg = mb.addMenu("Configuracion")
            menu_cfg.addAction(self._action("Cargar receta...", self._menu_load_recipe))
            menu_cfg.addAction(self._action("Guardar receta...", self._menu_save_recipe))
            menu_cfg.addAction(self._action("Receta por defecto", self._menu_reset_recipe))
            menu_cfg.addSeparator()
            menu_cfg.addAction(self._action("Configuracion global...", self._open_global_settings_dialog))
            menu_cfg.addSeparator()
            menu_cfg.addAction(self._action("Ir a pestaña Sesión", lambda: self.main_tabs.setCurrentIndex(0)))
            menu_cfg.addAction(self._action("Ir a pestaña Revelado", lambda: self.main_tabs.setCurrentIndex(1)))
            menu_cfg.addAction(self._action("Ir a pestaña Cola", lambda: self.main_tabs.setCurrentIndex(2)))

            menu_profile = mb.addMenu("Perfil ICC")
            menu_profile.addAction(self._action("Cargar perfil activo...", self._menu_load_profile))
            menu_profile.addAction(self._action("Usar perfil generado", self._use_generated_profile_as_active))
            menu_profile.addAction(self._action("Comparar reportes QA...", self._menu_compare_qa_reports))

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
            menu_help.addAction(self._action("Diagnóstico herramientas...", self._menu_check_tools))
            menu_help.addAction(self._action("Buscar actualizaciones...", self._menu_check_updates))
            menu_help.addAction(self._action(f"Acerca de {APP_NAME}", self._menu_about))

        def _go_to_nitidez_tab(self) -> None:
            self.main_tabs.setCurrentIndex(1)
            index = self.config_tabs.indexOf("Nitidez") if hasattr(self.config_tabs, "indexOf") else -1
            self.config_tabs.setCurrentIndex(index if index >= 0 else 3)

        def _menu_toggle_fullscreen(self, _checked: bool = False) -> None:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()

        def _reset_layout_splitters(self) -> None:
            if hasattr(self, "raw_splitter"):
                w = max(1200, int(self.width() * 0.98))
                left = max(260, int(w * 0.16))
                right = max(300, int(w * 0.21))
                center = max(520, w - left - right)
                self.raw_splitter.setSizes([left, center, right])

            if hasattr(self, "compare_splitter"):
                cw = max(600, int(self.width() * 0.55))
                self.compare_splitter.setSizes([cw // 2, cw // 2])

            if hasattr(self, "viewer_splitter"):
                h = max(700, int(self.height() * 0.85))
                self.viewer_splitter.setSizes([
                    int(h * 0.76),
                    int(h * 0.24),
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

        def _settings_bool(self, key: str, default: bool = False) -> bool:
            value = self._settings.value(key, default)
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)

        def _default_work_directory(self) -> Path:
            try:
                return Path.home().expanduser().resolve()
            except Exception:
                return Path.cwd().expanduser().resolve()

        def _startup_directory_from_settings(self) -> Path:
            folder = self._persistent_directory("browser/last_dir")
            return folder or self._default_work_directory()

        def _persistent_directory(self, key: str) -> Path | None:
            text = str(self._settings.value(key) or "").strip()
            if not text:
                return None
            if self._is_legacy_temp_output_path(text):
                self._settings.remove(key)
                return None
            folder = Path(text).expanduser()
            if folder.exists() and folder.is_dir():
                return folder.resolve()
            self._settings.remove(key)
            return None

        def _persistent_session_root(self) -> Path | None:
            key = "session/last_root"
            text = str(self._settings.value(key) or "").strip()
            if not text:
                return None
            if self._is_legacy_temp_output_path(text):
                self._settings.remove(key)
                return None
            root = Path(text).expanduser()
            if session_file_path(root).exists():
                return root.resolve()
            self._settings.remove(key)
            return None

        def _restore_startup_context(self) -> bool:
            root = self._persistent_session_root()
            if root is not None:
                try:
                    self._activate_session(root, load_session(root))
                    return True
                except Exception as exc:
                    self._settings.remove("session/last_root")
                    self._set_status(f"No se pudo restaurar la última sesión: {exc}")

            folder = self._persistent_directory("browser/last_dir")
            if folder is not None:
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

            self.session_root_path = QtWidgets.QLineEdit(str(self._current_dir / "nexoraw_session"))
            self._add_path_row(grid, 0, "Directorio raíz de sesión", self.session_root_path, file_mode=False, save_mode=False, dir_mode=True)
            self.session_root_path.editingFinished.connect(self._on_session_root_edited)
            self.session_root_path.textChanged.connect(lambda _text: self._session_root_update_timer.start(150))

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

            dirs_box = QtWidgets.QGroupBox("Estructura persistente del proyecto")
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

            dirs_grid.addWidget(QtWidgets.QLabel("00_configuraciones"), 0, 0)
            dirs_grid.addWidget(self.session_dir_config, 0, 1)
            dirs_grid.addWidget(QtWidgets.QLabel("01_ORG originales RAW"), 1, 0)
            dirs_grid.addWidget(self.session_dir_raw, 1, 1)
            dirs_grid.addWidget(QtWidgets.QLabel("02_DRV derivados"), 2, 0)
            dirs_grid.addWidget(self.session_dir_exports, 2, 1)

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

            box = QtWidgets.QGroupBox("Carta de color: perfil avanzado de ajuste + ICC de entrada")
            grid = QtWidgets.QGridLayout(box)

            self.profile_charts_dir = QtWidgets.QLineEdit(str(self._current_dir))
            self._add_path_row(grid, 0, "Carpeta de referencias colorimétricas", self.profile_charts_dir, file_mode=False, save_mode=False, dir_mode=True)

            self.profile_chart_selection_label = QtWidgets.QLabel("Referencias colorimétricas: todas las compatibles de la carpeta indicada")
            self.profile_chart_selection_label.setWordWrap(True)
            self.profile_chart_selection_label.setStyleSheet("font-size: 12px; color: #374151;")
            grid.addWidget(self.profile_chart_selection_label, 1, 0, 1, 3)

            self.path_reference = QtWidgets.QLineEdit("testdata/references/colorchecker24_colorchecker2005_d50.json")
            self._add_path_row(grid, 2, "Referencia carta JSON", self.path_reference, file_mode=True, save_mode=False, dir_mode=False)

            self.profile_out_path_edit = QtWidgets.QLineEdit("/tmp/camera_profile_gui.icc")
            self.path_profile_out = self.profile_out_path_edit
            self._add_path_row(grid, 3, "Perfil ICC de entrada", self.profile_out_path_edit, file_mode=False, save_mode=True, dir_mode=False)

            self.profile_report_out = QtWidgets.QLineEdit("/tmp/profile_report_gui.json")
            self._hide_row_widgets(self._add_path_row(grid, 4, "Reporte perfil JSON", self.profile_report_out, file_mode=False, save_mode=True, dir_mode=False))

            self.profile_workdir = QtWidgets.QLineEdit("/tmp/nexoraw_profile_work")
            self._hide_row_widgets(self._add_path_row(grid, 5, "Directorio artefactos", self.profile_workdir, file_mode=False, save_mode=False, dir_mode=True))

            self.develop_profile_out = QtWidgets.QLineEdit("/tmp/development_profile_gui.json")
            self._hide_row_widgets(self._add_path_row(grid, 6, "Perfil de ajuste avanzado JSON", self.develop_profile_out, file_mode=False, save_mode=True, dir_mode=False))

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

            grid.addWidget(QtWidgets.QLabel("Formato ICC"), 11, 0)
            self.combo_profile_format = QtWidgets.QComboBox()
            self.combo_profile_format.addItems(PROFILE_FORMAT_OPTIONS)
            grid.addWidget(self.combo_profile_format, 11, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Tipo de perfil ICC"), 12, 0)
            self.combo_profile_algo = QtWidgets.QComboBox()
            for label, flag in PROFILE_ALGO_OPTIONS:
                self.combo_profile_algo.addItem(label, flag)
            grid.addWidget(self.combo_profile_algo, 12, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Calidad colprof"), 13, 0)
            self.combo_profile_quality = QtWidgets.QComboBox()
            for label, q in PROFILE_QUALITY_OPTIONS:
                self.combo_profile_quality.addItem(label, q)
            self.combo_profile_quality.setCurrentIndex(1)
            grid.addWidget(self.combo_profile_quality, 13, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Args extra colprof"), 14, 0)
            self.edit_colprof_args = QtWidgets.QLineEdit("")
            self.edit_colprof_args.setPlaceholderText("Ejemplo: -D \"Perfil Camara Museo\"")
            grid.addWidget(self.edit_colprof_args, 14, 1, 1, 2)

            label_camera = QtWidgets.QLabel("Cámara (opcional)")
            grid.addWidget(label_camera, 15, 0)
            self.profile_camera = QtWidgets.QLineEdit("")
            grid.addWidget(self.profile_camera, 15, 1, 1, 2)
            label_camera.hide()
            self.profile_camera.hide()

            label_lens = QtWidgets.QLabel("Lente (opcional)")
            grid.addWidget(label_lens, 16, 0)
            self.profile_lens = QtWidgets.QLineEdit("")
            grid.addWidget(self.profile_lens, 16, 1, 1, 2)
            label_lens.hide()
            self.profile_lens.hide()

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

            row_generate = QtWidgets.QHBoxLayout()
            row_generate.addWidget(self._button("Generar perfil avanzado con carta", self._on_generate_profile))
            outer.addLayout(row_generate)

            self.profile_summary_label = QtWidgets.QLabel("Sin perfil avanzado generado")
            self.profile_summary_label.setWordWrap(True)
            self.profile_summary_label.setStyleSheet("font-size: 12px; color: #d1d5db;")
            outer.addWidget(self.profile_summary_label)

            self.profile_output = QtWidgets.QPlainTextEdit()
            self.profile_output.setReadOnly(True)
            self.profile_output.setPlaceholderText("Resultado JSON de la generación de perfil")
            self.profile_output.setMaximumHeight(170)
            outer.addWidget(self.profile_output, 1)
            return tab

        def _build_development_profiles_panel(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(tab)

            grid.addWidget(QtWidgets.QLabel("Perfil de ajuste activo"), 0, 0)
            self.development_profile_combo = QtWidgets.QComboBox()
            self.development_profile_combo.setToolTip(
                "Perfil de ajuste guardado. Al aplicarlo, sus parametros pasan a los controles de revelado del RAW."
            )
            grid.addWidget(self.development_profile_combo, 0, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Nombre del ajuste"), 1, 0)
            self.development_profile_name_edit = QtWidgets.QLineEdit("Perfil manual")
            grid.addWidget(self.development_profile_name_edit, 1, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("ICC sin carta"), 2, 0)
            self.development_output_space_combo = QtWidgets.QComboBox()
            self.development_output_space_combo.setToolTip(
                "Para imagenes sin carta, asigna un perfil ICC generico de salida al TIFF. "
                "Con carta se recomienda mantener RGB de camara e incrustar el ICC de entrada generado."
            )
            self.development_output_space_combo.addItem("Carta / RGB de cámara", "scene_linear_camera_rgb")
            self.development_output_space_combo.addItem("sRGB genérico", "srgb")
            self.development_output_space_combo.addItem("Adobe RGB (1998) genérico", "adobe_rgb")
            self.development_output_space_combo.addItem("ProPhoto RGB genérico", "prophoto_rgb")
            self.development_output_space_combo.currentIndexChanged.connect(self._on_development_output_space_changed)
            grid.addWidget(self.development_output_space_combo, 2, 1, 1, 2)

            profile_buttons = QtWidgets.QGridLayout()
            profile_buttons.addWidget(self._button("Guardar perfil básico", self._save_current_development_profile), 0, 0)
            profile_buttons.addWidget(self._button("Aplicar a controles", self._activate_selected_development_profile), 0, 1)
            profile_buttons.addWidget(self._button("Asignar activo a cola", self._queue_assign_active_development_profile), 1, 0, 1, 2)
            grid.addLayout(profile_buttons, 3, 0, 1, 3)

            self.development_profile_status_label = QtWidgets.QLabel("Sin perfiles de ajuste guardados")
            self.development_profile_status_label.setWordWrap(True)
            self.development_profile_status_label.setStyleSheet("font-size: 12px; color: #374151;")
            grid.addWidget(self.development_profile_status_label, 4, 0, 1, 3)

            self._refresh_development_profile_combo()
            return tab

        def _build_color_management_calibration_panel(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(tab)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(10)

            profile_box = QtWidgets.QGroupBox("Perfiles de ajuste por archivo")
            profile_layout = QtWidgets.QVBoxLayout(profile_box)
            profile_layout.addWidget(self._build_development_profiles_panel())
            layout.addWidget(profile_box)

            layout.addWidget(self._build_tab_profile_generation())

            self._advanced_profile_config = self._build_tab_profile_config()
            icc_box = QtWidgets.QGroupBox("ICC activo para preview y exportación")
            icc_layout = QtWidgets.QVBoxLayout(icc_box)
            icc_layout.addWidget(self._advanced_profile_config)
            layout.addWidget(icc_box)
            layout.addStretch(1)
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
            queue_actions.addWidget(self._button("Asignar perfil activo", self._queue_assign_active_development_profile))
            queue_actions.addWidget(self._button("Quitar seleccionados", self._queue_remove_selected))
            queue_actions.addWidget(self._button("Limpiar cola", self._queue_clear))
            queue_actions.addWidget(self._button("Revelar cola", self._queue_process))
            queue_layout.addLayout(queue_actions)

            self.queue_status_label = QtWidgets.QLabel("Cola vacía")
            self.queue_status_label.setStyleSheet("font-size: 12px; color: #374151;")
            queue_layout.addWidget(self.queue_status_label)

            self.queue_table = QtWidgets.QTableWidget(0, 5)
            self.queue_table.setHorizontalHeaderLabels(["Archivo", "Perfil", "Estado", "TIFF salida", "Mensaje"])
            self.queue_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            self.queue_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            self.queue_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
            self.queue_table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)
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
            pane.setMinimumWidth(260)
            layout = QtWidgets.QVBoxLayout(pane)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            self.left_tabs = QtWidgets.QTabWidget()
            self.left_tabs.setTabPosition(QtWidgets.QTabWidget.West)
            self.left_tabs.setDocumentMode(True)
            self.left_tabs.addTab(self._build_browser_panel(), "Explorador")
            self.left_tabs.addTab(self._build_viewer_controls_panel(), "Visor")
            self.left_tabs.addTab(self._build_analysis_panel(), "Análisis")
            self.left_tabs.addTab(self._build_metadata_panel(), "Metadatos")
            self.left_tabs.addTab(self._build_preview_log_panel(), "Log")
            layout.addWidget(self.left_tabs, 1)
            return pane

        def _build_browser_panel(self) -> QtWidgets.QWidget:
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
            return box

        def _build_viewer_controls_panel(self) -> QtWidgets.QWidget:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)

            layout.addWidget(QtWidgets.QLabel("Archivo actual"))
            self.selected_file_label = QtWidgets.QLabel("Sin archivo seleccionado")
            self.selected_file_label.setWordWrap(True)
            self.selected_file_label.setStyleSheet("font-size: 12px; color: #1f2937;")
            layout.addWidget(self.selected_file_label)

            self.chk_compare = QtWidgets.QCheckBox("Comparar original / resultado")
            self.chk_compare.toggled.connect(self._toggle_compare)
            layout.addWidget(self.chk_compare)

            self.chk_apply_profile = QtWidgets.QCheckBox("Aplicar perfil ICC en resultado")
            self.chk_apply_profile.setChecked(False)
            self.chk_apply_profile.setToolTip(
                "Desactivado por defecto para evitar dominantes si el perfil no corresponde "
                "a camara + iluminacion + receta actuales."
            )
            self.chk_apply_profile.toggled.connect(lambda _v: self._schedule_preview_refresh())
            layout.addWidget(self.chk_apply_profile)

            zoom_grid = QtWidgets.QGridLayout()
            zoom_grid.setHorizontalSpacing(6)
            zoom_grid.setVerticalSpacing(6)
            self.viewer_zoom_label = QtWidgets.QLabel("100%")
            self.viewer_zoom_label.setAlignment(QtCore.Qt.AlignCenter)
            self.viewer_zoom_label.setMinimumWidth(52)
            zoom_grid.addWidget(self._button("-", self._viewer_zoom_out), 0, 0)
            zoom_grid.addWidget(self.viewer_zoom_label, 0, 1)
            zoom_grid.addWidget(self._button("+", self._viewer_zoom_in), 0, 2)
            zoom_grid.addWidget(self._button("1:1", self._viewer_zoom_100), 1, 0)
            zoom_grid.addWidget(self._button("Girar izq.", self._viewer_rotate_left), 1, 1)
            zoom_grid.addWidget(self._button("Girar der.", self._viewer_rotate_right), 1, 2)
            zoom_grid.addWidget(self._button("Encajar", self._viewer_fit), 2, 0, 1, 3)
            layout.addLayout(zoom_grid)

            histogram_box = QtWidgets.QGroupBox("Histograma RGB")
            histogram_layout = QtWidgets.QVBoxLayout(histogram_box)
            histogram_layout.setContentsMargins(6, 6, 6, 6)
            histogram_layout.setSpacing(4)
            self.viewer_histogram = RGBHistogramWidget()
            histogram_layout.addWidget(self.viewer_histogram, 1)
            self.check_histogram_clip_witness = QtWidgets.QCheckBox(
                "Testigos de clipping en sombras/luces"
            )
            self.check_histogram_clip_witness.setChecked(
                self._settings_bool("view/histogram_clip_witness", True)
            )
            self.check_histogram_clip_witness.toggled.connect(self._on_histogram_clip_witness_toggled)
            histogram_layout.addWidget(self.check_histogram_clip_witness)
            self.check_image_clip_overlay = QtWidgets.QCheckBox(
                "Overlay clipping en imagen (azul sombras / rojo luces)"
            )
            self.check_image_clip_overlay.setChecked(
                self._settings_bool("view/image_clip_overlay", True)
            )
            self.check_image_clip_overlay.toggled.connect(self._on_image_clip_overlay_toggled)
            histogram_layout.addWidget(self.check_image_clip_overlay)
            clip_row = QtWidgets.QHBoxLayout()
            clip_row.setContentsMargins(0, 0, 0, 0)
            self.histogram_shadow_label = QtWidgets.QLabel("Sombras: --")
            self.histogram_shadow_label.setStyleSheet("font-size: 12px; color: #6b7280;")
            self.histogram_highlight_label = QtWidgets.QLabel("Luces: --")
            self.histogram_highlight_label.setStyleSheet("font-size: 12px; color: #6b7280;")
            clip_row.addWidget(self.histogram_shadow_label, 1)
            clip_row.addWidget(self.histogram_highlight_label, 1)
            histogram_layout.addLayout(clip_row)
            self.viewer_histogram.set_clip_markers_enabled(
                bool(self.check_histogram_clip_witness.isChecked())
            )
            for panel_name in ("image_result_single", "image_result_compare", "image_original_compare"):
                if hasattr(self, panel_name):
                    getattr(self, panel_name).set_clip_overlay_enabled(
                        bool(self.check_image_clip_overlay.isChecked())
                    )
            layout.addWidget(histogram_box, 0)

            cache_row = QtWidgets.QHBoxLayout()
            cache_row.addWidget(
                self._button(
                    "Precache carpeta",
                    lambda: self._on_precache_visible_previews(full_resolution=False),
                )
            )
            cache_row.addWidget(
                self._button(
                    "Precache 1:1",
                    lambda: self._on_precache_visible_previews(full_resolution=True),
                )
            )
            layout.addLayout(cache_row)
            layout.addStretch(1)
            return panel

        def _build_analysis_panel(self) -> QtWidgets.QWidget:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(4, 4, 4, 4)
            self.preview_analysis = QtWidgets.QPlainTextEdit()
            self.preview_analysis.setReadOnly(True)
            self.preview_analysis.setPlaceholderText("Analisis tecnico lineal")
            layout.addWidget(self.preview_analysis, 1)
            return panel

        def _build_metadata_panel(self) -> QtWidgets.QWidget:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(6)

            self.metadata_file_label = QtWidgets.QLabel("Sin archivo seleccionado")
            self.metadata_file_label.setWordWrap(True)
            self.metadata_file_label.setStyleSheet("font-size: 12px; color: #d1d5db;")
            layout.addWidget(self.metadata_file_label)

            actions = QtWidgets.QHBoxLayout()
            actions.addWidget(self._button("Leer metadatos", self._refresh_metadata_view))
            actions.addWidget(self._button("JSON completo", self._show_metadata_all_tab))
            layout.addLayout(actions)

            self.metadata_tabs = QtWidgets.QTabWidget()
            self.metadata_summary = self._metadata_tree_widget()
            self.metadata_exif = self._metadata_tree_widget()
            self.metadata_gps = self._metadata_tree_widget()
            self.metadata_c2pa = self._metadata_tree_widget()
            self.metadata_all = self._metadata_text_widget("JSON completo")
            self.metadata_tabs.addTab(self.metadata_summary, "Resumen")
            self.metadata_tabs.addTab(self.metadata_exif, "EXIF")
            self.metadata_tabs.addTab(self.metadata_gps, "GPS")
            self.metadata_tabs.addTab(self.metadata_c2pa, "C2PA")
            self.metadata_tabs.addTab(self.metadata_all, "Todo")
            layout.addWidget(self.metadata_tabs, 1)
            return panel

        def _metadata_tree_widget(self) -> QtWidgets.QTreeWidget:
            tree = QtWidgets.QTreeWidget()
            tree.setHeaderLabels(["Campo", "Valor"])
            tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            tree.setAlternatingRowColors(True)
            tree.setRootIsDecorated(True)
            tree.setUniformRowHeights(False)
            tree.setTextElideMode(QtCore.Qt.ElideMiddle)
            return tree

        def _metadata_text_widget(self, placeholder: str) -> QtWidgets.QPlainTextEdit:
            widget = QtWidgets.QPlainTextEdit()
            widget.setReadOnly(True)
            widget.setPlaceholderText(placeholder)
            widget.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
            return widget

        def _build_preview_log_panel(self) -> QtWidgets.QWidget:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(4, 4, 4, 4)
            self.preview_log = QtWidgets.QPlainTextEdit()
            self.preview_log.setReadOnly(True)
            self.preview_log.setPlaceholderText("Eventos y trazas de ejecucion")
            layout.addWidget(self.preview_log, 1)
            return panel

        def _build_thumbnails_pane(self) -> QtWidgets.QWidget:
            pane = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(pane)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)

            toolbar = QtWidgets.QHBoxLayout()
            toolbar.setContentsMargins(4, 0, 4, 0)
            toolbar.addWidget(QtWidgets.QLabel("Miniaturas"))
            self.thumbnail_size_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            self.thumbnail_size_slider.setRange(MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE)
            self.thumbnail_size_slider.setSingleStep(8)
            self.thumbnail_size_slider.setPageStep(16)
            thumbnail_size = self._thumbnail_size_from_settings()
            self.thumbnail_size_slider.setValue(thumbnail_size)
            self.thumbnail_size_slider.valueChanged.connect(self._on_thumbnail_size_changed)
            toolbar.addWidget(self.thumbnail_size_slider, 1)
            self.thumbnail_size_label = QtWidgets.QLabel(f"{thumbnail_size}px")
            self.thumbnail_size_label.setMinimumWidth(48)
            self.thumbnail_size_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            toolbar.addWidget(self.thumbnail_size_label)
            layout.addLayout(toolbar)

            self.file_list = QtWidgets.QListWidget()
            self.file_list.setViewMode(QtWidgets.QListView.IconMode)
            self.file_list.setFlow(QtWidgets.QListView.LeftToRight)
            self.file_list.setWrapping(False)
            self.file_list.setResizeMode(QtWidgets.QListView.Adjust)
            self.file_list.setMovement(QtWidgets.QListView.Static)
            self.file_list.setSpacing(2)
            self.file_list.setWordWrap(False)
            self.file_list.setUniformItemSizes(True)
            self.file_list.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
            self.file_list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
            self.file_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            self.file_list.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self.file_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            self.file_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self.file_list.setStyleSheet(
                "QListWidget {"
                "background-color: #1b1f24;"
                "border: 1px solid #343a40;"
                "padding: 2px;"
                "}"
                "QListWidget::item {"
                "background-color: #171a1e;"
                "border: 1px solid #2c3238;"
                "margin: 0px;"
                "padding: 0px;"
                "}"
                "QListWidget::item:selected {"
                "border: 2px solid #d1d5db;"
                "background-color: #1f252b;"
                "}"
            )
            self.file_list.itemSelectionChanged.connect(self._on_file_selection_changed)
            self.file_list.itemDoubleClicked.connect(self._on_file_double_clicked)
            self.file_list.customContextMenuRequested.connect(self._show_file_list_context_menu)
            self.file_list.horizontalScrollBar().valueChanged.connect(self._on_thumbnail_scroll_changed)
            self._apply_thumbnail_size(thumbnail_size)
            layout.addWidget(self.file_list, 1)

            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("Usar selección como referencias colorimétricas", self._use_selected_files_as_profile_charts))
            row.addWidget(self._button("Añadir selección a cola", self._queue_add_selected))
            layout.addLayout(row)

            profile_row = QtWidgets.QHBoxLayout()
            profile_row.addWidget(self._button("Guardar perfil básico en imagen", self._save_current_development_settings_to_selected))
            profile_row.addWidget(self._button("Copiar perfil de ajuste", self._copy_development_settings_from_selected))
            profile_row.addWidget(self._button("Pegar perfil de ajuste", self._paste_development_settings_to_selected))
            layout.addLayout(profile_row)
            return pane

        def _thumbnail_size_from_settings(self) -> int:
            value = self._settings.value("view/thumbnail_size", DEFAULT_THUMBNAIL_SIZE)
            try:
                size = int(value)
            except (TypeError, ValueError):
                size = DEFAULT_THUMBNAIL_SIZE
            return int(np.clip(size, MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE))

        def _apply_thumbnail_size(self, size: int) -> None:
            size = int(np.clip(size, MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE))
            thumb_h = size
            thumb_w = size
            self.file_list.setIconSize(QtCore.QSize(thumb_w, thumb_h))
            grid_size = QtCore.QSize(thumb_w + 4, thumb_h + 4)
            self.file_list.setGridSize(grid_size)
            for row in range(self.file_list.count()):
                item = self.file_list.item(row)
                if item is not None and item.flags() != QtCore.Qt.NoItemFlags:
                    item.setSizeHint(grid_size)
            if hasattr(self, "thumbnail_size_label"):
                self.thumbnail_size_label.setText(f"{size}px")

        def _on_thumbnail_size_changed(self, size: int) -> None:
            size = int(np.clip(size, MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE))
            self._settings.setValue("view/thumbnail_size", size)
            self._apply_thumbnail_size(size)
            self._refresh_color_reference_thumbnail_markers()
            self._queue_thumbnail_generation(self._file_list_paths(), delay_ms=80)

        def _build_center_pane(self) -> QtWidgets.QWidget:
            pane = QtWidgets.QWidget()
            pane.setMinimumWidth(420)
            layout = QtWidgets.QVBoxLayout(pane)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            self.viewer_stack = QtWidgets.QStackedWidget()

            self.image_result_single = ImagePanel("Resultado")
            self.image_result_single.imageClicked.connect(self._on_result_image_click)
            single_page = QtWidgets.QWidget()
            single_layout = QtWidgets.QVBoxLayout(single_page)
            single_layout.setContentsMargins(0, 0, 0, 0)
            single_layout.addWidget(self.image_result_single, 1)
            self.viewer_stack.addWidget(single_page)

            self.image_original_compare = ImagePanel("", framed=False, background="#15181d")
            self.image_result_compare = ImagePanel("", framed=False, background="#15181d")
            self.image_result_compare.imageClicked.connect(self._on_result_image_click)
            self.compare_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            self.compare_splitter.setChildrenCollapsible(True)
            self.compare_splitter.setHandleWidth(3)
            self.compare_splitter.setStyleSheet(
                "QSplitter::handle:horizontal {"
                "background-color: #0f1115;"
                "border-left: 1px solid #2f353d;"
                "border-right: 1px solid #2f353d;"
                "}"
            )
            self.compare_splitter.addWidget(self.image_original_compare)
            self.compare_splitter.addWidget(self.image_result_compare)
            self.compare_splitter.setSizes([560, 560])
            compare_page = QtWidgets.QWidget()
            compare_layout = QtWidgets.QVBoxLayout(compare_page)
            compare_layout.setContentsMargins(0, 0, 0, 0)
            compare_layout.setSpacing(0)
            compare_header = QtWidgets.QWidget()
            compare_header.setStyleSheet("background-color: #15181d;")
            compare_header_layout = QtWidgets.QHBoxLayout(compare_header)
            compare_header_layout.setContentsMargins(0, 2, 0, 2)
            compare_header_layout.setSpacing(0)
            compare_header_layout.addStretch(1)
            before_label = QtWidgets.QLabel("Antes")
            after_label = QtWidgets.QLabel("Despues")
            for label in (before_label, after_label):
                label.setAlignment(QtCore.Qt.AlignCenter)
                label.setMinimumWidth(72)
                label.setStyleSheet(
                    "QLabel {"
                    "background-color: #7a7d82;"
                    "color: #f8fafc;"
                    "font-size: 11px;"
                    "font-weight: 600;"
                    "padding: 1px 8px;"
                    "border: 1px solid #8f9399;"
                    "}"
                )
            compare_header_layout.addWidget(before_label, 0, QtCore.Qt.AlignHCenter)
            compare_header_layout.addWidget(after_label, 0, QtCore.Qt.AlignHCenter)
            compare_header_layout.addStretch(1)
            compare_layout.addWidget(compare_header, 0)
            compare_layout.addWidget(self.compare_splitter, 1)
            self.viewer_stack.addWidget(compare_page)
            self.viewer_stack.setCurrentIndex(0)

            self.viewer_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
            self.viewer_splitter.setChildrenCollapsible(True)
            self.viewer_splitter.setHandleWidth(8)
            self.viewer_splitter.addWidget(self.viewer_stack)
            self.viewer_splitter.addWidget(self._build_thumbnails_pane())
            self.viewer_splitter.setStretchFactor(0, 1)
            self.viewer_splitter.setStretchFactor(1, 0)
            self.viewer_splitter.setSizes([760, 240])
            layout.addWidget(self.viewer_splitter, 1)
            return pane

        def _build_right_pane(self) -> QtWidgets.QWidget:
            pane = QtWidgets.QWidget()
            pane.setMinimumWidth(280)
            layout = QtWidgets.QVBoxLayout(pane)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            self.config_tabs = CollapsibleToolPanel()
            self.config_tabs.addItem(self._build_tab_brightness_contrast(), "Brillo y contraste", expanded=True)
            self.config_tabs.addItem(self._build_tab_color_adjustments(), "Color", expanded=True)
            self.config_tabs.addItem(self._build_tab_preview_settings(), "Nitidez", expanded=True)
            self.config_tabs.addItem(self._build_color_management_calibration_panel(), "Gestión de color y calibración", expanded=True)
            self._advanced_raw_config = self._build_tab_raw_config("Criterios RAW globales")
            self.config_tabs.addItem(self._advanced_raw_config, "RAW Global", expanded=False)
            self.config_tabs.addItem(self._build_tab_batch_config(), "Exportar derivados", expanded=False)
            layout.addWidget(self.config_tabs, 1)

            return pane

        def _build_tab_color_adjustments(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(tab)

            grid.addWidget(QtWidgets.QLabel("Iluminante final"), 0, 0)
            self.combo_illuminant_render = QtWidgets.QComboBox()
            for label, temp, tint in ILLUMINANT_OPTIONS:
                self.combo_illuminant_render.addItem(label, {"temperature": temp, "tint": tint})
            self.combo_illuminant_render.setCurrentIndex(1)
            self.combo_illuminant_render.currentIndexChanged.connect(self._on_illuminant_changed)
            grid.addWidget(self.combo_illuminant_render, 0, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Temperatura (K)"), 1, 0)
            self.spin_render_temperature = QtWidgets.QSpinBox()
            self.spin_render_temperature.setRange(2000, 12000)
            self.spin_render_temperature.setSingleStep(50)
            self.spin_render_temperature.setValue(5003)
            self.spin_render_temperature.valueChanged.connect(lambda _v: self._on_render_control_change())
            grid.addWidget(self.spin_render_temperature, 1, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Matiz"), 2, 0)
            self.spin_render_tint = QtWidgets.QDoubleSpinBox()
            self.spin_render_tint.setRange(-100.0, 100.0)
            self.spin_render_tint.setSingleStep(1.0)
            self.spin_render_tint.setDecimals(1)
            self.spin_render_tint.valueChanged.connect(lambda _v: self._on_render_control_change())
            grid.addWidget(self.spin_render_tint, 2, 1, 1, 2)

            neutral_row = QtWidgets.QHBoxLayout()
            self.btn_neutral_picker = QtWidgets.QPushButton("Cuentagotas neutro")
            self.btn_neutral_picker.setCheckable(True)
            self.btn_neutral_picker.clicked.connect(self._toggle_neutral_picker)
            neutral_row.addWidget(self.btn_neutral_picker)
            self.label_neutral_picker = QtWidgets.QLabel("Punto neutro: sin muestra")
            self.label_neutral_picker.setWordWrap(True)
            self.label_neutral_picker.setStyleSheet("font-size: 12px; color: #cbd5e1;")
            neutral_row.addWidget(self.label_neutral_picker, 1)
            grid.addLayout(neutral_row, 3, 0, 1, 3)

            grid.addWidget(self._button("Restablecer color", self._reset_color_adjustments), 4, 0, 1, 3)
            return tab

        def _build_tab_brightness_contrast(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(tab)

            self.slider_brightness, self.label_brightness = self._slider(
                minimum=-200,
                maximum=200,
                value=0,
                on_change=self._on_render_control_change,
                formatter=lambda v: f"Brillo: {v / 100:+.2f} EV",
            )
            grid.addWidget(self.label_brightness, 0, 0, 1, 3)
            grid.addWidget(self.slider_brightness, 1, 0, 1, 3)

            self.slider_black_point, self.label_black_point = self._slider(
                minimum=0,
                maximum=300,
                value=0,
                on_change=self._on_render_control_change,
                formatter=lambda v: f"Nivel negro: {v / 1000:.3f}",
            )
            grid.addWidget(self.label_black_point, 2, 0, 1, 3)
            grid.addWidget(self.slider_black_point, 3, 0, 1, 3)

            self.slider_white_point, self.label_white_point = self._slider(
                minimum=500,
                maximum=1000,
                value=1000,
                on_change=self._on_render_control_change,
                formatter=lambda v: f"Nivel blanco: {v / 1000:.3f}",
            )
            grid.addWidget(self.label_white_point, 4, 0, 1, 3)
            grid.addWidget(self.slider_white_point, 5, 0, 1, 3)

            self.slider_contrast, self.label_contrast = self._slider(
                minimum=-100,
                maximum=100,
                value=0,
                on_change=self._on_render_control_change,
                formatter=lambda v: f"Contraste: {v / 100:+.2f}",
            )
            grid.addWidget(self.label_contrast, 6, 0, 1, 3)
            grid.addWidget(self.slider_contrast, 7, 0, 1, 3)

            self.slider_midtone, self.label_midtone = self._slider(
                minimum=50,
                maximum=200,
                value=100,
                on_change=self._on_render_control_change,
                formatter=lambda v: f"Curva medios: {v / 100:.2f}",
            )
            grid.addWidget(self.label_midtone, 8, 0, 1, 3)
            grid.addWidget(self.slider_midtone, 9, 0, 1, 3)

            self.check_tone_curve_enabled = QtWidgets.QCheckBox("Curva tonal avanzada")
            self.check_tone_curve_enabled.setChecked(False)
            self.check_tone_curve_enabled.toggled.connect(self._on_tone_curve_enabled_changed)
            grid.addWidget(self.check_tone_curve_enabled, 10, 0, 1, 3)

            grid.addWidget(QtWidgets.QLabel("Preset curva"), 11, 0)
            self.combo_tone_curve_preset = QtWidgets.QComboBox()
            for label, key, _points in TONE_CURVE_PRESETS:
                self.combo_tone_curve_preset.addItem(label, key)
            self.combo_tone_curve_preset.currentIndexChanged.connect(self._on_tone_curve_preset_changed)
            grid.addWidget(self.combo_tone_curve_preset, 11, 1, 1, 2)

            self.slider_tone_curve_black, self.label_tone_curve_black = self._slider(
                minimum=0,
                maximum=950,
                value=0,
                on_change=self._on_tone_curve_range_changed,
                formatter=lambda v: f"Negro curva: {v / 1000:.3f}",
            )
            grid.addWidget(self.label_tone_curve_black, 12, 0, 1, 3)
            grid.addWidget(self.slider_tone_curve_black, 13, 0, 1, 3)

            self.slider_tone_curve_white, self.label_tone_curve_white = self._slider(
                minimum=50,
                maximum=1000,
                value=1000,
                on_change=self._on_tone_curve_range_changed,
                formatter=lambda v: f"Blanco curva: {v / 1000:.3f}",
            )
            grid.addWidget(self.label_tone_curve_white, 14, 0, 1, 3)
            grid.addWidget(self.slider_tone_curve_white, 15, 0, 1, 3)

            self.tone_curve_editor = ToneCurveEditor()
            self.tone_curve_editor.pointsChanged.connect(self._on_tone_curve_points_changed)
            self.tone_curve_editor.interactionFinished.connect(self._on_render_control_change)
            grid.addWidget(self.tone_curve_editor, 16, 0, 1, 3)
            grid.addWidget(self._button("Restablecer curva", self._reset_tone_curve), 17, 0, 1, 3)
            self._set_tone_curve_controls_enabled(False)

            grid.addWidget(self._button("Restablecer brillo y contraste", self._reset_tone_adjustments), 18, 0, 1, 3)
            return tab

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

            self.slider_ca_red, self.label_ca_red = self._slider(
                minimum=-100,
                maximum=100,
                value=0,
                on_change=self._on_slider_change,
                formatter=lambda v: f"CA lateral rojo/cian: {1.0 + v / 10000:.4f}",
            )
            grid.addWidget(self.label_ca_red, 8, 0, 1, 3)
            grid.addWidget(self.slider_ca_red, 9, 0, 1, 3)

            self.slider_ca_blue, self.label_ca_blue = self._slider(
                minimum=-100,
                maximum=100,
                value=0,
                on_change=self._on_slider_change,
                formatter=lambda v: f"CA lateral azul/amarillo: {1.0 + v / 10000:.4f}",
            )
            grid.addWidget(self.label_ca_blue, 10, 0, 1, 3)
            grid.addWidget(self.slider_ca_blue, 11, 0, 1, 3)

            self.check_precision_detail_preview = QtWidgets.QCheckBox(
                "Modo precision 1:1 para nitidez (mas lento)"
            )
            self.check_precision_detail_preview.setToolTip(
                "Aplica ajustes de nitidez/ruido/CA sobre fuente a resolucion real durante el arrastre."
            )
            self.check_precision_detail_preview.setChecked(
                self._settings_bool("preview/precision_detail_1to1", False)
            )
            self.check_precision_detail_preview.toggled.connect(
                self._on_precision_detail_preview_toggled
            )
            grid.addWidget(self.check_precision_detail_preview, 12, 0, 1, 3)

            recipe_filter_note = QtWidgets.QLabel(
                "Modo receta de denoise y sharpen para el revelado final. "
                "Se aplica al lote y al preview, no a la generación de perfil ICC."
            )
            recipe_filter_note.setWordWrap(True)
            recipe_filter_note.setStyleSheet("font-size: 12px; color: #6b7280; padding-top: 6px;")
            grid.addWidget(recipe_filter_note, 13, 0, 1, 3)

            grid.addWidget(QtWidgets.QLabel("Denoise modo receta"), 14, 0)
            self.combo_recipe_denoise = QtWidgets.QComboBox()
            self.combo_recipe_denoise.addItems(FILTER_MODE_OPTIONS)
            grid.addWidget(self.combo_recipe_denoise, 14, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Sharpen modo receta"), 15, 0)
            self.combo_recipe_sharpen = QtWidgets.QComboBox()
            self.combo_recipe_sharpen.addItems(FILTER_MODE_OPTIONS)
            grid.addWidget(self.combo_recipe_sharpen, 15, 1, 1, 2)

            grid.addWidget(self._button("Restablecer nitidez", self._reset_adjustments), 16, 0, 1, 3)
            return tab

        def _build_tab_raw_config(self, title: str | None = None) -> QtWidgets.QWidget:
            tab = QtWidgets.QGroupBox(title) if title else QtWidgets.QWidget()
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
            self.combo_raw_developer.addItem("LibRaw / rawpy", "libraw")
            self.combo_raw_developer.setEnabled(False)
            grid.addWidget(self.combo_raw_developer, 2, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Demosaic/interpolacion"), 3, 0)
            self.combo_demosaic = QtWidgets.QComboBox()
            for label, opt in DEMOSAIC_OPTIONS:
                self.combo_demosaic.addItem(label, opt)
            self._sync_demosaic_capabilities()
            grid.addWidget(self.combo_demosaic, 3, 1, 1, 2)

            note = QtWidgets.QLabel(
                "LibRaw/rawpy es el único motor RAW. DCB es el preset instalable de alta calidad. "
                "AMaZE queda disponible solo cuando rawpy informa DEMOSAIC_PACK_GPL3=True."
            )
            note.setWordWrap(True)
            note.setStyleSheet("font-size: 12px; color: #6b7280;")
            grid.addWidget(note, 4, 0, 1, 3)

            grid.addWidget(QtWidgets.QLabel("Balance de blancos"), 5, 0)
            self.combo_wb_mode = QtWidgets.QComboBox()
            for label, val in WB_MODE_OPTIONS:
                self.combo_wb_mode.addItem(label, val)
            grid.addWidget(self.combo_wb_mode, 5, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("WB multiplicadores"), 6, 0)
            self.edit_wb_multipliers = QtWidgets.QLineEdit("1,1,1,1")
            self.edit_wb_multipliers.setToolTip("Formato: R,G,B,G (o R,G,B)")
            grid.addWidget(self.edit_wb_multipliers, 6, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Black level mode"), 7, 0)
            self.combo_black_mode = QtWidgets.QComboBox()
            for label, val in BLACK_MODE_OPTIONS:
                self.combo_black_mode.addItem(label, val)
            grid.addWidget(self.combo_black_mode, 7, 1)
            self.spin_black_value = QtWidgets.QSpinBox()
            self.spin_black_value.setRange(0, 65535)
            self.spin_black_value.setValue(0)
            grid.addWidget(self.spin_black_value, 7, 2)

            grid.addWidget(QtWidgets.QLabel("Exposure compensation (EV)"), 8, 0)
            self.spin_exposure = QtWidgets.QDoubleSpinBox()
            self.spin_exposure.setRange(-8.0, 8.0)
            self.spin_exposure.setDecimals(2)
            self.spin_exposure.setSingleStep(0.1)
            grid.addWidget(self.spin_exposure, 8, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Tone curve"), 9, 0)
            self.combo_tone_curve = QtWidgets.QComboBox()
            for label, val in TONE_OPTIONS:
                self.combo_tone_curve.addItem(label, val)
            grid.addWidget(self.combo_tone_curve, 9, 1)
            self.spin_gamma = QtWidgets.QDoubleSpinBox()
            self.spin_gamma.setRange(0.8, 4.0)
            self.spin_gamma.setDecimals(2)
            self.spin_gamma.setValue(2.2)
            grid.addWidget(self.spin_gamma, 9, 2)

            self.check_output_linear = QtWidgets.QCheckBox("Salida lineal")
            self.check_output_linear.setChecked(True)
            grid.addWidget(self.check_output_linear, 10, 0, 1, 3)

            grid.addWidget(QtWidgets.QLabel("Working space"), 11, 0)
            self.combo_working_space = QtWidgets.QComboBox()
            self.combo_working_space.addItems(SPACE_OPTIONS)
            grid.addWidget(self.combo_working_space, 11, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Output space"), 12, 0)
            self.combo_output_space = QtWidgets.QComboBox()
            self.combo_output_space.addItems(SPACE_OPTIONS)
            grid.addWidget(self.combo_output_space, 12, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Sampling strategy"), 13, 0)
            self.combo_sampling = QtWidgets.QComboBox()
            self.combo_sampling.addItems(SAMPLE_OPTIONS)
            grid.addWidget(self.combo_sampling, 13, 1, 1, 2)

            self.check_profiling_mode = QtWidgets.QCheckBox("Profiling mode")
            self.check_profiling_mode.setChecked(True)
            grid.addWidget(self.check_profiling_mode, 14, 0, 1, 3)

            grid.addWidget(QtWidgets.QLabel("Input color assumption"), 15, 0)
            self.edit_input_color = QtWidgets.QLineEdit("camera_native")
            grid.addWidget(self.edit_input_color, 15, 1, 1, 2)

            grid.addWidget(QtWidgets.QLabel("Illuminant metadata"), 16, 0)
            self.edit_illuminant = QtWidgets.QLineEdit("")
            grid.addWidget(self.edit_illuminant, 16, 1, 1, 2)

            scientific_note = QtWidgets.QLabel(
                "Durante la generación de un perfil avanzado con carta, NexoRAW fuerza estos parámetros a "
                "modo objetivo: tone_curve=linear, salida lineal=on, output_space=scene_linear_camera_rgb. "
                "Denoise y sharpen quedan desactivados durante la medición de carta y se "
                "configuran en la pestaña Nitidez para el revelado final."
            )
            scientific_note.setWordWrap(True)
            scientific_note.setStyleSheet("font-size: 12px; color: #6b7280; padding-top: 6px;")
            grid.addWidget(scientific_note, 17, 0, 1, 3)
            return tab

        def _build_tab_profile_config(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(tab)

            self.path_profile_active = QtWidgets.QLineEdit("/tmp/camera_profile.icc")
            self._add_path_row(grid, 0, "Perfil ICC de entrada activo", self.path_profile_active, file_mode=True, save_mode=False, dir_mode=False)

            row = QtWidgets.QHBoxLayout()
            row.addWidget(self._button("Cargar perfil activo", self._menu_load_profile))
            row.addWidget(self._button("Usar perfil generado", self._use_generated_profile_as_active))
            grid.addLayout(row, 1, 0, 1, 3)
            return tab

        def _build_tab_batch_config(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(tab)
            grid = QtWidgets.QGridLayout()

            self.batch_input_dir = QtWidgets.QLineEdit(str(self._current_dir))
            self._add_path_row(grid, 0, "RAW a revelar (carpeta)", self.batch_input_dir, file_mode=False, save_mode=False, dir_mode=True)

            self.batch_out_dir = QtWidgets.QLineEdit("/tmp/nexoraw_batch_tiffs")
            self._add_path_row(grid, 1, "Salida TIFF derivados", self.batch_out_dir, file_mode=False, save_mode=False, dir_mode=True)

            self.batch_embed_profile = QtWidgets.QCheckBox("Incrustar/aplicar ICC en TIFF")
            self.batch_embed_profile.setChecked(True)
            self.batch_embed_profile.setEnabled(False)
            grid.addWidget(self.batch_embed_profile, 2, 0, 1, 3)

            self.batch_apply_adjustments = QtWidgets.QCheckBox("Aplicar ajustes básicos y de nitidez")
            self.batch_apply_adjustments.setChecked(True)
            grid.addWidget(self.batch_apply_adjustments, 3, 0, 1, 3)

            row_1 = QtWidgets.QHBoxLayout()
            row_1.addWidget(self._button("Usar carpeta actual", self._use_current_dir_as_batch_input))
            row_1.addWidget(self._button("Aplicar a selección", self._on_batch_develop_selected))
            row_1.addWidget(self._button("Aplicar a carpeta", self._on_batch_develop_directory))

            self.batch_output = QtWidgets.QPlainTextEdit()
            self.batch_output.setReadOnly(True)
            self.batch_output.setPlaceholderText("Salida JSON de exportación de derivados")

            layout.addLayout(grid)
            layout.addLayout(row_1)
            layout.addWidget(self.batch_output, 1)
            return tab

        def _build_global_settings_dialog(self) -> None:
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle("Configuracion global de NexoRAW")
            dialog.setModal(False)
            dialog.resize(760, 620)
            self.global_settings_dialog = dialog

            layout = QtWidgets.QVBoxLayout(dialog)
            intro = QtWidgets.QLabel(
                "Ajustes globales de trazabilidad, C2PA, previsualizacion y gestion de color del monitor. "
                "Estos controles no modifican la imagen por si mismos; definen infraestructura de firma y visualizacion."
            )
            intro.setWordWrap(True)
            intro.setStyleSheet("font-size: 12px; color: #6b7280;")
            layout.addWidget(intro)

            self.global_settings_tabs = QtWidgets.QTabWidget()
            self.global_settings_tabs.addTab(
                self._settings_scroll_area(self._build_signature_settings_panel()),
                "Firma / C2PA",
            )
            self.global_settings_tabs.addTab(
                self._settings_scroll_area(self._build_preview_monitor_settings_panel()),
                "Preview / monitor",
            )
            layout.addWidget(self.global_settings_tabs, 1)

            buttons = QtWidgets.QHBoxLayout()
            buttons.addStretch(1)
            buttons.addWidget(self._button("Guardar configuracion", self._save_global_settings))
            buttons.addWidget(self._button("Cerrar", dialog.hide))
            layout.addLayout(buttons)

        def _settings_scroll_area(self, widget: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            return scroll

        def _build_signature_settings_panel(self) -> QtWidgets.QWidget:
            tab = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(tab)

            proof_box = QtWidgets.QGroupBox("NexoRAW Proof")
            proof_grid = QtWidgets.QGridLayout(proof_box)

            self.batch_proof_key_path = QtWidgets.QLineEdit(str(self._settings.value("proof/key_path") or ""))
            self._add_path_row(proof_grid, 0, "Clave privada Proof (Ed25519)", self.batch_proof_key_path, file_mode=True, save_mode=False, dir_mode=False)

            self.batch_proof_public_key_path = QtWidgets.QLineEdit(str(self._settings.value("proof/public_key_path") or ""))
            self._add_path_row(proof_grid, 1, "Clave publica Proof", self.batch_proof_public_key_path, file_mode=True, save_mode=False, dir_mode=False)

            proof_grid.addWidget(QtWidgets.QLabel("Frase clave Proof"), 2, 0)
            self.batch_proof_key_passphrase = QtWidgets.QLineEdit("")
            self.batch_proof_key_passphrase.setEchoMode(QtWidgets.QLineEdit.Password)
            self.batch_proof_key_passphrase.setPlaceholderText("No se guarda")
            proof_grid.addWidget(self.batch_proof_key_passphrase, 2, 1, 1, 2)

            proof_grid.addWidget(QtWidgets.QLabel("Firmante Proof"), 3, 0)
            self.batch_proof_signer_name = QtWidgets.QLineEdit(str(self._settings.value("proof/signer_name") or "NexoRAW local signer"))
            proof_grid.addWidget(self.batch_proof_signer_name, 3, 1, 1, 2)

            proof_grid.addWidget(self._button("Generar identidad local Proof", self._generate_local_proof_identity), 4, 0, 1, 3)

            proof_note = QtWidgets.QLabel(
                "Firma autonoma obligatoria para los TIFF finales. Vincula RAW, TIFF, receta, perfil y ajustes "
                "sin depender de una autoridad central."
            )
            proof_note.setWordWrap(True)
            proof_note.setStyleSheet("font-size: 12px; color: #6b7280; padding-top: 4px;")
            proof_grid.addWidget(proof_note, 5, 0, 1, 3)
            layout.addWidget(proof_box)

            c2pa_box = QtWidgets.QGroupBox("C2PA / CAI")
            c2pa_grid = QtWidgets.QGridLayout(c2pa_box)

            self.batch_c2pa_cert_path = QtWidgets.QLineEdit(str(self._settings.value("c2pa/cert_path") or ""))
            self._add_path_row(c2pa_grid, 0, "Certificado C2PA opcional (PEM)", self.batch_c2pa_cert_path, file_mode=True, save_mode=False, dir_mode=False)

            self.batch_c2pa_key_path = QtWidgets.QLineEdit(str(self._settings.value("c2pa/key_path") or ""))
            self._add_path_row(c2pa_grid, 1, "Clave privada C2PA opcional", self.batch_c2pa_key_path, file_mode=True, save_mode=False, dir_mode=False)

            c2pa_grid.addWidget(QtWidgets.QLabel("Frase clave C2PA"), 2, 0)
            self.batch_c2pa_key_passphrase = QtWidgets.QLineEdit("")
            self.batch_c2pa_key_passphrase.setEchoMode(QtWidgets.QLineEdit.Password)
            self.batch_c2pa_key_passphrase.setPlaceholderText("No se guarda")
            c2pa_grid.addWidget(self.batch_c2pa_key_passphrase, 2, 1, 1, 2)

            c2pa_grid.addWidget(QtWidgets.QLabel("Algoritmo C2PA"), 3, 0)
            self.batch_c2pa_alg = QtWidgets.QComboBox()
            self.batch_c2pa_alg.addItems(["ps256", "ps384", "es256", "es384"])
            self._set_combo_text(self.batch_c2pa_alg, str(self._settings.value("c2pa/alg") or "ps256"))
            c2pa_grid.addWidget(self.batch_c2pa_alg, 3, 1, 1, 2)

            c2pa_grid.addWidget(QtWidgets.QLabel("Servidor TSA"), 4, 0)
            self.batch_c2pa_timestamp_url = QtWidgets.QLineEdit(
                str(self._settings.value("c2pa/timestamp_url") or DEFAULT_TIMESTAMP_URL)
            )
            c2pa_grid.addWidget(self.batch_c2pa_timestamp_url, 4, 1, 1, 2)

            c2pa_grid.addWidget(QtWidgets.QLabel("Firmante C2PA"), 5, 0)
            self.batch_c2pa_signer_name = QtWidgets.QLineEdit(str(self._settings.value("c2pa/signer_name") or APP_NAME))
            c2pa_grid.addWidget(self.batch_c2pa_signer_name, 5, 1, 1, 2)

            c2pa_note = QtWidgets.QLabel(
                "C2PA se usa automaticamente con una identidad local de laboratorio cuando no hay certificado externo. "
                "Los certificados CAI oficiales solo son necesarios si se quiere aparecer como firmante reconocido por su lista de confianza."
            )
            c2pa_note.setWordWrap(True)
            c2pa_note.setStyleSheet("font-size: 12px; color: #6b7280; padding-top: 4px;")
            c2pa_grid.addWidget(c2pa_note, 6, 0, 1, 3)
            layout.addWidget(c2pa_box)

            for widget in (
                self.batch_proof_key_path,
                self.batch_proof_public_key_path,
                self.batch_proof_signer_name,
                self.batch_c2pa_cert_path,
                self.batch_c2pa_key_path,
                self.batch_c2pa_timestamp_url,
                self.batch_c2pa_signer_name,
            ):
                widget.editingFinished.connect(self._save_signature_settings)
            self.batch_c2pa_alg.currentTextChanged.connect(lambda _value: self._save_signature_settings())

            layout.addStretch(1)
            return tab

        def _build_preview_monitor_settings_panel(self) -> QtWidgets.QWidget:
            self._migrate_display_color_settings()
            tab = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(tab)

            note = QtWidgets.QLabel(
                "Opciones globales de navegacion y visualizacion. La preview rapida no debe usarse como referencia "
                "colorimetrica. La vista de maxima calidad se carga automaticamente al activar comparar original/resultado."
            )
            note.setWordWrap(True)
            note.setStyleSheet("font-size: 12px; color: #6b7280; padding-bottom: 6px;")
            grid.addWidget(note, 0, 0, 1, 3)

            preview_policy = QtWidgets.QLabel(
                "Politica fija: preview RAW automatica (rapida en navegacion, maxima calidad en comparar)."
            )
            preview_policy.setWordWrap(True)
            preview_policy.setStyleSheet("font-size: 12px; color: #9ca3af;")
            grid.addWidget(preview_policy, 1, 0, 1, 3)

            # Compat attribute kept for tests/legacy sessions. Policy is now fixed.
            self.check_fast_raw_preview = QtWidgets.QCheckBox(
                "Modo preview RAW automatico (rapida fuera de comparar, maxima calidad en comparar)"
            )
            self.check_fast_raw_preview.setChecked(True)
            self.check_fast_raw_preview.setEnabled(False)
            self.check_fast_raw_preview.hide()
            grid.addWidget(self.check_fast_raw_preview, 1, 0, 1, 3)

            grid.addWidget(QtWidgets.QLabel("Resolucion de preview"), 2, 0)
            self.preview_resolution_policy_label = QtWidgets.QLabel(
                "Automatica: usa fuente completa cuando es necesario (1:1 / precision / comparar)."
            )
            self.preview_resolution_policy_label.setWordWrap(True)
            self.preview_resolution_policy_label.setStyleSheet("font-size: 12px; color: #9ca3af;")
            grid.addWidget(self.preview_resolution_policy_label, 2, 1, 1, 2)

            # Legacy backing value kept for session compatibility; no longer user-editable.
            self.spin_preview_max_side = QtWidgets.QSpinBox()
            self.spin_preview_max_side.setRange(900, 6000)
            self.spin_preview_max_side.setSingleStep(100)
            self.spin_preview_max_side.setValue(int(PREVIEW_AUTO_BASE_MAX_SIDE))
            self.spin_preview_max_side.hide()

            self.check_display_color_management = QtWidgets.QCheckBox("Gestion ICC del monitor del sistema")
            self.check_display_color_management.setToolTip(
                "Usa automaticamente el perfil ICC configurado para el monitor en el sistema. "
                "Si necesitas revisar otro monitor o flujo, puedes seleccionar un perfil manualmente."
            )
            self.check_display_color_management.setChecked(self._settings_bool("display/color_management_enabled", True))
            self.check_display_color_management.toggled.connect(self._on_display_color_settings_changed)
            grid.addWidget(self.check_display_color_management, 3, 0, 1, 3)

            self.path_display_profile = QtWidgets.QLineEdit(str(self._settings.value("display/monitor_profile") or ""))
            self.path_display_profile.editingFinished.connect(self._on_display_color_settings_changed)
            self._add_path_row(grid, 4, "Perfil ICC monitor", self.path_display_profile, file_mode=True, save_mode=False, dir_mode=False)

            display_row = QtWidgets.QHBoxLayout()
            display_row.addWidget(self._button("Detectar", self._detect_display_profile))
            self.display_profile_status = QtWidgets.QLabel("")
            self.display_profile_status.setWordWrap(True)
            self.display_profile_status.setStyleSheet("font-size: 12px; color: #6b7280;")
            display_row.addWidget(self.display_profile_status, 1)
            grid.addLayout(display_row, 5, 0, 1, 3)
            self._ensure_display_profile_if_enabled()
            self._update_display_profile_status()

            self.path_preview_png = QtWidgets.QLineEdit(str(self._session_default_outputs()["preview"]))
            self.path_preview_png.hide()
            self.path_preview_png.editingFinished.connect(self._save_preview_monitor_settings)

            self.preview_png_policy_label = QtWidgets.QLabel(
                "Exportacion PNG: se elige destino con 'Guardar preview PNG' (Guardar como...)."
            )
            self.preview_png_policy_label.setWordWrap(True)
            self.preview_png_policy_label.setStyleSheet("font-size: 12px; color: #9ca3af;")
            grid.addWidget(self.preview_png_policy_label, 6, 0, 1, 3)

            cache_row = QtWidgets.QHBoxLayout()
            cache_row.addWidget(self._button("Limpiar cache", self._on_clear_preview_caches))
            cache_row.addStretch(1)
            grid.addLayout(cache_row, 7, 0, 1, 3)

            grid.setRowStretch(8, 1)
            return tab

        def _migrate_display_color_settings(self) -> None:
            marker = "display/system_profile_default_v1"
            if self._settings_bool(marker, False):
                return
            detected = detect_system_display_profile()
            self._settings.setValue("display/color_management_enabled", True)
            if detected is not None and not str(self._settings.value("display/monitor_profile") or "").strip():
                self._settings.setValue("display/monitor_profile", str(detected))
            self._settings.setValue(marker, True)
            self._settings.sync()

        def _open_global_settings_dialog(self, *_args) -> None:
            if not hasattr(self, "global_settings_dialog"):
                self._build_global_settings_dialog()
            self.global_settings_dialog.show()
            self.global_settings_dialog.raise_()
            self.global_settings_dialog.activateWindow()

        def _save_preview_monitor_settings(self) -> None:
            if not hasattr(self, "path_preview_png"):
                return
            self._settings.setValue("preview/fast_raw_preview", True)
            self._settings.setValue("preview/max_side", int(PREVIEW_AUTO_BASE_MAX_SIDE))
            if hasattr(self, "check_precision_detail_preview"):
                self._settings.setValue(
                    "preview/precision_detail_1to1",
                    bool(self.check_precision_detail_preview.isChecked()),
                )
            self._settings.remove("preview/png_path")
            self._settings.sync()

        def _cache_dirs_for_cleanup(self) -> list[Path]:
            dirs: list[Path] = [
                self._user_disk_cache_dir("previews"),
                self._user_disk_cache_dir("thumbnails"),
            ]
            if self._active_session_root is not None:
                work_cache = self._session_paths_from_root(self._active_session_root)["work"] / "cache"
                dirs.extend(
                    [
                        work_cache / "previews",
                        work_cache / "thumbnails",
                    ]
                )
            unique: list[Path] = []
            seen: set[str] = set()
            for d in dirs:
                key = str(d.resolve(strict=False))
                if key in seen:
                    continue
                seen.add(key)
                unique.append(d)
            return unique

        def _on_clear_preview_caches(self) -> None:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Limpiar cache",
                (
                    "Se eliminaran caches de previews y miniaturas (sesion y usuario).\n"
                    "Se regeneraran cuando sea necesario.\n\n"
                    "¿Continuar?"
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return

            removed_files = 0
            removed_dirs = 0
            errors: list[str] = []
            for cache_dir in self._cache_dirs_for_cleanup():
                if not cache_dir.exists():
                    continue
                try:
                    removed_files += sum(1 for p in cache_dir.rglob("*") if p.is_file())
                except Exception:
                    pass
                try:
                    shutil.rmtree(cache_dir)
                    removed_dirs += 1
                except Exception as exc:
                    errors.append(f"{cache_dir}: {exc}")

            self._thumb_cache.clear()
            self._image_thumb_cache.clear()
            self._thumbnail_disk_writes_since_prune = 0
            self._invalidate_preview_cache()
            self._save_preview_monitor_settings()

            if hasattr(self, "file_list"):
                self._queue_thumbnail_generation(self._file_list_paths(), delay_ms=0)
            if self._selected_file is not None:
                self._on_load_selected(show_message=False)

            self._set_status(f"Cache limpiada: {removed_dirs} carpetas, {removed_files} archivos.")
            self._log_preview(f"Cache limpiada ({removed_dirs} carpetas, {removed_files} archivos).")
            if errors:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Cache parcialmente limpiada",
                    "\n".join(errors[:6]),
                )

        def _precision_detail_preview_enabled(self) -> bool:
            checkbox = getattr(self, "check_precision_detail_preview", None)
            return bool(checkbox is not None and checkbox.isChecked())

        def _effective_preview_max_side(self) -> int:
            if self._precision_detail_preview_enabled():
                return 0
            if self._preview_requires_max_quality():
                return 0
            return int(PREVIEW_AUTO_BASE_MAX_SIDE)

        def _on_precision_detail_preview_toggled(self, enabled: bool) -> None:
            self._save_preview_monitor_settings()
            if self._original_linear is not None:
                self._schedule_preview_refresh()
            if not bool(enabled):
                return
            if self._original_linear is None or self._selected_file is None:
                return
            if self._selected_file.suffix.lower() not in RAW_EXTENSIONS:
                return
            # Force a reload at full source resolution when enabling precision mode.
            self._last_loaded_preview_key = None
            self._on_load_selected(show_message=False)

        def _save_global_settings(self) -> None:
            self._save_signature_settings()
            self._save_preview_monitor_settings()
            self._on_display_color_settings_changed()
            self._set_status("Configuracion global guardada")

        def _save_signature_settings(self) -> None:
            self._settings.setValue("proof/key_path", self.batch_proof_key_path.text().strip())
            self._settings.setValue("proof/public_key_path", self.batch_proof_public_key_path.text().strip())
            self._settings.setValue("proof/signer_name", self.batch_proof_signer_name.text().strip() or "NexoRAW local signer")
            self._settings.remove("proof/key_passphrase")
            self._settings.setValue("c2pa/cert_path", self.batch_c2pa_cert_path.text().strip())
            self._settings.setValue("c2pa/key_path", self.batch_c2pa_key_path.text().strip())
            self._settings.setValue("c2pa/alg", self.batch_c2pa_alg.currentText().strip() or "ps256")
            self._settings.setValue("c2pa/timestamp_url", self.batch_c2pa_timestamp_url.text().strip())
            self._settings.setValue("c2pa/signer_name", self.batch_c2pa_signer_name.text().strip() or APP_NAME)
            self._settings.remove("c2pa/key_passphrase")
            self._settings.sync()

        def _save_c2pa_settings(self) -> None:
            self._save_signature_settings()

        def _generate_local_proof_identity(self) -> None:
            base = Path.home().expanduser() / ".nexoraw" / "proof"
            private_key = base / "nexoraw-proof-private.pem"
            public_key = base / "nexoraw-proof-public.pem"
            try:
                result = generate_ed25519_identity(
                    private_key_path=private_key,
                    public_key_path=public_key,
                    passphrase=self.batch_proof_key_passphrase.text() or None,
                    overwrite=False,
                )
            except FileExistsError:
                self.batch_proof_key_path.setText(str(private_key))
                self.batch_proof_public_key_path.setText(str(public_key))
                self._save_signature_settings()
                QtWidgets.QMessageBox.information(
                    self,
                    "Identidad Proof existente",
                    "Ya existe una identidad local NexoRAW Proof. Se han cargado sus rutas.",
                )
                return
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Error Proof", str(exc))
                return
            self.batch_proof_key_path.setText(result["private_key"])
            self.batch_proof_public_key_path.setText(result["public_key"])
            self._save_signature_settings()
            QtWidgets.QMessageBox.information(
                self,
                "Identidad Proof generada",
                f"Clave publica SHA-256:\n{result['public_key_sha256']}",
            )

        def _technical_manifest_path_for_c2pa(self) -> Path | None:
            profile_report_text = self.profile_report_out.text().strip()
            if profile_report_text:
                profile_report = Path(profile_report_text).expanduser()
                if profile_report.exists():
                    return profile_report
            if self._active_session_root is not None:
                session_path = session_file_path(self._active_session_root)
                if session_path.exists():
                    return session_path
            return None

        def _session_id_for_c2pa(self) -> str | None:
            if self._active_session_root is not None:
                return str(self._active_session_root)
            try:
                session_name = self.session_name_edit.text().strip()
            except Exception:
                session_name = ""
            return session_name or None

        def _c2pa_config_from_controls(self) -> C2PASignConfig | None:
            cert_text = self.batch_c2pa_cert_path.text().strip()
            key_text = self.batch_c2pa_key_path.text().strip()
            if not cert_text and not key_text:
                return None
            if not cert_text or not key_text:
                raise RuntimeError("Configura certificado y clave privada C2PA, o deja ambos campos vacios.")

            cert_path = Path(os.path.expandvars(cert_text)).expanduser()
            key_path = Path(os.path.expandvars(key_text)).expanduser()
            if not cert_path.exists():
                raise RuntimeError(f"No existe certificado C2PA: {cert_path}")
            if not key_path.exists():
                raise RuntimeError(f"No existe clave privada C2PA: {key_path}")

            return C2PASignConfig(
                cert_path=cert_path,
                key_path=key_path,
                alg=self.batch_c2pa_alg.currentText().strip() or "ps256",
                timestamp_url=self.batch_c2pa_timestamp_url.text().strip() or None,
                signer_name=self.batch_c2pa_signer_name.text().strip() or APP_NAME,
                technical_manifest_path=self._technical_manifest_path_for_c2pa(),
                session_id=self._session_id_for_c2pa(),
                key_passphrase=self.batch_c2pa_key_passphrase.text() or None,
            )

        def _proof_config_from_controls(self) -> NexoRawProofConfig | None:
            key_text = self.batch_proof_key_path.text().strip()
            public_text = self.batch_proof_public_key_path.text().strip()
            if not key_text:
                return None
            key_path = Path(os.path.expandvars(key_text)).expanduser()
            public_path = Path(os.path.expandvars(public_text)).expanduser() if public_text else None
            if not key_path.exists():
                raise RuntimeError(f"No existe clave privada NexoRAW Proof: {key_path}")
            if public_path is not None and not public_path.exists():
                raise RuntimeError(f"No existe clave publica NexoRAW Proof: {public_path}")
            return NexoRawProofConfig(
                private_key_path=key_path,
                public_key_path=public_path,
                key_passphrase=self.batch_proof_key_passphrase.text() or None,
                signer_name=self.batch_proof_signer_name.text().strip() or "NexoRAW local signer",
                signer_id=self._session_id_for_c2pa(),
            )

        def _resolve_proof_config_for_gui(self) -> NexoRawProofConfig:
            control_config = self._proof_config_from_controls()
            if control_config is not None:
                self._save_signature_settings()
                return control_config
            return proof_config_from_environment()

        def _resolve_c2pa_config_for_gui(self) -> C2PASignConfig | None:
            control_config = self._c2pa_config_from_controls()
            if control_config is not None:
                self._save_signature_settings()
                return control_config
            return auto_c2pa_config(
                technical_manifest_path=self._technical_manifest_path_for_c2pa(),
                session_id=self._session_id_for_c2pa(),
                signer_name=self.batch_c2pa_signer_name.text().strip()
                or self.batch_proof_signer_name.text().strip()
                or APP_NAME,
                timestamp_url=self.batch_c2pa_timestamp_url.text().strip() or DEFAULT_TIMESTAMP_URL,
            )

        def _show_signature_config_error(self, exc: Exception) -> None:
            QtWidgets.QMessageBox.warning(
                self,
                "Firma forense requerida",
                f"{exc}\n\n"
                "NexoRAW crea por defecto una identidad local Proof y una identidad C2PA local. "
                "Revisa Configuracion > Configuracion global si quieres usar credenciales propias.",
            )

        def _show_c2pa_config_error(self, exc: Exception) -> None:
            self._show_signature_config_error(exc)

        def _init_fs_model(self) -> None:
            self._dir_model = QtWidgets.QFileSystemModel(self)
            for option in (
                "DontResolveSymlinks",
                "DontUseCustomDirectoryIcons",
            ):
                if hasattr(QtWidgets.QFileSystemModel, option):
                    self._dir_model.setOption(getattr(QtWidgets.QFileSystemModel, option), True)
            self._dir_model.setFilter(QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot)
            root_path = self._filesystem_model_root(self._current_dir)
            self._dir_model_root_path = root_path
            index = self._dir_model.setRootPath(root_path)
            self.dir_tree.setModel(self._dir_model)
            self.dir_tree.setRootIndex(index)
            for c in (1, 2, 3):
                self.dir_tree.hideColumn(c)

        def _filesystem_model_root(self, folder: Path) -> str:
            if sys.platform.startswith("win"):
                return folder.anchor or str(folder)
            return "/"

        def _set_filesystem_model_root(self, folder: Path) -> None:
            root_path = self._filesystem_model_root(folder)
            if getattr(self, "_dir_model_root_path", None) == root_path:
                return
            self._dir_model_root_path = root_path
            root_index = self._dir_model.setRootPath(root_path)
            self.dir_tree.setRootIndex(root_index)

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

        def _go_home_directory(self) -> None:
            self._set_current_directory(self._default_work_directory())

        def _slider(self, minimum: int, maximum: int, value: int, on_change, formatter):
            label = QtWidgets.QLabel(formatter(value))
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setRange(minimum, maximum)
            slider.setValue(value)
            slider.valueChanged.connect(lambda v: label.setText(formatter(v)))
            slider.valueChanged.connect(on_change)
            slider.sliderReleased.connect(self._on_slider_release)
            return slider, label

        def _render_adjustment_state(self) -> dict[str, Any]:
            return {
                "illuminant": self.combo_illuminant_render.currentText().strip(),
                "temperature_kelvin": int(self.spin_render_temperature.value()),
                "tint": float(self.spin_render_tint.value()),
                "brightness_ev": self.slider_brightness.value() / 100.0,
                "black_point": self.slider_black_point.value() / 1000.0,
                "white_point": self.slider_white_point.value() / 1000.0,
                "contrast": self.slider_contrast.value() / 100.0,
                "midtone": self.slider_midtone.value() / 100.0,
                "tone_curve_enabled": bool(self.check_tone_curve_enabled.isChecked()),
                "tone_curve_preset": self._tone_curve_preset_key(),
                "tone_curve_black_point": self.slider_tone_curve_black.value() / 1000.0,
                "tone_curve_white_point": self.slider_tone_curve_white.value() / 1000.0,
                "tone_curve_points": [
                    [float(x), float(y)]
                    for x, y in normalize_tone_curve_points(self.tone_curve_editor.points())
                ],
            }

        def _render_adjustment_kwargs_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
            return {
                "temperature_kelvin": float(state.get("temperature_kelvin", 5003.0)),
                "neutral_kelvin": 5003.0,
                "tint": float(state.get("tint", 0.0)),
                "brightness_ev": float(state.get("brightness_ev", 0.0)),
                "black_point": float(state.get("black_point", 0.0)),
                "white_point": float(max(float(state.get("black_point", 0.0)) + 0.001, float(state.get("white_point", 1.0)))),
                "contrast": float(state.get("contrast", 0.0)),
                "midtone": float(state.get("midtone", 1.0)),
                "tone_curve_points": state.get("tone_curve_points") if state.get("tone_curve_enabled") else None,
                "tone_curve_black_point": float(state.get("tone_curve_black_point", 0.0)),
                "tone_curve_white_point": float(
                    max(float(state.get("tone_curve_black_point", 0.0)) + 0.01, float(state.get("tone_curve_white_point", 1.0)))
                ),
            }

        def _render_adjustment_kwargs(self) -> dict[str, Any]:
            return self._render_adjustment_kwargs_from_state(self._render_adjustment_state())

        def _detail_adjustment_state(self) -> dict[str, Any]:
            return {
                "sharpen": int(self.slider_sharpen.value()),
                "radius": int(self.slider_radius.value()),
                "noise_luma": int(self.slider_noise_luma.value()),
                "noise_color": int(self.slider_noise_color.value()),
                "ca_red": int(self.slider_ca_red.value()),
                "ca_blue": int(self.slider_ca_blue.value()),
            }

        def _detail_adjustment_kwargs_from_state(self, state: dict[str, Any]) -> dict[str, float]:
            return {
                "denoise_luma": float(state.get("noise_luma", 0)) / 100.0,
                "denoise_color": float(state.get("noise_color", 0)) / 100.0,
                "sharpen_amount": float(state.get("sharpen", 0)) / 100.0,
                "sharpen_radius": float(state.get("radius", 10)) / 10.0,
                "lateral_ca_red_scale": 1.0 + float(state.get("ca_red", 0)) / 10000.0,
                "lateral_ca_blue_scale": 1.0 + float(state.get("ca_blue", 0)) / 10000.0,
            }

        def _apply_detail_adjustment_state(self, state: dict[str, Any]) -> None:
            self.slider_sharpen.setValue(int(state.get("sharpen", self.slider_sharpen.value())))
            self.slider_radius.setValue(int(state.get("radius", self.slider_radius.value())))
            self.slider_noise_luma.setValue(int(state.get("noise_luma", self.slider_noise_luma.value())))
            self.slider_noise_color.setValue(int(state.get("noise_color", self.slider_noise_color.value())))
            self.slider_ca_red.setValue(int(state.get("ca_red", self.slider_ca_red.value())))
            self.slider_ca_blue.setValue(int(state.get("ca_blue", self.slider_ca_blue.value())))

        def _apply_render_adjustment_state(self, state: dict[str, Any]) -> None:
            self._set_combo_text(
                self.combo_illuminant_render,
                str(state.get("illuminant") or self.combo_illuminant_render.currentText()),
            )
            self.spin_render_temperature.setValue(int(state.get("temperature_kelvin", self.spin_render_temperature.value())))
            self.spin_render_tint.setValue(float(state.get("tint", self.spin_render_tint.value())))
            self.slider_brightness.setValue(int(round(float(state.get("brightness_ev", 0.0)) * 100)))
            self.slider_black_point.setValue(int(round(float(state.get("black_point", 0.0)) * 1000)))
            self.slider_white_point.setValue(int(round(float(state.get("white_point", 1.0)) * 1000)))
            self.slider_contrast.setValue(int(round(float(state.get("contrast", 0.0)) * 100)))
            self.slider_midtone.setValue(int(round(float(state.get("midtone", 1.0)) * 100)))
            curve_enabled = bool(state.get("tone_curve_enabled", False))
            curve_preset = str(state.get("tone_curve_preset") or "linear")
            curve_points = self._coerce_tone_curve_points(state.get("tone_curve_points"))
            curve_black = float(state.get("tone_curve_black_point", 0.0))
            curve_white = float(state.get("tone_curve_white_point", 1.0))
            self._set_combo_data(self.combo_tone_curve_preset, curve_preset)
            self._set_tone_curve_range_controls(curve_black, curve_white)
            self.tone_curve_editor.set_points(
                curve_points or self._tone_curve_preset_points(curve_preset),
                emit=False,
            )
            self.check_tone_curve_enabled.setChecked(curve_enabled)
            self._set_tone_curve_controls_enabled(curve_enabled)

        def _ca_scale_factors(self) -> tuple[float, float]:
            return 1.0 + self.slider_ca_red.value() / 10000.0, 1.0 + self.slider_ca_blue.value() / 10000.0

        def _apply_output_adjustments(
            self,
            image: np.ndarray,
            *,
            denoise_luma: float,
            denoise_color: float,
            sharpen_amount: float,
            sharpen_radius: float,
            lateral_ca_red_scale: float,
            lateral_ca_blue_scale: float,
            render_adjustments: dict[str, Any],
        ) -> np.ndarray:
            adjusted = apply_adjustments(
                image,
                denoise_luminance=denoise_luma,
                denoise_color=denoise_color,
                sharpen_amount=sharpen_amount,
                sharpen_radius=sharpen_radius,
                lateral_ca_red_scale=lateral_ca_red_scale,
                lateral_ca_blue_scale=lateral_ca_blue_scale,
            )
            return apply_render_adjustments(adjusted, **render_adjustments)

        def _detail_cache_key(
            self,
            *,
            denoise_luma: float,
            denoise_color: float,
            sharpen_amount: float,
            sharpen_radius: float,
            lateral_ca_red_scale: float,
            lateral_ca_blue_scale: float,
        ) -> str:
            source_key = self._last_loaded_preview_key or str(id(self._original_linear))
            return "|".join(
                [
                    source_key,
                    f"nl={denoise_luma:.5f}",
                    f"nc={denoise_color:.5f}",
                    f"sh={sharpen_amount:.5f}",
                    f"sr={sharpen_radius:.5f}",
                    f"cr={lateral_ca_red_scale:.7f}",
                    f"cb={lateral_ca_blue_scale:.7f}",
                ]
            )

        def _detail_adjusted_preview(
            self,
            image: np.ndarray,
            *,
            denoise_luma: float,
            denoise_color: float,
            sharpen_amount: float,
            sharpen_radius: float,
            lateral_ca_red_scale: float,
            lateral_ca_blue_scale: float,
        ) -> np.ndarray:
            key = self._detail_cache_key(
                denoise_luma=denoise_luma,
                denoise_color=denoise_color,
                sharpen_amount=sharpen_amount,
                sharpen_radius=sharpen_radius,
                lateral_ca_red_scale=lateral_ca_red_scale,
                lateral_ca_blue_scale=lateral_ca_blue_scale,
            )
            if self._detail_adjustment_cache_key == key and self._detail_adjusted_linear is not None:
                return self._detail_adjusted_linear

            adjusted = apply_adjustments(
                image,
                denoise_luminance=denoise_luma,
                denoise_color=denoise_color,
                sharpen_amount=sharpen_amount,
                sharpen_radius=sharpen_radius,
                lateral_ca_red_scale=lateral_ca_red_scale,
                lateral_ca_blue_scale=lateral_ca_blue_scale,
            )
            self._detail_adjusted_linear = adjusted
            self._detail_adjustment_cache_key = key
            return adjusted

        def _original_srgb_preview(self) -> np.ndarray:
            source_key = self._last_loaded_preview_key or str(id(self._original_linear))
            if self._original_srgb_cache_key == source_key and self._original_srgb_cache is not None:
                return self._original_srgb_cache
            if self._original_linear is None:
                raise RuntimeError("No hay imagen original cargada para preview.")
            srgb = linear_to_srgb_display(self._original_linear)
            self._original_srgb_cache = srgb
            self._original_srgb_cache_key = source_key
            return srgb

        def _display_profile_stamp(self) -> str:
            profile_path = self._active_display_profile_path()
            if profile_path is None:
                return "none"
            try:
                resolved = profile_path.expanduser().resolve()
                st = resolved.stat()
                return f"{resolved}|{st.st_mtime_ns}|{st.st_size}"
            except OSError:
                return str(profile_path)

        def _original_display_u8_preview(self, *, bypass_profile: bool) -> np.ndarray:
            source_key = self._last_loaded_preview_key or str(id(self._original_linear))
            key = f"{source_key}|{self._display_profile_stamp()}|bypass={int(bool(bypass_profile))}"
            if self._original_display_u8_cache_key == key and self._original_display_u8_cache is not None:
                return self._original_display_u8_cache
            srgb = self._original_srgb_preview()
            u8 = self._display_u8_for_screen(srgb, bypass_profile=bypass_profile)
            self._original_display_u8_cache = u8
            self._original_display_u8_cache_key = key
            return u8

        def _clear_adjustment_caches(self) -> None:
            self._detail_adjusted_linear = None
            self._detail_adjustment_cache_key = None
            self._original_srgb_cache = None
            self._original_srgb_cache_key = None
            self._original_display_u8_cache = None
            self._original_display_u8_cache_key = None
            self._original_compare_panel_key = None

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
            start = target.text().strip() or str(self._current_dir)
            if dir_mode:
                path = QtWidgets.QFileDialog.getExistingDirectory(self, "Selecciona directorio", start)
                if path:
                    target.setText(path)
                    target.editingFinished.emit()
                return
            if save_mode:
                path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar como", start)
                if path:
                    target.setText(path)
                    target.editingFinished.emit()
                return
            if file_mode:
                path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Selecciona archivo", start)
                if path:
                    target.setText(path)
                    target.editingFinished.emit()

        def _detect_display_profile(self) -> None:
            detected = detect_system_display_profile()
            if detected is None:
                QtWidgets.QMessageBox.information(
                    self,
                    "Info",
                    "No se pudo detectar automaticamente el perfil ICC del monitor. Seleccionalo manualmente.",
                )
                return
            self.path_display_profile.setText(str(detected))
            self.check_display_color_management.setChecked(True)
            self._on_display_color_settings_changed()

        def _ensure_display_profile_if_enabled(self) -> None:
            if not hasattr(self, "check_display_color_management") or not hasattr(self, "path_display_profile"):
                return
            if not self.check_display_color_management.isChecked():
                return
            if self.path_display_profile.text().strip():
                return
            detected = detect_system_display_profile()
            if detected is not None:
                self.path_display_profile.setText(str(detected))

        def _on_display_color_settings_changed(self, *_args) -> None:
            if not hasattr(self, "check_display_color_management"):
                return
            self._ensure_display_profile_if_enabled()

            self._settings.setValue(
                "display/color_management_enabled",
                bool(self.check_display_color_management.isChecked()),
            )
            self._settings.setValue("display/monitor_profile", self.path_display_profile.text().strip())
            self._display_color_error_key = None
            self._image_thumb_cache.clear()
            self._original_display_u8_cache = None
            self._original_display_u8_cache_key = None
            self._original_compare_panel_key = None
            self._update_display_profile_status()
            if self._preview_srgb is not None and self._original_linear is not None:
                self._refresh_preview()
            if hasattr(self, "file_list"):
                self._queue_thumbnail_generation(self._file_list_paths(), delay_ms=0)

        def _active_display_profile_path(self) -> Path | None:
            if not hasattr(self, "check_display_color_management"):
                return None
            if not self.check_display_color_management.isChecked():
                return None
            text = self.path_display_profile.text().strip()
            if not text:
                return None
            return Path(text).expanduser()

        def _display_u8_for_screen(self, image_srgb: np.ndarray, *, bypass_profile: bool = False) -> np.ndarray:
            if bypass_profile:
                return srgb_to_display_u8(image_srgb, None)
            profile_path = self._active_display_profile_path()
            try:
                return srgb_to_display_u8(image_srgb, profile_path)
            except Exception as exc:
                key = f"{profile_path}|{exc}"
                if self._display_color_error_key != key:
                    self._display_color_error_key = key
                    self._log_preview(f"Aviso: gestion ICC de monitor desactivada para esta vista: {exc}")
                    self._update_display_profile_status(error=str(exc))
                return srgb_to_display_u8(image_srgb, None)

        def _thumbnail_u8_for_screen(self, rgb_u8: np.ndarray) -> np.ndarray:
            profile_path = self._active_display_profile_path()
            try:
                return srgb_u8_to_display_u8(rgb_u8, profile_path)
            except Exception:
                return srgb_u8_to_display_u8(rgb_u8, None)

        def _set_preview_panel_image(
            self,
            panel: ImagePanel,
            image_srgb: np.ndarray,
            *,
            bypass_profile: bool = False,
        ) -> None:
            panel.set_rgb_u8_image(self._display_u8_for_screen(image_srgb, bypass_profile=bypass_profile))

        def _compare_view_active(self) -> bool:
            return bool(
                hasattr(self, "viewer_stack")
                and hasattr(self, "chk_compare")
                and self.chk_compare.isChecked()
                and int(self.viewer_stack.currentIndex()) == 1
            )

        def _set_result_display_u8(self, display_u8: np.ndarray, *, compare_enabled: bool) -> None:
            if bool(compare_enabled and self._compare_view_active()):
                self.image_result_compare.set_rgb_u8_image(display_u8)
                self._apply_clip_overlay_to_panel(self.image_result_compare, display_u8)
            else:
                self.image_result_single.set_rgb_u8_image(display_u8)
                self._apply_clip_overlay_to_panel(self.image_result_single, display_u8)
            self._update_viewer_histogram(display_u8)

        def _ensure_original_compare_panel(self, *, bypass_profile: bool) -> None:
            if self._original_linear is None:
                return
            source_key = self._last_loaded_preview_key or str(id(self._original_linear))
            key = f"{source_key}|{self._display_profile_stamp()}|bp={int(bool(bypass_profile))}"
            if self._original_compare_panel_key == key:
                if bool(hasattr(self, "check_image_clip_overlay") and self.check_image_clip_overlay.isChecked()):
                    self._apply_clip_overlay_to_panel(
                        self.image_original_compare,
                        self._original_display_u8_preview(bypass_profile=bypass_profile),
                    )
                return
            original_display_u8 = self._original_display_u8_preview(bypass_profile=bypass_profile)
            self.image_original_compare.set_rgb_u8_image(original_display_u8)
            self._apply_clip_overlay_to_panel(self.image_original_compare, original_display_u8)
            self._original_compare_panel_key = key

        def _update_display_profile_status(self, *, error: str | None = None) -> None:
            if not hasattr(self, "display_profile_status"):
                return
            if error:
                self.display_profile_status.setText("Monitor: error de perfil; mostrando sRGB")
                return
            profile_path = self._active_display_profile_path()
            if profile_path is None:
                if hasattr(self, "check_display_color_management") and not self.check_display_color_management.isChecked():
                    self.display_profile_status.setText("Monitor: gestion ICC desactivada")
                else:
                    self.display_profile_status.setText("Monitor: sRGB (sin perfil de sistema detectado)")
                return
            if not profile_path.exists():
                self.display_profile_status.setText(f"Monitor: perfil no encontrado ({profile_path.name})")
                return
            self.display_profile_status.setText(f"Monitor: {display_profile_label(profile_path)}")

        def _initialize_session_tab_defaults(self) -> None:
            suggested = (self._current_dir / "nexoraw_session").resolve()
            self.session_root_path.setText(str(suggested))
            self.session_name_edit.setText(suggested.name)
            self._populate_session_directory_fields(self._session_paths_from_root(suggested))

        def _session_paths_from_root(self, root: Path) -> dict[str, Path]:
            absolute = root.expanduser().resolve()
            return {
                "root": absolute,
                "config": absolute / "00_configuraciones",
                "raw": absolute / "01_ORG",
                "exports": absolute / "02_DRV",
                "charts": absolute / "01_ORG",
                "profiles": absolute / "00_configuraciones" / "profiles",
                "work": absolute / "00_configuraciones" / "work",
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

        def _session_relative_or_absolute(self, path: Path | str | None) -> str:
            if path is None:
                return ""
            candidate = Path(str(path)).expanduser()
            if self._active_session_root is not None:
                try:
                    root = self._active_session_root.expanduser().resolve(strict=False)
                    resolved = candidate.resolve(strict=False)
                    return resolved.relative_to(root).as_posix()
                except Exception:
                    pass
            return str(candidate)

        def _session_stored_path(self, value: Any) -> Path | None:
            text = str(value or "").strip()
            if not text:
                return None
            candidate = Path(text).expanduser()
            if candidate.is_absolute() or self._active_session_root is None:
                return candidate
            return self._active_session_root / candidate

        def _session_reference_source_dirs(self, *, paths: dict[str, Path] | None = None) -> list[tuple[str, Path]]:
            if paths is None:
                paths = self._session_paths_from_root(self._active_session_root) if self._active_session_root else {}
                if isinstance(self._active_session_payload, dict) and isinstance(
                    self._active_session_payload.get("directories"),
                    dict,
                ):
                    paths = {
                        key: Path(str(value)).expanduser()
                        for key, value in self._active_session_payload["directories"].items()
                        if isinstance(value, str) and value.strip()
                    }
            seen: set[str] = set()
            result: list[tuple[str, Path]] = []
            for key in ("raw", "charts"):
                p = paths.get(key)
                if p is None:
                    continue
                try:
                    marker = str(p.expanduser().resolve(strict=False))
                except Exception:
                    marker = str(p)
                if marker in seen:
                    continue
                seen.add(marker)
                result.append((key, p))
            return result

        def _preferred_profile_reference_dir(self, *, paths: dict[str, Path] | None = None) -> Path | None:
            for key, candidate in self._session_reference_source_dirs(paths=paths):
                if candidate.exists() and candidate.is_dir():
                    if self._directory_has_chart_captures(candidate) or key == "raw":
                        return candidate
            return None

        def _profile_reference_rejection_reason(
            self,
            path: Path,
            *,
            paths: dict[str, Path] | None = None,
        ) -> str | None:
            if paths is None:
                paths = {}
                if self._active_session_root is not None:
                    paths.update(self._session_paths_from_root(self._active_session_root))
                if isinstance(self._active_session_payload, dict) and isinstance(
                    self._active_session_payload.get("directories"),
                    dict,
                ):
                    paths.update(
                        {
                            key: Path(str(value)).expanduser()
                            for key, value in self._active_session_payload["directories"].items()
                            if isinstance(value, str) and value.strip()
                        }
                    )

            for key, label in PROFILE_REFERENCE_FORBIDDEN_DIRS.items():
                root = paths.get(key)
                if root is not None and self._path_is_inside(path, root):
                    return f"{label} de la sesion"
            return None

        def _profile_status_for_path(self, profile_path: Path) -> str | None:
            sidecars = [profile_path.with_suffix(".profile.json")]
            if self._active_session_root is not None:
                defaults = self._session_default_outputs()
                sidecars.append(defaults["profile_report"])

            for sidecar in sidecars:
                try:
                    if not sidecar.exists():
                        continue
                    data = json.loads(sidecar.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                if sidecar.name == "profile_report.json":
                    reported = str(data.get("output_icc") or "").strip()
                    if not reported:
                        continue
                    try:
                        if Path(reported).expanduser().resolve(strict=False) != profile_path.expanduser().resolve(strict=False):
                            continue
                    except Exception:
                        continue
                metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
                candidates = [
                    data.get("profile_status"),
                    data.get("session_profile_status"),
                    metadata.get("profile_status"),
                    metadata.get("session_profile_status"),
                ]
                for candidate in candidates:
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate.strip().lower()
                    if isinstance(candidate, dict):
                        status = str(candidate.get("status") or "").strip().lower()
                        if status:
                            return status
            return None

        def _profile_can_be_active(self, profile_path: Path) -> bool:
            if not profile_path.exists():
                return False
            status = self._profile_status_for_path(profile_path)
            return status not in {"rejected", "expired"}

        def _filter_profile_reference_files(
            self,
            files: list[Path],
            *,
            paths: dict[str, Path] | None = None,
        ) -> tuple[list[Path], list[tuple[Path, str]]]:
            accepted: list[Path] = []
            rejected: list[tuple[Path, str]] = []
            seen: set[str] = set()
            for path in files:
                if path.suffix.lower() not in PROFILE_CHART_EXTENSIONS:
                    continue
                reason = self._profile_reference_rejection_reason(path, paths=paths)
                if reason is not None:
                    rejected.append((path, reason))
                    continue
                try:
                    key = str(path.expanduser().resolve(strict=False))
                except Exception:
                    key = str(path.expanduser())
                if key in seen:
                    continue
                seen.add(key)
                accepted.append(path)
            return accepted, rejected

        def _set_profile_reference_dir(self, folder: Path) -> bool:
            reason = self._profile_reference_rejection_reason(folder)
            if reason is None:
                self.profile_charts_dir.setText(str(folder))
                return True

            fallback = self._preferred_profile_reference_dir()
            if fallback is not None:
                self.profile_charts_dir.setText(str(fallback))
                self._set_status(
                    f"No se usan {reason} como referencias colorimetricas; se usa {fallback}"
                )
                return False

            self._set_status(f"No se usan {reason} como referencias colorimetricas.")
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
            if not text or self._is_legacy_temp_output_path(text):
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

        def _session_state_dir_or_default(
            self,
            value: Any,
            default: Path,
            *,
            root: Path | None = None,
        ) -> Path:
            candidate = self._session_state_path_or_default(value, default)
            session_root = root or self._active_session_root
            if session_root is not None and not self._path_is_inside(candidate, session_root):
                return default.expanduser()
            return candidate

        def _is_legacy_temp_output_path(self, value: Any) -> bool:
            text = str(value or "").strip()
            if not text:
                return False
            candidate = Path(text).expanduser()
            try:
                resolved = candidate.resolve(strict=False)
                temp_root = Path(tempfile.gettempdir()).resolve(strict=False)
                if resolved == temp_root or temp_root in resolved.parents:
                    return True
            except Exception:
                pass
            return candidate.name in LEGACY_TEMP_OUTPUT_NAMES

        def _session_output_path_or_default(self, value: Any, default: Path) -> Path:
            text = str(value or "").strip()
            default = default.expanduser()
            if not text or self._is_legacy_temp_output_path(text):
                return default

            candidate = Path(text).expanduser()
            try:
                if candidate.resolve(strict=False) == Path.home().resolve(strict=False):
                    return default
            except Exception:
                return default
            return candidate

        def _session_default_outputs(
            self,
            *,
            paths: dict[str, Path] | None = None,
            session_name: str | None = None,
        ) -> dict[str, Path]:
            if paths is None:
                if isinstance(self._active_session_payload, dict) and isinstance(
                    self._active_session_payload.get("directories"),
                    dict,
                ):
                    paths = {
                        k: Path(v)
                        for k, v in self._active_session_payload["directories"].items()
                        if isinstance(v, str)
                    }
                elif self._active_session_root is not None:
                    paths = self._session_paths_from_root(self._active_session_root)
                else:
                    paths = {}

            root = paths.get("root", self._active_session_root or Path.cwd())
            exports_dir = paths.get("exports", root / "02_DRV")
            profiles_dir = paths.get("profiles", root / "00_configuraciones" / "profiles")
            config_dir = paths.get("config", root / "00_configuraciones")
            work_dir = paths.get("work", root / "00_configuraciones" / "work")

            safe_name = (session_name or self.session_name_edit.text().strip() or root.name or "session").strip()
            return {
                "profile_out": profiles_dir / f"{safe_name}.icc",
                "profile_report": config_dir / "profile_report.json",
                "workdir": work_dir / "profile_generation",
                "development_profile": config_dir / "development_profile.json",
                "calibrated_recipe": config_dir / "recipe_calibrated.yml",
                "recipe": config_dir / "recipe.yml",
                "preview": exports_dir / "preview.png",
                "tiff_dir": exports_dir,
            }

        def _ensure_session_output_controls(self) -> None:
            defaults = self._session_default_outputs()
            replacements = [
                (self.profile_out_path_edit, defaults["profile_out"]),
                (self.path_profile_out, defaults["profile_out"]),
                (self.profile_report_out, defaults["profile_report"]),
                (self.profile_workdir, defaults["workdir"]),
                (self.develop_profile_out, defaults["development_profile"]),
                (self.calibrated_recipe_out, defaults["calibrated_recipe"]),
                (self.path_recipe, defaults["calibrated_recipe"]),
                (self.path_preview_png, defaults["preview"]),
                (self.batch_out_dir, defaults["tiff_dir"]),
            ]
            for widget, default in replacements:
                current = widget.text().strip()
                if not current or self._is_legacy_temp_output_path(current):
                    widget.setText(str(default))
            if self.path_profile_out.text().strip() != self.profile_out_path_edit.text().strip():
                self.path_profile_out.setText(self.profile_out_path_edit.text().strip())

        def _preferred_session_start_directory(self, directories: dict[str, Any], state: dict[str, Any]) -> Path:
            root = self._active_session_root or Path.cwd()
            paths = {
                k: Path(str(v)).expanduser()
                for k, v in directories.items()
                if isinstance(v, (str, Path)) and str(v).strip()
            }

            charts_default = paths.get("charts", root)
            raw_default = paths.get("raw", root)
            charts_state = self._session_state_dir_or_default(
                state.get("profile_charts_dir"),
                charts_default,
                root=root,
            )
            raw_state = self._session_state_dir_or_default(
                state.get("batch_input_dir"),
                raw_default,
                root=root,
            )

            candidates: list[Path] = []
            for chart_file in self._selected_chart_files:
                if chart_file.exists() and chart_file.is_file():
                    candidates.append(chart_file.parent)
                    break
            candidates.extend([raw_state, charts_state, raw_default, charts_default, root])

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
            if (
                self._should_replace_operational_dir(self.profile_charts_dir.text(), folder)
                and self._profile_reference_rejection_reason(folder) is None
            ):
                self.profile_charts_dir.setText(str(folder))
            if self._should_replace_operational_dir(self.batch_input_dir.text(), folder):
                self.batch_input_dir.setText(str(folder))

        def _profile_timestamp(self) -> str:
            return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        def _slug_for_development_profile(self, name: str) -> str:
            raw = "".join(ch.lower() if ch.isalnum() else "-" for ch in name.strip())
            slug = "-".join(part for part in raw.split("-") if part) or "perfil"
            return slug[:48]

        def _unique_development_profile_id(self, name: str) -> str:
            base = self._slug_for_development_profile(name)
            existing = {str(profile.get("id") or "") for profile in self._development_profiles}
            if base not in existing:
                return base
            index = 2
            while f"{base}-{index}" in existing:
                index += 1
            return f"{base}-{index}"

        def _development_profile_dir(self, profile_id: str) -> Path:
            root = self._active_session_root or Path(self.session_root_path.text().strip() or Path.cwd())
            return self._session_paths_from_root(root)["config"] / "development_profiles" / profile_id

        def _session_generic_profile_dir(self) -> Path | None:
            root = self._active_session_root
            if root is None and hasattr(self, "session_root_path"):
                text = self.session_root_path.text().strip()
                root = Path(text).expanduser() if text else None
            if root is None:
                return None
            return self._session_paths_from_root(Path(root).expanduser())["profiles"] / "generic"

        def _render_profile_path_for_recipe(
            self,
            recipe: Recipe,
            *,
            input_profile_path: Path | None,
            color_management_mode: str,
        ) -> Path | None:
            try:
                return profile_path_for_render_settings(
                    recipe,
                    input_profile_path=input_profile_path,
                    color_management_mode=color_management_mode,
                    generic_profile_dir=self._session_generic_profile_dir(),
                )
            except Exception:
                return input_profile_path

        def _configured_color_profile_for_recipe(self, recipe: Recipe) -> tuple[Path | None, Path | None, str]:
            input_profile_path = self._active_session_icc_for_settings()
            if is_generic_output_space(recipe.output_space):
                output_profile = ensure_generic_output_profile(
                    recipe.output_space,
                    directory=self._session_generic_profile_dir(),
                )
                mode = (
                    f"assigned_{generic_output_profile(recipe.output_space).key}_output_icc"
                    if input_profile_path is None
                    else f"converted_{generic_output_profile(recipe.output_space).key}"
                )
                if generic_output_profile(recipe.output_space).key == "srgb" and input_profile_path is not None:
                    mode = "converted_srgb"
                return input_profile_path, output_profile, mode
            if input_profile_path is not None:
                return input_profile_path, input_profile_path, "camera_rgb_with_input_icc"
            return None, None, "no_profile"

        def _development_profile_by_id(self, profile_id: str) -> dict[str, Any] | None:
            for profile in self._development_profiles:
                if str(profile.get("id") or "") == profile_id:
                    return profile
            return None

        @staticmethod
        def _adjustment_profile_type_for_kind(kind: str) -> str:
            return "advanced" if str(kind or "").strip().lower() in {"chart", "advanced"} else "basic"

        def _development_profile_label(self, profile_id: str) -> str:
            if not profile_id:
                return "Actual"
            profile = self._development_profile_by_id(profile_id)
            if profile is None:
                return profile_id
            return str(profile.get("name") or profile_id)

        def _refresh_development_profile_combo(self) -> None:
            if not hasattr(self, "development_profile_combo"):
                return
            current = self._active_development_profile_id
            self.development_profile_combo.blockSignals(True)
            self.development_profile_combo.clear()
            self.development_profile_combo.addItem("Ajustes actuales", "")
            for profile in self._development_profiles:
                profile_id = str(profile.get("id") or "").strip()
                if not profile_id:
                    continue
                label = str(profile.get("name") or profile_id)
                kind = str(profile.get("kind") or "manual")
                self.development_profile_combo.addItem(f"{label} ({kind})", profile_id)
            index = self.development_profile_combo.findData(current)
            self.development_profile_combo.setCurrentIndex(index if index >= 0 else 0)
            self.development_profile_combo.blockSignals(False)
            if hasattr(self, "development_profile_status_label"):
                active = self._development_profile_label(current)
                self.development_profile_status_label.setText(
                    f"Perfiles de ajuste: {len(self._development_profiles)} | Activo: {active}"
                )

        def _on_development_output_space_changed(self) -> None:
            if not hasattr(self, "development_output_space_combo") or not hasattr(self, "combo_output_space"):
                return
            output_space = str(self.development_output_space_combo.currentData() or "scene_linear_camera_rgb")
            self._set_combo_text(self.combo_output_space, output_space)
            if output_space == "scene_linear_camera_rgb":
                self.check_output_linear.setChecked(True)
                self._set_combo_data(self.combo_tone_curve, "linear")
            elif output_space == "srgb":
                self.check_output_linear.setChecked(False)
                self._set_combo_data(self.combo_tone_curve, "srgb")
            else:
                self.check_output_linear.setChecked(False)
                self._set_combo_data(self.combo_tone_curve, "gamma")
                self.spin_gamma.setValue(1.8 if output_space == "prophoto_rgb" else 2.2)
            if self._original_linear is not None:
                self._schedule_preview_refresh()

        def _sync_development_output_space_combo(self, output_space: str) -> None:
            if not hasattr(self, "development_output_space_combo"):
                return
            target = output_space if is_generic_output_space(output_space) else "scene_linear_camera_rgb"
            index = self.development_output_space_combo.findData(target)
            if index >= 0 and self.development_output_space_combo.currentIndex() != index:
                self.development_output_space_combo.blockSignals(True)
                self.development_output_space_combo.setCurrentIndex(index)
                self.development_output_space_combo.blockSignals(False)

        def _register_development_profile(self, descriptor: dict[str, Any], *, activate: bool = True) -> None:
            profile_id = str(descriptor.get("id") or "").strip()
            if not profile_id:
                return
            now = self._profile_timestamp()
            descriptor = dict(descriptor)
            descriptor.setdefault("created_at", now)
            descriptor["updated_at"] = now
            replaced = False
            for idx, existing in enumerate(self._development_profiles):
                if str(existing.get("id") or "") == profile_id:
                    merged = dict(existing)
                    merged.update(descriptor)
                    self._development_profiles[idx] = merged
                    replaced = True
                    break
            if not replaced:
                self._development_profiles.append(descriptor)
            self._development_profiles.sort(key=lambda item: str(item.get("name") or item.get("id") or ""))
            if activate:
                self._active_development_profile_id = profile_id
            self._refresh_development_profile_combo()
            self._save_active_session(silent=True)

        def _development_profile_manifest(self, profile: dict[str, Any]) -> dict[str, Any]:
            manifest_path = self._session_stored_path(profile.get("manifest_path"))
            if manifest_path is None or not manifest_path.exists():
                return {}
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                return payload if isinstance(payload, dict) else {}
            except Exception:
                return {}

        def _development_profile_recipe(self, profile: dict[str, Any], manifest: dict[str, Any]) -> Recipe:
            recipe_path = self._session_stored_path(profile.get("recipe_path") or manifest.get("render_recipe_path"))
            if recipe_path is not None and recipe_path.exists():
                return load_recipe(recipe_path)
            recipe_payload = manifest.get("recipe") or manifest.get("calibrated_recipe")
            if isinstance(recipe_payload, dict):
                allowed = set(Recipe.__dataclass_fields__.keys())
                filtered = {k: v for k, v in recipe_payload.items() if k in allowed}
                return Recipe(**filtered)
            return self._build_effective_recipe()

        def _development_profile_settings(self, profile_id: str) -> dict[str, Any]:
            profile = self._development_profile_by_id(profile_id) if profile_id else None
            if profile is None:
                detail_state = self._detail_adjustment_state()
                render_state = self._render_adjustment_state()
                profile_path = self._active_session_icc_for_settings()
                return {
                    "id": "",
                    "name": "Ajustes actuales",
                    "kind": "manual",
                    "profile_type": "basic",
                    "recipe": self._build_effective_recipe(),
                    "detail_adjustments": detail_state,
                    "render_adjustments": render_state,
                    "icc_profile_path": profile_path,
                    "output_icc_profile_path": None,
                }

            manifest = self._development_profile_manifest(profile)
            detail_state = manifest.get("detail_adjustments") if isinstance(manifest.get("detail_adjustments"), dict) else {}
            render_state = manifest.get("render_adjustments") if isinstance(manifest.get("render_adjustments"), dict) else {}
            icc_profile_path = self._session_stored_path(profile.get("icc_profile_path") or manifest.get("icc_profile_path"))
            output_icc_profile_path = self._session_stored_path(
                profile.get("output_icc_profile_path") or manifest.get("output_icc_profile_path")
            )
            kind = str(profile.get("kind") or manifest.get("kind") or "manual")
            profile_type = str(profile.get("profile_type") or manifest.get("profile_type") or "")
            if profile_type not in {"advanced", "basic"}:
                profile_type = self._adjustment_profile_type_for_kind(kind)
            return {
                "id": str(profile.get("id") or ""),
                "name": str(profile.get("name") or profile.get("id") or ""),
                "kind": kind,
                "profile_type": profile_type,
                "recipe": self._development_profile_recipe(profile, manifest),
                "detail_adjustments": detail_state or self._detail_adjustment_state(),
                "render_adjustments": render_state or self._render_adjustment_state(),
                "icc_profile_path": icc_profile_path,
                "output_icc_profile_path": output_icc_profile_path,
            }

        def _recipe_from_payload(self, payload: Any) -> Recipe | None:
            if not isinstance(payload, dict):
                return None
            try:
                allowed = set(Recipe.__dataclass_fields__.keys())
                filtered = {k: v for k, v in payload.items() if k in allowed}
                return Recipe(**filtered)
            except Exception:
                return None

        def _development_profile_from_sidecar(self, path: Path) -> str:
            try:
                payload = load_raw_sidecar(path)
            except Exception:
                return ""
            profile = payload.get("development_profile") if isinstance(payload, dict) else {}
            profile_id = str(profile.get("id") or "") if isinstance(profile, dict) else ""
            if profile_id and self._development_profile_by_id(profile_id) is not None:
                return profile_id
            return ""

        def _development_profile_payload_for_active_settings(self) -> dict[str, str]:
            profile_id = self._active_development_profile_id
            if not profile_id and hasattr(self, "development_profile_combo"):
                profile_id = str(self.development_profile_combo.currentData() or "")
            profile = self._development_profile_by_id(profile_id) if profile_id else None
            if profile is None:
                return {"id": "", "name": "Ajustes actuales", "kind": "manual", "profile_type": "basic"}
            kind = str(profile.get("kind") or "manual")
            return {
                "id": profile_id,
                "name": str(profile.get("name") or profile_id),
                "kind": kind,
                "profile_type": str(profile.get("profile_type") or self._adjustment_profile_type_for_kind(kind)),
            }

        def _profile_payload_from_development_settings(self, settings: dict[str, Any]) -> dict[str, str]:
            kind = str(settings.get("kind") or "manual")
            profile_type = str(settings.get("profile_type") or self._adjustment_profile_type_for_kind(kind))
            return {
                "id": str(settings.get("id") or ""),
                "name": str(settings.get("name") or "Ajustes actuales"),
                "kind": kind,
                "profile_type": profile_type,
            }

        def _render_profile_and_mode_for_development_settings(
            self,
            settings: dict[str, Any],
        ) -> tuple[Path | None, str]:
            recipe = settings["recipe"]
            input_profile = settings.get("icc_profile_path") if isinstance(settings.get("icc_profile_path"), Path) else None
            if is_generic_output_space(recipe.output_space):
                rendered_profile = ensure_generic_output_profile(
                    recipe.output_space,
                    directory=self._session_generic_profile_dir(),
                )
                generic_key = generic_output_profile(recipe.output_space).key
                if input_profile is not None:
                    mode = "converted_srgb" if generic_key == "srgb" else f"converted_{generic_key}"
                else:
                    mode = f"assigned_{generic_key}_output_icc"
                return rendered_profile, mode
            return input_profile, "camera_rgb_with_input_icc" if input_profile is not None else "no_profile"

        def _assign_development_profile_to_raw_files(
            self,
            profile_id: str,
            files: list[Path],
            *,
            status: str = "assigned",
        ) -> int:
            if not profile_id:
                return 0
            settings = self._development_profile_settings(profile_id)
            rendered_profile, mode = self._render_profile_and_mode_for_development_settings(settings)
            development_profile = self._profile_payload_from_development_settings(settings)
            written = 0
            for path in files:
                if path.suffix.lower() not in RAW_EXTENSIONS:
                    continue
                sidecar = self._write_raw_settings_sidecar(
                    path,
                    recipe=settings["recipe"],
                    development_profile=development_profile,
                    detail_adjustments=settings["detail_adjustments"],
                    render_adjustments=settings["render_adjustments"],
                    profile_path=rendered_profile,
                    color_management_mode=mode,
                    status=status,
                )
                if sidecar is not None:
                    written += 1
            if written:
                self._refresh_color_reference_thumbnail_markers()
            return written

        def _active_session_icc_for_settings(self) -> Path | None:
            if not hasattr(self, "path_profile_active") or not hasattr(self, "chk_apply_profile"):
                return None
            if not self.chk_apply_profile.isChecked():
                return None
            text = self.path_profile_active.text().strip()
            if not text:
                return None
            path = Path(text).expanduser()
            return path if path.exists() else None

        def _write_current_development_settings_to_raw(self, path: Path, *, status: str = "configured") -> Path | None:
            recipe = self._build_effective_recipe()
            _input_profile, rendered_profile, mode = self._configured_color_profile_for_recipe(recipe)
            sidecar = self._write_raw_settings_sidecar(
                path,
                recipe=recipe,
                development_profile=self._development_profile_payload_for_active_settings(),
                detail_adjustments=self._detail_adjustment_state(),
                render_adjustments=self._render_adjustment_state(),
                profile_path=rendered_profile,
                color_management_mode=mode,
                status=status,
            )
            if sidecar is not None:
                self._refresh_color_reference_thumbnail_markers()
            return sidecar

        def _raw_sidecar_development_summary(self, path: Path) -> str:
            try:
                payload = load_raw_sidecar(path)
            except Exception:
                return ""
            profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
            profile_type = self._adjustment_profile_type_from_sidecar(payload)
            name = str(profile.get("name") or profile.get("id") or "").strip()
            status = str(payload.get("status") or "").strip()
            label = "Perfil de ajuste avanzado" if profile_type == "advanced" else "Perfil de ajuste básico"
            if name:
                return f"{label}: {name}"
            if isinstance(payload.get("recipe"), dict):
                return f"{label} guardado"
            return f"Mochila NexoRAW: {status}" if status else ""

        def _has_raw_development_settings(self, path: Path) -> bool:
            if path.suffix.lower() not in RAW_EXTENSIONS:
                return False
            return bool(self._raw_sidecar_development_summary(path))

        def _adjustment_profile_type_from_sidecar(self, payload: dict[str, Any]) -> str:
            profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
            profile_type = str(profile.get("profile_type") or "").strip().lower()
            if profile_type in {"advanced", "basic"}:
                return profile_type
            kind = str(profile.get("kind") or "").strip().lower()
            if kind in {"chart", "advanced"}:
                return "advanced"
            return "basic" if isinstance(payload.get("recipe"), dict) else ""

        def _raw_adjustment_profile_type(self, path: Path) -> str:
            if path.suffix.lower() not in RAW_EXTENSIONS:
                return ""
            try:
                payload = load_raw_sidecar(path)
            except Exception:
                return ""
            return self._adjustment_profile_type_from_sidecar(payload)

        def _development_settings_payload_from_sidecar(self, source: Path, sidecar: dict[str, Any]) -> dict[str, Any]:
            return {
                "source": str(source),
                "recipe": sidecar.get("recipe") if isinstance(sidecar.get("recipe"), dict) else {},
                "development_profile": sidecar.get("development_profile")
                if isinstance(sidecar.get("development_profile"), dict)
                else {},
                "detail_adjustments": sidecar.get("detail_adjustments")
                if isinstance(sidecar.get("detail_adjustments"), dict)
                else {},
                "render_adjustments": sidecar.get("render_adjustments")
                if isinstance(sidecar.get("render_adjustments"), dict)
                else {},
                "color_management": sidecar.get("color_management")
                if isinstance(sidecar.get("color_management"), dict)
                else {},
            }

        def _selected_or_current_file_paths(self) -> list[Path]:
            files = self._collect_selected_file_paths()
            if files:
                return files
            if self._selected_file is not None and self._selected_file.exists():
                return [self._selected_file]
            return []

        def _save_current_development_settings_to_selected(self) -> None:
            files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
            if not files:
                QtWidgets.QMessageBox.information(self, "Info", "Selecciona uno o más RAW para guardar un perfil básico.")
                return
            written = 0
            for path in files:
                if self._write_current_development_settings_to_raw(path) is not None:
                    written += 1
            if self._selected_file is not None and any(self._normalized_path_key(self._selected_file) == self._normalized_path_key(p) for p in files):
                self._apply_raw_sidecar_to_controls(self._selected_file)
            self._set_status(f"Perfil básico guardado en {written} imagen(es)")

        def _copy_development_settings_from_selected(self) -> None:
            files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
            if not files:
                QtWidgets.QMessageBox.information(self, "Info", "Selecciona un RAW con perfil de ajuste.")
                return
            source = files[0]
            try:
                sidecar = load_raw_sidecar(source)
            except FileNotFoundError:
                QtWidgets.QMessageBox.information(
                    self,
                    "Info",
                    "Esta imagen todavía no tiene perfil de ajuste guardado. Usa primero 'Guardar perfil básico en imagen' o genera un perfil con carta.",
                )
                return
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Mochila no válida", str(exc))
                return
            self._development_settings_clipboard = self._development_settings_payload_from_sidecar(source, sidecar)
            profile_type = self._adjustment_profile_type_from_sidecar(sidecar)
            label = "avanzado" if profile_type == "advanced" else "básico"
            self._set_status(f"Perfil de ajuste {label} copiado: {source.name}")

        def _icc_profile_path_from_copied_settings(self, copied: dict[str, Any]) -> Path | None:
            color = copied.get("color_management") if isinstance(copied.get("color_management"), dict) else {}
            raw_path = str(color.get("icc_profile_path") or "").strip()
            if not raw_path:
                return None
            stored = self._session_stored_path(raw_path)
            if stored is not None and stored.exists():
                return stored
            path = Path(raw_path).expanduser()
            return path if path.exists() else None

        def _paste_development_settings_to_selected(self) -> None:
            copied = self._development_settings_clipboard
            if not copied:
                QtWidgets.QMessageBox.information(self, "Info", "Copia primero un perfil de ajuste desde una miniatura.")
                return
            files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
            if not files:
                QtWidgets.QMessageBox.information(self, "Info", "Selecciona uno o más RAW de destino.")
                return
            recipe = self._recipe_from_payload(copied.get("recipe"))
            if recipe is None:
                QtWidgets.QMessageBox.warning(self, "Mochila no válida", "El perfil de ajuste copiado no contiene una receta válida.")
                return
            profile = copied.get("development_profile") if isinstance(copied.get("development_profile"), dict) else {}
            detail = copied.get("detail_adjustments") if isinstance(copied.get("detail_adjustments"), dict) else {}
            render = copied.get("render_adjustments") if isinstance(copied.get("render_adjustments"), dict) else {}
            icc_path = self._icc_profile_path_from_copied_settings(copied)
            mode = str((copied.get("color_management") or {}).get("mode") or "")
            written = 0
            targets = {self._normalized_path_key(path) for path in files}
            profile_id = str(profile.get("id") or "")
            for path in files:
                sidecar = self._write_raw_settings_sidecar(
                    path,
                    recipe=recipe,
                    development_profile=profile,
                    detail_adjustments=detail,
                    render_adjustments=render,
                    profile_path=icc_path,
                    color_management_mode=mode or ("camera_rgb_with_input_icc" if icc_path is not None else "no_profile"),
                    status="configured",
                )
                if sidecar is not None:
                    written += 1
                if profile_id:
                    for item in self._develop_queue:
                        if self._normalized_path_key(Path(str(item.get("source") or ""))) == self._normalized_path_key(path):
                            item["development_profile_id"] = profile_id
                            item["status"] = "pending"
                            item["message"] = ""
            self._refresh_queue_table()
            self._refresh_color_reference_thumbnail_markers()
            self._save_active_session(silent=True)
            if self._selected_file is not None and self._normalized_path_key(self._selected_file) in targets:
                self._apply_raw_sidecar_to_controls(self._selected_file)
                if self._original_linear is not None:
                    self._on_load_selected(show_message=False)
            self._set_status(f"Perfil de ajuste pegado en {written} imagen(es)")

        def _apply_raw_sidecar_to_controls(self, path: Path) -> bool:
            try:
                payload = load_raw_sidecar(path)
            except FileNotFoundError:
                return False
            except Exception as exc:
                self._log_preview(f"Aviso: no se pudo leer mochila NexoRAW ({raw_sidecar_path(path).name}): {exc}")
                return False

            recipe = self._recipe_from_payload(payload.get("recipe"))
            if recipe is not None:
                self._apply_recipe_to_controls(recipe)
            detail_state = payload.get("detail_adjustments")
            if isinstance(detail_state, dict):
                self._apply_detail_adjustment_state(detail_state)
            render_state = payload.get("render_adjustments")
            if isinstance(render_state, dict):
                self._apply_render_adjustment_state(render_state)

            profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
            profile_id = str(profile.get("id") or "")
            if profile_id and self._development_profile_by_id(profile_id) is not None:
                self._active_development_profile_id = profile_id
                self._refresh_development_profile_combo()

            color = payload.get("color_management") if isinstance(payload.get("color_management"), dict) else {}
            icc_path = self._session_stored_path(color.get("icc_profile_path")) if color else None
            icc_role = str(color.get("icc_profile_role") or "") if color else ""
            if icc_role == "session_input_icc" and icc_path is not None and icc_path.exists() and self._profile_can_be_active(icc_path):
                self.path_profile_active.setText(str(icc_path))
                self.chk_apply_profile.setChecked(True)

            self._invalidate_preview_cache()
            self._log_preview(f"Mochila NexoRAW aplicada: {raw_sidecar_path(path).name}")
            return True

        def _write_raw_settings_sidecar(
            self,
            source: Path,
            *,
            recipe: Recipe,
            development_profile: dict[str, Any] | None,
            detail_adjustments: dict[str, Any],
            render_adjustments: dict[str, Any],
            profile_path: Path | None,
            color_management_mode: str | None = None,
            output_tiff: Path | None = None,
            proof_path: Path | None = None,
            status: str = "configured",
        ) -> Path | None:
            if source.suffix.lower() not in RAW_EXTENSIONS:
                return None
            try:
                session_name = self.session_name_edit.text().strip() if hasattr(self, "session_name_edit") else ""
                return write_raw_sidecar(
                    source,
                    recipe=recipe,
                    development_profile=development_profile,
                    detail_adjustments=detail_adjustments,
                    render_adjustments=render_adjustments,
                    icc_profile_path=profile_path,
                    color_management_mode=color_management_mode,
                    session_root=self._active_session_root,
                    session_name=session_name,
                    output_tiff=output_tiff,
                    proof_path=proof_path,
                    status=status,
                )
            except Exception as exc:
                del exc
                return None

        def _save_current_development_profile(self) -> None:
            if self._active_session_root is None:
                self._on_create_session()
                if self._active_session_root is None:
                    return
            name = self.development_profile_name_edit.text().strip() or "Perfil manual"
            profile_id = self._unique_development_profile_id(name)
            profile_dir = self._development_profile_dir(profile_id)
            profile_dir.mkdir(parents=True, exist_ok=True)
            recipe_path = profile_dir / "recipe.yml"
            manifest_path = profile_dir / "development_profile.json"
            recipe = self._build_effective_recipe()
            save_recipe(recipe, recipe_path)
            active_icc = self._active_session_icc_for_settings()
            output_icc = None
            if is_generic_output_space(recipe.output_space):
                output_icc = ensure_generic_output_profile(recipe.output_space, directory=self._session_generic_profile_dir())
            manifest = {
                "id": profile_id,
                "name": name,
                "kind": "manual",
                "profile_type": "basic",
                "created_at": self._profile_timestamp(),
                "recipe_path": self._session_relative_or_absolute(recipe_path),
                "recipe": asdict(recipe),
                "detail_adjustments": self._detail_adjustment_state(),
                "render_adjustments": self._render_adjustment_state(),
                "icc_profile_path": self._session_relative_or_absolute(active_icc) if active_icc and active_icc.exists() else "",
                "generic_output_space": generic_output_profile(recipe.output_space).key if is_generic_output_space(recipe.output_space) else "",
                "output_icc_profile_path": self._session_relative_or_absolute(output_icc) if output_icc and output_icc.exists() else "",
            }
            write_json(manifest_path, manifest)
            self._register_development_profile(
                {
                    "id": profile_id,
                    "name": name,
                    "kind": "manual",
                    "profile_type": "basic",
                    "recipe_path": self._session_relative_or_absolute(recipe_path),
                    "manifest_path": self._session_relative_or_absolute(manifest_path),
                    "icc_profile_path": manifest["icc_profile_path"],
                    "generic_output_space": manifest["generic_output_space"],
                    "output_icc_profile_path": manifest["output_icc_profile_path"],
                },
                activate=True,
            )
            self._set_status(f"Perfil de ajuste básico guardado: {name}")

        def _activate_selected_development_profile(self) -> None:
            profile_id = str(self.development_profile_combo.currentData() or "")
            self._apply_development_profile_to_controls(profile_id)

        def _apply_development_profile_to_controls(self, profile_id: str) -> None:
            settings = self._development_profile_settings(profile_id)
            self._apply_recipe_to_controls(settings["recipe"])
            profile = self._development_profile_by_id(profile_id) if profile_id else None
            recipe_path = self._session_stored_path(profile.get("recipe_path")) if profile else None
            if recipe_path is not None:
                self.path_recipe.setText(str(recipe_path))
            self._apply_detail_adjustment_state(settings["detail_adjustments"])
            self._apply_render_adjustment_state(settings["render_adjustments"])
            icc_path = settings.get("icc_profile_path")
            if isinstance(icc_path, Path) and icc_path.exists() and self._profile_can_be_active(icc_path):
                self.path_profile_active.setText(str(icc_path))
                self.chk_apply_profile.setChecked(True)
            elif is_generic_output_space(settings["recipe"].output_space):
                self.path_profile_active.clear()
                self.chk_apply_profile.setChecked(False)
            self._active_development_profile_id = profile_id
            self._refresh_development_profile_combo()
            self._invalidate_preview_cache()
            self._save_active_session(silent=True)
            self._set_status(f"Perfil de ajuste activo: {settings['name']}")

        def _register_chart_development_profile(
            self,
            *,
            name: str,
            development_profile_path: Path,
            calibrated_recipe_path: Path,
            icc_profile_path: Path,
            profile_report_path: Path,
        ) -> str:
            if self._active_session_root is None:
                return ""
            base_id = self._slug_for_development_profile(name)
            existing = self._development_profile_by_id(base_id)
            profile_id = base_id if existing is None else str(existing.get("id") or base_id)
            try:
                payload = json.loads(development_profile_path.read_text(encoding="utf-8")) if development_profile_path.exists() else {}
                if not isinstance(payload, dict):
                    payload = {}
                payload.update(
                    {
                        "id": profile_id,
                        "name": name,
                        "kind": "chart",
                        "profile_type": "advanced",
                        "recipe_path": self._session_relative_or_absolute(calibrated_recipe_path),
                        "icc_profile_path": self._session_relative_or_absolute(icc_profile_path),
                        "profile_report_path": self._session_relative_or_absolute(profile_report_path),
                        "detail_adjustments": self._detail_adjustment_state(),
                        "render_adjustments": self._render_adjustment_state(),
                    }
                )
                write_json(development_profile_path, payload)
            except Exception:
                pass
            self._register_development_profile(
                {
                    "id": profile_id,
                    "name": name,
                    "kind": "chart",
                    "profile_type": "advanced",
                    "recipe_path": self._session_relative_or_absolute(calibrated_recipe_path),
                    "manifest_path": self._session_relative_or_absolute(development_profile_path),
                    "icc_profile_path": self._session_relative_or_absolute(icc_profile_path),
                    "profile_report_path": self._session_relative_or_absolute(profile_report_path),
                },
                activate=True,
            )
            return profile_id

        def _queue_assign_active_development_profile(self) -> None:
            profile_id = self._active_development_profile_id
            if not profile_id and hasattr(self, "development_profile_combo"):
                profile_id = str(self.development_profile_combo.currentData() or "")
            if not profile_id:
                QtWidgets.QMessageBox.information(self, "Info", "Activa o guarda primero un perfil de ajuste.")
                return
            try:
                settings = self._development_profile_settings(profile_id)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Perfil de ajuste no válido", str(exc))
                return
            rows = sorted({i.row() for i in self.queue_table.selectionModel().selectedRows()})
            if not rows:
                QtWidgets.QMessageBox.information(self, "Info", "Selecciona filas de la cola.")
                return
            rendered_profile, mode = self._render_profile_and_mode_for_development_settings(settings)
            development_profile = self._profile_payload_from_development_settings(settings)
            for row in rows:
                if 0 <= row < len(self._develop_queue):
                    self._develop_queue[row]["development_profile_id"] = profile_id
                    self._develop_queue[row]["status"] = "pending"
                    self._develop_queue[row]["message"] = ""
                    self._write_raw_settings_sidecar(
                        Path(str(self._develop_queue[row].get("source") or "")),
                        recipe=settings["recipe"],
                        development_profile=development_profile,
                        detail_adjustments=settings["detail_adjustments"],
                        render_adjustments=settings["render_adjustments"],
                        profile_path=rendered_profile,
                        color_management_mode=mode,
                        status="assigned",
                    )
            self._refresh_queue_table()
            self._refresh_color_reference_thumbnail_markers()
            self._save_active_session(silent=True)
            self._set_status(f"Perfil asignado a {len(rows)} elemento(s) de cola")

        def _use_current_dir_as_session_root(self) -> None:
            root = self._project_root_for_path(self._current_dir) or self._current_dir
            self.session_root_path.setText(str(root))
            self.session_name_edit.setText(root.name)
            self._populate_session_directory_fields(self._session_paths_from_root(root))
            self._set_status(f"Raíz de sesión: {root}")

        def _on_session_root_edited(self) -> None:
            text = self.session_root_path.text().strip()
            if not text:
                return
            root = Path(text).expanduser()
            if not self.session_name_edit.text().strip() and root.name:
                self.session_name_edit.setText(root.name)
            self._populate_session_directory_fields(self._session_paths_from_root(root))

        def _session_state_snapshot(self) -> dict[str, Any]:
            chart_files, _rejected_chart_files = self._filter_profile_reference_files(self._selected_chart_files)
            active_profile = self.path_profile_active.text().strip()
            active_profile_path = Path(active_profile).expanduser() if active_profile else None
            active_profile_valid = active_profile_path is not None and self._profile_can_be_active(active_profile_path)
            return {
                "profile_charts_dir": self.profile_charts_dir.text().strip(),
                "profile_chart_files": [str(p) for p in chart_files],
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
                "profile_active_path": active_profile if active_profile_valid else "",
                "development_profiles": list(self._development_profiles),
                "active_development_profile_id": self._active_development_profile_id,
                "batch_input_dir": self.batch_input_dir.text().strip(),
                "batch_output_dir": self.batch_out_dir.text().strip(),
                "preview_png_path": str(self._session_default_outputs()["preview"]),
                "preview_apply_profile": bool(self.chk_apply_profile.isChecked()) and active_profile_valid,
                "batch_embed_profile": True,
                "batch_apply_adjustments": bool(self.batch_apply_adjustments.isChecked()),
                "fast_raw_preview": True,
                "preview_max_side": int(self.spin_preview_max_side.value()),
                "adjustments": self._detail_adjustment_state(),
                "render_adjustments": self._render_adjustment_state(),
                "recipe": asdict(self._build_effective_recipe()),
            }

        def _default_detail_adjustment_state(self) -> dict[str, int]:
            return {
                "sharpen": 0,
                "radius": 10,
                "noise_luma": 0,
                "noise_color": 0,
                "ca_red": 0,
                "ca_blue": 0,
            }

        def _default_render_adjustment_state(self) -> dict[str, Any]:
            return {
                "illuminant": "D50 (5003 K)",
                "temperature_kelvin": 5003,
                "tint": 0.0,
                "brightness_ev": 0.0,
                "black_point": 0.0,
                "white_point": 1.0,
                "contrast": 0.0,
                "midtone": 1.0,
                "tone_curve_enabled": False,
                "tone_curve_preset": "linear",
                "tone_curve_black_point": 0.0,
                "tone_curve_white_point": 1.0,
                "tone_curve_points": [[0.0, 0.0], [1.0, 1.0]],
            }

        def _new_session_initial_state(self, root: Path, session_name: str) -> dict[str, Any]:
            paths = self._session_paths_from_root(root)
            defaults = self._session_default_outputs(paths=paths, session_name=session_name)
            return {
                "profile_charts_dir": str(paths["charts"]),
                "profile_chart_files": [],
                "reference_path": self.path_reference.text().strip(),
                "profile_output_path": str(defaults["profile_out"]),
                "profile_report_path": str(defaults["profile_report"]),
                "profile_workdir": str(defaults["workdir"]),
                "development_profile_path": str(defaults["development_profile"]),
                "calibrated_recipe_path": str(defaults["calibrated_recipe"]),
                "profile_chart_type": "colorchecker24",
                "profile_min_confidence": 0.35,
                "profile_allow_fallback_detection": False,
                "profile_camera": "",
                "profile_lens": "",
                "recipe_path": str(defaults["recipe"]),
                "profile_active_path": "",
                "development_profiles": [],
                "active_development_profile_id": "",
                "batch_input_dir": str(paths["raw"]),
                "batch_output_dir": str(defaults["tiff_dir"]),
                "preview_png_path": str(defaults["preview"]),
                "preview_apply_profile": False,
                "batch_embed_profile": True,
                "batch_apply_adjustments": True,
                "fast_raw_preview": True,
                "preview_max_side": int(self.spin_preview_max_side.value()),
                "adjustments": self._default_detail_adjustment_state(),
                "render_adjustments": self._default_render_adjustment_state(),
                "recipe": asdict(Recipe()),
            }

        def _apply_state_to_ui_from_session(
            self,
            *,
            state: dict[str, Any],
            directories: dict[str, str],
            session_name: str,
        ) -> None:
            paths = {k: Path(v) for k, v in directories.items() if isinstance(v, str)}
            session_root = paths.get("root", self._active_session_root)
            charts_dir = self._session_state_dir_or_default(
                state.get("profile_charts_dir"),
                paths.get("charts", Path.cwd()),
                root=session_root,
            )
            if self._profile_reference_rejection_reason(charts_dir, paths=paths) is not None:
                charts_dir = paths.get("raw") or paths.get("charts") or charts_dir
            raw_dir = self._session_state_dir_or_default(
                state.get("batch_input_dir"),
                paths.get("raw", Path.cwd()),
                root=session_root,
            )
            defaults = self._session_default_outputs(paths=paths, session_name=session_name)
            raw_profiles = state.get("development_profiles")
            self._development_profiles = [
                dict(profile)
                for profile in raw_profiles
                if isinstance(profile, dict) and str(profile.get("id") or "").strip()
            ] if isinstance(raw_profiles, list) else []
            self._active_development_profile_id = str(state.get("active_development_profile_id") or "")
            self._refresh_development_profile_combo()

            self.profile_charts_dir.setText(str(charts_dir))
            chart_files_state = state.get("profile_chart_files")
            if isinstance(chart_files_state, list):
                chart_files = [
                    Path(str(p)).expanduser()
                    for p in chart_files_state
                    if str(p).strip() and Path(str(p)).expanduser().exists()
                ]
                if session_root is not None:
                    chart_files = [p for p in chart_files if self._path_is_inside(p, session_root)]
                self._selected_chart_files, _rejected_chart_files = self._filter_profile_reference_files(
                    chart_files,
                    paths=paths,
                )
            else:
                self._selected_chart_files = []
            self._sync_profile_chart_selection_label()
            self.path_reference.setText(str(state.get("reference_path") or self.path_reference.text().strip()))
            self.profile_out_path_edit.setText(
                str(self._session_output_path_or_default(state.get("profile_output_path"), defaults["profile_out"]))
            )
            self.path_profile_out.setText(self.profile_out_path_edit.text().strip())
            self.profile_report_out.setText(
                str(self._session_output_path_or_default(state.get("profile_report_path"), defaults["profile_report"]))
            )
            self.profile_workdir.setText(
                str(self._session_output_path_or_default(state.get("profile_workdir"), defaults["workdir"]))
            )
            self.develop_profile_out.setText(
                str(
                    self._session_output_path_or_default(
                        state.get("development_profile_path"),
                        defaults["development_profile"],
                    )
                )
            )
            self.calibrated_recipe_out.setText(
                str(
                    self._session_output_path_or_default(
                        state.get("calibrated_recipe_path"),
                        defaults["calibrated_recipe"],
                    )
                )
            )
            self.batch_input_dir.setText(str(raw_dir))
            self.batch_out_dir.setText(
                str(self._session_output_path_or_default(state.get("batch_output_dir"), defaults["tiff_dir"]))
            )
            self.path_preview_png.setText(str(defaults["preview"]))
            recipe_path = state.get("recipe_path")
            recipe_default = defaults["calibrated_recipe"] if defaults["calibrated_recipe"].exists() else defaults["recipe"]
            self.path_recipe.setText(str(self._session_state_path_or_default(recipe_path, recipe_default)))

            profile_active = str(state.get("profile_active_path") or "").strip()
            active_candidate: Path | None = None
            if profile_active and not self._is_legacy_temp_output_path(profile_active):
                active_candidate = Path(profile_active).expanduser()
            elif defaults["profile_out"].exists():
                active_candidate = defaults["profile_out"]

            if active_candidate is not None and self._profile_can_be_active(active_candidate):
                self.path_profile_active.setText(str(active_candidate))
            else:
                self.path_profile_active.clear()

            chart_type = str(state.get("profile_chart_type") or "colorchecker24")
            self._set_combo_text(self.profile_chart_type, chart_type)
            try:
                self.profile_min_conf.setValue(float(state.get("profile_min_confidence", 0.35)))
            except Exception:
                self.profile_min_conf.setValue(0.35)
            self.profile_allow_fallback.setChecked(bool(state.get("profile_allow_fallback_detection", False)))

            self.profile_camera.setText(str(state.get("profile_camera") or ""))
            self.profile_lens.setText(str(state.get("profile_lens") or ""))

            preview_apply_profile = bool(state.get("preview_apply_profile", self.chk_apply_profile.isChecked()))
            self.chk_apply_profile.setChecked(preview_apply_profile and bool(self.path_profile_active.text().strip()))
            self.batch_embed_profile.setChecked(True)
            self.batch_apply_adjustments.setChecked(bool(state.get("batch_apply_adjustments", self.batch_apply_adjustments.isChecked())))

            try:
                self.spin_preview_max_side.setValue(int(state.get("preview_max_side", self.spin_preview_max_side.value())))
            except Exception:
                pass

            adjustments = state.get("adjustments") if isinstance(state.get("adjustments"), dict) else {}
            try:
                self._apply_detail_adjustment_state(adjustments)
            except Exception:
                pass

            render_adjustments = state.get("render_adjustments") if isinstance(state.get("render_adjustments"), dict) else {}
            try:
                self._apply_render_adjustment_state(render_adjustments)
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
                    "development_profile_id": str(item.get("development_profile_id") or ""),
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
            self._save_active_session(silent=True)

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
                state=self._new_session_initial_state(root, name),
                queue=[],
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
                profile_id = self._development_profile_from_sidecar(src) or self._active_development_profile_id
                self._develop_queue.append(
                    {
                        "source": source,
                        "development_profile_id": profile_id,
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
                self.queue_table.setItem(row, 1, QtWidgets.QTableWidgetItem(self._development_profile_label(str(item.get("development_profile_id") or ""))))
                self.queue_table.setItem(row, 2, QtWidgets.QTableWidgetItem(status))
                self.queue_table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(item.get("output_tiff") or "")))
                self.queue_table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(item.get("message") or "")))

            self.queue_status_label.setText(
                f"Elementos: {len(self._develop_queue)} | Pendientes: {pending} | OK: {done} | Error: {errors}"
            )

        def _queue_process(self) -> None:
            if not self._develop_queue:
                QtWidgets.QMessageBox.information(self, "Info", "No hay elementos en cola.")
                return

            valid_entries: list[tuple[dict[str, str], Path]] = []
            for item in self._develop_queue:
                src = Path(str(item.get("source") or ""))
                if src.exists() and src.is_file() and src.suffix.lower() in BROWSABLE_EXTENSIONS:
                    valid_entries.append((item, src))
                else:
                    item["status"] = "error"
                    item["message"] = "Archivo no encontrado o extensión incompatible"
                    item["output_tiff"] = ""

            if not valid_entries:
                self._refresh_queue_table()
                self._save_active_session(silent=True)
                QtWidgets.QMessageBox.information(self, "Info", "No hay archivos válidos para procesar en la cola.")
                return

            valid_sources = {str(p) for _item, p in valid_entries}
            for item in self._develop_queue:
                source = str(item.get("source") or "")
                if source and source in valid_sources:
                    item["status"] = "pending"
                    item["message"] = ""
                    item["output_tiff"] = ""
            self._refresh_queue_table()

            self._ensure_session_output_controls()
            out_dir = Path(self.batch_out_dir.text().strip())
            apply_adjust = bool(self.batch_apply_adjustments.isChecked())
            embed_profile = bool(self.batch_embed_profile.isChecked())
            groups: dict[str, list[Path]] = {}
            for item, src in valid_entries:
                profile_id = str(item.get("development_profile_id") or "")
                groups.setdefault(profile_id, []).append(src)
            try:
                settings_by_profile = {
                    profile_id: self._development_profile_settings(profile_id)
                    for profile_id in groups
                }
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Perfil de ajuste no válido", str(exc))
                return
            try:
                proof_config = self._resolve_proof_config_for_gui()
                c2pa_config = self._resolve_c2pa_config_for_gui()
            except Exception as exc:
                self._show_signature_config_error(exc)
                return

            def task():
                combined = {"input_files": len(valid_entries), "output_dir": str(out_dir), "outputs": [], "errors": [], "profiles": []}
                for profile_id, group_files in groups.items():
                    settings = settings_by_profile[profile_id]
                    detail = self._detail_adjustment_kwargs_from_state(settings["detail_adjustments"])
                    profile_path = settings.get("icc_profile_path")
                    use_profile = bool(embed_profile and isinstance(profile_path, Path) and str(profile_path))
                    payload = self._process_batch_files(
                        files=group_files,
                        out_dir=out_dir,
                        recipe=settings["recipe"],
                        apply_adjust=apply_adjust,
                        use_profile=use_profile,
                        profile_path=profile_path if use_profile else None,
                        denoise_luma=detail["denoise_luma"],
                        denoise_color=detail["denoise_color"],
                        sharpen_amount=detail["sharpen_amount"],
                        sharpen_radius=detail["sharpen_radius"],
                        lateral_ca_red_scale=detail["lateral_ca_red_scale"],
                        lateral_ca_blue_scale=detail["lateral_ca_blue_scale"],
                        render_adjustments=self._render_adjustment_kwargs_from_state(settings["render_adjustments"]),
                        sidecar_detail_adjustments=settings["detail_adjustments"],
                        sidecar_render_adjustments=settings["render_adjustments"],
                        c2pa_config=c2pa_config,
                        proof_config=proof_config,
                        development_profile={
                            "id": settings["id"],
                            "name": settings["name"],
                            "kind": str((self._development_profile_by_id(settings["id"]) or {}).get("kind") or ""),
                        },
                    )
                    combined["outputs"].extend(payload.get("outputs", []))
                    combined["errors"].extend(payload.get("errors", []))
                    combined["profiles"].append({"id": settings["id"], "name": settings["name"], "files": len(group_files)})
                combined["task"] = "Cola de revelado"
                return combined

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
            project_root = self._project_root_for_path(selected)
            if project_root is not None:
                self.session_root_path.setText(str(project_root))
                self._on_session_root_edited()
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
            resolved_folder = self._resolve_existing_directory(folder)
            if resolved_folder is None:
                self._set_status(f"Directorio no encontrado: {folder}")
                return
            folder = self._preferred_browsing_directory(resolved_folder)
            self._current_dir = folder
            self.current_dir_label.setText(str(folder))
            self._settings.setValue("browser/last_dir", str(folder))
            self._refresh_storage_roots()
            self._set_filesystem_model_root(folder)
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
            self._selection_load_timer.stop()
            self.file_list.clear()
            self._file_items_by_key.clear()
            self._preview_load_pending_request = None
            self._profile_preview_pending_request = None
            self._profile_preview_expected_key = None
            self._metadata_pending_request = None
            self._selected_file = None
            self._clear_manual_chart_points_for_file_change()
            self._last_loaded_preview_key = None
            self.selected_file_label.setText("Sin archivo seleccionado")
            self._clear_metadata_view()
            self._clear_viewer_histogram()

            max_items = 500
            shown: list[Path] = []
            truncated = False
            try:
                for p in folder.iterdir():
                    if not p.is_file() or p.suffix.lower() not in BROWSABLE_EXTENSIONS:
                        continue
                    shown.append(p)
                    if len(shown) >= max_items:
                        truncated = True
                        break
            except OSError as exc:
                self._log_preview(f"No se pudo listar carpeta: {exc}")
                return

            shown.sort(key=lambda p: p.name.lower())

            for p in shown:
                item = QtWidgets.QListWidgetItem("")
                item.setData(QtCore.Qt.UserRole, str(p))
                item.setData(QtCore.Qt.UserRole + 1, p.name)
                item.setTextAlignment(QtCore.Qt.AlignHCenter)
                item.setToolTip(self._file_item_tooltip(p))
                item.setIcon(self._display_icon_for_path(p, self._icon_for_file(p)))
                item.setSizeHint(self.file_list.gridSize())
                self.file_list.addItem(item)
                self._file_items_by_key[self._normalized_path_key(p)] = item

            if truncated:
                i = QtWidgets.QListWidgetItem("... mas archivos no mostrados")
                i.setFlags(QtCore.Qt.NoItemFlags)
                self.file_list.addItem(i)

            self._queue_thumbnail_generation(shown)

        def _file_list_paths(self) -> list[Path]:
            paths: list[Path] = []
            for row in range(self.file_list.count()):
                item = self.file_list.item(row)
                raw_path = item.data(QtCore.Qt.UserRole)
                if raw_path:
                    path = self._resolve_existing_browsable_path(Path(str(raw_path)))
                    if path is not None:
                        if self._normalized_path_key(path) != self._normalized_path_key(Path(str(raw_path))):
                            self._update_file_item_path(item, path)
                        paths.append(path)
            return paths

        def _set_file_list_placeholder_icons(self) -> None:
            for row in range(self.file_list.count()):
                item = self.file_list.item(row)
                raw_path = item.data(QtCore.Qt.UserRole)
                if raw_path:
                    path = Path(str(raw_path))
                    item.setToolTip(self._file_item_tooltip(path))
                    item.setIcon(self._display_icon_for_path(path, self._icon_for_file(path)))

        def _queue_thumbnail_generation(self, paths: list[Path], *, delay_ms: int = 220) -> None:
            self._thumbnail_generation += 1
            self._pending_thumbnail_paths = list(paths)
            self._thumbnail_scan_index = 0
            if not self._pending_thumbnail_paths:
                self._thumbnail_timer.stop()
                return
            self._thumbnail_timer.start(max(0, int(delay_ms)))

        def _start_pending_thumbnail_generation(self) -> None:
            if self._thumbnail_task_active:
                return
            paths = [p for p in self._pending_thumbnail_paths if p.exists() and p.is_file()]
            if not paths:
                return

            size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
            generation = self._thumbnail_generation
            self._apply_cached_thumbnails(paths, size)
            missing = self._next_thumbnail_batch(paths, size)
            if not missing:
                return

            payload_inputs = [(path, self._thumbnail_cache_key(path, size)) for path in missing]

            def task():
                return generation, size, self._build_thumbnail_payloads_for_keys(payload_inputs, size)

            thread = TaskThread(task)
            self._thumbnail_task_active = True
            self._threads.append(thread)

            def cleanup() -> None:
                self._thumbnail_task_active = False
                if thread in self._threads:
                    self._threads.remove(thread)
                thread.deleteLater()
                if self._pending_thumbnail_paths and generation != self._thumbnail_generation:
                    self._thumbnail_timer.start(0)

            def ok(payload) -> None:
                try:
                    payload_generation, payload_size, thumbnails = payload
                    if payload_generation != self._thumbnail_generation:
                        return
                    touched_cache_dirs: set[Path] = set()
                    target_icon_size = self.file_list.iconSize()
                    for raw_path, key, rgb_u8 in thumbnails:
                        icon = self._icon_from_thumbnail_array(rgb_u8, target_size=target_icon_size)
                        self._image_thumb_cache[key] = icon
                        path = Path(raw_path)
                        cache_dir = self._write_thumbnail_to_disk_cache(key, rgb_u8, path=path, prune=False)
                        if cache_dir is not None:
                            touched_cache_dirs.add(cache_dir)
                        self._set_item_icon_for_path(path, icon)
                    if touched_cache_dirs:
                        self._thumbnail_disk_writes_since_prune += len(thumbnails)
                        if self._thumbnail_disk_writes_since_prune >= THUMBNAIL_DISK_PRUNE_INTERVAL_WRITES:
                            for cache_dir in touched_cache_dirs:
                                self._prune_disk_cache(
                                    cache_dir,
                                    pattern="*.png",
                                    max_entries=THUMBNAIL_DISK_CACHE_MAX_ENTRIES,
                                    max_bytes=THUMBNAIL_DISK_CACHE_MAX_BYTES,
                                )
                            self._thumbnail_disk_writes_since_prune = 0
                    self._prune_thumbnail_cache()
                    self._apply_cached_thumbnails(self._file_list_paths(), int(payload_size))
                    if self._should_prefetch_more_thumbnails():
                        self._thumbnail_timer.start(80)
                finally:
                    cleanup()

            def fail(trace: str) -> None:
                cleanup()
                self._log_preview(f"No se pudieron generar miniaturas: {trace.strip().splitlines()[-1] if trace.strip() else 'error'}")

            thread.succeeded.connect(ok)
            thread.failed.connect(fail)
            thread.start()

        def _next_thumbnail_batch(self, paths: list[Path], size: int) -> list[Path]:
            batch: list[Path] = []
            while self._thumbnail_scan_index < len(paths) and len(batch) < THUMBNAIL_BATCH_SIZE:
                path = paths[self._thumbnail_scan_index]
                self._thumbnail_scan_index += 1
                if self._cached_thumbnail_icon(self._thumbnail_cache_key(path, size), path=path) is None:
                    batch.append(path)
            return batch

        def _on_thumbnail_scroll_changed(self, _value: int) -> None:
            if self._thumbnail_task_active or not self._pending_thumbnail_paths:
                return
            if self._thumbnail_scan_index >= len(self._pending_thumbnail_paths):
                return
            if self._should_prefetch_more_thumbnails():
                self._thumbnail_timer.start(80)

        def _should_prefetch_more_thumbnails(self) -> bool:
            if not hasattr(self, "file_list"):
                return False
            if self._thumbnail_scan_index >= len(self._pending_thumbnail_paths):
                return False
            scrollbar = self.file_list.horizontalScrollBar()
            maximum = int(scrollbar.maximum())
            if maximum <= 0:
                return False
            margin = max(1, int(scrollbar.pageStep()) * THUMBNAIL_PREFETCH_MARGIN_PAGES)
            return int(scrollbar.value()) >= maximum - margin

        def _apply_cached_thumbnails(self, paths: list[Path], size: int) -> None:
            for p in paths:
                icon = self._cached_thumbnail_icon(self._thumbnail_cache_key(p, size), path=p)
                if icon is not None:
                    self._set_item_icon_for_path(p, icon)

        def _cached_thumbnail_icon(self, key: str, *, path: Path | None = None) -> QtGui.QIcon | None:
            icon = self._image_thumb_cache.get(key)
            if icon is not None:
                return icon
            icon = self._read_thumbnail_from_disk_cache(key, path=path)
            if icon is None:
                return None
            self._image_thumb_cache[key] = icon
            self._prune_thumbnail_cache()
            return icon

        def _user_disk_cache_dir(self, kind: str) -> Path:
            if sys.platform == "win32":
                base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
            elif sys.platform == "darwin":
                base = Path.home() / "Library" / "Caches"
            else:
                base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
            return base / APP_NAME / kind

        def _project_disk_cache_dir(self, path: Path | None, kind: str) -> Path | None:
            if path is None or self._active_session_root is None:
                return None
            if not self._path_is_inside(path, self._active_session_root):
                return None
            return self._session_paths_from_root(self._active_session_root)["work"] / "cache" / kind

        def _disk_cache_dirs(self, path: Path | None, kind: str) -> list[Path]:
            dirs: list[Path] = []
            project_dir = self._project_disk_cache_dir(path, kind)
            if project_dir is not None:
                dirs.append(project_dir)
            user_dir = self._user_disk_cache_dir(kind)
            if user_dir not in dirs:
                dirs.append(user_dir)
            return dirs

        def _thumbnail_disk_cache_dir(self, path: Path | None = None) -> Path:
            return self._disk_cache_dirs(path, "thumbnails")[0]

        def _disk_cache_path(self, base_dir: Path, key: str, suffix: str) -> Path:
            digest = hashlib.sha256(key.encode("utf-8", errors="surrogatepass")).hexdigest()
            return base_dir / digest[:2] / f"{digest}{suffix}"

        def _thumbnail_disk_cache_path(self, key: str, *, base_dir: Path | None = None, path: Path | None = None) -> Path:
            return self._disk_cache_path(base_dir or self._thumbnail_disk_cache_dir(path), key, ".png")

        def _read_thumbnail_from_disk_cache(self, key: str, *, path: Path | None = None) -> QtGui.QIcon | None:
            for cache_dir in self._disk_cache_dirs(path, "thumbnails"):
                cache_path = self._thumbnail_disk_cache_path(key, base_dir=cache_dir)
                if not cache_path.is_file():
                    continue
                pixmap = QtGui.QPixmap(str(cache_path))
                if pixmap.isNull():
                    continue
                try:
                    os.utime(cache_path, None)
                except Exception:
                    pass
                return QtGui.QIcon(pixmap)
            return None

        def _write_thumbnail_to_disk_cache(
            self,
            key: str,
            rgb_u8: np.ndarray,
            *,
            path: Path | None = None,
            prune: bool = True,
        ) -> Path | None:
            try:
                cache_dir = self._thumbnail_disk_cache_dir(path)
                cache_path = self._thumbnail_disk_cache_path(key, base_dir=cache_dir)
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                image = np.asarray(rgb_u8, dtype=np.uint8)
                if image.ndim == 2:
                    image = np.repeat(image[..., None], 3, axis=2)
                if image.shape[-1] > 3:
                    image = image[..., :3]
                Image.fromarray(np.ascontiguousarray(image)).save(cache_path, format="PNG")
                if prune:
                    self._prune_disk_cache(
                        cache_dir,
                        pattern="*.png",
                        max_entries=THUMBNAIL_DISK_CACHE_MAX_ENTRIES,
                        max_bytes=THUMBNAIL_DISK_CACHE_MAX_BYTES,
                    )
                return cache_dir
            except Exception:
                return None

        def _prune_disk_cache(self, cache_dir: Path, *, pattern: str, max_entries: int, max_bytes: int) -> None:
            try:
                files = [p for p in cache_dir.glob(f"*/*{pattern.removeprefix('*')}") if p.is_file()]
            except Exception:
                return
            records: list[tuple[float, int, Path]] = []
            total_bytes = 0
            for file_path in files:
                try:
                    stat = file_path.stat()
                except OSError:
                    continue
                size = int(stat.st_size)
                total_bytes += size
                records.append((float(stat.st_mtime), size, file_path))
            records.sort(key=lambda item: item[0])
            while records and (len(records) > max_entries or total_bytes > max_bytes):
                _mtime, size, file_path = records.pop(0)
                try:
                    file_path.unlink()
                    total_bytes -= size
                except OSError:
                    pass

        def _prune_thumbnail_cache(self) -> None:
            overflow = len(self._image_thumb_cache) - THUMBNAIL_CACHE_MAX_ENTRIES
            if overflow <= 0:
                return
            for key in list(self._image_thumb_cache.keys())[:overflow]:
                self._image_thumb_cache.pop(key, None)

        def _set_item_icon_for_path(self, path: Path, icon: QtGui.QIcon) -> None:
            key = self._normalized_path_key(path)
            item = self._file_items_by_key.get(key)
            if item is not None and self.file_list.row(item) >= 0:
                item.setIcon(self._display_icon_for_path(path, icon))
                return
            self._file_items_by_key.pop(key, None)

        def _refresh_color_reference_thumbnail_markers(self) -> None:
            if not hasattr(self, "file_list"):
                return
            icon_size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
            for row in range(self.file_list.count()):
                item = self.file_list.item(row)
                raw_path = item.data(QtCore.Qt.UserRole)
                if not raw_path:
                    continue
                path = Path(str(raw_path))
                icon = self._cached_thumbnail_icon(self._thumbnail_cache_key(path, icon_size), path=path)
                if icon is None:
                    icon = self._icon_for_file(path)
                item.setToolTip(self._file_item_tooltip(path))
                item.setIcon(self._display_icon_for_path(path, icon))

        def _display_icon_for_path(self, path: Path, icon: QtGui.QIcon) -> QtGui.QIcon:
            adjustment_profile_type = self._raw_adjustment_profile_type(path)
            if not adjustment_profile_type:
                return icon
            size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
            size = int(np.clip(size, MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE))
            return self._icon_with_thumbnail_markers(
                icon,
                size=size,
                adjustment_profile_type=adjustment_profile_type,
            )

        def _file_item_tooltip(self, path: Path) -> str:
            lines = [str(path)]
            summary = self._raw_sidecar_development_summary(path)
            if summary:
                lines.append(summary)
            if self._is_color_reference_file(path):
                lines.append("Referencia colorimétrica seleccionada")
            return "\n".join(lines)

        def _is_color_reference_file(self, path: Path) -> bool:
            key = self._normalized_path_key(path)
            return key in {self._normalized_path_key(p) for p in self._selected_chart_files}

        @staticmethod
        def _normalized_path_key(path: Path) -> str:
            try:
                return str(path.expanduser().resolve(strict=False)).lower()
            except Exception:
                return str(path).lower()

        def _icon_with_color_reference_marker(self, icon: QtGui.QIcon, *, size: int) -> QtGui.QIcon:
            return self._icon_with_thumbnail_markers(icon, size=size, adjustment_profile_type="advanced")

        def _icon_with_thumbnail_markers(
            self,
            icon: QtGui.QIcon,
            *,
            size: int,
            adjustment_profile_type: str,
        ) -> QtGui.QIcon:
            pixmap = icon.pixmap(QtCore.QSize(size, size))
            if pixmap.isNull():
                return icon
            marked = QtGui.QPixmap(pixmap)
            painter = QtGui.QPainter(marked)
            marker_h = max(3, int(round(marked.height() * 0.045)))
            marker_color = "#38bdf8" if adjustment_profile_type == "advanced" else "#22c55e"
            painter.fillRect(0, marked.height() - marker_h, marked.width(), marker_h, QtGui.QColor(marker_color))
            painter.end()
            return QtGui.QIcon(marked)

        def _thumbnail_cache_key(self, path: Path, size: int | None = None) -> str:
            try:
                st = path.stat()
                stamp = f"{st.st_mtime_ns}:{st.st_size}"
            except OSError:
                stamp = "nostat"
            return f"{self._cache_path_identity(path)}|{stamp}|thumb-v4"

        def _cache_path_identity(self, path: Path) -> str:
            try:
                resolved = path.expanduser().resolve(strict=False)
            except Exception:
                resolved = path
            if self._active_session_root is not None:
                try:
                    root = self._active_session_root.expanduser().resolve(strict=False)
                    relative = resolved.relative_to(root)
                    return f"session:{relative.as_posix()}"
                except Exception:
                    pass
            return str(resolved)

        def _legacy_project_path_candidate(self, path: Path) -> Path | None:
            candidate = Path(path).expanduser()
            roots: list[Path] = []
            if self._active_session_root is not None:
                roots.append(self._active_session_root)
            for parent in candidate.parents:
                if (parent / "00_configuraciones").is_dir() or (parent / "01_ORG").is_dir() or (parent / "02_DRV").is_dir():
                    roots.append(parent)
                    break

            seen: set[str] = set()
            for root in roots:
                try:
                    root = root.expanduser().resolve(strict=False)
                    rel = candidate.resolve(strict=False).relative_to(root)
                except Exception:
                    continue
                if not rel.parts:
                    continue
                replacement = LEGACY_PROJECT_DIR_RENAMES.get(rel.parts[0])
                if replacement is None:
                    continue
                mapped = root / replacement
                if len(rel.parts) > 1:
                    mapped = mapped.joinpath(*rel.parts[1:])
                key = str(mapped)
                if key in seen:
                    continue
                seen.add(key)
                if mapped.exists():
                    return mapped
            return None

        def _project_root_for_path(self, path: Path) -> Path | None:
            candidate = Path(path).expanduser()
            search = [candidate, *candidate.parents]
            for parent in search:
                if (
                    (parent / "00_configuraciones").is_dir()
                    and (parent / "01_ORG").is_dir()
                    and (parent / "02_DRV").is_dir()
                ):
                    try:
                        return parent.resolve()
                    except Exception:
                        return parent
            return None

        def _preferred_browsing_directory(self, folder: Path) -> Path:
            project_root = self._project_root_for_path(folder)
            if project_root is not None:
                org_dir = project_root / "01_ORG"
                if folder == project_root and org_dir.is_dir():
                    return org_dir.resolve()
            return folder

        def _resolve_existing_directory(self, folder: Path) -> Path | None:
            candidate = Path(folder).expanduser()
            if candidate.exists() and candidate.is_dir():
                return candidate.resolve()
            mapped = self._legacy_project_path_candidate(candidate)
            if mapped is not None and mapped.exists() and mapped.is_dir():
                return mapped.resolve()
            return None

        def _resolve_existing_browsable_path(self, path: Path) -> Path | None:
            candidate = Path(path).expanduser()
            if candidate.exists() and candidate.is_file() and candidate.suffix.lower() in BROWSABLE_EXTENSIONS:
                return candidate.resolve()
            mapped = self._legacy_project_path_candidate(candidate)
            if mapped is not None and mapped.exists() and mapped.is_file() and mapped.suffix.lower() in BROWSABLE_EXTENSIONS:
                return mapped.resolve()
            return None

        def _update_file_item_path(self, item: QtWidgets.QListWidgetItem, path: Path) -> None:
            old_raw_path = item.data(QtCore.Qt.UserRole)
            if old_raw_path:
                self._file_items_by_key.pop(self._normalized_path_key(Path(str(old_raw_path))), None)
            item.setData(QtCore.Qt.UserRole, str(path))
            item.setToolTip(self._file_item_tooltip(path))
            self._file_items_by_key[self._normalized_path_key(path)] = item
            icon_size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
            icon = self._cached_thumbnail_icon(self._thumbnail_cache_key(path, icon_size), path=path)
            if icon is None:
                icon = self._icon_for_file(path)
            item.setIcon(self._display_icon_for_path(path, icon))

        def _remove_stale_file_item(self, item: QtWidgets.QListWidgetItem, path: Path) -> None:
            self._file_items_by_key.pop(self._normalized_path_key(path), None)
            row = self.file_list.row(item)
            if row >= 0:
                self.file_list.takeItem(row)
            self._selected_file = None
            self._clear_manual_chart_points_for_file_change()
            self.selected_file_label.setText("Sin archivo seleccionado")
            self._selection_load_timer.stop()
            self._metadata_timer.stop()
            self._clear_metadata_view()
            self._set_status(f"Archivo no encontrado, miniatura retirada: {path.name}")

        @staticmethod
        def _build_thumbnail_payloads(paths: list[Path], size: int) -> list[tuple[str, str, np.ndarray]]:
            return NexoRawMainWindow._build_thumbnail_payloads_for_keys(
                [(path, NexoRawMainWindow._thumbnail_cache_key_for_path(path, size)) for path in paths],
                size,
            )

        @staticmethod
        def _build_thumbnail_payloads_for_keys(
            items: list[tuple[Path, str]], size: int
        ) -> list[tuple[str, str, np.ndarray]]:
            payloads: list[tuple[str, str, np.ndarray]] = []
            for path, key in items:
                try:
                    rgb_u8 = NexoRawMainWindow._thumbnail_array_for_path(path, MAX_THUMBNAIL_SIZE)
                except Exception:
                    continue
                if rgb_u8 is None:
                    continue
                payloads.append((str(path), key, rgb_u8))
            return payloads

        @staticmethod
        def _thumbnail_cache_key_for_path(path: Path, size: int | None = None) -> str:
            try:
                st = path.stat()
                stamp = f"{st.st_mtime_ns}:{st.st_size}"
            except OSError:
                stamp = "nostat"
            try:
                identity = str(path.expanduser().resolve(strict=False))
            except Exception:
                identity = str(path)
            return f"{identity}|{stamp}|thumb-v4"

        @staticmethod
        def _thumbnail_array_for_path(path: Path, size: int) -> np.ndarray | None:
            suffix = path.suffix.lower()
            if suffix in RAW_EXTENSIONS:
                image = extract_embedded_preview(path)
                if image is not None:
                    return NexoRawMainWindow._thumbnail_u8(linear_to_srgb_display(image), size)
                image = NexoRawMainWindow._raw_thumbnail_fallback(path)
                if image is not None:
                    return NexoRawMainWindow._thumbnail_u8(linear_to_srgb_display(image), size)
                return None

            try:
                with Image.open(path) as img:
                    img = ImageOps.exif_transpose(img)
                    if "A" in img.getbands():
                        rgba = img.convert("RGBA")
                        base = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                        base.alpha_composite(rgba)
                        img = base.convert("RGB")
                    else:
                        img = img.convert("RGB")
                    img.thumbnail((size, size), Image.Resampling.LANCZOS)
                    return np.asarray(img, dtype=np.uint8).copy()
            except Exception:
                image = read_image(path)
                return NexoRawMainWindow._thumbnail_u8(linear_to_srgb_display(image), size)

        @staticmethod
        def _raw_thumbnail_fallback(path: Path) -> np.ndarray | None:
            recipe = Recipe(
                demosaic_algorithm="linear",
                white_balance_mode="camera_metadata",
                output_space="scene_linear_camera_rgb",
                output_linear=True,
                tone_curve="linear",
                profiling_mode=False,
            )
            try:
                image = develop_image_array(path, recipe, half_size=True)
            except Exception:
                return None
            image = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
            if image.ndim != 3 or image.shape[2] < 3:
                return None
            return NexoRawMainWindow._neutralize_camera_rgb_thumbnail(image[..., :3])

        @staticmethod
        def _neutralize_camera_rgb_thumbnail(image: np.ndarray) -> np.ndarray:
            rgb = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
            means = np.mean(rgb, axis=(0, 1), dtype=np.float64)
            if not np.all(np.isfinite(means)) or float(np.min(means)) <= 1e-6:
                return rgb
            if float(np.max(means) / np.min(means)) < 1.35:
                return rgb
            target = float(np.median(means))
            gains = np.clip(target / means, 0.35, 2.8).astype(np.float32)
            balanced = rgb * gains.reshape((1, 1, 3))
            return np.clip(balanced, 0.0, 1.0).astype(np.float32)

        @staticmethod
        def _thumbnail_u8(image_rgb: np.ndarray, size: int) -> np.ndarray:
            rgb = np.asarray(image_rgb)
            if rgb.ndim == 2:
                rgb = np.repeat(rgb[..., None], 3, axis=2)
            if rgb.shape[-1] > 3:
                rgb = rgb[..., :3]
            if np.issubdtype(rgb.dtype, np.integer):
                maxv = float(np.iinfo(rgb.dtype).max)
                rgb_f = np.clip(rgb.astype(np.float32) / maxv, 0.0, 1.0)
            else:
                rgb_f = np.clip(rgb.astype(np.float32), 0.0, 1.0)

            h, w = int(rgb_f.shape[0]), int(rgb_f.shape[1])
            if h <= 0 or w <= 0:
                return np.zeros((1, 1, 3), dtype=np.uint8)
            scale = min(float(size) / float(max(w, h)), 1.0)
            if scale < 1.0:
                nw = max(1, int(round(w * scale)))
                nh = max(1, int(round(h * scale)))
                rgb_f = cv2.resize(rgb_f, (nw, nh), interpolation=cv2.INTER_AREA)
            return np.ascontiguousarray(np.clip(np.round(rgb_f * 255.0), 0, 255).astype(np.uint8))

        def _icon_from_thumbnail_array(
            self,
            rgb_u8: np.ndarray,
            *,
            target_size: QtCore.QSize | None = None,
        ) -> QtGui.QIcon:
            rgb_u8 = self._thumbnail_u8_for_screen(rgb_u8)
            if target_size is not None:
                target_w = max(1, int(target_size.width()))
                target_h = max(1, int(target_size.height()))
                src_h, src_w = int(rgb_u8.shape[0]), int(rgb_u8.shape[1])
                if src_h > 0 and src_w > 0:
                    src_aspect = float(src_w) / float(src_h)
                    target_aspect = float(target_w) / float(target_h)
                    if src_aspect > target_aspect:
                        crop_w = max(1, int(round(src_h * target_aspect)))
                        x0 = max(0, (src_w - crop_w) // 2)
                        rgb_u8 = rgb_u8[:, x0 : x0 + crop_w]
                    else:
                        crop_h = max(1, int(round(src_w / target_aspect)))
                        y0 = max(0, (src_h - crop_h) // 2)
                        rgb_u8 = rgb_u8[y0 : y0 + crop_h, :]
                interpolation = (
                    cv2.INTER_AREA
                    if int(rgb_u8.shape[1]) >= target_w and int(rgb_u8.shape[0]) >= target_h
                    else cv2.INTER_LINEAR
                )
                rgb_u8 = cv2.resize(rgb_u8, (target_w, target_h), interpolation=interpolation)
            rgb_u8 = np.ascontiguousarray(rgb_u8.astype(np.uint8))
            h, w = int(rgb_u8.shape[0]), int(rgb_u8.shape[1])
            qimg = QtGui.QImage(rgb_u8.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()
            return QtGui.QIcon(QtGui.QPixmap.fromImage(qimg))

        def _icon_for_file(self, path: Path) -> QtGui.QIcon:
            suffix = path.suffix.lower()
            key = "raw" if suffix in RAW_EXTENSIONS else "image"
            cached = self._thumb_cache.get(key)
            if cached is not None:
                return cached

            icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
            self._thumb_cache[key] = icon
            return icon

        def _on_file_selection_changed(self) -> None:
            item = self.file_list.currentItem()
            if item is None:
                self._selected_file = None
                self._clear_manual_chart_points_for_file_change()
                self.selected_file_label.setText("Sin archivo seleccionado")
                self._selection_load_timer.stop()
                self._metadata_timer.stop()
                self._clear_metadata_view()
                self._clear_viewer_histogram()
                return
            raw_path = item.data(QtCore.Qt.UserRole)
            if not raw_path:
                self._selected_file = None
                self._clear_manual_chart_points_for_file_change()
                self._selection_load_timer.stop()
                self._metadata_timer.stop()
                self._clear_metadata_view()
                self._clear_viewer_histogram()
                return
            stale_path = Path(str(raw_path))
            selected = self._resolve_existing_browsable_path(stale_path)
            if selected is None:
                self._remove_stale_file_item(item, stale_path)
                return
            if self._normalized_path_key(selected) != self._normalized_path_key(stale_path):
                self._update_file_item_path(item, selected)
            if self._selected_file is None or self._normalized_path_key(self._selected_file) != self._normalized_path_key(selected):
                self._clear_manual_chart_points_for_file_change()
            self._selected_file = selected
            self.selected_file_label.setText(str(self._selected_file))
            self._apply_raw_sidecar_to_controls(self._selected_file)
            self._queue_metadata_load(self._selected_file, include_c2pa=False)
            if self._selected_file.suffix.lower() in BROWSABLE_EXTENSIONS:
                self._set_status(f"Seleccionado: {self._selected_file.name}. Cargando preview...")
                self._selection_load_timer.start(250)

        def _on_file_double_clicked(self, _item) -> None:
            self._selection_load_timer.stop()
            self._on_load_selected()

        def _show_file_list_context_menu(self, pos: QtCore.QPoint) -> None:
            item = self.file_list.itemAt(pos)
            if item is not None and not item.isSelected():
                self.file_list.clearSelection()
                item.setSelected(True)
                self.file_list.setCurrentItem(item)

            menu = QtWidgets.QMenu(self)
            menu.addAction("Guardar perfil básico en imagen", self._save_current_development_settings_to_selected)
            menu.addAction("Copiar perfil de ajuste", self._copy_development_settings_from_selected)
            paste_action = menu.addAction("Pegar perfil de ajuste", self._paste_development_settings_to_selected)
            paste_action.setEnabled(self._development_settings_clipboard is not None)
            menu.addSeparator()
            menu.addAction("Usar como referencia colorimétrica", self._use_selected_files_as_profile_charts)
            menu.addAction("Añadir a cola", self._queue_add_selected)
            menu.exec(self.file_list.mapToGlobal(pos))

        def _queue_metadata_load(self, path: Path, *, delay_ms: int = 180, include_c2pa: bool = True) -> None:
            self._metadata_generation += 1
            self._queued_metadata_include_c2pa = bool(include_c2pa)
            if hasattr(self, "metadata_file_label"):
                self.metadata_file_label.setText(f"Metadatos: {path.name}")
            if hasattr(self, "metadata_summary"):
                self._metadata_tree_message(self.metadata_summary, "Leyendo metadatos...")
            self._metadata_timer.start(max(0, int(delay_ms)))

        def _load_metadata_from_timer(self) -> None:
            self._refresh_metadata_view(include_c2pa=self._queued_metadata_include_c2pa)

        def _refresh_metadata_view(self, _checked: bool = False, *, include_c2pa: bool = True) -> None:
            if self._selected_file is None:
                self._clear_metadata_view()
                return
            selected = self._selected_file
            if hasattr(self, "metadata_file_label"):
                self.metadata_file_label.setText(f"Metadatos: {selected}")
            if hasattr(self, "metadata_summary"):
                self._metadata_tree_message(self.metadata_summary, "Leyendo metadatos...")
            if self._metadata_task_active:
                self._metadata_pending_request = (selected, bool(include_c2pa))
                return
            self._start_metadata_refresh_task(selected, bool(include_c2pa))

        def _start_metadata_refresh_task(self, selected: Path, include_c2pa: bool) -> None:
            self._metadata_generation += 1
            generation = self._metadata_generation

            def task():
                return generation, selected, inspect_file_metadata(selected, include_c2pa=include_c2pa)

            thread = TaskThread(task)
            self._metadata_task_active = True
            self._threads.append(thread)

            def cleanup() -> None:
                self._metadata_task_active = False
                if thread in self._threads:
                    self._threads.remove(thread)
                thread.deleteLater()
                pending = self._metadata_pending_request
                self._metadata_pending_request = None
                if pending is not None:
                    _pending_path, pending_c2pa = pending
                    if self._selected_file is not None:
                        self._start_metadata_refresh_task(self._selected_file, pending_c2pa)

            def ok(payload) -> None:
                try:
                    payload_generation, payload_path, metadata = payload
                    if payload_generation != self._metadata_generation or self._selected_file != payload_path:
                        return
                    self._apply_metadata_payload(payload_path, metadata)
                finally:
                    cleanup()

            def fail(trace: str) -> None:
                try:
                    if self._selected_file == selected:
                        msg = trace.strip().splitlines()[-1] if trace.strip() else "No se pudieron leer metadatos"
                        self._metadata_tree_message(self.metadata_summary, msg)
                        self.metadata_exif.clear()
                        self.metadata_gps.clear()
                        self.metadata_c2pa.clear()
                        self.metadata_all.setPlainText(trace[-4000:])
                finally:
                    cleanup()

            thread.succeeded.connect(ok)
            thread.failed.connect(fail)
            thread.start()

        def _apply_metadata_payload(self, path: Path, payload: dict[str, Any]) -> None:
            sections = metadata_sections_text(payload)
            display = metadata_display_sections(payload)
            self.metadata_file_label.setText(f"Metadatos: {path}")
            self._populate_metadata_tree(self.metadata_summary, display["summary"])
            self._populate_metadata_tree(self.metadata_exif, display["exif"])
            self._populate_metadata_tree(self.metadata_gps, display["gps"])
            self._populate_metadata_tree(self.metadata_c2pa, display["c2pa"])
            self.metadata_all.setPlainText(sections["all"])

        def _clear_metadata_view(self) -> None:
            if not hasattr(self, "metadata_summary"):
                return
            self.metadata_file_label.setText("Sin archivo seleccionado")
            for widget in (
                self.metadata_summary,
                self.metadata_exif,
                self.metadata_gps,
                self.metadata_c2pa,
            ):
                widget.clear()
            self.metadata_all.clear()

        def _show_metadata_all_tab(self) -> None:
            if hasattr(self, "metadata_tabs"):
                self.metadata_tabs.setCurrentWidget(self.metadata_all)

        def _metadata_tree_message(self, tree: QtWidgets.QTreeWidget, message: str) -> None:
            tree.clear()
            item = QtWidgets.QTreeWidgetItem([str(message), ""])
            tree.addTopLevelItem(item)

        def _populate_metadata_tree(self, tree: QtWidgets.QTreeWidget, groups: Any) -> None:
            tree.clear()
            if not groups:
                self._metadata_tree_message(tree, "Sin datos")
                return
            if isinstance(groups, list):
                for group in groups:
                    self._add_metadata_group(tree, group)
            elif isinstance(groups, dict):
                self._add_metadata_dict(tree, None, groups)
            else:
                self._metadata_tree_message(tree, str(groups))
            tree.expandToDepth(0)

        def _add_metadata_group(self, tree: QtWidgets.QTreeWidget, group: dict[str, Any]) -> None:
            title = str(group.get("title") or "Metadatos")
            parent = QtWidgets.QTreeWidgetItem([title, ""])
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setFirstColumnSpanned(False)
            tree.addTopLevelItem(parent)
            for item in group.get("items") or []:
                if isinstance(item, dict):
                    child = QtWidgets.QTreeWidgetItem([str(item.get("label", "")), str(item.get("value", ""))])
                    child.setToolTip(1, str(item.get("value", "")))
                    parent.addChild(child)

        def _add_metadata_dict(self, tree: QtWidgets.QTreeWidget, parent: QtWidgets.QTreeWidgetItem | None, payload: dict[str, Any]) -> None:
            for key, value in sorted(payload.items()):
                if isinstance(value, dict):
                    node = QtWidgets.QTreeWidgetItem([str(key), ""])
                    if parent is None:
                        tree.addTopLevelItem(node)
                    else:
                        parent.addChild(node)
                    self._add_metadata_dict(tree, node, value)
                elif isinstance(value, list):
                    node = QtWidgets.QTreeWidgetItem([str(key), f"{len(value)} elementos"])
                    if parent is None:
                        tree.addTopLevelItem(node)
                    else:
                        parent.addChild(node)
                    for idx, item in enumerate(value):
                        child = QtWidgets.QTreeWidgetItem([str(idx + 1), json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item)])
                        node.addChild(child)
                else:
                    node = QtWidgets.QTreeWidgetItem([str(key), str(value)])
                    node.setToolTip(1, str(value))
                    if parent is None:
                        tree.addTopLevelItem(node)
                    else:
                        parent.addChild(node)

        def _toggle_compare(self, enabled: bool) -> None:
            self.viewer_stack.setCurrentIndex(1 if enabled else 0)
            if hasattr(self, "_action_compare"):
                self._action_compare.blockSignals(True)
                self._action_compare.setChecked(enabled)
                self._action_compare.blockSignals(False)
            selected = self._selected_file
            if selected is not None and selected.suffix.lower() in RAW_EXTENSIONS:
                self._last_loaded_preview_key = None
                self._on_load_selected(show_message=False)
                return
            if self._original_linear is not None:
                self._schedule_preview_refresh()

        def _menu_toggle_compare(self, checked: bool) -> None:
            self.chk_compare.setChecked(checked)
            self._toggle_compare(checked)

        def _menu_check_updates(self) -> None:
            self._start_update_check(
                on_success=self._on_manual_update_check_success,
                on_error=self._on_manual_update_check_error,
            )

        def _on_manual_update_check_success(self, payload: dict[str, Any]) -> None:
            self._update_check_last = payload
            status_text = self._update_status_summary(payload)
            if payload.get("error"):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Actualizaciones",
                    status_text,
                )
                return
            QtWidgets.QMessageBox.information(self, "Actualizaciones", status_text)

        def _on_manual_update_check_error(self, message: str) -> None:
            QtWidgets.QMessageBox.warning(self, "Actualizaciones", message)

        def _menu_about(self) -> None:
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle(f"Acerca de {APP_NAME}")
            dialog.setModal(True)
            dialog.resize(640, 360)

            layout = QtWidgets.QVBoxLayout(dialog)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)

            title = QtWidgets.QLabel(APP_NAME)
            title.setStyleSheet("font-size: 22px; font-weight: 700;")
            layout.addWidget(title)

            subtitle = QtWidgets.QLabel(
                "Revelado RAW tecnico, trazable y reproducible para entornos cientificos."
            )
            subtitle.setWordWrap(True)
            subtitle.setStyleSheet("font-size: 12px; color: #4b5563;")
            layout.addWidget(subtitle)

            grid = QtWidgets.QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(6)

            def add_row(row: int, label: str, value: str) -> QtWidgets.QLabel:
                k = QtWidgets.QLabel(label)
                k.setStyleSheet("font-weight: 600; color: #374151;")
                v = QtWidgets.QLabel(value)
                v.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
                v.setWordWrap(True)
                grid.addWidget(k, row, 0)
                grid.addWidget(v, row, 1)
                return v

            add_row(0, "Director del proyecto:", PROJECT_DIRECTOR_NAME)
            add_row(1, "Version en ejecucion:", __version__)
            add_row(2, "Backend:", "LibRaw/rawpy + ArgyllCMS")
            amaze_info = self._amaze_status_summary()
            add_row(3, "Soporte AMaZE:", amaze_info)
            latest_label = add_row(4, "Estado de version:", "Sin comprobar")

            layout.addLayout(grid)

            status_note = QtWidgets.QLabel(
                "La comprobacion usa GitHub Releases; la actualizacion automatica descarga y ejecuta el instalador."
            )
            status_note.setWordWrap(True)
            status_note.setStyleSheet("font-size: 12px; color: #6b7280;")
            layout.addWidget(status_note)

            button_row = QtWidgets.QHBoxLayout()
            btn_check = QtWidgets.QPushButton("Comprobar ultima version")
            btn_update = QtWidgets.QPushButton("Actualizar automaticamente")
            btn_release = QtWidgets.QPushButton("Abrir releases")
            btn_close = QtWidgets.QPushButton("Cerrar")
            btn_update.setEnabled(False)
            button_row.addWidget(btn_check)
            button_row.addWidget(btn_update)
            button_row.addStretch(1)
            button_row.addWidget(btn_release)
            button_row.addWidget(btn_close)
            layout.addLayout(button_row)

            state: dict[str, Any] = {"payload": self._update_check_last}

            def refresh_about_payload(payload: dict[str, Any] | None) -> None:
                p = payload or {}
                latest_label.setText(self._update_status_summary(p))
                latest_label.setStyleSheet("color: #dc2626;" if p.get("error") else "color: #1f2937;")
                can_auto = bool(p.get("update_available") and p.get("asset_url"))
                btn_update.setEnabled(can_auto)

            def open_release_page() -> None:
                payload = state.get("payload") or {}
                url = str(payload.get("release_url") or f"https://github.com/{os.environ.get('NEXORAW_RELEASE_REPOSITORY', 'alejandro-probatia/NexoRAW')}/releases")
                QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

            def run_check() -> None:
                btn_check.setEnabled(False)
                latest_label.setText("Comprobando version mas reciente...")

                def ok(payload: dict[str, Any]) -> None:
                    state["payload"] = payload
                    self._update_check_last = payload
                    refresh_about_payload(payload)
                    btn_check.setEnabled(True)

                def fail(message: str) -> None:
                    btn_check.setEnabled(True)
                    fallback = {"error": message}
                    state["payload"] = fallback
                    refresh_about_payload(fallback)

                self._start_update_check(on_success=ok, on_error=fail)

            def run_auto_update() -> None:
                payload = state.get("payload")
                if not isinstance(payload, dict):
                    QtWidgets.QMessageBox.information(dialog, "Actualizacion", "Primero comprueba la ultima version.")
                    return
                if payload.get("error"):
                    QtWidgets.QMessageBox.warning(dialog, "Actualizacion", str(payload.get("error")))
                    return
                if not payload.get("update_available"):
                    QtWidgets.QMessageBox.information(dialog, "Actualizacion", "Ya estas en la ultima version.")
                    return
                if not payload.get("asset_url"):
                    QtWidgets.QMessageBox.information(
                        dialog,
                        "Actualizacion",
                        "No hay instalador automatico para esta plataforma en la release detectada.",
                    )
                    return
                answer = QtWidgets.QMessageBox.question(
                    dialog,
                    "Actualizar automaticamente",
                    "Se descargara el instalador mas reciente y se ejecutara en modo silencioso.\n"
                    "Deseas continuar?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No,
                )
                if answer != QtWidgets.QMessageBox.Yes:
                    return

                btn_update.setEnabled(False)
                btn_check.setEnabled(False)
                latest_label.setText("Descargando e iniciando actualizacion...")

                def task() -> dict[str, Any]:
                    fresh_check = check_latest_release()
                    check_payload = asdict(fresh_check)
                    if fresh_check.error:
                        raise RuntimeError(str(fresh_check.error))
                    if not fresh_check.update_available:
                        raise RuntimeError("No hay una version mas reciente disponible.")
                    installer = auto_update(check=fresh_check, silent=True)
                    return {"installer_path": str(installer), "check": check_payload}

                def ok(result: dict[str, Any]) -> None:
                    installer_path = str(result.get("installer_path") or "")
                    latest_label.setText("Instalador lanzado correctamente.")
                    QtWidgets.QMessageBox.information(
                        dialog,
                        "Actualizacion iniciada",
                        "Se ha iniciado el instalador de actualizacion:\n"
                        f"{installer_path}\n\n"
                        "Cierra NexoRAW cuando el instalador lo solicite.",
                    )
                    btn_check.setEnabled(True)
                    btn_update.setEnabled(True)

                def fail(message: str) -> None:
                    latest_label.setText("No se pudo iniciar la actualizacion automatica.")
                    QtWidgets.QMessageBox.warning(dialog, "Actualizacion", message)
                    btn_check.setEnabled(True)
                    btn_update.setEnabled(True)

                self._run_lightweight_task(task, on_success=ok, on_error=fail)

            btn_check.clicked.connect(run_check)
            btn_update.clicked.connect(run_auto_update)
            btn_release.clicked.connect(open_release_page)
            btn_close.clicked.connect(dialog.accept)

            refresh_about_payload(state.get("payload"))
            dialog.exec()

        def _update_status_summary(self, payload: dict[str, Any]) -> str:
            if not payload:
                return "Sin comprobar"
            error = payload.get("error")
            if error:
                return f"No se pudo comprobar la version: {error}"
            latest = str(payload.get("latest_version") or "desconocida")
            current = str(payload.get("current_version") or __version__)
            if bool(payload.get("update_available")):
                return f"Actualizacion disponible: {latest} (actual: {current})"
            if payload.get("is_latest") is True:
                return f"Estas en la ultima version: {current}"
            return f"Version actual: {current}. Ultima detectada: {latest}"

        def _amaze_status_summary(self) -> str:
            try:
                payload = check_amaze_backend()
            except Exception as exc:
                return f"No disponible ({exc})"
            supported = bool(payload.get("amaze_supported"))
            rawpy_name = str(payload.get("rawpy_demosaic_distribution") or payload.get("rawpy_distribution") or "rawpy")
            return "Activo" if supported else f"No activo ({rawpy_name})"

        def _start_update_check(self, *, on_success, on_error) -> None:
            def task() -> dict[str, Any]:
                return asdict(check_latest_release())

            self._run_lightweight_task(task, on_success=on_success, on_error=on_error)

        def _run_lightweight_task(self, task, *, on_success, on_error) -> None:
            thread = TaskThread(task)
            self._threads.append(thread)

            def cleanup() -> None:
                if thread in self._threads:
                    self._threads.remove(thread)
                thread.deleteLater()

            def ok(payload) -> None:
                try:
                    on_success(payload)
                finally:
                    cleanup()

            def fail(trace: str) -> None:
                try:
                    message = trace.strip().splitlines()[-1] if trace.strip() else "Error"
                    on_error(message)
                finally:
                    cleanup()

            thread.succeeded.connect(ok)
            thread.failed.connect(fail)
            thread.start()

        def _menu_check_tools(self) -> None:
            result = check_external_tools()
            self.profile_output.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
            missing = result.get("missing_required", [])
            if hasattr(self, "profile_summary_label"):
                if missing:
                    self.profile_summary_label.setText(
                        "Diagnostico herramientas: faltan " + ", ".join(str(name) for name in missing)
                    )
                else:
                    self.profile_summary_label.setText("Diagnostico herramientas: entorno externo completo")
            if missing:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Diagnostico herramientas",
                    "Faltan herramientas requeridas en PATH: " + ", ".join(str(name) for name in missing),
                )
                self._set_status("Faltan herramientas externas requeridas")
            else:
                self._set_status("Herramientas externas disponibles")

        def _menu_load_profile(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Selecciona perfil ICC",
                self.path_profile_active.text().strip(),
                "ICC Profiles (*.icc *.icm);;Todos (*)",
            )
            if not path:
                return
            profile_path = Path(path).expanduser()
            if not self._profile_can_be_active(profile_path):
                status = self._profile_status_for_path(profile_path) or "no disponible"
                QtWidgets.QMessageBox.warning(
                    self,
                    "Perfil no activable",
                    f"No se activa el perfil porque su estado QA es '{status}'. "
                    "Regenera el perfil con referencias RAW/DNG originales.",
                )
                return
            self.path_profile_active.setText(path)
            self._set_status(f"Perfil activo: {path}")
            self._refresh_preview()
            self._save_active_session(silent=True)

        def _menu_compare_qa_reports(self) -> None:
            paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
                self,
                "Comparar reportes QA de sesión",
                str(self._current_dir),
                "Reportes JSON (*.json);;Todos (*)",
            )
            if not paths:
                return
            try:
                comparison = compare_qa_reports([Path(path) for path in paths])
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Comparación QA", str(exc))
                return
            self.profile_output.setPlainText(json.dumps(comparison, indent=2, ensure_ascii=False))
            if hasattr(self, "profile_summary_label"):
                self.profile_summary_label.setText(self._qa_comparison_summary(comparison))
            self._set_status(f"Comparados {comparison.get('report_count', len(paths))} reportes QA")

        def _qa_comparison_summary(self, comparison: dict[str, Any]) -> str:
            status_counts = comparison.get("status_counts") if isinstance(comparison.get("status_counts"), dict) else {}
            best = comparison.get("best_validation_mean_delta_e2000")
            worst = comparison.get("worst_validation_mean_delta_e2000")
            parts = [
                f"Reportes QA comparados: {comparison.get('report_count', 0)}",
                "Estados: " + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())),
            ]
            if isinstance(best, dict) and best.get("validation_mean_delta_e2000") is not None:
                parts.append(
                    f"Mejor validación: {best.get('label')} "
                    f"media {float(best['validation_mean_delta_e2000']):.2f}"
                )
            if isinstance(worst, dict) and worst.get("validation_mean_delta_e2000") is not None:
                parts.append(
                    f"Peor validación: {worst.get('label')} "
                    f"media {float(worst['validation_mean_delta_e2000']):.2f}"
                )
            return "\n".join(parts)

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
            self._set_combo_data(self.combo_raw_developer, recipe.raw_developer)
            self._set_combo_data(
                self.combo_demosaic,
                self._supported_gui_demosaic(recipe.demosaic_algorithm, notify=True),
            )
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
            self._sync_development_output_space_combo(recipe.output_space)
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

        def _sync_demosaic_capabilities(self) -> None:
            flags = rawpy_feature_flags()
            has_gpl3 = bool(flags.get("DEMOSAIC_PACK_GPL3", False))
            model = self.combo_demosaic.model()
            for i in range(self.combo_demosaic.count()):
                value = str(self.combo_demosaic.itemData(i) or "").strip().lower()
                item = model.item(i) if hasattr(model, "item") else None
                if item is not None:
                    item.setEnabled(is_libraw_demosaic_supported(value))
                if value == "amaze":
                    suffix = "disponible" if has_gpl3 else "no disponible: requiere rawpy-demosaic/GPL3"
                    self.combo_demosaic.setItemText(i, f"AMaZE (GPL3, {suffix})")

        def _supported_gui_demosaic(self, demosaic_algorithm: str, *, notify: bool) -> str:
            requested = str(demosaic_algorithm or "dcb").strip().lower()
            reason = unavailable_demosaic_reason(requested)
            if reason is None:
                return requested
            if notify:
                self._log_preview(f"Aviso: {reason} Se usa DCB en la GUI hasta instalar soporte GPL.")
            return "dcb"

        def _balanced_preview_demosaic(self) -> str:
            for candidate in PREVIEW_BALANCED_DEMOSAIC_ORDER:
                if unavailable_demosaic_reason(candidate) is None:
                    return candidate
            return self._supported_gui_demosaic("dcb", notify=False)

        def _preview_requires_max_quality(self) -> bool:
            compare_enabled = bool(getattr(self, "chk_compare", None) and self.chk_compare.isChecked())
            return compare_enabled or bool(self._manual_chart_marking_after_reload)

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

        def _tone_curve_preset_points(self, key: str) -> list[tuple[float, float]]:
            for _label, preset_key, points in TONE_CURVE_PRESETS:
                if preset_key == key:
                    return list(points)
            return [(0.0, 0.0), (1.0, 1.0)]

        def _tone_curve_preset_key(self) -> str:
            return str(self.combo_tone_curve_preset.currentData() or "linear")

        def _set_tone_curve_controls_enabled(self, enabled: bool) -> None:
            self.combo_tone_curve_preset.setEnabled(bool(enabled))
            self.label_tone_curve_black.setEnabled(bool(enabled))
            self.slider_tone_curve_black.setEnabled(bool(enabled))
            self.label_tone_curve_white.setEnabled(bool(enabled))
            self.slider_tone_curve_white.setEnabled(bool(enabled))
            self.tone_curve_editor.setEnabled(bool(enabled))

        def _tone_curve_range_values(self) -> tuple[float, float]:
            black = self.slider_tone_curve_black.value() / 1000.0
            white = self.slider_tone_curve_white.value() / 1000.0
            black = float(np.clip(black, 0.0, 0.95))
            white = float(np.clip(white, black + 0.01, 1.0))
            return black, white

        def _set_tone_curve_range_controls(self, black_point: float, white_point: float) -> None:
            black = float(np.clip(black_point, 0.0, 0.95))
            white = float(np.clip(white_point, black + 0.01, 1.0))
            self.slider_tone_curve_black.blockSignals(True)
            self.slider_tone_curve_white.blockSignals(True)
            self.slider_tone_curve_black.setValue(int(round(black * 1000.0)))
            self.slider_tone_curve_white.setValue(int(round(white * 1000.0)))
            self.slider_tone_curve_black.blockSignals(False)
            self.slider_tone_curve_white.blockSignals(False)
            self.label_tone_curve_black.setText(f"Negro curva: {self.slider_tone_curve_black.value() / 1000:.3f}")
            self.label_tone_curve_white.setText(f"Blanco curva: {self.slider_tone_curve_white.value() / 1000:.3f}")
            self.tone_curve_editor.set_input_range(
                self.slider_tone_curve_black.value() / 1000.0,
                self.slider_tone_curve_white.value() / 1000.0,
            )

        def _coerce_tone_curve_points(self, value: Any) -> list[tuple[float, float]] | None:
            if not isinstance(value, (list, tuple)):
                return None
            points: list[tuple[float, float]] = []
            for item in value:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                try:
                    points.append((float(item[0]), float(item[1])))
                except (TypeError, ValueError):
                    continue
            if not points:
                return None
            return normalize_tone_curve_points(points)

        def _on_illuminant_changed(self) -> None:
            data = self.combo_illuminant_render.currentData()
            if isinstance(data, dict) and data.get("temperature") is not None:
                self.spin_render_temperature.blockSignals(True)
                self.spin_render_tint.blockSignals(True)
                self.spin_render_temperature.setValue(int(data["temperature"]))
                self.spin_render_tint.setValue(float(data.get("tint") or 0.0))
                self.spin_render_temperature.blockSignals(False)
                self.spin_render_tint.blockSignals(False)
                if hasattr(self, "edit_illuminant"):
                    self.edit_illuminant.setText(self.combo_illuminant_render.currentText().split("(", 1)[0].strip())
            self._on_render_control_change()

        def _set_neutral_picker_active(self, active: bool) -> None:
            self._neutral_picker_active = bool(active)
            if hasattr(self, "btn_neutral_picker"):
                self.btn_neutral_picker.blockSignals(True)
                self.btn_neutral_picker.setChecked(self._neutral_picker_active)
                self.btn_neutral_picker.blockSignals(False)
            cursor = QtCore.Qt.CrossCursor if self._neutral_picker_active else QtCore.Qt.ArrowCursor
            for panel_name in ("image_result_single", "image_result_compare"):
                if hasattr(self, panel_name):
                    getattr(self, panel_name).setCursor(cursor)

        def _toggle_neutral_picker(self, checked: bool = False) -> None:
            if checked and self._original_linear is None:
                self._set_neutral_picker_active(False)
                QtWidgets.QMessageBox.information(self, "Info", "Carga primero una imagen en el visor.")
                return
            self._set_neutral_picker_active(bool(checked))
            if self._neutral_picker_active:
                self._manual_chart_marking = False
                self._sync_manual_chart_overlay()
                self._set_status("Cuentagotas neutro activo: haz clic en un gris/blanco sin saturar")
            else:
                self._set_status("Cuentagotas neutro desactivado")

        def _sample_neutral_patch(self, x: float, y: float, *, radius: int = 9) -> tuple[np.ndarray, int]:
            if self._original_linear is None:
                raise ValueError("No hay imagen cargada para muestrear.")
            image = np.asarray(self._original_linear, dtype=np.float32)
            if image.ndim != 3 or image.shape[2] < 3:
                raise ValueError("La imagen cargada no contiene datos RGB.")

            h, w = image.shape[:2]
            xi = int(round(float(np.clip(x, 0, max(0, w - 1)))))
            yi = int(round(float(np.clip(y, 0, max(0, h - 1)))))
            r = max(2, int(radius))
            crop = image[max(0, yi - r) : min(h, yi + r + 1), max(0, xi - r) : min(w, xi + r + 1), :3]
            flat = crop.reshape((-1, 3))
            finite = np.all(np.isfinite(flat), axis=1)
            flat = np.clip(flat[finite], 0.0, 1.0)
            if flat.shape[0] < 4:
                raise ValueError("La zona muestreada no contiene suficientes pixeles validos.")

            luminance = flat @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
            max_channel = np.max(flat, axis=1)
            valid = (luminance > 0.015) & (luminance < 0.98) & (max_channel < 0.995)
            if int(np.count_nonzero(valid)) < 4:
                raise ValueError("El punto elegido esta demasiado oscuro o saturado; elige un gris/blanco sin clipping.")

            sample = np.median(flat[valid], axis=0).astype(np.float32)
            return sample, int(np.count_nonzero(valid))

        def _apply_neutral_picker_at(self, x: float, y: float) -> None:
            try:
                sample, count = self._sample_neutral_patch(x, y)
                temperature, tint = estimate_temperature_tint_from_neutral_sample(sample)
            except ValueError as exc:
                QtWidgets.QMessageBox.information(self, "Punto neutro", str(exc))
                self._set_status(str(exc))
                return

            self.combo_illuminant_render.blockSignals(True)
            self._set_combo_text(self.combo_illuminant_render, "Personalizado")
            self.combo_illuminant_render.blockSignals(False)

            self.spin_render_temperature.blockSignals(True)
            self.spin_render_tint.blockSignals(True)
            self.spin_render_temperature.setValue(int(temperature))
            self.spin_render_tint.setValue(float(tint))
            self.spin_render_temperature.blockSignals(False)
            self.spin_render_tint.blockSignals(False)

            if hasattr(self, "label_neutral_picker"):
                self.label_neutral_picker.setText(
                    (
                        "Punto neutro: "
                        f"RGB {sample[0]:.3f}, {sample[1]:.3f}, {sample[2]:.3f} "
                        f"({count} px) -> {temperature} K / matiz {tint:+.1f}"
                    )
                )
            self._set_neutral_picker_active(False)
            if self._original_linear is not None:
                self._refresh_preview()
            self._save_active_session(silent=True)
            self._set_status(f"Balance neutro aplicado: {temperature} K, matiz {tint:+.1f}")

        def _on_tone_curve_enabled_changed(self, enabled: bool) -> None:
            self._set_tone_curve_controls_enabled(enabled)
            self._on_render_control_change()

        def _on_tone_curve_preset_changed(self, _index: int) -> None:
            key = self._tone_curve_preset_key()
            if key != "custom":
                self.tone_curve_editor.set_points(self._tone_curve_preset_points(key), emit=False)
            self._on_render_control_change()

        def _on_tone_curve_range_changed(self, *_args) -> None:
            black = self.slider_tone_curve_black.value() / 1000.0
            white = self.slider_tone_curve_white.value() / 1000.0
            if white <= black + 0.01:
                if self.sender() is self.slider_tone_curve_black:
                    black = max(0.0, white - 0.01)
                else:
                    white = min(1.0, black + 0.01)
                self._set_tone_curve_range_controls(black, white)
            else:
                self.tone_curve_editor.set_input_range(black, white)
            self._on_render_control_change()

        def _on_tone_curve_points_changed(self, _points: object) -> None:
            if self._tone_curve_preset_key() != "custom":
                self.combo_tone_curve_preset.blockSignals(True)
                self._set_combo_data(self.combo_tone_curve_preset, "custom")
                self.combo_tone_curve_preset.blockSignals(False)
            self._on_render_control_change()

        def _on_render_control_change(self) -> None:
            if self._original_linear is not None:
                self._schedule_preview_refresh()

        def _reset_tone_curve(self) -> None:
            self.check_tone_curve_enabled.setChecked(False)
            self._set_combo_data(self.combo_tone_curve_preset, "linear")
            self._set_tone_curve_range_controls(0.0, 1.0)
            self.tone_curve_editor.set_points(self._tone_curve_preset_points("linear"), emit=False)
            self._set_tone_curve_controls_enabled(False)
            self._on_render_control_change()

        def _reset_color_adjustments(self, *_args: object, refresh: bool = True) -> None:
            self._set_neutral_picker_active(False)
            if hasattr(self, "label_neutral_picker"):
                self.label_neutral_picker.setText("Punto neutro: sin muestra")
            self.combo_illuminant_render.setCurrentIndex(1)
            self.spin_render_temperature.setValue(5003)
            self.spin_render_tint.setValue(0.0)
            if refresh and self._original_linear is not None:
                self._refresh_preview()

        def _reset_tone_adjustments(self, *_args: object, refresh: bool = True) -> None:
            self.slider_brightness.setValue(0)
            self.slider_black_point.setValue(0)
            self.slider_white_point.setValue(1000)
            self.slider_contrast.setValue(0)
            self.slider_midtone.setValue(100)
            self._reset_tone_curve()
            if refresh and self._original_linear is not None:
                self._refresh_preview()

        def _reset_basic_adjustments(self) -> None:
            self._reset_color_adjustments(refresh=False)
            self._reset_tone_adjustments(refresh=False)
            if self._original_linear is not None:
                self._refresh_preview()

        def _sync_viewer_transform(self) -> None:
            for panel_name in (
                "image_result_single",
                "image_original_compare",
                "image_result_compare",
            ):
                if hasattr(self, panel_name):
                    getattr(self, panel_name).set_view_transform(
                        zoom=self._viewer_zoom,
                        rotation=self._viewer_rotation,
                    )
            if hasattr(self, "viewer_zoom_label"):
                self.viewer_zoom_label.setText(f"{int(round(self._viewer_zoom * 100))}%")

        def _viewer_zoom_in(self) -> None:
            self._viewer_zoom = float(np.clip(self._viewer_zoom * 1.25, 0.2, 8.0))
            self._sync_viewer_transform()

        def _viewer_zoom_out(self) -> None:
            self._viewer_zoom = float(np.clip(self._viewer_zoom / 1.25, 0.2, 8.0))
            self._sync_viewer_transform()

        def _viewer_zoom_100(self) -> None:
            self._viewer_zoom = 1.0
            self._sync_viewer_transform()

        def _viewer_fit(self) -> None:
            self._viewer_zoom = 1.0
            self._viewer_rotation = 0
            self._sync_viewer_transform()

        def _viewer_rotate_left(self) -> None:
            self._viewer_rotation = (self._viewer_rotation - 90) % 360
            self._sync_viewer_transform()

        def _viewer_rotate_right(self) -> None:
            self._viewer_rotation = (self._viewer_rotation + 90) % 360
            self._sync_viewer_transform()

        def _on_histogram_clip_witness_toggled(self, checked: bool) -> None:
            self._settings.setValue("view/histogram_clip_witness", bool(checked))
            if hasattr(self, "viewer_histogram"):
                self.viewer_histogram.set_clip_markers_enabled(bool(checked))
                self._apply_histogram_clip_metrics(self.viewer_histogram.clip_metrics())

        def _on_image_clip_overlay_toggled(self, checked: bool) -> None:
            self._settings.setValue("view/image_clip_overlay", bool(checked))
            for panel_name in ("image_result_single", "image_result_compare", "image_original_compare"):
                if hasattr(self, panel_name):
                    panel = getattr(self, panel_name)
                    panel.set_clip_overlay_enabled(bool(checked))
                    if not checked:
                        panel.clear_clip_overlay()
            if checked and self._preview_srgb is not None:
                compare_enabled = bool(getattr(self, "chk_compare", None) and self.chk_compare.isChecked())
                display_u8 = self._display_u8_for_screen(
                    self._preview_srgb,
                    bypass_profile=False,
                )
                self._set_result_display_u8(display_u8, compare_enabled=compare_enabled)
                if compare_enabled:
                    self._ensure_original_compare_panel(bypass_profile=False)

        @staticmethod
        def _clip_overlay_classes(display_u8: np.ndarray | None) -> np.ndarray | None:
            if display_u8 is None:
                return None
            rgb = np.asarray(display_u8)
            if rgb.ndim != 3 or rgb.shape[2] < 3:
                return None
            rgb_u8 = np.ascontiguousarray(rgb[..., :3].astype(np.uint8))
            shadow_mask = np.all(rgb_u8 <= int(VIEWER_HISTOGRAM_SHADOW_CLIP_U8), axis=2)
            highlight_mask = np.any(rgb_u8 >= int(VIEWER_HISTOGRAM_HIGHLIGHT_CLIP_U8), axis=2)
            classes = np.zeros(rgb_u8.shape[:2], dtype=np.uint8)
            classes[shadow_mask] = 1
            classes[highlight_mask] = 2
            classes[np.logical_and(shadow_mask, highlight_mask)] = 3
            return classes

        def _apply_clip_overlay_to_panel(self, panel: ImagePanel, display_u8: np.ndarray | None) -> None:
            enabled = bool(hasattr(self, "check_image_clip_overlay") and self.check_image_clip_overlay.isChecked())
            panel.set_clip_overlay_enabled(enabled)
            if not enabled:
                panel.clear_clip_overlay()
                return
            panel.set_clip_overlay_classes(self._clip_overlay_classes(display_u8))

        def _clear_clip_overlay_panels(self) -> None:
            for panel_name in ("image_result_single", "image_result_compare", "image_original_compare"):
                if hasattr(self, panel_name):
                    getattr(self, panel_name).clear_clip_overlay()

        def _update_viewer_histogram(self, display_u8: np.ndarray | None) -> None:
            if not hasattr(self, "viewer_histogram"):
                return
            self.viewer_histogram.set_image_u8(display_u8)
            self._apply_histogram_clip_metrics(self.viewer_histogram.clip_metrics())

        def _clear_viewer_histogram(self) -> None:
            if hasattr(self, "viewer_histogram"):
                self.viewer_histogram.clear()
            self._clear_clip_overlay_panels()
            self._apply_histogram_clip_metrics(None)

        def _apply_histogram_clip_metrics(self, metrics: dict[str, float] | None) -> None:
            if not hasattr(self, "histogram_shadow_label") or not hasattr(self, "histogram_highlight_label"):
                return
            if metrics is None:
                self.histogram_shadow_label.setText("Sombras: --")
                self.histogram_highlight_label.setText("Luces: --")
                self.histogram_shadow_label.setStyleSheet("font-size: 12px; color: #6b7280;")
                self.histogram_highlight_label.setStyleSheet("font-size: 12px; color: #6b7280;")
                return

            shadow_pct = float(metrics.get("shadow_any", 0.0)) * 100.0
            highlight_pct = float(metrics.get("highlight_any", 0.0)) * 100.0
            self.histogram_shadow_label.setText(f"Sombras: {shadow_pct:.2f}%")
            self.histogram_highlight_label.setText(f"Luces: {highlight_pct:.2f}%")
            alert_pct = float(VIEWER_HISTOGRAM_CLIP_ALERT_RATIO) * 100.0
            shadow_alert = shadow_pct > alert_pct
            highlight_alert = highlight_pct > alert_pct
            self.histogram_shadow_label.setStyleSheet(
                "font-size: 12px; color: #60a5fa;" if shadow_alert else "font-size: 12px; color: #94a3b8;"
            )
            self.histogram_highlight_label.setStyleSheet(
                "font-size: 12px; color: #f87171;" if highlight_alert else "font-size: 12px; color: #94a3b8;"
            )

        def _build_effective_recipe(self) -> Recipe:
            recipe = Recipe()
            path_text = self.path_recipe.text().strip()
            if path_text:
                p = Path(path_text)
                if p.exists():
                    recipe = load_recipe(p)

            recipe.raw_developer = str(self.combo_raw_developer.currentData() or self.combo_raw_developer.currentText())
            recipe.demosaic_algorithm = self._supported_gui_demosaic(
                str(self.combo_demosaic.currentData() or self.combo_demosaic.currentText()),
                notify=False,
            )
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
            self._ensure_session_output_controls()
            current = self.path_profile_out.text().strip()
            if not current or self._is_legacy_temp_output_path(current):
                current = str(self._session_default_outputs()["profile_out"])
            ext = self.combo_profile_format.currentText().strip().lower() or ".icc"
            p = Path(current)
            if p.suffix.lower() != ext:
                p = p.with_suffix(ext)
            self.path_profile_out.setText(str(p))
            if hasattr(self, "profile_out_path_edit"):
                self.profile_out_path_edit.setText(str(p))
            return p

        def _preview_recipe_signature(self, recipe: Recipe) -> str:
            wb = ",".join(f"{float(v):.6g}" for v in recipe.wb_multipliers)
            return "|".join(
                [
                    recipe.raw_developer,
                    recipe.demosaic_algorithm,
                    recipe.white_balance_mode,
                    recipe.black_level_mode,
                    recipe.tone_curve,
                    f"{float(recipe.exposure_compensation):.3g}",
                    recipe.output_space,
                    str(bool(recipe.profiling_mode)),
                    wb,
                ]
            )

        def _preview_base_signature(
            self,
            *,
            selected: Path,
            recipe: Recipe,
        ) -> str:
            try:
                st = selected.stat()
                stamp = f"{st.st_mtime_ns}:{st.st_size}"
            except Exception:
                stamp = "nostat"
            recipe_sig = self._preview_recipe_signature(recipe)
            return f"{self._cache_path_identity(selected)}|{stamp}|preview-v4|{recipe_sig}"

        def _preview_cache_key(
            self,
            *,
            selected: Path,
            recipe: Recipe,
            fast_raw: bool,
            max_preview_side: int,
        ) -> str:
            base_sig = self._preview_base_signature(
                selected=selected,
                recipe=recipe,
            )
            fast_token = int(bool(fast_raw))
            return f"{base_sig}|{fast_token}|fr={fast_token}|ms={int(max_preview_side)}"

        @staticmethod
        def _run_preview_load_inline() -> bool:
            # Tests expect deterministic preview loading without waiting for Qt threads.
            return bool(
                os.environ.get("PYTEST_CURRENT_TEST")
                or os.environ.get("NEXORAW_SYNC_PREVIEW_LOAD")
            )

        def _cache_preview_memory(self, key: str, image: np.ndarray) -> None:
            if key in self._preview_cache:
                self._preview_cache.pop(key, None)
                self._preview_cache_order = [k for k in self._preview_cache_order if k != key]
            self._preview_cache[key] = image.copy()
            self._preview_cache_order.append(key)
            while (
                len(self._preview_cache_order) > PREVIEW_CACHE_MAX_ENTRIES
                or self._preview_cache_bytes() > PREVIEW_CACHE_MAX_BYTES
            ):
                old = self._preview_cache_order.pop(0)
                self._preview_cache.pop(old, None)

        def _cache_preview_image(self, key: str, image: np.ndarray, *, selected: Path | None = None) -> None:
            self._cache_preview_memory(key, image)
            self._write_preview_to_disk_cache(key, image, selected=selected)

        def _cached_preview_image(self, key: str, *, selected: Path | None = None) -> np.ndarray | None:
            image = self._preview_cache.get(key)
            if image is not None:
                self._preview_cache_order = [k for k in self._preview_cache_order if k != key]
                self._preview_cache_order.append(key)
                return image
            image = self._read_preview_from_disk_cache(key, selected=selected)
            if image is not None:
                self._cache_preview_memory(key, image)
                return image
            self._preview_cache_order = [k for k in self._preview_cache_order if k != key]
            return None

        def _preview_disk_cache_dir(self, selected: Path | None = None) -> Path:
            return self._disk_cache_dirs(selected, "previews")[0]

        def _preview_disk_cache_path(self, key: str, *, base_dir: Path | None = None, selected: Path | None = None) -> Path:
            return self._disk_cache_path(base_dir or self._preview_disk_cache_dir(selected), key, ".npy")

        def _read_preview_from_disk_cache(self, key: str, *, selected: Path | None = None) -> np.ndarray | None:
            for cache_dir in self._disk_cache_dirs(selected, "previews"):
                cache_path = self._preview_disk_cache_path(key, base_dir=cache_dir)
                if not cache_path.is_file():
                    continue
                try:
                    with cache_path.open("rb") as handle:
                        image = np.load(handle, allow_pickle=False)
                    image = np.asarray(image, dtype=np.float32)
                    if image.ndim != 3 or image.shape[-1] < 3:
                        continue
                    try:
                        os.utime(cache_path, None)
                    except Exception:
                        pass
                    return np.ascontiguousarray(image[..., :3])
                except Exception:
                    continue
            return None

        def _write_preview_to_disk_cache(self, key: str, image: np.ndarray, *, selected: Path | None = None) -> None:
            try:
                cache_dir = self._preview_disk_cache_dir(selected)
                cache_path = self._preview_disk_cache_path(key, base_dir=cache_dir)
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = cache_path.with_name(f"{cache_path.name}.tmp")
                array = np.ascontiguousarray(np.asarray(image, dtype=np.float32)[..., :3])
                with tmp_path.open("wb") as handle:
                    np.save(handle, array, allow_pickle=False)
                os.replace(tmp_path, cache_path)
                self._prune_disk_cache(
                    cache_dir,
                    pattern="*.npy",
                    max_entries=PREVIEW_DISK_CACHE_MAX_ENTRIES,
                    max_bytes=PREVIEW_DISK_CACHE_MAX_BYTES,
                )
            except Exception:
                return

        def _preview_cache_bytes(self) -> int:
            return int(sum(int(image.nbytes) for image in self._preview_cache.values()))

        def _invalidate_preview_cache(self) -> None:
            self._preview_cache.clear()
            self._preview_cache_order.clear()
            self._last_loaded_preview_key = None
            self._loaded_preview_base_signature = None
            self._loaded_preview_fast_raw = None
            self._loaded_preview_source_max_side = 0
            self._tone_curve_histogram_key = None
            self._preview_load_pending_request = None
            self._profile_preview_pending_request = None
            self._profile_preview_expected_key = None
            self._profile_preview_error_key = None
            self._interactive_preview_pending_request = None
            self._interactive_preview_expected_key = None
            self._interactive_preview_request_seq = 0
            self._profile_preview_cache.clear()
            self._profile_preview_cache_order.clear()
            self._clear_adjustment_caches()
            self._set_interactive_preview_busy(False)

        def _load_selected_from_timer(self) -> None:
            if self._selected_file is None:
                return
            self._on_load_selected(show_message=False)

        def _on_load_selected(self, _checked: bool = False, *, show_message: bool = True) -> None:
            if self._selected_file is None:
                self._clear_viewer_histogram()
                if show_message:
                    QtWidgets.QMessageBox.information(self, "Info", "Selecciona primero un archivo.")
                return

            original_selected = self._selected_file
            selected = self._resolve_existing_browsable_path(original_selected)
            if selected is None:
                self._selection_load_timer.stop()
                self._metadata_timer.stop()
                self._selected_file = None
                self._last_loaded_preview_key = None
                self._clear_manual_chart_points_for_file_change()
                self.selected_file_label.setText("Sin archivo seleccionado")
                self._clear_metadata_view()
                self._clear_viewer_histogram()
                self._set_status(f"Archivo no encontrado: {original_selected}")
                if show_message:
                    QtWidgets.QMessageBox.information(self, "Info", f"No existe el archivo:\n{original_selected}")
                return
            if self._normalized_path_key(selected) != self._normalized_path_key(original_selected):
                self._selected_file = selected
                self.selected_file_label.setText(str(selected))
            recipe = self._build_effective_recipe()
            max_quality_preview = self._preview_requires_max_quality()
            is_raw = selected.suffix.lower() in RAW_EXTENSIONS
            fast_raw = bool(is_raw and not max_quality_preview)
            if is_raw:
                # Preview policy: always use the most responsive demosaic path.
                # Final render keeps the recipe-selected algorithm (e.g. AMaZE).
                recipe.demosaic_algorithm = self._balanced_preview_demosaic()
            max_preview_side = self._effective_preview_max_side()
            base_signature = self._preview_base_signature(
                selected=selected,
                recipe=recipe,
            )
            cache_key = self._preview_cache_key(
                selected=selected,
                recipe=recipe,
                fast_raw=fast_raw,
                max_preview_side=max_preview_side,
            )

            if (
                self._original_linear is not None
                and self._loaded_preview_base_signature == base_signature
                and self._last_loaded_preview_key is not None
            ):
                current_side = int(max(self._original_linear.shape[0], self._original_linear.shape[1]))
                loaded_fast_raw = bool(self._loaded_preview_fast_raw)
                same_or_higher_quality = (
                    (max_preview_side <= 0 and not loaded_fast_raw)
                    or (max_preview_side > 0 and current_side >= int(max_preview_side))
                )
                # Never downgrade quality/source size implicitly while staying on
                # the same file + processing recipe.
                if (not loaded_fast_raw and fast_raw) or same_or_higher_quality:
                    if self._manual_chart_marking_after_reload:
                        self._manual_chart_marking_after_reload = False
                        self._begin_manual_chart_marking()
                    if cache_key == self._last_loaded_preview_key:
                        return
                    self._refresh_preview()
                    return

            if cache_key == self._last_loaded_preview_key and self._original_linear is not None:
                if self._manual_chart_marking_after_reload:
                    self._manual_chart_marking_after_reload = False
                    self._begin_manual_chart_marking()
                return

            cached = self._cached_preview_image(cache_key, selected=selected)
            if cached is not None:
                self._original_linear = cached.copy()
                self._adjusted_linear = self._original_linear.copy()
                self._last_loaded_preview_key = cache_key
                self._loaded_preview_base_signature = base_signature
                self._loaded_preview_fast_raw = bool(fast_raw)
                self._loaded_preview_source_max_side = int(max(self._original_linear.shape[0], self._original_linear.shape[1]))
                self._clear_adjustment_caches()
                self._refresh_preview()
                self._log_preview(f"Preview cargada desde cache: {selected.name}")
                self._set_status(f"Preview en cache: {selected.name}")
                if self._manual_chart_marking_after_reload:
                    self._manual_chart_marking_after_reload = False
                    self._begin_manual_chart_marking()
                return

            recipe_request = Recipe(**asdict(recipe))
            self._queue_preview_load_request((selected, recipe_request, fast_raw, max_preview_side, cache_key))

        def _queue_preview_load_request(
            self,
            request: tuple[Path, Recipe, bool, int, str],
        ) -> None:
            selected, _recipe, _fast_raw, _max_preview_side, cache_key = request
            if self._preview_load_task_active:
                if self._preview_load_inflight_key == cache_key:
                    return
                self._preview_load_pending_request = request
                return
            self._preview_load_pending_request = None
            self._start_preview_load_task(request)
            self._set_status(f"Cargando preview: {selected.name}")

        def _start_preview_load_task(
            self,
            request: tuple[Path, Recipe, bool, int, str],
        ) -> None:
            selected, recipe, fast_raw, max_preview_side, cache_key = request

            def task():
                image_linear, msg = load_image_for_preview(
                    selected,
                    recipe=recipe,
                    fast_raw=fast_raw,
                    max_preview_side=max_preview_side,
                )
                return selected, cache_key, image_linear, msg

            self._preview_load_task_active = True
            self._preview_load_inflight_key = cache_key
            thread: TaskThread | None = None

            def cleanup() -> None:
                self._preview_load_task_active = False
                self._preview_load_inflight_key = None
                if thread is not None and thread in self._threads:
                    self._threads.remove(thread)
                if thread is not None:
                    thread.deleteLater()
                pending = self._preview_load_pending_request
                self._preview_load_pending_request = None
                if pending is not None:
                    self._start_preview_load_task(pending)

            def ok(payload) -> None:
                try:
                    loaded_selected, loaded_key, image_linear, msg = payload
                    if self._selected_file != loaded_selected:
                        return
                    self._original_linear = np.asarray(image_linear, dtype=np.float32)
                    self._adjusted_linear = self._original_linear.copy()
                    self._last_loaded_preview_key = loaded_key
                    self._loaded_preview_base_signature = self._preview_base_signature(
                        selected=selected,
                        recipe=recipe,
                    )
                    self._loaded_preview_fast_raw = bool(fast_raw)
                    self._loaded_preview_source_max_side = int(
                        max(self._original_linear.shape[0], self._original_linear.shape[1])
                    )
                    self._clear_adjustment_caches()
                    self._cache_preview_image(loaded_key, self._original_linear, selected=loaded_selected)
                    self._refresh_preview()
                    self._log_preview(msg)
                    self._set_status(f"Preview cargada: {loaded_selected.name}")
                    if self._manual_chart_marking_after_reload:
                        self._manual_chart_marking_after_reload = False
                        self._begin_manual_chart_marking()
                finally:
                    cleanup()

            def fail(trace: str) -> None:
                try:
                    self._log_preview(trace[-1200:])
                    if self._selected_file == selected:
                        self._set_status(f"Error de preview: {selected.name}")
                finally:
                    cleanup()

            if self._run_preview_load_inline():
                try:
                    ok(task())
                except Exception:
                    fail(traceback.format_exc())
                return

            thread = TaskThread(task)
            self._threads.append(thread)
            thread.succeeded.connect(ok)
            thread.failed.connect(fail)
            thread.start()

        def _on_precache_visible_previews(self, *, full_resolution: bool) -> None:
            files = [p for p in self._file_list_paths() if p.suffix.lower() in RAW_EXTENSIONS]
            if not files:
                QtWidgets.QMessageBox.information(self, "Info", "No hay RAW visibles para precache.")
                return
            mode_label = "1:1" if full_resolution else "normal"
            reply = QtWidgets.QMessageBox.question(
                self,
                "Precache de previews",
                (
                    f"Se van a precalcular {len(files)} previews RAW en modo {mode_label}.\n\n"
                    "Este proceso puede tardar, pero mejora la respuesta posterior.\n"
                    "¿Continuar?"
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return
            self._start_precache_visible_previews(files, full_resolution=full_resolution)

        def _start_precache_visible_previews(self, files: list[Path], *, full_resolution: bool) -> None:
            recipe_base = self._build_effective_recipe()
            recipe_base_payload = asdict(recipe_base)
            max_quality_preview = bool(full_resolution or self._preview_requires_max_quality())
            max_preview_side = 0 if full_resolution else int(PREVIEW_AUTO_BASE_MAX_SIDE)
            mode_label = "1:1" if full_resolution else "normal"

            def task():
                built = 0
                skipped = 0
                errors: list[dict[str, str]] = []
                for src in files:
                    try:
                        recipe = Recipe(**recipe_base_payload)
                        is_raw = src.suffix.lower() in RAW_EXTENSIONS
                        fast_raw = bool(is_raw and not max_quality_preview)
                        if is_raw:
                            recipe.demosaic_algorithm = self._balanced_preview_demosaic()
                        cache_key = self._preview_cache_key(
                            selected=src,
                            recipe=recipe,
                            fast_raw=fast_raw,
                            max_preview_side=max_preview_side,
                        )
                        if self._read_preview_from_disk_cache(cache_key, selected=src) is not None:
                            skipped += 1
                            continue
                        image_linear, _msg = load_image_for_preview(
                            src,
                            recipe=recipe,
                            fast_raw=fast_raw,
                            max_preview_side=max_preview_side,
                        )
                        self._write_preview_to_disk_cache(
                            cache_key,
                            np.asarray(image_linear, dtype=np.float32),
                            selected=src,
                        )
                        built += 1
                    except Exception as exc:
                        errors.append({"source": str(src), "error": str(exc)})
                return {
                    "mode": mode_label,
                    "total": len(files),
                    "built": built,
                    "skipped": skipped,
                    "errors": errors,
                }

            def on_success(payload) -> None:
                total = int(payload.get("total", 0))
                built = int(payload.get("built", 0))
                skipped = int(payload.get("skipped", 0))
                errors = payload.get("errors", [])
                self._log_preview(
                    f"Precache {payload.get('mode', 'normal')}: "
                    f"{built} generadas, {skipped} ya en cache, {len(errors)} errores (total {total})."
                )
                self._set_status(
                    f"Precache {payload.get('mode', 'normal')} completada: "
                    f"{built} nuevas, {skipped} reutilizadas."
                )
                if full_resolution and self._selected_file is not None:
                    self._last_loaded_preview_key = None
                    self._on_load_selected(show_message=False)

            self._start_background_task(
                f"Precache previews RAW ({mode_label})",
                task,
                on_success,
            )

        def _on_slider_change(self) -> None:
            if self._original_linear is not None:
                self._schedule_preview_refresh()

        def _on_slider_release(self) -> None:
            if self._original_linear is not None:
                self._schedule_preview_refresh()

        def _is_preview_interaction_active(self) -> bool:
            slider_names = (
                "slider_sharpen",
                "slider_radius",
                "slider_noise_luma",
                "slider_noise_color",
                "slider_ca_red",
                "slider_ca_blue",
                "slider_brightness",
                "slider_black_point",
                "slider_white_point",
                "slider_contrast",
                "slider_midtone",
                "slider_tone_curve_black",
                "slider_tone_curve_white",
            )
            for name in slider_names:
                slider = getattr(self, name, None)
                if slider is not None and bool(slider.isSliderDown()):
                    return True
            editor = getattr(self, "tone_curve_editor", None)
            return bool(editor is not None and editor.is_dragging())

        def _is_detail_interaction_active(self) -> bool:
            detail_slider_names = (
                "slider_sharpen",
                "slider_radius",
                "slider_noise_luma",
                "slider_noise_color",
                "slider_ca_red",
                "slider_ca_blue",
            )
            for name in detail_slider_names:
                slider = getattr(self, name, None)
                if slider is not None and bool(slider.isSliderDown()):
                    return True
            return False

        def _interactive_preview_source(
            self,
            image: np.ndarray,
            *,
            max_side_limit: int = PREVIEW_INTERACTIVE_MAX_SIDE,
        ) -> np.ndarray:
            rgb = np.asarray(image, dtype=np.float32)
            if max_side_limit <= 0:
                return rgb
            h, w = int(rgb.shape[0]), int(rgb.shape[1])
            max_side = max(h, w)
            if max_side <= int(max_side_limit):
                return rgb
            scale = float(max_side_limit) / float(max_side)
            nw = max(1, int(round(w * scale)))
            nh = max(1, int(round(h * scale)))
            return np.clip(
                cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA),
                0.0,
                1.0,
            ).astype(np.float32)

        def _profile_preview_profile_stamp(self, profile_path: Path) -> str:
            try:
                resolved = profile_path.expanduser().resolve()
                st = resolved.stat()
                return f"{resolved}|{st.st_mtime_ns}|{st.st_size}"
            except OSError:
                return str(profile_path)

        def _preview_profile_settings_signature(self) -> str:
            detail_state = self._detail_adjustment_state()
            render_state = self._render_adjustment_state()
            tone_points = render_state.get("tone_curve_points") or []
            tone_sig = ",".join(
                f"{float(x):.4f}:{float(y):.4f}"
                for x, y in normalize_tone_curve_points(
                    [
                        (p[0], p[1])
                        for p in tone_points
                        if isinstance(p, (list, tuple)) and len(p) >= 2
                    ]
                )
            )
            source_key = self._last_loaded_preview_key or str(id(self._original_linear))
            return "|".join(
                [
                    source_key,
                    f"sh={int(detail_state.get('sharpen', 0))}",
                    f"sr={int(detail_state.get('radius', 10))}",
                    f"nl={int(detail_state.get('noise_luma', 0))}",
                    f"nc={int(detail_state.get('noise_color', 0))}",
                    f"cr={int(detail_state.get('ca_red', 0))}",
                    f"cb={int(detail_state.get('ca_blue', 0))}",
                    f"tk={int(render_state.get('temperature_kelvin', 5003))}",
                    f"ti={float(render_state.get('tint', 0.0)):.3f}",
                    f"be={float(render_state.get('brightness_ev', 0.0)):.3f}",
                    f"bp={float(render_state.get('black_point', 0.0)):.4f}",
                    f"wp={float(render_state.get('white_point', 1.0)):.4f}",
                    f"ct={float(render_state.get('contrast', 0.0)):.3f}",
                    f"mt={float(render_state.get('midtone', 1.0)):.3f}",
                    f"te={int(bool(render_state.get('tone_curve_enabled', False)))}",
                    f"tb={float(render_state.get('tone_curve_black_point', 0.0)):.4f}",
                    f"tw={float(render_state.get('tone_curve_white_point', 1.0)):.4f}",
                    f"tp={tone_sig}",
                ]
            )

        def _profile_preview_request_key(self, profile_path: Path) -> str:
            max_side_limit = self._profile_preview_max_side_limit()
            return "|".join(
                [
                    self._preview_profile_settings_signature(),
                    self._profile_preview_profile_stamp(profile_path),
                    f"pm={int(max_side_limit)}",
                ]
            )

        def _profile_preview_max_side_limit(self) -> int:
            if self._precision_detail_preview_enabled() or float(self._viewer_zoom) >= 1.0:
                return 0
            return int(PREVIEW_PROFILE_APPLY_MAX_SIDE)

        def _cached_profile_preview_image(self, key: str) -> np.ndarray | None:
            image = self._profile_preview_cache.get(key)
            if image is None:
                return None
            self._profile_preview_cache_order = [k for k in self._profile_preview_cache_order if k != key]
            self._profile_preview_cache_order.append(key)
            return image

        def _cache_profile_preview_image(self, key: str, image: np.ndarray) -> None:
            if key in self._profile_preview_cache:
                self._profile_preview_cache.pop(key, None)
                self._profile_preview_cache_order = [k for k in self._profile_preview_cache_order if k != key]
            self._profile_preview_cache[key] = np.asarray(image, dtype=np.float32).copy()
            self._profile_preview_cache_order.append(key)
            while len(self._profile_preview_cache_order) > PREVIEW_PROFILE_CACHE_MAX_ENTRIES:
                old = self._profile_preview_cache_order.pop(0)
                self._profile_preview_cache.pop(old, None)

        def _profile_preview_source_for_async(
            self,
            image: np.ndarray,
            *,
            max_side_limit: int,
        ) -> tuple[np.ndarray, bool]:
            rgb = np.asarray(image, dtype=np.float32)
            if int(max_side_limit) <= 0:
                return rgb, False
            h, w = int(rgb.shape[0]), int(rgb.shape[1])
            max_side = max(h, w)
            if max_side <= int(max_side_limit):
                return rgb, False
            scale = float(max_side_limit) / float(max_side)
            nw = max(1, int(round(w * scale)))
            nh = max(1, int(round(h * scale)))
            resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
            return np.clip(resized, 0.0, 1.0).astype(np.float32), True

        def _queue_profile_preview_request(
            self,
            request_key: str,
            profile_path: Path,
            image_linear: np.ndarray,
            target_shape: tuple[int, int],
        ) -> None:
            image_copy = np.asarray(image_linear, dtype=np.float32).copy()
            if self._profile_preview_task_active:
                if self._profile_preview_inflight_key == request_key:
                    return
                self._profile_preview_pending_request = (
                    request_key,
                    profile_path,
                    image_copy,
                    target_shape,
                )
                return
            self._start_profile_preview_task(
                (
                    request_key,
                    profile_path,
                    image_copy,
                    target_shape,
                )
            )

        def _start_profile_preview_task(
            self,
            request: tuple[str, Path, np.ndarray, tuple[int, int]],
        ) -> None:
            request_key, profile_path, image_linear, target_shape = request
            max_side_limit = self._profile_preview_max_side_limit()

            def task():
                source, downscaled = self._profile_preview_source_for_async(
                    image_linear,
                    max_side_limit=max_side_limit,
                )
                candidate = apply_profile_preview(source, profile_path)
                if downscaled:
                    target_h, target_w = target_shape
                    candidate = cv2.resize(
                        np.asarray(candidate, dtype=np.float32),
                        (max(1, int(target_w)), max(1, int(target_h))),
                        interpolation=cv2.INTER_LINEAR,
                    )
                return request_key, np.asarray(candidate, dtype=np.float32)

            thread = TaskThread(task)
            self._profile_preview_task_active = True
            self._profile_preview_inflight_key = request_key
            self._threads.append(thread)

            def cleanup() -> None:
                self._profile_preview_task_active = False
                self._profile_preview_inflight_key = None
                if thread in self._threads:
                    self._threads.remove(thread)
                thread.deleteLater()
                pending = self._profile_preview_pending_request
                self._profile_preview_pending_request = None
                if pending is not None:
                    self._start_profile_preview_task(pending)

            def ok(payload) -> None:
                try:
                    key, candidate = payload
                    if self._looks_broken_profile_preview(candidate):
                        self._log_preview(
                            "Aviso: preview del perfil ICC parece no fiable "
                            "(dominante/clipping extremo). Se muestra vista sin perfil."
                        )
                        return
                    self._cache_profile_preview_image(key, candidate)
                    if key != self._profile_preview_expected_key:
                        return
                    self._preview_srgb = np.asarray(candidate, dtype=np.float32)
                    display_u8 = self._display_u8_for_screen(self._preview_srgb, bypass_profile=False)
                    self._set_result_display_u8(display_u8, compare_enabled=bool(self.chk_compare.isChecked()))
                finally:
                    cleanup()

            def fail(trace: str) -> None:
                try:
                    key = f"{request_key}|{trace.strip().splitlines()[-1] if trace.strip() else 'error'}"
                    if self._profile_preview_error_key != key:
                        self._profile_preview_error_key = key
                        self._log_preview(
                            f"Aviso: no se pudo aplicar preview ICC con ArgyllCMS: "
                            f"{trace.strip().splitlines()[-1] if trace.strip() else 'error'}"
                        )
                finally:
                    cleanup()

            thread.succeeded.connect(ok)
            thread.failed.connect(fail)
            thread.start()

        def _queue_interactive_preview_request(
            self,
            request: tuple[
                str,
                str | None,
                np.ndarray,
                dict[str, float],
                dict[str, Any],
                bool,
                bool,
                int,
                bool,
            ],
        ) -> None:
            request_key, _source_key, _source_linear, _detail_kwargs, _render_kwargs, _compare_enabled, _bypass, _max_side_limit, _apply_detail = request
            self._interactive_preview_expected_key = request_key
            if self._interactive_preview_task_active:
                if self._interactive_preview_inflight_key == request_key:
                    return
                self._interactive_preview_pending_request = request
                return
            self._interactive_preview_pending_request = None
            self._start_interactive_preview_task(request)

        def _start_interactive_preview_task(
            self,
            request: tuple[
                str,
                str | None,
                np.ndarray,
                dict[str, float],
                dict[str, Any],
                bool,
                bool,
                int,
                bool,
            ],
        ) -> None:
            (
                request_key,
                source_key,
                source_linear,
                detail_kwargs,
                render_kwargs,
                compare_enabled,
                bypass_display_profile,
                max_side_limit,
                apply_detail,
            ) = request

            def task():
                source = self._interactive_preview_source(
                    np.asarray(source_linear, dtype=np.float32),
                    max_side_limit=int(max_side_limit),
                )
                if apply_detail:
                    detail_adjusted = apply_adjustments(
                        source,
                        denoise_luminance=float(detail_kwargs.get("denoise_luminance", 0.0)),
                        denoise_color=float(detail_kwargs.get("denoise_color", 0.0)),
                        sharpen_amount=float(detail_kwargs.get("sharpen_amount", 0.0)),
                        sharpen_radius=float(detail_kwargs.get("sharpen_radius", 1.0)),
                        lateral_ca_red_scale=float(detail_kwargs.get("lateral_ca_red_scale", 1.0)),
                        lateral_ca_blue_scale=float(detail_kwargs.get("lateral_ca_blue_scale", 1.0)),
                    )
                else:
                    # During tonal curve/slider drag prioritize responsiveness and
                    # defer detail operators to the final non-interactive refresh.
                    detail_adjusted = source
                adjusted = apply_render_adjustments(detail_adjusted, **render_kwargs)
                result_srgb = linear_to_srgb_display(adjusted)
                return (
                    request_key,
                    source_key,
                    np.asarray(result_srgb, dtype=np.float32),
                    bool(compare_enabled),
                bool(bypass_display_profile),
            )

            thread = TaskThread(task)
            started_at = time.perf_counter()
            self._interactive_preview_task_active = True
            self._interactive_preview_inflight_key = request_key
            self._set_interactive_preview_busy(True)
            self._threads.append(thread)

            def cleanup() -> None:
                self._interactive_preview_task_active = False
                self._interactive_preview_inflight_key = None
                if thread in self._threads:
                    self._threads.remove(thread)
                thread.deleteLater()
                pending = self._interactive_preview_pending_request
                self._interactive_preview_pending_request = None
                if pending is not None:
                    self._start_interactive_preview_task(pending)
                    return
                self._set_interactive_preview_busy(False)

            def ok(payload) -> None:
                try:
                    (
                        key,
                        payload_source_key,
                        candidate,
                        payload_compare_enabled,
                        payload_bypass_display_profile,
                    ) = payload
                    applied = False
                    if key != self._interactive_preview_expected_key:
                        return
                    if payload_source_key is not None and payload_source_key != self._last_loaded_preview_key:
                        return
                    self._preview_srgb = np.asarray(candidate, dtype=np.float32)
                    display_u8 = self._display_u8_for_screen(
                        self._preview_srgb,
                        bypass_profile=bool(payload_bypass_display_profile),
                    )
                    self._set_result_display_u8(
                        display_u8,
                        compare_enabled=bool(payload_compare_enabled and self.chk_compare.isChecked()),
                    )
                    applied = True
                    if applied:
                        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                        self._interactive_preview_last_ms = float(max(elapsed_ms, 0.0))
                        self._update_interactive_preview_time_label()
                finally:
                    cleanup()

            def fail(_trace: str) -> None:
                cleanup()

            thread.succeeded.connect(ok)
            thread.failed.connect(fail)
            thread.start()

        def _reset_adjustments(self) -> None:
            self.slider_sharpen.setValue(0)
            self.slider_radius.setValue(10)
            self.slider_noise_luma.setValue(0)
            self.slider_noise_color.setValue(0)
            self.slider_ca_red.setValue(0)
            self.slider_ca_blue.setValue(0)
            if self._original_linear is not None:
                self._refresh_preview()

        def _refresh_preview(self) -> None:
            if self._original_linear is None:
                return
            self._preview_refresh_timer.stop()
            try:
                interactive = self._is_preview_interaction_active()
                detail_interactive = interactive and self._is_detail_interaction_active()
                bypass_display_profile = bool(interactive and self._interactive_bypass_display_icc)
                nl = self.slider_noise_luma.value() / 100.0
                nc = self.slider_noise_color.value() / 100.0
                sharpen = self.slider_sharpen.value() / 100.0
                radius = self.slider_radius.value() / 10.0
                ca_red, ca_blue = self._ca_scale_factors()
                detail_kwargs: dict[str, float] = {
                    "denoise_luminance": float(nl),
                    "denoise_color": float(nc),
                    "sharpen_amount": float(sharpen),
                    "sharpen_radius": float(radius),
                    "lateral_ca_red_scale": float(ca_red),
                    "lateral_ca_blue_scale": float(ca_blue),
                }
                render_kwargs = self._render_adjustment_kwargs()
                histogram_key = self._last_loaded_preview_key or str(id(self._original_linear))
                if not interactive and self._tone_curve_histogram_key != histogram_key:
                    self.tone_curve_editor.set_histogram_from_image(self._original_linear)
                    self._tone_curve_histogram_key = histogram_key

                compare_enabled = bool(self.chk_compare.isChecked())
                if compare_enabled:
                    self._ensure_original_compare_panel(bypass_profile=bypass_display_profile)

                source_key = self._last_loaded_preview_key or str(id(self._original_linear))
                if interactive:
                    apply_detail = bool(detail_interactive)
                    if apply_detail and self._precision_detail_preview_enabled():
                        max_side_limit = 0
                    else:
                        max_side_limit = (
                            PREVIEW_INTERACTIVE_DRAG_MAX_SIDE
                            if apply_detail
                            else PREVIEW_INTERACTIVE_TONAL_MAX_SIDE
                        )
                    self._interactive_preview_request_seq += 1
                    request_key = f"{source_key}|interactive|{self._interactive_preview_request_seq}"
                    self._profile_preview_expected_key = None
                    self._profile_preview_pending_request = None
                    self._queue_interactive_preview_request(
                        (
                            request_key,
                            source_key,
                            self._original_linear,
                            detail_kwargs,
                            render_kwargs,
                            compare_enabled,
                            bypass_display_profile,
                            int(max_side_limit),
                            bool(apply_detail),
                        )
                    )
                    return

                self._interactive_preview_expected_key = None
                self._interactive_preview_pending_request = None
                self._set_interactive_preview_busy(False)

                detail_adjusted = self._detail_adjusted_preview(
                    self._original_linear,
                    denoise_luma=nl,
                    denoise_color=nc,
                    sharpen_amount=sharpen,
                    sharpen_radius=radius,
                    lateral_ca_red_scale=ca_red,
                    lateral_ca_blue_scale=ca_blue,
                )
                adjusted = apply_render_adjustments(detail_adjusted, **render_kwargs)
                self._adjusted_linear = adjusted
                result_srgb = linear_to_srgb_display(adjusted)
                should_apply_profile = (
                    self.chk_apply_profile.isChecked()
                    and self.path_profile_active.text().strip() != ""
                )
                if should_apply_profile:
                    p = Path(self.path_profile_active.text().strip())
                    if not self._profile_can_be_active(p):
                        status = self._profile_status_for_path(p) or "no disponible"
                        self._log_preview(
                            f"Aviso: perfil ICC no aplicado porque su estado QA es {status}."
                        )
                        self.path_profile_active.clear()
                        self.chk_apply_profile.setChecked(False)
                        self._profile_preview_expected_key = None
                    elif p.exists():
                        request_key = self._profile_preview_request_key(p)
                        self._profile_preview_expected_key = request_key
                        cached_profile = self._cached_profile_preview_image(request_key)
                        if cached_profile is not None:
                            result_srgb = cached_profile
                        else:
                            self._queue_profile_preview_request(
                                request_key,
                                p,
                                adjusted,
                                (int(adjusted.shape[0]), int(adjusted.shape[1])),
                            )
                    else:
                        self._profile_preview_expected_key = None
                        self._log_preview(
                            f"Aviso: perfil activo no encontrado ({p}). Se muestra vista sin perfil."
                        )
                else:
                    self._profile_preview_expected_key = None

                self._preview_srgb = np.asarray(result_srgb, dtype=np.float32)
                display_u8 = self._display_u8_for_screen(
                    self._preview_srgb,
                    bypass_profile=bypass_display_profile,
                )
                self._set_result_display_u8(display_u8, compare_enabled=compare_enabled)
                self.preview_analysis.setPlainText(preview_analysis_text(self._original_linear, adjusted))
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Aviso", str(exc))

        def _schedule_preview_refresh(self) -> None:
            if self._original_linear is None:
                return
            if self._is_preview_interaction_active():
                if not self._preview_refresh_timer.isActive():
                    self._preview_refresh_timer.start(PREVIEW_REFRESH_THROTTLE_MS)
                return
            self._preview_refresh_timer.start(PREVIEW_REFRESH_DEBOUNCE_MS)

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
            self._ensure_session_output_controls()
            default_out = str(self._session_default_outputs()["preview"])
            out_text, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Guardar preview PNG",
                default_out,
                "PNG (*.png)",
            )
            if not out_text:
                return
            out = Path(out_text)
            if out.suffix.lower() != ".png":
                out = out.with_suffix(".png")
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
            defaults = self._session_default_outputs()
            default_out = str(defaults["tiff_dir"] / f"{in_path.stem}.tiff")
            out_text, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Guardar TIFF revelado",
                default_out,
                "TIFF (*.tif *.tiff)",
            )
            if not out_text:
                return
            requested_out_path = Path(out_text)
            out_path = versioned_output_path(requested_out_path)

            recipe = self._build_effective_recipe()
            use_profile = self.chk_apply_profile.isChecked() and self.path_profile_active.text().strip() != ""
            profile_path = Path(self.path_profile_active.text().strip()) if use_profile else None
            nl = self.slider_noise_luma.value() / 100.0
            nc = self.slider_noise_color.value() / 100.0
            sharpen = self.slider_sharpen.value() / 100.0
            radius = self.slider_radius.value() / 10.0
            ca_red, ca_blue = self._ca_scale_factors()
            render_adjustments = self._render_adjustment_kwargs()
            c2pa_render_adjustments = {"applied": True, **render_adjustments}
            detail_adjustments = {
                "applied": True,
                "denoise_luminance": nl,
                "denoise_color": nc,
                "sharpen_amount": sharpen,
                "sharpen_radius": radius,
                "lateral_ca_red_scale": ca_red,
                "lateral_ca_blue_scale": ca_blue,
            }
            try:
                proof_config = self._resolve_proof_config_for_gui()
                c2pa_config = self._resolve_c2pa_config_for_gui()
            except Exception as exc:
                self._show_signature_config_error(exc)
                return

            def task():
                image = develop_image_array(in_path, recipe)
                image = self._apply_output_adjustments(
                    image,
                    denoise_luma=nl,
                    denoise_color=nc,
                    sharpen_amount=sharpen,
                    sharpen_radius=radius,
                    lateral_ca_red_scale=ca_red,
                    lateral_ca_blue_scale=ca_blue,
                    render_adjustments=render_adjustments,
                )
                mode, proof_result = write_signed_profiled_tiff(
                    out_path,
                    image,
                    source_raw=in_path,
                    recipe=recipe,
                    profile_path=profile_path,
                    c2pa_config=c2pa_config,
                    proof_config=proof_config,
                    detail_adjustments=detail_adjustments,
                    render_adjustments=c2pa_render_adjustments,
                    render_context={"entrypoint": "gui_single_develop"},
                    generic_profile_dir=self._session_generic_profile_dir(),
                )
                rendered_profile_path = self._render_profile_path_for_recipe(
                    recipe,
                    input_profile_path=profile_path,
                    color_management_mode=mode,
                )
                profile_id = self._active_development_profile_id
                development_profile = None
                if profile_id:
                    profile_descriptor = self._development_profile_by_id(profile_id) or {}
                    kind = str(profile_descriptor.get("kind") or "manual")
                    development_profile = {
                        "id": profile_id,
                        "name": str(profile_descriptor.get("name") or profile_id),
                        "kind": kind,
                        "profile_type": str(profile_descriptor.get("profile_type") or self._adjustment_profile_type_for_kind(kind)),
                    }
                sidecar = self._write_raw_settings_sidecar(
                    in_path,
                    recipe=recipe,
                    development_profile=development_profile,
                    detail_adjustments=self._detail_adjustment_state(),
                    render_adjustments=self._render_adjustment_state(),
                    profile_path=rendered_profile_path,
                    color_management_mode=mode,
                    output_tiff=out_path,
                    proof_path=Path(proof_result.proof_path),
                    status="rendered",
                )
                return {
                    "output_tiff": str(out_path),
                    "requested_tiff": str(requested_out_path),
                    "proof": proof_result.proof_path,
                    "raw_sidecar": str(sidecar) if sidecar is not None else "",
                }

            def on_success(payload) -> None:
                if payload.get("requested_tiff") != payload.get("output_tiff"):
                    self._log_preview(f"Salida existente preservada; nueva version: {payload['output_tiff']}")
                self._log_preview(f"TIFF revelado: {payload['output_tiff']}")
                self._log_preview(f"NexoRAW Proof: {payload['proof']}")
                if payload.get("raw_sidecar"):
                    self._log_preview(f"Mochila NexoRAW: {payload['raw_sidecar']}")
                self._refresh_color_reference_thumbnail_markers()
                self._set_status(f"Revelado completado: {payload['output_tiff']}")
                self._save_active_session(silent=True)

            self._start_background_task("Revelado a TIFF", task, on_success)

        def _use_current_dir_as_profile_charts(self) -> None:
            accepted = self._set_profile_reference_dir(self._current_dir)
            self._selected_chart_files = []
            self._sync_profile_chart_selection_label()
            self._refresh_color_reference_thumbnail_markers()
            if accepted:
                self._set_status(f"Directorio de referencias colorimetricas: {self._current_dir}")
            self._save_active_session(silent=True)

        def _use_selected_files_as_profile_charts(self) -> None:
            candidates = [
                p for p in self._collect_selected_file_paths()
                if p.suffix.lower() in PROFILE_CHART_EXTENSIONS
            ]
            files, rejected = self._filter_profile_reference_files(candidates)
            if not files:
                if rejected:
                    reason = rejected[0][1]
                    QtWidgets.QMessageBox.information(
                        self,
                        "Referencias no validas",
                        "Las referencias colorimetricas deben ser RAW/DNG o TIFFs originales de carta, "
                        f"no {reason}. Selecciona las capturas en 01_ORG.",
                    )
                    fallback = self._preferred_profile_reference_dir()
                    if fallback is not None:
                        self.profile_charts_dir.setText(str(fallback))
                    self._selected_chart_files = []
                    self._sync_profile_chart_selection_label()
                    self._refresh_color_reference_thumbnail_markers()
                    self._save_active_session(silent=True)
                    return
                QtWidgets.QMessageBox.information(
                    self,
                    "Info",
                    "Selecciona una o mas capturas RAW/DNG/TIFF como referencias colorimetricas.",
                )
                return
            self._selected_chart_files = sorted(set(files), key=lambda p: str(p))
            parents = {p.parent for p in self._selected_chart_files}
            if len(parents) == 1:
                self.profile_charts_dir.setText(str(next(iter(parents))))
            self._sync_profile_chart_selection_label()
            self._refresh_color_reference_thumbnail_markers()
            suffix = f"; ignoradas {len(rejected)} no validas" if rejected else ""
            self._set_status(f"Referencias colorimetricas seleccionadas: {len(self._selected_chart_files)}{suffix}")
            self._save_active_session(silent=True)

        def _sync_profile_chart_selection_label(self) -> None:
            if not hasattr(self, "profile_chart_selection_label"):
                return
            if not self._selected_chart_files:
                self.profile_chart_selection_label.setText("Referencias colorimétricas: todas las compatibles de la carpeta indicada")
                self._refresh_color_reference_thumbnail_markers()
                return
            preview = ", ".join(p.name for p in self._selected_chart_files[:4])
            if len(self._selected_chart_files) > 4:
                preview += f" (+{len(self._selected_chart_files) - 4} más)"
            self.profile_chart_selection_label.setText(
                f"Referencias colorimétricas seleccionadas: {len(self._selected_chart_files)} - {preview}"
            )
            self._refresh_color_reference_thumbnail_markers()

        def _profile_chart_files_or_none(self) -> list[Path] | None:
            files, rejected = self._filter_profile_reference_files(
                [p for p in self._selected_chart_files if p.suffix.lower() in PROFILE_CHART_EXTENSIONS]
            )
            if rejected:
                self._selected_chart_files = files
                self._sync_profile_chart_selection_label()
            return files if files else None

        def _infer_profile_chart_files(self) -> list[Path] | None:
            files = self._profile_chart_files_or_none()
            if files:
                return files

            selected = [
                p for p in self._collect_selected_file_paths()
                if p.suffix.lower() in PROFILE_CHART_EXTENSIONS
            ]
            selected, rejected = self._filter_profile_reference_files(selected)
            if selected:
                self._selected_chart_files = sorted(set(selected), key=lambda p: str(p))
                self._sync_profile_chart_selection_label()
                parents = {p.parent for p in self._selected_chart_files}
                if len(parents) == 1:
                    self.profile_charts_dir.setText(str(next(iter(parents))))
                self._refresh_color_reference_thumbnail_markers()
                self._set_status(f"Referencias colorimétricas tomadas de la selección: {len(self._selected_chart_files)}")
                return list(self._selected_chart_files)

            if (
                self._selected_file is not None
                and self._selected_file.suffix.lower() in PROFILE_CHART_EXTENSIONS
                and self._profile_reference_rejection_reason(self._selected_file) is None
            ):
                self._selected_chart_files = [self._selected_file]
                self.profile_charts_dir.setText(str(self._selected_file.parent))
                self._sync_profile_chart_selection_label()
                self._refresh_color_reference_thumbnail_markers()
                self._set_status(f"Referencia colorimétrica tomada del archivo cargado: {self._selected_file.name}")
                return list(self._selected_chart_files)

            if rejected:
                fallback = self._preferred_profile_reference_dir()
                if fallback is not None:
                    self.profile_charts_dir.setText(str(fallback))
                self._set_status("Se ignoraron referencias colorimetricas no validas en carpetas operativas.")

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

        def _pending_manual_detection_request(self, chart_files: list[Path] | None) -> dict[str, Any] | None:
            if self._selected_file is None or self._original_linear is None or len(self._manual_chart_points) != 4:
                return None

            source = self._selected_file.expanduser().resolve()
            if not self._manual_chart_points_match_selected_file():
                return None
            if chart_files:
                selected = {str(p.expanduser().resolve()) for p in chart_files}
                if str(source) not in selected:
                    return None

            if str(source) in self._manual_chart_detections:
                return None

            preview_h, preview_w = self._original_linear.shape[:2]
            return {
                "source": source,
                "points_preview": list(self._manual_chart_points),
                "preview_shape": (int(preview_h), int(preview_w)),
            }

        def _build_pending_manual_detection(
            self,
            request: dict[str, Any],
            *,
            recipe: Recipe,
            chart_type: str,
            workdir: Path,
        ) -> tuple[Path, Any]:
            source = Path(str(request["source"])).expanduser().resolve()
            points_preview = [(float(x), float(y)) for x, y in request["points_preview"]]
            preview_h, preview_w = request["preview_shape"]

            manual_dir = workdir / "manual_detections"
            manual_dir.mkdir(parents=True, exist_ok=True)
            if source.suffix.lower() in RAW_EXTENSIONS:
                target_image = manual_dir / f"{source.stem}.manual_for_profile.tiff"
                full_image = develop_image_array(source, recipe)
                write_tiff16(target_image, full_image)
            else:
                target_image = source
                full_image = read_image(target_image)

            full_h, full_w = full_image.shape[:2]
            sx = full_w / max(1, int(preview_w))
            sy = full_h / max(1, int(preview_h))
            corners = [(x * sx, y * sy) for x, y in points_preview]
            detection = detect_chart_from_corners_array(full_image, corners=corners, chart_type=chart_type)

            detection_path = manual_dir / f"{source.stem}.manual_for_profile.json"
            overlay_path = manual_dir / f"{source.stem}.manual_for_profile.overlay.png"
            write_json(detection_path, detection)
            draw_detection_overlay_array(full_image, detection, overlay_path)
            return source, detection

        def _directory_has_chart_captures(self, folder: Path) -> bool:
            try:
                return folder.exists() and folder.is_dir() and any(
                    p.is_file() and p.suffix.lower() in PROFILE_CHART_EXTENSIONS
                    for p in folder.iterdir()
                )
            except Exception:
                return False

        def _raw_files_for_chart_profile_assignment(
            self,
            charts: Path,
            chart_capture_files: list[Path] | None,
        ) -> list[Path]:
            candidates = list(chart_capture_files or [])
            if not candidates:
                try:
                    candidates = [
                        p for p in sorted(charts.iterdir())
                        if p.is_file() and p.suffix.lower() in PROFILE_CHART_EXTENSIONS
                    ]
                except Exception:
                    candidates = []
            return [p for p in candidates if p.suffix.lower() in RAW_EXTENSIONS and p.exists()]

        def _use_current_dir_as_batch_input(self) -> None:
            self.batch_input_dir.setText(str(self._current_dir))
            self._set_status(f"Directorio lote: {self._current_dir}")
            self._save_active_session(silent=True)

        def _on_generate_profile(self) -> None:
            self._ensure_session_output_controls()
            charts = Path(self.profile_charts_dir.text().strip())
            chart_capture_files = self._infer_profile_chart_files()
            if chart_capture_files is None:
                reason = self._profile_reference_rejection_reason(charts)
                if reason is not None:
                    fallback = self._preferred_profile_reference_dir()
                    if fallback is not None:
                        charts = fallback
                        self.profile_charts_dir.setText(str(charts))
                        self._set_status(
                            f"No se usan {reason} como referencias colorimetricas; se usa {charts}"
                        )
                    else:
                        QtWidgets.QMessageBox.information(
                            self,
                            "Referencias no validas",
                            "La generacion de perfil no puede usar carpetas operativas de la sesion "
                            f"({reason}). Selecciona capturas RAW/DNG originales en 01_ORG.",
                        )
                        return
            if chart_capture_files is None and not self._directory_has_chart_captures(charts):
                if (
                    self._profile_reference_rejection_reason(self._current_dir) is None
                    and self._directory_has_chart_captures(self._current_dir)
                ):
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
            pending_manual_detection = self._pending_manual_detection_request(chart_capture_files)
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
                task_manual_detections = dict(manual_detections or {})
                if pending_manual_detection is not None:
                    source, detection = self._build_pending_manual_detection(
                        pending_manual_detection,
                        recipe=recipe,
                        chart_type=chart_type,
                        workdir=workdir,
                    )
                    task_manual_detections[source] = detection

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
                    manual_detections=task_manual_detections or None,
                    validation_holdout_count=validation_holdout_count,
                )

            def on_success(payload) -> None:
                self.profile_output.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
                normalizations = payload.get("recipe_profiling_normalizations")
                if isinstance(normalizations, list) and normalizations:
                    summary = ", ".join(
                        f"{c.get('field')}: {c.get('from')} -> {c.get('to')}"
                        for c in normalizations
                        if isinstance(c, dict)
                    )
                    self._log_preview(f"Receta normalizada para perfilado cientifico: {summary}")
                profile_status = payload.get("profile_status") if isinstance(payload.get("profile_status"), dict) else {}
                status = str(profile_status.get("status") or "draft")
                if status not in {"rejected", "expired"}:
                    self.path_profile_active.setText(str(profile_out))
                    if status == "draft":
                        reasons = profile_status.get("reasons") if isinstance(profile_status.get("reasons"), list) else []
                        detail = f" ({', '.join(str(r) for r in reasons[:3])})" if reasons else ""
                        self._log_preview(f"Aviso: perfil activado en estado draft{detail}; no sustituye una validacion independiente.")
                else:
                    self.path_profile_active.clear()
                    self._log_preview(f"Perfil no activado por estado: {status}")
                if payload.get("calibrated_recipe_path"):
                    calibrated_recipe_path = Path(str(payload["calibrated_recipe_path"]))
                    self.path_recipe.setText(str(calibrated_recipe_path))
                    try:
                        self._apply_recipe_to_controls(load_recipe(calibrated_recipe_path))
                        self._invalidate_preview_cache()
                        QtCore.QTimer.singleShot(0, lambda: self._on_load_selected(show_message=False))
                    except Exception as exc:
                        self._log_preview(f"No se pudo cargar receta calibrada en la GUI: {exc}")
                if payload.get("development_profile_path") and payload.get("calibrated_recipe_path"):
                    chart_profile_name = f"{self.session_name_edit.text().strip() or profile_out.stem} - carta"
                    profile_id = self._register_chart_development_profile(
                        name=chart_profile_name,
                        development_profile_path=Path(str(payload["development_profile_path"])),
                        calibrated_recipe_path=Path(str(payload["calibrated_recipe_path"])),
                        icc_profile_path=profile_out,
                        profile_report_path=profile_report,
                    )
                    assigned = self._assign_development_profile_to_raw_files(
                        profile_id,
                        self._raw_files_for_chart_profile_assignment(charts, chart_capture_files),
                        status="assigned",
                    )
                    if assigned:
                        self._log_preview(f"Perfil de ajuste avanzado asignado a {assigned} RAW de carta")
                if hasattr(self, "profile_summary_label"):
                    self.profile_summary_label.setText(self._profile_success_summary(payload, profile_out))
                self._log_preview(f"Perfil de ajuste avanzado: {payload.get('development_profile_path')}")
                self._log_preview(f"Perfil ICC de entrada generado: {profile_out}")
                self._set_status(f"Perfil avanzado con carta + ICC de entrada generado: {profile_out}")
                self._save_active_session(silent=True)

            self._start_background_task("Generación de perfil avanzado con carta + ICC", task, on_success)

        def _profile_chart_candidate_count(self, charts: Path, chart_capture_files: list[Path] | None) -> int:
            if chart_capture_files is not None:
                return len(chart_capture_files)
            try:
                return sum(
                    1
                    for p in charts.iterdir()
                    if p.is_file() and p.suffix.lower() in PROFILE_CHART_EXTENSIONS
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
                f"ICC de entrada generado: {profile_out}",
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
            if self._selected_file is None or self._selected_file.suffix.lower() not in PROFILE_CHART_EXTENSIONS:
                QtWidgets.QMessageBox.information(
                    self,
                    "Referencia no compatible",
                    "El marcado manual para perfilado cientifico solo acepta RAW/DNG/TIFF.",
                )
                return
            if (
                self._selected_file is not None
                and self._selected_file.suffix.lower() in RAW_EXTENSIONS
                and not self._preview_requires_max_quality()
            ):
                self._manual_chart_marking_after_reload = True
                self._last_loaded_preview_key = None
                self._set_status("Recargando preview de alta calidad antes del marcado manual")
                self._on_load_selected(show_message=False)
                return
            self._begin_manual_chart_marking()

        def _begin_manual_chart_marking(self) -> None:
            if self._original_linear is None:
                return
            self._set_neutral_picker_active(False)
            self._manual_chart_marking = True
            self._manual_chart_points = []
            self._manual_chart_points_source = self._selected_file.expanduser().resolve(strict=False) if self._selected_file else None
            self._sync_manual_chart_overlay()
            self._set_status("Marcado manual activo sobre preview de revelado: selecciona 4 esquinas en el visor")

        def _clear_manual_chart_points(self) -> None:
            self._manual_chart_marking = False
            self._manual_chart_points = []
            self._manual_chart_points_source = None
            self._sync_manual_chart_overlay()
            self._set_status("Marcado manual limpiado")

        def _clear_manual_chart_points_for_file_change(self) -> None:
            if not self._manual_chart_points and not self._manual_chart_marking and self._manual_chart_points_source is None:
                return
            self._manual_chart_marking = False
            self._manual_chart_marking_after_reload = False
            self._manual_chart_points = []
            self._manual_chart_points_source = None
            self._sync_manual_chart_overlay()

        def _manual_chart_points_match_selected_file(self) -> bool:
            if not self._manual_chart_points:
                return True
            if self._selected_file is None or self._manual_chart_points_source is None:
                return False
            return self._normalized_path_key(self._manual_chart_points_source) == self._normalized_path_key(self._selected_file)

        def _on_result_image_click(self, x: float, y: float) -> None:
            if self._neutral_picker_active:
                self._apply_neutral_picker_at(x, y)
                return
            self._on_manual_chart_click(x, y)

        def _on_manual_chart_click(self, x: float, y: float) -> None:
            if not self._manual_chart_marking:
                return
            if not self._manual_chart_points_match_selected_file():
                self._manual_chart_points = []
                self._manual_chart_points_source = self._selected_file.expanduser().resolve(strict=False) if self._selected_file else None
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
            points = self._manual_chart_points if self._manual_chart_points_match_selected_file() else []
            if hasattr(self, "manual_chart_points_label"):
                if points:
                    coords = " | ".join(f"{idx}:{x:.0f},{y:.0f}" for idx, (x, y) in enumerate(points, start=1))
                    self.manual_chart_points_label.setText(f"Puntos: {len(points)}/4 - {coords}")
                else:
                    self.manual_chart_points_label.setText("Puntos: 0/4")
            if hasattr(self, "image_result_single"):
                self.image_result_single.set_overlay_points(points)
            if hasattr(self, "image_result_compare"):
                self.image_result_compare.set_overlay_points(points)

        def _save_manual_chart_detection(self) -> None:
            if self._selected_file is None:
                QtWidgets.QMessageBox.information(self, "Info", "Selecciona primero una captura de carta.")
                return
            if self._selected_file.suffix.lower() not in PROFILE_CHART_EXTENSIONS:
                QtWidgets.QMessageBox.information(
                    self,
                    "Referencia no compatible",
                    "Las detecciones de carta para perfilado cientifico solo aceptan RAW/DNG/TIFF.",
                )
                return
            if self._original_linear is None:
                QtWidgets.QMessageBox.information(self, "Info", "Carga primero la captura de carta en el visor.")
                return
            if len(self._manual_chart_points) != 4:
                QtWidgets.QMessageBox.information(self, "Info", "Marca exactamente 4 esquinas antes de guardar.")
                return
            if not self._manual_chart_points_match_selected_file():
                self._clear_manual_chart_points_for_file_change()
                QtWidgets.QMessageBox.information(
                    self,
                    "Marcado no valido",
                    "El marcado manual pertenecia a otra imagen. Marca de nuevo la carta en la captura actual.",
                )
                return

            workdir = Path(self.profile_workdir.text().strip() or "/tmp/nexoraw_profile_work")
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
                    full_image = develop_image_array(selected, recipe)
                    write_tiff16(target_image, full_image)
                else:
                    target_image = selected
                    full_image = read_image(target_image)

                full_h, full_w = full_image.shape[:2]
                sx = full_w / max(1, preview_w)
                sy = full_h / max(1, preview_h)
                corners = [(x * sx, y * sy) for x, y in points_preview]
                detection = detect_chart_from_corners_array(full_image, corners=corners, chart_type=chart_type)
                write_json(out_json, detection)
                draw_detection_overlay_array(full_image, detection, overlay_path)
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
                stale_path = Path(str(value))
                p = self._resolve_existing_browsable_path(stale_path)
                if p is not None:
                    if self._normalized_path_key(p) != self._normalized_path_key(stale_path):
                        self._update_file_item_path(item, p)
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

        def _batch_worker_count(self, total_items: int) -> int:
            return resolve_batch_workers(total_items)

        @staticmethod
        def _versioned_output_path_with_reservations(
            requested_path: Path,
            reserved_paths: set[str],
        ) -> Path:
            requested = Path(requested_path)
            candidate = requested
            candidate_key = str(candidate)
            if not candidate.exists() and candidate_key not in reserved_paths:
                reserved_paths.add(candidate_key)
                return candidate
            for index in range(2, 10000):
                candidate = requested.with_name(f"{requested.stem}_v{index:03d}{requested.suffix}")
                candidate_key = str(candidate)
                if not candidate.exists() and candidate_key not in reserved_paths:
                    reserved_paths.add(candidate_key)
                    return candidate
            raise RuntimeError(f"No se pudo generar salida versionada para {requested.name}")

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
            lateral_ca_red_scale: float,
            lateral_ca_blue_scale: float,
            render_adjustments: dict[str, Any],
            c2pa_config: C2PASignConfig | None,
            proof_config: NexoRawProofConfig,
            sidecar_detail_adjustments: dict[str, Any] | None = None,
            sidecar_render_adjustments: dict[str, Any] | None = None,
            development_profile: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            out_dir.mkdir(parents=True, exist_ok=True)
            outputs: list[dict[str, str]] = []
            errors: list[dict[str, str]] = []

            if profile_path is not None and not profile_path.exists():
                raise RuntimeError(f"No existe perfil ICC activo: {profile_path}")

            detail_adjustments = {
                "applied": bool(apply_adjust),
                "denoise_luminance": denoise_luma if apply_adjust else 0.0,
                "denoise_color": denoise_color if apply_adjust else 0.0,
                "sharpen_amount": sharpen_amount if apply_adjust else 0.0,
                "sharpen_radius": sharpen_radius if apply_adjust else 0.0,
                "lateral_ca_red_scale": lateral_ca_red_scale if apply_adjust else 1.0,
                "lateral_ca_blue_scale": lateral_ca_blue_scale if apply_adjust else 1.0,
            }
            c2pa_render_adjustments = {"applied": True, **render_adjustments} if apply_adjust else {"applied": False}
            sidecar_detail_state = sidecar_detail_adjustments or {
                "sharpen": int(round((sharpen_amount if apply_adjust else 0.0) * 100)),
                "radius": int(round((sharpen_radius if apply_adjust else 1.0) * 10)),
                "noise_luma": int(round((denoise_luma if apply_adjust else 0.0) * 100)),
                "noise_color": int(round((denoise_color if apply_adjust else 0.0) * 100)),
                "ca_red": int(round(((lateral_ca_red_scale if apply_adjust else 1.0) - 1.0) * 10000)),
                "ca_blue": int(round(((lateral_ca_blue_scale if apply_adjust else 1.0) - 1.0) * 10000)),
            }
            sidecar_render_state = sidecar_render_adjustments or render_adjustments

            generic_profile_dir = (
                self._session_paths_from_root(self._active_session_root)["profiles"] / "generic"
                if self._active_session_root is not None
                else None
            )
            session_name = ""
            metadata_payload = (
                self._active_session_payload.get("metadata", {})
                if isinstance(self._active_session_payload, dict)
                else {}
            )
            if isinstance(metadata_payload, dict):
                session_name = str(metadata_payload.get("name") or "")
            if not session_name and self._active_session_root is not None:
                session_name = self._active_session_root.name

            planned: list[tuple[int, Path, Path, Path]] = []
            reserved_outputs: set[str] = set()
            for idx, src in enumerate(files):
                requested_out_path = out_dir / f"{src.stem}.tiff"
                out_path = self._versioned_output_path_with_reservations(requested_out_path, reserved_outputs)
                planned.append((idx, src, requested_out_path, out_path))

            output_slots: list[dict[str, str] | None] = [None] * len(planned)
            error_slots: list[dict[str, str] | None] = [None] * len(planned)

            def process_one(
                index: int,
                src: Path,
                requested_out_path: Path,
                out_path: Path,
            ) -> tuple[int, dict[str, str] | None, dict[str, str] | None]:
                try:
                    if src.suffix.lower() in RAW_EXTENSIONS:
                        image = develop_image_array(src, recipe)
                    else:
                        image = read_image(src)

                    if apply_adjust:
                        image = self._apply_output_adjustments(
                            image,
                            denoise_luma=denoise_luma,
                            denoise_color=denoise_color,
                            sharpen_amount=sharpen_amount,
                            sharpen_radius=sharpen_radius,
                            lateral_ca_red_scale=lateral_ca_red_scale,
                            lateral_ca_blue_scale=lateral_ca_blue_scale,
                            render_adjustments=render_adjustments,
                        )

                    mode, proof_result = write_signed_profiled_tiff(
                        out_path,
                        image,
                        source_raw=src,
                        recipe=recipe,
                        profile_path=profile_path if use_profile else None,
                        c2pa_config=c2pa_config,
                        proof_config=proof_config,
                        detail_adjustments=detail_adjustments,
                        render_adjustments=c2pa_render_adjustments,
                        render_context={"entrypoint": "gui_batch_develop", "apply_adjustments": bool(apply_adjust)},
                        generic_profile_dir=generic_profile_dir,
                    )
                    rendered_profile_path = profile_path_for_render_settings(
                        recipe,
                        input_profile_path=profile_path if use_profile else None,
                        color_management_mode=mode,
                        generic_profile_dir=generic_profile_dir,
                    )

                    output = {"source": str(src), "output": str(out_path), "proof": proof_result.proof_path}
                    if development_profile:
                        output["development_profile_id"] = str(development_profile.get("id") or "")
                        output["development_profile_name"] = str(development_profile.get("name") or "")
                    if out_path != requested_out_path:
                        output["requested_output"] = str(requested_out_path)

                    if src.suffix.lower() in RAW_EXTENSIONS:
                        sidecar_path = write_raw_sidecar(
                            src,
                            recipe=recipe,
                            development_profile=development_profile,
                            detail_adjustments=sidecar_detail_state,
                            render_adjustments=sidecar_render_state,
                            icc_profile_path=rendered_profile_path,
                            color_management_mode=mode,
                            session_root=self._active_session_root,
                            session_name=session_name,
                            output_tiff=out_path,
                            proof_path=Path(proof_result.proof_path),
                            status="rendered",
                        )
                        output["raw_sidecar"] = str(sidecar_path)
                    return index, output, None
                except Exception as exc:
                    return index, None, {"source": str(src), "error": str(exc)}

            worker_count = self._batch_worker_count(len(planned))
            if worker_count <= 1:
                for idx, src, requested_out_path, out_path in planned:
                    i, output, error = process_one(idx, src, requested_out_path, out_path)
                    output_slots[i] = output
                    error_slots[i] = error
            else:
                with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="nexoraw-batch") as executor:
                    futures = [
                        executor.submit(process_one, idx, src, requested_out_path, out_path)
                        for idx, src, requested_out_path, out_path in planned
                    ]
                    for future in as_completed(futures):
                        i, output, error = future.result()
                        output_slots[i] = output
                        error_slots[i] = error

            outputs.extend([output for output in output_slots if output is not None])
            errors.extend([error for error in error_slots if error is not None])

            return {
                "input_files": len(files),
                "output_dir": str(out_dir),
                "outputs": outputs,
                "errors": errors,
                "development_profile": development_profile or {},
                "workers": worker_count,
            }

        def _start_batch_develop(self, files: list[Path], task_label: str) -> None:
            self._ensure_session_output_controls()
            out_dir = Path(self.batch_out_dir.text().strip())
            apply_adjust = bool(self.batch_apply_adjustments.isChecked())
            embed_profile = bool(self.batch_embed_profile.isChecked())
            settings = self._development_profile_settings(self._active_development_profile_id)
            detail = self._detail_adjustment_kwargs_from_state(settings["detail_adjustments"])
            profile_path = settings.get("icc_profile_path")
            use_profile = bool(embed_profile and isinstance(profile_path, Path) and str(profile_path))
            try:
                proof_config = self._resolve_proof_config_for_gui()
                c2pa_config = self._resolve_c2pa_config_for_gui()
            except Exception as exc:
                self._show_signature_config_error(exc)
                return

            def task():
                payload = self._process_batch_files(
                    files=files,
                    out_dir=out_dir,
                    recipe=settings["recipe"],
                    apply_adjust=apply_adjust,
                    use_profile=use_profile,
                    profile_path=profile_path,
                    denoise_luma=detail["denoise_luma"],
                    denoise_color=detail["denoise_color"],
                    sharpen_amount=detail["sharpen_amount"],
                    sharpen_radius=detail["sharpen_radius"],
                    lateral_ca_red_scale=detail["lateral_ca_red_scale"],
                    lateral_ca_blue_scale=detail["lateral_ca_blue_scale"],
                    render_adjustments=self._render_adjustment_kwargs_from_state(settings["render_adjustments"]),
                    sidecar_detail_adjustments=settings["detail_adjustments"],
                    sidecar_render_adjustments=settings["render_adjustments"],
                    c2pa_config=c2pa_config,
                    proof_config=proof_config,
                    development_profile=self._profile_payload_from_development_settings(settings),
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
                self._refresh_color_reference_thumbnail_markers()
                self._save_active_session(silent=True)

            self._start_background_task(task_label, task, on_success)

        def _use_generated_profile_as_active(self) -> None:
            p = self._normalized_profile_out_path()
            if not p.exists():
                QtWidgets.QMessageBox.information(self, "Info", "El perfil ICC de entrada aún no existe.")
                return
            if not self._profile_can_be_active(p):
                status = self._profile_status_for_path(p) or "no disponible"
                QtWidgets.QMessageBox.warning(
                    self,
                    "Perfil no activable",
                    f"No se activa el perfil generado porque su estado QA es '{status}'. "
                    "Regenera el perfil con referencias RAW/DNG originales.",
                )
                self.path_profile_active.clear()
                self.chk_apply_profile.setChecked(False)
                self._save_active_session(silent=True)
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
            if hasattr(self, "global_status_label"):
                self.global_status_label.setText(f"Ejecutando: {label}")
                self.global_progress.setRange(0, 0)
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
                if hasattr(self, "global_status_label"):
                    self.global_progress.setRange(0, 1)
                    self.global_progress.setValue(1 if status == "Completado" else 0)
                    self.global_status_label.setText(f"{status}: {detail}")
                    QtCore.QTimer.singleShot(1800, self._reset_global_progress_if_idle)

        def _reset_global_progress_if_idle(self) -> None:
            if self._active_tasks != 0 or not hasattr(self, "global_status_label"):
                return
            self.global_status_label.setText("Listo")
            self.global_progress.setRange(0, 1)
            self.global_progress.setValue(0)

        def _setup_interactive_preview_status_widgets(self) -> None:
            self._interactive_preview_spinner = QtWidgets.QProgressBar()
            self._interactive_preview_spinner.setTextVisible(False)
            self._interactive_preview_spinner.setRange(0, 1)
            self._interactive_preview_spinner.setValue(0)
            self._interactive_preview_spinner.setFixedWidth(84)
            self._interactive_preview_spinner.setMaximumHeight(9)
            self._interactive_preview_time_label = QtWidgets.QLabel("Ultimo ajuste: -- ms")
            self._interactive_preview_time_label.setStyleSheet("color: #4b5563;")
            status = self.statusBar()
            status.addPermanentWidget(self._interactive_preview_spinner)
            status.addPermanentWidget(self._interactive_preview_time_label)

        def _set_interactive_preview_busy(self, busy: bool) -> None:
            spinner = getattr(self, "_interactive_preview_spinner", None)
            if spinner is not None:
                if busy:
                    spinner.setRange(0, 0)
                else:
                    spinner.setRange(0, 1)
                    spinner.setValue(0)
            label = getattr(self, "_interactive_preview_time_label", None)
            if label is not None and bool(busy):
                label.setText("Ajustando...")
            elif label is not None:
                self._update_interactive_preview_time_label()

        def _update_interactive_preview_time_label(self) -> None:
            label = getattr(self, "_interactive_preview_time_label", None)
            if label is None:
                return
            if self._interactive_preview_last_ms is None:
                label.setText("Ultimo ajuste: -- ms")
                return
            label.setText(f"Ultimo ajuste: {int(round(self._interactive_preview_last_ms))} ms")

        def _set_status(self, text: str) -> None:
            self.statusBar().showMessage(text, 8000)


    ICCRawMainWindow = NexoRawMainWindow


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
    app.setDesktopFileName("nexoraw")
    icon = _app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    win = NexoRawMainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
