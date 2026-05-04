"""Benchmark de fluidez de la interfaz PySide6.

Simula arrastres de sliders y curva tonal con una imagen ya cargada. Mide el
coste inmediato de cada evento UI y los huecos del event loop mientras se
procesan previews interactivas en segundo plano.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from typing import Any

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets  # noqa: E402

from probraw.core.models import Recipe  # noqa: E402
from probraw.gui import ICCRawMainWindow  # noqa: E402
from probraw.raw.pipeline import develop_scene_linear_array  # noqa: E402
from probraw.raw.preview import load_image_for_preview, normalize_tone_curve_points  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark de interaccion GUI ProbRAW")
    parser.add_argument("--raw", type=Path, default=None, help="RAW real para cargar como fuente lineal")
    parser.add_argument("--algorithm", default="dcb")
    parser.add_argument("--full-resolution", action="store_true", help="Usa RAW completo en vez de half-size")
    parser.add_argument("--synthetic-size", default="2160x3240", help="Alto x ancho si no se indica RAW")
    parser.add_argument("--steps", type=int, default=80)
    parser.add_argument("--interval-ms", type=int, default=12)
    parser.add_argument("--settle-ms", type=int, default=1600)
    parser.add_argument("--display-color-management", action="store_true", help="Mide aplicando ICC de monitor")
    parser.add_argument("--display-profile", type=Path, default=None, help="Perfil ICC de monitor para la medicion")
    parser.add_argument("--clip-overlay", action="store_true", help="Mide con el overlay de clipping de imagen activo")
    parser.add_argument("--window-size", default="2048x1100", help="Ancho x alto de la ventana de prueba")
    parser.add_argument("--out", type=Path, default=Path("tmp/gui_benchmark/results.json"))
    return parser.parse_args()


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * pct / 100.0))))
    return float(ordered[idx])


class EventLoopProbe(QtCore.QObject):
    def __init__(self, *, interval_ms: int = 16) -> None:
        super().__init__()
        self._interval_ms = max(1, int(interval_ms))
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self._tick)
        self._last = 0.0
        self.gaps_ms: list[float] = []

    def start(self) -> None:
        self.gaps_ms.clear()
        self._last = time.perf_counter()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        now = time.perf_counter()
        if self._last:
            self.gaps_ms.append((now - self._last) * 1000.0)
        self._last = now

    def summary(self) -> dict[str, float]:
        values = list(self.gaps_ms)
        over_budget = [v for v in values if v > 33.4]
        return {
            "samples": float(len(values)),
            "max_ms": round(max(values), 3) if values else 0.0,
            "p95_ms": round(percentile(values, 95), 3),
            "p99_ms": round(percentile(values, 99), 3),
            "over_33ms": float(len(over_budget)),
        }


def wait_ms(ms: int) -> None:
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(max(0, int(ms)), loop.quit)
    loop.exec()


def wait_for_interactive_idle(window: ICCRawMainWindow, *, timeout_ms: int = 120_000) -> bool:
    deadline = time.perf_counter() + max(1, int(timeout_ms)) / 1000.0
    while time.perf_counter() < deadline:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents()
        if not bool(getattr(window, "_interactive_preview_task_active", False)):
            return True
        wait_ms(25)
    return False


def load_source(args: argparse.Namespace, window: ICCRawMainWindow | None = None) -> tuple[np.ndarray, dict[str, Any]]:
    if args.raw is not None:
        raw = args.raw.expanduser().resolve()
        if not raw.is_file():
            raise SystemExit(f"No existe RAW: {raw}")
        recipe = Recipe(demosaic_algorithm=str(args.algorithm), output_space="scene_linear_camera_rgb")
        if window is not None and hasattr(window, "_color_managed_preview_recipe"):
            base_recipe = window._build_effective_recipe()
            base_recipe.demosaic_algorithm = str(args.algorithm)
            recipe = window._color_managed_preview_recipe(base_recipe)
        started = time.perf_counter()
        if window is not None:
            image, _message = load_image_for_preview(
                raw,
                recipe=recipe,
                fast_raw=False,
                max_preview_side=0 if bool(args.full_resolution) else 2600,
                input_profile_path=window._active_session_icc_for_settings(),
                cache_dir=window._preview_decode_cache_dir(raw) if hasattr(window, "_preview_decode_cache_dir") else None,
            )
        else:
            image = develop_scene_linear_array(raw, recipe, half_size=not bool(args.full_resolution))
        return image, {
            "kind": "raw",
            "path": str(raw),
            "algorithm": str(args.algorithm),
            "full_resolution": bool(args.full_resolution),
            "managed_output_space": str(recipe.output_space),
            "managed_output_linear": bool(recipe.output_linear),
            "load_seconds": round(time.perf_counter() - started, 4),
        }

    try:
        h_text, w_text = str(args.synthetic_size).lower().split("x", 1)
        h, w = int(h_text), int(w_text)
    except Exception as exc:
        raise SystemExit("--synthetic-size debe tener formato AltoxAncho, por ejemplo 2160x3240") from exc
    y = np.linspace(0.0, 1.0, h, dtype=np.float32).reshape(h, 1)
    x = np.linspace(0.0, 1.0, w, dtype=np.float32).reshape(1, w)
    image = np.empty((h, w, 3), dtype=np.float32)
    image[..., 0] = x
    image[..., 1] = y
    image[..., 2] = np.clip((x + y) * 0.5, 0.0, 1.0)
    return image, {"kind": "synthetic", "shape": [h, w, 3], "load_seconds": 0.0}


def run_slider_drag(
    app: QtWidgets.QApplication,
    window: ICCRawMainWindow,
    *,
    steps: int,
    interval_ms: int,
    settle_ms: int,
) -> dict[str, Any]:
    del app
    probe = EventLoopProbe(interval_ms=16)
    slider = window.slider_brightness
    call_ms: list[float] = []
    values = [int(round(v)) for v in np.linspace(-120, 120, max(2, int(steps)))]
    loop = QtCore.QEventLoop()
    timer = QtCore.QTimer()
    timer.setInterval(max(1, int(interval_ms)))
    index = {"value": 0}

    def step() -> None:
        i = index["value"]
        if i >= len(values):
            timer.stop()
            slider.setSliderDown(False)
            window._on_slider_release()
            QtCore.QTimer.singleShot(max(0, int(settle_ms)), loop.quit)
            return
        started = time.perf_counter()
        slider.setValue(values[i])
        call_ms.append((time.perf_counter() - started) * 1000.0)
        index["value"] = i + 1

    slider.setSliderDown(True)
    probe.start()
    timer.timeout.connect(step)
    timer.start()
    loop.exec()
    probe.stop()
    return {
        "name": "brightness_slider_drag",
        "steps": len(values),
        "set_value_ms": {
            "median": round(float(statistics.median(call_ms)), 3),
            "p95": round(percentile(call_ms, 95), 3),
            "max": round(max(call_ms), 3),
        },
        "event_loop": probe.summary(),
        "last_preview_ms": round(float(window._interactive_preview_last_ms or 0.0), 3),
        "threads_alive": len(getattr(window, "_threads", [])),
    }


def run_single_brightness_change(
    window: ICCRawMainWindow,
    *,
    timeout_ms: int = 3000,
) -> dict[str, Any]:
    probe = EventLoopProbe(interval_ms=16)
    slider = window.slider_brightness
    slider.setSliderDown(False)
    before_seq = int(getattr(window, "_interactive_preview_request_seq", 0))
    target = int(np.clip(int(slider.value()) + 20, slider.minimum(), slider.maximum()))
    if target == int(slider.value()):
        target = int(np.clip(int(slider.value()) - 20, slider.minimum(), slider.maximum()))
    started = time.perf_counter()
    probe.start()
    set_started = time.perf_counter()
    slider.setValue(target)
    set_value_ms = (time.perf_counter() - set_started) * 1000.0
    deadline = time.perf_counter() + max(1, int(timeout_ms)) / 1000.0
    reached = False
    while time.perf_counter() < deadline:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents()
        if (
            int(getattr(window, "_interactive_preview_request_seq", 0)) > before_seq
            and not bool(getattr(window, "_interactive_preview_task_active", False))
        ):
            reached = True
            break
        wait_ms(10)
    probe.stop()
    final_timer = getattr(window, "_preview_final_refresh_timer", None)
    if final_timer is not None:
        final_timer.stop()
    return {
        "name": "brightness_single_change",
        "completed": bool(reached),
        "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "set_value_ms": round(float(set_value_ms), 3),
        "event_loop": probe.summary(),
        "last_preview_ms": round(float(window._interactive_preview_last_ms or 0.0), 3),
        "threads_alive": len(getattr(window, "_threads", [])),
    }


def run_tone_curve_drag(
    window: ICCRawMainWindow,
    *,
    steps: int,
    interval_ms: int,
    settle_ms: int,
) -> dict[str, Any]:
    probe = EventLoopProbe(interval_ms=16)
    editor = window.tone_curve_editor
    window.check_tone_curve_enabled.setChecked(True)
    editor._points = normalize_tone_curve_points([(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)])
    editor._drag_index = 1
    emit_ms: list[float] = []
    values = np.linspace(0.25, 0.75, max(2, int(steps)), dtype=np.float32)
    loop = QtCore.QEventLoop()
    timer = QtCore.QTimer()
    timer.setInterval(max(1, int(interval_ms)))
    index = {"value": 0}

    def step() -> None:
        i = index["value"]
        if i >= len(values):
            timer.stop()
            editor._drag_index = None
            editor.interactionFinished.emit()
            QtCore.QTimer.singleShot(max(0, int(settle_ms)), loop.quit)
            return
        x = float(values[i])
        y = float(np.clip(0.55 + 0.18 * np.sin(i / 5.0), 0.05, 0.95))
        started = time.perf_counter()
        editor._points = normalize_tone_curve_points([(0.0, 0.0), (x, y), (1.0, 1.0)])
        editor.update()
        editor.pointsChanged.emit(editor.points())
        emit_ms.append((time.perf_counter() - started) * 1000.0)
        index["value"] = i + 1

    probe.start()
    timer.timeout.connect(step)
    timer.start()
    loop.exec()
    probe.stop()
    return {
        "name": "tone_curve_drag",
        "steps": len(values),
        "emit_ms": {
            "median": round(float(statistics.median(emit_ms)), 3),
            "p95": round(percentile(emit_ms, 95), 3),
            "max": round(max(emit_ms), 3),
        },
        "event_loop": probe.summary(),
        "last_preview_ms": round(float(window._interactive_preview_last_ms or 0.0), 3),
        "threads_alive": len(getattr(window, "_threads", [])),
    }


def main() -> int:
    args = parse_args()
    settings_dir = Path(tempfile.gettempdir()) / "probraw_gui_benchmark_settings"
    os.environ.setdefault("PROBRAW_SETTINGS_DIR", str(settings_dir))

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = ICCRawMainWindow()
    try:
        width_text, height_text = str(args.window_size).lower().split("x", 1)
        window.resize(max(640, int(width_text)), max(480, int(height_text)))
    except Exception:
        window.resize(2048, 1100)
    window.check_display_color_management.setChecked(bool(args.display_color_management))
    if args.display_profile is not None:
        window.path_display_profile.setText(str(args.display_profile.expanduser().resolve()))
        window.check_display_color_management.setChecked(True)
        window._on_display_color_settings_changed()
    if hasattr(window, "main_tabs"):
        window.main_tabs.setCurrentIndex(1)
    if hasattr(window, "right_workflow_tabs"):
        window.right_workflow_tabs.setCurrentIndex(1)
    image, source_info = load_source(args, window)
    window.chk_compare.setChecked(False)
    if hasattr(window, "check_image_clip_overlay"):
        window.check_image_clip_overlay.setChecked(bool(args.clip_overlay))
    window._original_linear = np.asarray(image, dtype=np.float32)
    window._last_loaded_preview_key = f"benchmark|{source_info.get('kind')}|{window._original_linear.shape}"
    window.show()
    app.processEvents()

    initial_started = time.perf_counter()
    window._refresh_preview()
    initial_idle = wait_for_interactive_idle(window)
    initial_render_seconds = time.perf_counter() - initial_started
    if hasattr(window, "image_result_single"):
        panel = window.image_result_single
        panel.set_view_transform(
            zoom=panel.view_zoom_for_display_scale(1.0),
            rotation=0,
        )
    app.processEvents()
    viewport_rect = None
    viewer_scale = None
    panel_size = None
    if hasattr(window, "image_result_single"):
        panel = window.image_result_single
        panel_size = [int(panel.width()), int(panel.height())]
        if hasattr(panel, "visible_image_rect"):
            viewport_rect = panel.visible_image_rect(margin=0)
        if hasattr(panel, "current_display_scale"):
            viewer_scale = panel.current_display_scale()

    started = time.perf_counter()
    single_brightness = run_single_brightness_change(window)
    slider = run_slider_drag(
        app,
        window,
        steps=int(args.steps),
        interval_ms=int(args.interval_ms),
        settle_ms=int(args.settle_ms),
    )
    curve = run_tone_curve_drag(
        window,
        steps=int(args.steps),
        interval_ms=int(args.interval_ms),
        settle_ms=int(args.settle_ms),
    )
    total_seconds = time.perf_counter() - started
    final_idle = wait_for_interactive_idle(window, timeout_ms=30_000)
    wait_ms(250)
    app.processEvents()

    result = {
        "schema": 1,
        "qt_platform": os.environ.get("QT_QPA_PLATFORM", ""),
        "display_color_management": {
            "enabled": bool(window.check_display_color_management.isChecked()),
            "profile": str(window._active_display_profile_path()) if window._active_display_profile_path() else None,
        },
        "clip_overlay": bool(getattr(window, "check_image_clip_overlay", None) and window.check_image_clip_overlay.isChecked()),
        "viewer": {
            "panel_size": panel_size,
            "display_scale": round(float(viewer_scale), 4) if viewer_scale is not None else None,
            "visible_rect": list(viewport_rect) if viewport_rect is not None else None,
        },
        "source": {
            **source_info,
            "shape": list(window._original_linear.shape),
            "array_mb": round(float(window._original_linear.nbytes) / (1024.0 * 1024.0), 1),
        },
        "initial_render": {
            "idle": bool(initial_idle),
            "seconds": round(float(initial_render_seconds), 4),
        },
        "total_seconds": round(total_seconds, 4),
        "final_idle": bool(final_idle),
        "phases": [single_brightness, slider, curve],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
