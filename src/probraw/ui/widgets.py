from __future__ import annotations

from typing import Any

import numpy as np

from ..gui_config import (
    IMAGE_PANEL_BACKGROUND,
    IMAGE_PANEL_BORDER,
    IMAGE_PANEL_TEXT,
    VIEWER_HISTOGRAM_CLIP_ALERT_RATIO,
    VIEWER_HISTOGRAM_HIGHLIGHT_CLIP_U8,
    VIEWER_HISTOGRAM_MAX_SAMPLE_PIXELS,
    VIEWER_HISTOGRAM_SHADOW_CLIP_U8,
)
from ..raw.preview import normalize_tone_curve_points, tone_curve_lut

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:  # pragma: no cover - entorno sin GUI
    QtCore = None
    QtGui = None
    QtWidgets = None

if QtWidgets is not None:
    class PersistentSideTabWidget(QtWidgets.QTabWidget):
        def __init__(self, *, collapsed_margin: int = 6, minimum_tab_width: int = 34) -> None:
            super().__init__()
            self._collapsed_margin = int(collapsed_margin)
            self._minimum_tab_width = int(minimum_tab_width)

        def collapsedWidth(self) -> int:  # noqa: N802
            tab_bar = self.tabBar()
            if tab_bar is None:
                return self._minimum_tab_width
            frame_width = self.style().pixelMetric(QtWidgets.QStyle.PM_DefaultFrameWidth, None, self)
            width = tab_bar.sizeHint().width() + 2 * frame_width + self._collapsed_margin
            return max(self._minimum_tab_width, int(width))

        def minimumSizeHint(self) -> QtCore.QSize:  # noqa: N802
            hint = super().minimumSizeHint()
            return QtCore.QSize(self.collapsedWidth(), min(hint.height(), 160))


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

        def set_histogram_from_image(self, image_linear_rgb: np.ndarray | None, *, channel: str = "luminance") -> None:
            if image_linear_rgb is None:
                self._histogram = None
                self.update()
                return
            rgb = np.asarray(image_linear_rgb)
            if rgb.ndim != 3 or rgb.shape[2] < 3:
                self._histogram = None
                self.update()
                return
            count = int(rgb.shape[0]) * int(rgb.shape[1])
            if count > VIEWER_HISTOGRAM_MAX_SAMPLE_PIXELS:
                stride = int(np.ceil(np.sqrt(count / float(VIEWER_HISTOGRAM_MAX_SAMPLE_PIXELS))))
                rgb = rgb[::max(1, stride), ::max(1, stride), :3]
            rgb = np.clip(rgb.astype(np.float32, copy=False), 0.0, 1.0)
            key = str(channel or "luminance").strip().lower()
            channel_index = {"red": 0, "green": 1, "blue": 2}.get(key)
            if channel_index is None:
                weights = np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
                values = np.sum(rgb[..., :3] * weights.reshape((1, 1, 3)), axis=2)
            else:
                values = rgb[..., channel_index]
            hist, _ = np.histogram(values, bins=64, range=(0.0, 1.0))
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


    class MTFPlotWidget(QtWidgets.QWidget):
        EXTENDED_DISPLAY_MAX_FREQUENCY = 1.0

        def __init__(self, curve: str = "mtf") -> None:
            super().__init__()
            self._curve = str(curve or "mtf").lower()
            self._result: Any | None = None
            self._hover_pos: QtCore.QPointF | None = None
            self.setMouseTracking(True)
            self.setMinimumHeight(260)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        def set_result(self, result: Any | None) -> None:
            self._result = result
            self.update()

        def clear(self) -> None:
            self._result = None
            self.update()

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.fillRect(self.rect(), QtGui.QColor("#20242b"))
            plot = self.rect().adjusted(56, 22, -18, -44)
            painter.fillRect(plot, QtGui.QColor("#15181d"))

            x_values, y_values, title, x_label, y_label = self._curve_payload()
            painter.setPen(QtGui.QPen(QtGui.QColor("#cbd5e1"), 1))
            painter.drawText(self.rect().adjusted(8, 2, -8, -4), QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft, title)
            painter.drawText(self.rect().adjusted(8, 0, -8, -8), QtCore.Qt.AlignBottom | QtCore.Qt.AlignHCenter, x_label)
            painter.save()
            painter.translate(14, self.rect().center().y())
            painter.rotate(-90)
            painter.drawText(QtCore.QRectF(-72, -8, 144, 16), QtCore.Qt.AlignCenter, y_label)
            painter.restore()

            if x_values.size < 2 or y_values.size < 2:
                self._draw_empty_grid(painter, plot)
                painter.setPen(QtGui.QPen(QtGui.QColor("#94a3b8"), 1))
                painter.drawText(plot, QtCore.Qt.AlignCenter, self.tr("Selecciona una ROI de borde inclinado"))
                painter.end()
                return

            xmin, xmax = self._x_range(x_values)
            ymin, ymax = self._y_range(y_values)
            if xmax <= xmin or ymax <= ymin:
                painter.end()
                return

            self._draw_axes(painter, plot, xmin, xmax, ymin, ymax)
            if self._curve == "mtf":
                self._draw_nyquist_marker(painter, plot, xmin, xmax)

            if self._curve == "mtf":
                self._draw_mtf_curve(painter, plot, x_values, y_values, xmin, xmax, ymin, ymax)
                self._draw_mtf_reference_levels(painter, plot, ymin, ymax)
            else:
                self._draw_curve_path(painter, plot, x_values, y_values, xmin, xmax, ymin, ymax)
            self._draw_hover_coordinates(painter, plot, xmin, xmax, ymin, ymax)
            painter.end()

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            self._hover_pos = event.position()
            self.update()
            super().mouseMoveEvent(event)

        def leaveEvent(self, event) -> None:  # noqa: N802
            self._hover_pos = None
            self.update()
            super().leaveEvent(event)

        def _curve_payload(self) -> tuple[np.ndarray, np.ndarray, str, str, str]:
            result = self._result
            if result is None:
                return np.asarray([]), np.asarray([]), self._title(), "", ""
            if self._curve == "esf":
                return (
                    np.asarray(getattr(result, "esf_distance", []), dtype=np.float64),
                    np.asarray(getattr(result, "esf", []), dtype=np.float64),
                    "ESF",
                    self.tr("distancia al borde (px)"),
                    self.tr("señal normalizada"),
                )
            if self._curve == "lsf":
                return (
                    np.asarray(getattr(result, "lsf_distance", []), dtype=np.float64),
                    np.asarray(getattr(result, "lsf", []), dtype=np.float64),
                    "LSF",
                    self.tr("distancia al borde (px)"),
                    self.tr("derivada"),
                )
            frequency = getattr(result, "frequency_extended", None)
            mtf = getattr(result, "mtf_extended", None)
            if frequency is None or len(frequency) == 0:
                frequency = getattr(result, "frequency", [])
            if mtf is None or len(mtf) == 0:
                mtf = getattr(result, "mtf", [])
            return (
                np.asarray(frequency, dtype=np.float64),
                np.asarray(mtf, dtype=np.float64),
                "MTF",
                self.tr("ciclos/píxel"),
                self.tr("modulación"),
            )

        def _title(self) -> str:
            return {"esf": "ESF", "lsf": "LSF"}.get(self._curve, "MTF")

        def _x_range(self, values: np.ndarray) -> tuple[float, float]:
            finite = np.asarray(values, dtype=np.float64)
            finite = finite[np.isfinite(finite)]
            if finite.size == 0:
                return 0.0, 1.0
            xmin = float(np.min(finite))
            xmax = float(np.max(finite))
            if self._curve == "mtf":
                xmin = min(0.0, xmin)
                xmax = max(0.5, xmax)
                if xmax > 0.5:
                    xmax = min(
                        self.EXTENDED_DISPLAY_MAX_FREQUENCY,
                        float(np.ceil(xmax / 0.5) * 0.5),
                    )
            if xmax <= xmin:
                return xmin - 0.5, xmax + 0.5
            return xmin, xmax

        def _y_range(self, values: np.ndarray) -> tuple[float, float]:
            if self._curve == "mtf":
                return 0.0, max(1.0, float(np.nanmax(values)) * 1.05)
            ymin = float(np.nanmin(values))
            ymax = float(np.nanmax(values))
            if ymax <= ymin:
                return ymin - 0.5, ymax + 0.5
            pad = (ymax - ymin) * 0.08
            return ymin - pad, ymax + pad

        def _draw_empty_grid(self, painter: QtGui.QPainter, plot: QtCore.QRect) -> None:
            painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1))
            for i in range(5):
                x = plot.left() + plot.width() * i / 4.0
                y = plot.top() + plot.height() * i / 4.0
                painter.drawLine(x, plot.top(), x, plot.bottom())
                painter.drawLine(plot.left(), y, plot.right(), y)

        def _draw_axes(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1))
            font = painter.font()
            font.setPointSize(max(7, font.pointSize() - 1))
            painter.setFont(font)

            for value in self._axis_ticks(xmin, xmax):
                px, _py = self._data_to_plot(value, ymin, plot, xmin, xmax, ymin, ymax)
                painter.drawLine(px, plot.top(), px, plot.bottom())
                painter.setPen(QtGui.QPen(QtGui.QColor("#94a3b8"), 1))
                label_rect = QtCore.QRectF(px - 28, plot.bottom() + 3, 56, 16)
                painter.drawText(label_rect, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop, self._format_axis_value(value))
                painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1))

            for value in self._axis_ticks(ymin, ymax):
                _px, py = self._data_to_plot(xmin, value, plot, xmin, xmax, ymin, ymax)
                painter.drawLine(plot.left(), py, plot.right(), py)
                painter.setPen(QtGui.QPen(QtGui.QColor("#94a3b8"), 1))
                label_rect = QtCore.QRectF(plot.left() - 50, py - 8, 44, 16)
                painter.drawText(label_rect, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, self._format_axis_value(value))
                painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1))

            painter.setPen(QtGui.QPen(QtGui.QColor("#4b5563"), 1))
            painter.drawRect(plot)

        def _draw_nyquist_marker(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
        ) -> None:
            if not (xmin <= 0.5 <= xmax):
                return
            px = plot.left() + (0.5 - xmin) / (xmax - xmin) * plot.width()
            if xmax > 0.5:
                post_rect = QtCore.QRectF(px, plot.top(), plot.right() - px, plot.height())
                painter.fillRect(post_rect, QtGui.QColor(239, 68, 68, 18))
            painter.setPen(QtGui.QPen(QtGui.QColor("#ef4444"), 1, QtCore.Qt.DashDotLine))
            painter.drawLine(px, plot.top(), px, plot.bottom())

        def _draw_curve_path(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            x_values: np.ndarray,
            y_values: np.ndarray,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
            *,
            pen: QtGui.QPen | None = None,
        ) -> None:
            path = QtGui.QPainterPath()
            started = False
            for x, y in zip(x_values, y_values, strict=True):
                if not np.isfinite(x) or not np.isfinite(y):
                    continue
                if float(x) < xmin or float(x) > xmax:
                    continue
                px, py = self._data_to_plot(float(x), float(y), plot, xmin, xmax, ymin, ymax)
                if not started:
                    path.moveTo(px, py)
                    started = True
                else:
                    path.lineTo(px, py)
            if started:
                painter.setPen(pen or QtGui.QPen(QtGui.QColor("#38bdf8"), 2))
                painter.drawPath(path)

        def _draw_mtf_curve(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            x_values: np.ndarray,
            y_values: np.ndarray,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            x = np.asarray(x_values, dtype=np.float64)
            y = np.asarray(y_values, dtype=np.float64)
            in_band = x <= 0.5
            post_band = x >= 0.5
            self._draw_curve_path(
                painter,
                plot,
                x[in_band],
                y[in_band],
                xmin,
                xmax,
                ymin,
                ymax,
                pen=QtGui.QPen(QtGui.QColor("#38bdf8"), 2),
            )
            self._draw_curve_path(
                painter,
                plot,
                x[post_band],
                y[post_band],
                xmin,
                xmax,
                ymin,
                ymax,
                pen=QtGui.QPen(QtGui.QColor("#f97316"), 2, QtCore.Qt.DashLine),
            )

        def _draw_mtf_reference_levels(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            ymin: float,
            ymax: float,
        ) -> None:
            painter.setPen(QtGui.QPen(QtGui.QColor("#f59e0b"), 1, QtCore.Qt.DashLine))
            for level in (0.5, 0.3, 0.1):
                py = plot.bottom() - (level - ymin) / (ymax - ymin) * plot.height()
                if plot.top() <= py <= plot.bottom():
                    painter.drawLine(plot.left(), py, plot.right(), py)

        def _draw_hover_coordinates(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            pos = self._hover_pos
            if pos is None or not plot.contains(pos.toPoint()):
                return
            x = xmin + (float(pos.x()) - plot.left()) / max(1.0, float(plot.width())) * (xmax - xmin)
            y = ymax - (float(pos.y()) - plot.top()) / max(1.0, float(plot.height())) * (ymax - ymin)
            x = float(np.clip(x, xmin, xmax))
            y = float(np.clip(y, ymin, ymax))
            px, py = self._data_to_plot(x, y, plot, xmin, xmax, ymin, ymax)

            painter.setPen(QtGui.QPen(QtGui.QColor("#e2e8f0"), 1, QtCore.Qt.DotLine))
            painter.drawLine(px, plot.top(), px, plot.bottom())
            painter.drawLine(plot.left(), py, plot.right(), py)

            label = self._coordinate_label(x, y)
            metrics = painter.fontMetrics()
            label_w = metrics.horizontalAdvance(label) + 14
            label_h = metrics.height() + 8
            lx = min(max(plot.left() + 4, px + 8), plot.right() - label_w - 4)
            ly = max(plot.top() + 4, py - label_h - 8)
            rect = QtCore.QRectF(lx, ly, label_w, label_h)
            painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1))
            painter.setBrush(QtGui.QColor(15, 23, 42, 230))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QtGui.QPen(QtGui.QColor("#f8fafc"), 1))
            painter.drawText(rect.adjusted(7, 0, -7, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, label)

        def _data_to_plot(
            self,
            x: float,
            y: float,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> tuple[float, float]:
            px = plot.left() + (float(x) - xmin) / (xmax - xmin) * plot.width()
            py = plot.bottom() - (float(y) - ymin) / (ymax - ymin) * plot.height()
            return px, py

        def _axis_ticks(self, minimum: float, maximum: float) -> list[float]:
            if self._curve == "mtf" and minimum <= 0.0 and maximum >= 0.5:
                if maximum <= 0.5:
                    return [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
                top = float(np.ceil(float(maximum) / 0.5) * 0.5)
                return [float(v) for v in np.arange(0.0, top + 0.25, 0.5)]
            return [float(v) for v in np.linspace(float(minimum), float(maximum), 5)]

        def _format_axis_value(self, value: float) -> str:
            value = float(value)
            if abs(value) >= 100.0:
                text = f"{value:.0f}"
            elif abs(value) >= 10.0:
                text = f"{value:.1f}"
            else:
                text = f"{value:.3f}"
            return text.rstrip("0").rstrip(".") if "." in text else text

        def _coordinate_label(self, x: float, y: float) -> str:
            suffix = " post-Nyquist" if self._curve == "mtf" and float(x) > 0.5 else ""
            return f"x={self._format_axis_value(x)}  y={self._format_axis_value(y)}{suffix}"


    class MTFComparisonPlotWidget(MTFPlotWidget):
        SERIES_COLORS = ("#38bdf8", "#f97316", "#a78bfa", "#22c55e")

        def __init__(self, curve: str = "mtf") -> None:
            super().__init__(curve)
            self._series: list[tuple[str, np.ndarray, np.ndarray]] = []
            self.setMinimumHeight(360)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        def set_payloads(self, payloads: list[tuple[str, dict[str, Any]]]) -> None:
            series: list[tuple[str, np.ndarray, np.ndarray]] = []
            for label, payload in payloads:
                x_values, y_values = self._curve_from_payload(payload)
                if x_values.size >= 2 and y_values.size >= 2:
                    series.append((str(label), x_values, y_values))
            self._series = series
            self.update()

        def clear(self) -> None:
            self._series = []
            self.update()

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.fillRect(self.rect(), QtGui.QColor("#20242b"))
            plot = self.rect().adjusted(56, 22, -18, -48)
            painter.fillRect(plot, QtGui.QColor("#15181d"))

            title, x_label, y_label = self._comparison_labels()
            painter.setPen(QtGui.QPen(QtGui.QColor("#cbd5e1"), 1))
            painter.drawText(self.rect().adjusted(8, 2, -8, -4), QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft, title)
            painter.drawText(self.rect().adjusted(8, 0, -8, -8), QtCore.Qt.AlignBottom | QtCore.Qt.AlignHCenter, x_label)
            painter.save()
            painter.translate(14, self.rect().center().y())
            painter.rotate(-90)
            painter.drawText(QtCore.QRectF(-72, -8, 144, 16), QtCore.Qt.AlignCenter, y_label)
            painter.restore()

            if not self._series:
                self._draw_empty_grid(painter, plot)
                painter.setPen(QtGui.QPen(QtGui.QColor("#94a3b8"), 1))
                painter.drawText(plot, QtCore.Qt.AlignCenter, self.tr("No hay curvas MTF guardadas"))
                painter.end()
                return

            all_x = np.concatenate([values[1] for values in self._series])
            all_y = np.concatenate([values[2] for values in self._series])
            xmin, xmax = self._x_range(all_x)
            ymin, ymax = self._y_range(all_y)
            if xmax <= xmin or ymax <= ymin:
                painter.end()
                return

            self._draw_axes(painter, plot, xmin, xmax, ymin, ymax)
            if self._curve == "mtf":
                self._draw_nyquist_marker(painter, plot, xmin, xmax)
                self._draw_mtf_reference_levels(painter, plot, ymin, ymax)

            for idx, (_label, x_values, y_values) in enumerate(self._series):
                color = QtGui.QColor(self.SERIES_COLORS[idx % len(self.SERIES_COLORS)])
                if self._curve == "mtf":
                    in_band = x_values <= 0.5
                    post_band = x_values >= 0.5
                    self._draw_curve_path(
                        painter,
                        plot,
                        x_values[in_band],
                        y_values[in_band],
                        xmin,
                        xmax,
                        ymin,
                        ymax,
                        pen=QtGui.QPen(color, 2),
                    )
                    self._draw_curve_path(
                        painter,
                        plot,
                        x_values[post_band],
                        y_values[post_band],
                        xmin,
                        xmax,
                        ymin,
                        ymax,
                        pen=QtGui.QPen(color, 2, QtCore.Qt.DashLine),
                    )
                else:
                    self._draw_curve_path(
                        painter,
                        plot,
                        x_values,
                        y_values,
                        xmin,
                        xmax,
                        ymin,
                        ymax,
                        pen=QtGui.QPen(color, 2),
                    )
            self._draw_legend(painter, plot)
            self._draw_hover_coordinates(painter, plot, xmin, xmax, ymin, ymax)
            painter.end()

        def _comparison_labels(self) -> tuple[str, str, str]:
            if self._curve == "esf":
                return "ESF", self.tr("distancia al borde (px)"), self.tr("señal normalizada")
            if self._curve == "lsf":
                return "LSF", self.tr("distancia al borde (px)"), self.tr("derivada")
            return "MTF", self.tr("ciclos/píxel"), self.tr("modulación")

        def _curve_from_payload(self, payload: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
            curves = payload.get("curves") if isinstance(payload, dict) else None
            curves = curves if isinstance(curves, dict) else {}
            if self._curve == "esf":
                return self._extract_payload_points(curves.get("esf"), "distance_px", "signal")
            if self._curve == "lsf":
                return self._extract_payload_points(curves.get("lsf"), "distance_px", "derivative")
            mtf_extended = curves.get("mtf_extended")
            if isinstance(mtf_extended, list) and mtf_extended:
                return self._extract_payload_points(mtf_extended, "frequency_cycles_per_pixel", "modulation")
            return self._extract_payload_points(curves.get("mtf"), "frequency_cycles_per_pixel", "modulation")

        def _extract_payload_points(self, points: Any, x_key: str, y_key: str) -> tuple[np.ndarray, np.ndarray]:
            if not isinstance(points, list):
                return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
            x_values: list[float] = []
            y_values: list[float] = []
            for point in points:
                if not isinstance(point, dict):
                    continue
                try:
                    x = float(point.get(x_key))
                    y = float(point.get(y_key))
                except (TypeError, ValueError):
                    continue
                if np.isfinite(x) and np.isfinite(y):
                    x_values.append(x)
                    y_values.append(y)
            return np.asarray(x_values, dtype=np.float64), np.asarray(y_values, dtype=np.float64)

        def _draw_legend(self, painter: QtGui.QPainter, plot: QtCore.QRect) -> None:
            metrics = painter.fontMetrics()
            row_h = metrics.height() + 6
            legend_w = min(300, max(160, int(plot.width() * 0.44)))
            legend_h = row_h * len(self._series) + 8
            rect = QtCore.QRectF(plot.right() - legend_w - 8, plot.top() + 8, legend_w, legend_h)
            painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1))
            painter.setBrush(QtGui.QColor(15, 23, 42, 220))
            painter.drawRoundedRect(rect, 4, 4)
            for idx, (label, _x_values, _y_values) in enumerate(self._series):
                color = QtGui.QColor(self.SERIES_COLORS[idx % len(self.SERIES_COLORS)])
                y = rect.top() + 8 + idx * row_h + row_h / 2.0
                painter.setPen(QtGui.QPen(color, 3))
                painter.drawLine(rect.left() + 10, y, rect.left() + 34, y)
                painter.setPen(QtGui.QPen(QtGui.QColor("#e2e8f0"), 1))
                text_rect = QtCore.QRectF(rect.left() + 42, rect.top() + 4 + idx * row_h, rect.width() - 50, row_h)
                text = metrics.elidedText(str(label), QtCore.Qt.ElideMiddle, int(text_rect.width()))
                painter.drawText(text_rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)


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
            self.setToolTip(self.tr(""))
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

        def set_image_u8(self, image_rgb_u8: np.ndarray | None, *, source_label: str | None = None) -> None:
            if image_rgb_u8 is None:
                self.clear()
                return
            rgb = np.asarray(image_rgb_u8)
            if rgb.ndim == 2:
                rgb = np.repeat(rgb[..., None], 3, axis=2)
            if rgb.ndim != 3 or rgb.shape[2] < 3:
                self.clear()
                return
            count = int(rgb.shape[0]) * int(rgb.shape[1])
            if count > VIEWER_HISTOGRAM_MAX_SAMPLE_PIXELS:
                stride = int(np.ceil(count / VIEWER_HISTOGRAM_MAX_SAMPLE_PIXELS))
                rgb = rgb[::max(1, stride), ::max(1, stride), :3]
            else:
                rgb = rgb[..., :3]
            if rgb.dtype != np.uint8:
                rgb = np.clip(np.round(rgb.astype(np.float32)), 0, 255).astype(np.uint8)
            else:
                rgb = np.ascontiguousarray(rgb)

            pixels = rgb.reshape((-1, 3))
            if pixels.size == 0:
                self.clear()
                return

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
            tooltip_parts = []
            if source_label:
                tooltip_parts.append(str(source_label))
            tooltip_parts.append(
                "Clipping sombras: "
                f"R {metrics['shadow_r'] * 100.0:.2f}%  "
                f"G {metrics['shadow_g'] * 100.0:.2f}%  "
                f"B {metrics['shadow_b'] * 100.0:.2f}%\n"
                "Clipping luces: "
                f"R {metrics['highlight_r'] * 100.0:.2f}%  "
                f"G {metrics['highlight_g'] * 100.0:.2f}%  "
                f"B {metrics['highlight_b'] * 100.0:.2f}%"
            )
            self.setToolTip("\n".join(tooltip_parts))
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


    class Gamut3DWidget(QtWidgets.QWidget):
        DEFAULT_AZIMUTH = -38.0
        DEFAULT_ELEVATION = 24.0
        DEFAULT_ZOOM = 1.0

        def __init__(self) -> None:
            super().__init__()
            self._series: list[dict[str, Any]] = []
            self._series_signature: tuple[Any, ...] | None = None
            self._azimuth = self.DEFAULT_AZIMUTH
            self._elevation = self.DEFAULT_ELEVATION
            self._zoom = self.DEFAULT_ZOOM
            self._drag_start: QtCore.QPoint | None = None
            self.setMinimumHeight(260)
            self.setMouseTracking(True)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        def sizeHint(self) -> QtCore.QSize:  # noqa: N802
            return QtCore.QSize(420, 320)

        def clear(self) -> None:
            self._series = []
            self._series_signature = None
            self.reset_view(update=False)
            self.setToolTip("")
            self.update()

        def reset_view(self, *, update: bool = True) -> None:
            self._azimuth = self.DEFAULT_AZIMUTH
            self._elevation = self.DEFAULT_ELEVATION
            self._zoom = self.DEFAULT_ZOOM
            self._drag_start = None
            if update:
                self.update()

        def set_gamut_payload(self, payload: dict[str, Any] | None) -> None:
            if not isinstance(payload, dict):
                self.clear()
                return
            self.set_series(payload.get("series") if isinstance(payload.get("series"), list) else [])
            comparisons = payload.get("comparisons") if isinstance(payload.get("comparisons"), list) else []
            skipped = payload.get("skipped") if isinstance(payload.get("skipped"), list) else []
            tooltip_lines = []
            for item in comparisons:
                if not isinstance(item, dict):
                    continue
                tooltip_lines.append(
                    f"{item.get('source', 'Perfil')} en {item.get('target', '')}: "
                    f"{float(item.get('inside_ratio') or 0.0) * 100.0:.1f}% dentro"
                )
            for item in skipped:
                if isinstance(item, dict):
                    tooltip_lines.append(f"Omitido {item.get('label', '')}: {item.get('reason', '')}")
            self.setToolTip("\n".join(line for line in tooltip_lines if line.strip()))

        def set_series(self, series: list[Any]) -> None:
            normalized: list[dict[str, Any]] = []
            for item in series:
                if not isinstance(item, dict):
                    continue
                points = np.asarray(item.get("points_lab"), dtype=np.float64)
                if points.ndim != 2 or points.shape[1] < 3:
                    continue
                points = points[:, :3]
                points = points[np.all(np.isfinite(points), axis=1)]
                if points.size == 0:
                    continue
                normalized.append(
                    {
                        "label": str(item.get("label") or "Perfil"),
                        "color": str(item.get("color") or "#94a3b8"),
                        "points": np.ascontiguousarray(points, dtype=np.float64),
                        "rgb": self._coerce_rgb_points(item.get("surface_rgb"), points.shape[0]),
                        "quads": self._coerce_quads(item.get("quads"), points.shape[0]),
                        "role": str(item.get("role") or "wire"),
                        "source_key": str(item.get("path") or item.get("profile_key") or item.get("label") or ""),
                    }
                )
            signature = self._series_payload_signature(normalized)
            if signature != self._series_signature:
                self.reset_view(update=False)
                self._series_signature = signature
            self._series = normalized
            self.update()
            QtCore.QTimer.singleShot(0, self.update)

        def _series_payload_signature(self, series: list[dict[str, Any]]) -> tuple[Any, ...]:
            signature: list[tuple[Any, ...]] = []
            for item in series:
                points = np.asarray(item.get("points"), dtype=np.float64)
                if points.ndim != 2 or points.shape[1] < 3 or points.size == 0:
                    stats = (0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                else:
                    finite = points[:, :3][np.all(np.isfinite(points[:, :3]), axis=1)]
                    if finite.size:
                        minv = np.min(finite, axis=0)
                        maxv = np.max(finite, axis=0)
                        stats = (
                            int(finite.shape[0]),
                            *[float(round(v, 3)) for v in minv],
                            *[float(round(v, 3)) for v in maxv],
                        )
                    else:
                        stats = (0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                signature.append(
                    (
                        str(item.get("label") or ""),
                        str(item.get("source_key") or ""),
                        str(item.get("role") or ""),
                        str(item.get("color") or ""),
                        stats,
                    )
                )
            return tuple(signature)

        def _coerce_rgb_points(self, value: Any, count: int) -> np.ndarray:
            rgb = np.asarray(value, dtype=np.float64)
            if rgb.ndim != 2 or rgb.shape[1] < 3 or rgb.shape[0] != count:
                return np.zeros((count, 3), dtype=np.float64)
            return np.ascontiguousarray(np.clip(rgb[:, :3], 0.0, 1.0), dtype=np.float64)

        def _coerce_quads(self, value: Any, count: int) -> list[list[int]]:
            quads: list[list[int]] = []
            if not isinstance(value, list):
                return quads
            for item in value:
                if not isinstance(item, (list, tuple)) or len(item) < 4:
                    continue
                try:
                    quad = [int(item[idx]) for idx in range(4)]
                except (TypeError, ValueError):
                    continue
                if all(0 <= idx < count for idx in quad):
                    quads.append(quad)
            return quads

        def mousePressEvent(self, event) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.LeftButton:
                self._drag_start = event.position().toPoint() if hasattr(event, "position") else event.pos()
                event.accept()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            if self._drag_start is None:
                return super().mouseMoveEvent(event)
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            delta = pos - self._drag_start
            self._drag_start = pos
            self._azimuth += float(delta.x()) * 0.45
            self._elevation = float(np.clip(self._elevation + float(delta.y()) * 0.35, -78.0, 78.0))
            self.update()
            event.accept()

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.LeftButton:
                self._drag_start = None
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.LeftButton:
                self.reset_view()
                event.accept()
                return
            super().mouseDoubleClickEvent(event)

        def wheelEvent(self, event) -> None:  # noqa: N802
            delta = event.angleDelta().y()
            if delta:
                factor = 1.12 if delta > 0 else 1.0 / 1.12
                self._zoom = float(np.clip(self._zoom * factor, 0.55, 3.0))
                self.update()
                event.accept()
                return
            super().wheelEvent(event)

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.fillRect(self.rect(), QtGui.QColor("#171a1f"))

            plot_rect = self.rect().adjusted(8, 8, -8, -30)
            if plot_rect.width() <= 40 or plot_rect.height() <= 40:
                return

            painter.setPen(QtGui.QPen(QtGui.QColor("#313842"), 1))
            painter.drawRect(plot_rect)

            if not self._series:
                self._draw_axes(painter, plot_rect, np.asarray([50.0, 0.0, 0.0], dtype=np.float64), 1.0)
                painter.setPen(QtGui.QColor("#9ca3af"))
                painter.drawText(plot_rect, QtCore.Qt.AlignCenter, self.tr("Sin datos de gamut 3D"))
                return

            all_points = np.vstack([item["points"] for item in self._series])
            center = self._lab_center(all_points)
            scale = self._projection_scale(all_points, center, plot_rect)
            self._draw_axes(painter, plot_rect, center, scale)

            solid_quads: list[tuple[float, QtGui.QPolygonF, QtGui.QColor]] = []
            wire_quads: list[tuple[float, QtGui.QPolygonF, QtGui.QColor]] = []
            fallback_points: list[tuple[float, QtCore.QPointF, QtGui.QColor]] = []
            for item in self._series:
                base_color = QtGui.QColor(str(item["color"]))
                projected, depth = self._project_points(item["points"], center, scale, plot_rect)
                quads = item.get("quads") or []
                if not quads:
                    base_color.setAlpha(210 if item.get("role") == "solid" else 170)
                    for point, z in zip(projected, depth, strict=True):
                        fallback_points.append((float(z), point, QtGui.QColor(base_color)))
                    continue
                for quad in quads:
                    polygon = QtGui.QPolygonF([projected[idx] for idx in quad])
                    z = float(np.mean([depth[idx] for idx in quad]))
                    if item.get("role") == "solid":
                        color = self._solid_quad_color(item, quad, fallback=base_color)
                        solid_quads.append((z, polygon, color))
                    else:
                        color = QtGui.QColor(base_color)
                        color.setAlpha(210)
                        wire_quads.append((z, polygon, color))

            painter.setPen(QtCore.Qt.NoPen)
            for _depth, polygon, color in sorted(solid_quads, key=lambda entry: entry[0]):
                painter.setBrush(QtGui.QBrush(color))
                painter.drawPolygon(polygon)
            painter.setBrush(QtCore.Qt.NoBrush)
            for _depth, polygon, color in sorted(solid_quads, key=lambda entry: entry[0]):
                edge = QtGui.QColor("#0f172a")
                edge.setAlpha(46)
                painter.setPen(QtGui.QPen(edge, 0.45))
                painter.drawPolygon(polygon)
            for _depth, polygon, color in sorted(wire_quads, key=lambda entry: entry[0]):
                painter.setPen(QtGui.QPen(color, 0.75))
                painter.drawPolygon(polygon)
            painter.setPen(QtCore.Qt.NoPen)
            for _depth, point, color in sorted(fallback_points, key=lambda entry: entry[0]):
                painter.setBrush(QtGui.QBrush(color))
                painter.drawEllipse(point, 2.0, 2.0)

            self._draw_legend(painter, plot_rect)
            painter.setPen(QtGui.QColor("#9ca3af"))
            painter.drawText(
                self.rect().adjusted(8, 0, -8, -6),
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom,
                f"Lab 3D | az {self._azimuth:.0f} / el {self._elevation:.0f}",
            )

        def _draw_axes(
            self,
            painter: QtGui.QPainter,
            rect: QtCore.QRect,
            center: np.ndarray,
            scale: float,
        ) -> None:
            axis_points = np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [100.0, 0.0, 0.0],
                    [50.0, -120.0, 0.0],
                    [50.0, 120.0, 0.0],
                    [50.0, 0.0, -120.0],
                    [50.0, 0.0, 120.0],
                ],
                dtype=np.float64,
            )
            projected, _depth = self._project_points(axis_points, center, scale, rect)
            painter.setPen(QtGui.QPen(QtGui.QColor("#4b5563"), 1))
            painter.drawLine(projected[0], projected[1])
            painter.drawLine(projected[2], projected[3])
            painter.drawLine(projected[4], projected[5])
            painter.setPen(QtGui.QColor("#cbd5e1"))
            painter.drawText(projected[1] + QtCore.QPointF(4, -4), "L*")
            painter.drawText(projected[3] + QtCore.QPointF(4, 0), "a*")
            painter.drawText(projected[5] + QtCore.QPointF(4, 0), "b*")

        def _draw_legend(self, painter: QtGui.QPainter, rect: QtCore.QRect) -> None:
            x = rect.left() + 10
            y = rect.top() + 10
            painter.setFont(QtGui.QFont(painter.font().family(), 8))
            for item in self._series:
                color = QtGui.QColor(str(item["color"]))
                color.setAlpha(230)
                painter.setPen(QtCore.Qt.NoPen)
                if item.get("role") == "solid":
                    painter.setBrush(QtGui.QBrush(color))
                    painter.drawRect(QtCore.QRectF(x + 1, y + 2, 9, 9))
                else:
                    painter.setBrush(QtCore.Qt.NoBrush)
                    painter.setPen(QtGui.QPen(color, 1.2))
                    painter.drawRect(QtCore.QRectF(x + 1, y + 2, 9, 9))
                painter.setPen(QtGui.QColor("#d1d5db"))
                painter.drawText(QtCore.QPointF(x + 16, y + 10), f"{item['label']} ({len(item['points'])})")
                y += 16

        def _solid_quad_color(self, item: dict[str, Any], quad: list[int], *, fallback: QtGui.QColor) -> QtGui.QColor:
            rgb = item.get("rgb")
            if isinstance(rgb, np.ndarray) and rgb.ndim == 2 and rgb.shape[0] > max(quad):
                mean_rgb = np.clip(np.mean(rgb[quad, :3], axis=0), 0.0, 1.0)
                color = QtGui.QColor(
                    int(round(float(mean_rgb[0]) * 255.0)),
                    int(round(float(mean_rgb[1]) * 255.0)),
                    int(round(float(mean_rgb[2]) * 255.0)),
                    168,
                )
                return color
            color = QtGui.QColor(fallback)
            color.setAlpha(150)
            return color

        def _project_points(
            self,
            points: np.ndarray,
            center: np.ndarray,
            scale: float,
            rect: QtCore.QRect,
            *,
            apply_zoom: bool = True,
        ) -> tuple[list[QtCore.QPointF], np.ndarray]:
            centered = np.asarray(points, dtype=np.float64) - center.reshape((1, 3))
            a = centered[:, 1]
            b = centered[:, 2]
            l = centered[:, 0]
            az = np.deg2rad(float(self._azimuth))
            el = np.deg2rad(float(self._elevation))
            x_rot = a * np.cos(az) - b * np.sin(az)
            depth = a * np.sin(az) + b * np.cos(az)
            y_rot = l * np.cos(el) - depth * np.sin(el)
            depth = depth * np.cos(el) + l * np.sin(el)
            cx = rect.center().x()
            cy = rect.center().y()
            effective_scale = float(scale) * (float(self._zoom) if apply_zoom else 1.0)
            projected = [
                QtCore.QPointF(cx + float(x) * effective_scale, cy - float(y) * effective_scale)
                for x, y in zip(x_rot, y_rot, strict=True)
            ]
            return projected, depth

        def _lab_center(self, points: np.ndarray) -> np.ndarray:
            if points.size == 0:
                return np.asarray([50.0, 0.0, 0.0], dtype=np.float64)
            return np.asarray(
                [
                    50.0,
                    float(np.median(points[:, 1])),
                    float(np.median(points[:, 2])),
                ],
                dtype=np.float64,
            )

        def _projection_scale(self, points: np.ndarray, center: np.ndarray, rect: QtCore.QRect) -> float:
            if points.size == 0:
                return 1.0
            projected, _depth = self._project_points(points, center, 1.0, rect, apply_zoom=False)
            xs = np.asarray([point.x() - rect.center().x() for point in projected], dtype=np.float64)
            ys = np.asarray([point.y() - rect.center().y() for point in projected], dtype=np.float64)
            span = max(float(np.max(np.abs(xs))), float(np.max(np.abs(ys))), 1.0)
            available = max(20.0, min(rect.width(), rect.height()) * 0.44)
            return available / span


    class ImagePanel(QtWidgets.QLabel):
        imageClicked = QtCore.Signal(float, float)
        roiSelected = QtCore.Signal(float, float, float, float)

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
            self._roi_rect: tuple[float, float, float, float] | None = None
            self._roi_selection_enabled = False
            self._roi_drag_start_image: tuple[float, float] | None = None
            self._roi_drag_current_image: tuple[float, float] | None = None
            self._pan = QtCore.QPointF(0.0, 0.0)
            self._drag_start: QtCore.QPointF | None = None
            self._drag_last: QtCore.QPointF | None = None
            self._drag_moved = False
            self._interaction_cursor: QtCore.Qt.CursorShape | None = None
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

        def image_size(self) -> tuple[int, int] | None:
            return self._image_size

        def set_interaction_cursor(self, cursor: QtCore.Qt.CursorShape | None) -> None:
            self._interaction_cursor = cursor
            self._apply_idle_cursor()

        def set_overlay_points(self, points: list[tuple[float, float]]) -> None:
            self._overlay_points = list(points)
            self._refresh_scaled_pixmap()

        def set_roi_selection_enabled(self, enabled: bool) -> None:
            self._roi_selection_enabled = bool(enabled)
            self._roi_drag_start_image = None
            self._roi_drag_current_image = None
            self._apply_idle_cursor()
            self.update()

        def set_roi_rect(self, rect: tuple[float, float, float, float] | None) -> None:
            self._roi_rect = _normalize_rect(rect) if rect is not None else None
            self._refresh_scaled_pixmap()

        def clear_roi_rect(self) -> None:
            self.set_roi_rect(None)

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
            self._apply_idle_cursor()

        def mousePressEvent(self, event) -> None:  # noqa: N802
            if (
                self._roi_selection_enabled
                and event.button() == QtCore.Qt.LeftButton
                and self._base_pixmap is not None
            ):
                mapped = self._map_widget_to_image(event.position())
                if mapped is not None:
                    self._roi_drag_start_image = mapped
                    self._roi_drag_current_image = mapped
                    self._roi_rect = _rect_from_points(mapped, mapped)
                    self.update()
                    return
            if event.button() == QtCore.Qt.LeftButton and self._base_pixmap is not None:
                self._drag_start = event.position()
                self._drag_last = event.position()
                self._drag_moved = False
                if self._view_zoom > 1.0:
                    self.setCursor(QtCore.Qt.ClosedHandCursor)
                else:
                    self._apply_idle_cursor()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            if self._roi_selection_enabled and self._roi_drag_start_image is not None:
                mapped = self._map_widget_to_image(event.position())
                if mapped is not None:
                    self._roi_drag_current_image = mapped
                    self._roi_rect = _rect_from_points(self._roi_drag_start_image, mapped)
                    self.update()
                return
            if self._drag_last is not None and self._drag_start is not None:
                delta = event.position() - self._drag_last
                distance = event.position() - self._drag_start
                if self._view_zoom > 1.0 and (abs(distance.x()) > 3.0 or abs(distance.y()) > 3.0):
                    self._pan += delta
                    self._drag_moved = True
                    self._refresh_scaled_pixmap()
                self._drag_last = event.position()
                return
            self._apply_idle_cursor()
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            if (
                self._roi_selection_enabled
                and event.button() == QtCore.Qt.LeftButton
                and self._roi_drag_start_image is not None
            ):
                mapped = self._map_widget_to_image(event.position()) or self._roi_drag_current_image
                if mapped is not None:
                    rect = _rect_from_points(self._roi_drag_start_image, mapped)
                    self._roi_rect = rect
                    if rect[2] >= 8.0 and rect[3] >= 8.0:
                        self.roiSelected.emit(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
                self._roi_drag_start_image = None
                self._roi_drag_current_image = None
                self._apply_idle_cursor()
                self.update()
                return
            if event.button() == QtCore.Qt.LeftButton and self._drag_start is not None:
                mapped = self._map_widget_to_image(event.position())
                if mapped is not None and not self._drag_moved:
                    self.imageClicked.emit(float(mapped[0]), float(mapped[1]))
                self._drag_start = None
                self._drag_last = None
                self._drag_moved = False
                self._apply_idle_cursor()
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

            if self._roi_rect is not None and self._image_size is not None:
                x, y, w, h = self._roi_rect
                corners = [
                    self._map_image_to_widget(x, y, rect, scale, transform, bounds),
                    self._map_image_to_widget(x + w, y, rect, scale, transform, bounds),
                    self._map_image_to_widget(x + w, y + h, rect, scale, transform, bounds),
                    self._map_image_to_widget(x, y + h, rect, scale, transform, bounds),
                ]
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                painter.setPen(QtGui.QPen(QtGui.QColor("#38bdf8"), 2))
                painter.setBrush(QtGui.QColor(56, 189, 248, 34))
                painter.drawPolygon(QtGui.QPolygonF(corners))
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawText(corners[0] + QtCore.QPointF(6, -6), "MTF")

            if self._framed:
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.setPen(QtGui.QPen(QtGui.QColor("#4b5563"), 1))
                painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            painter.end()

        def _refresh_scaled_pixmap(self) -> None:
            self.update()

        def _apply_idle_cursor(self) -> None:
            if self._roi_selection_enabled:
                self.setCursor(QtCore.Qt.CrossCursor)
            elif self._interaction_cursor is not None:
                self.setCursor(self._interaction_cursor)
            elif self._view_zoom > 1.0:
                self.setCursor(QtCore.Qt.OpenHandCursor)
            else:
                self.unsetCursor()

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
else:  # pragma: no cover - importable en entornos sin Qt
    PersistentSideTabWidget = None
    CollapsibleToolPanel = None
    ToneCurveEditor = None
    MTFComparisonPlotWidget = None
    MTFPlotWidget = None
    RGBHistogramWidget = None
    Gamut3DWidget = None
    ImagePanel = None


def _rect_from_points(
    a: tuple[float, float],
    b: tuple[float, float],
) -> tuple[float, float, float, float]:
    x0, y0 = float(a[0]), float(a[1])
    x1, y1 = float(b[0]), float(b[1])
    x = min(x0, x1)
    y = min(y0, y1)
    return x, y, abs(x1 - x0), abs(y1 - y0)


def _normalize_rect(rect: tuple[float, float, float, float] | None) -> tuple[float, float, float, float] | None:
    if rect is None:
        return None
    x, y, w, h = [float(v) for v in rect]
    if w < 0:
        x += w
        w = abs(w)
    if h < 0:
        y += h
        h = abs(h)
    return x, y, w, h


__all__ = [
    "PersistentSideTabWidget",
    "CollapsibleToolPanel",
    "ToneCurveEditor",
    "MTFComparisonPlotWidget",
    "MTFPlotWidget",
    "RGBHistogramWidget",
    "Gamut3DWidget",
    "ImagePanel",
]
