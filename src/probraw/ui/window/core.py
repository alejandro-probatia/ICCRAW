from __future__ import annotations

import os
from pathlib import Path
import traceback

from ...gui_config import (
    APP_NAME,
    LEGACY_SETTINGS_DIR_ENV,
    ORG_NAME,
    SETTINGS_DIR_ENV,
    _app_icon_path,
)

try:
    from PySide6 import QtCore, QtGui
except Exception:  # pragma: no cover - entorno sin GUI
    QtCore = None
    QtGui = None


def app_icon() -> QtGui.QIcon:
    if QtGui is None:
        raise RuntimeError("PySide6 no esta disponible")
    path = _app_icon_path()
    if path is None:
        return QtGui.QIcon()
    return QtGui.QIcon(str(path))


def make_app_settings() -> QtCore.QSettings:
    if QtCore is None:
        raise RuntimeError("PySide6 no esta disponible")
    settings_dir = (
        os.environ.get(SETTINGS_DIR_ENV, "").strip()
        or os.environ.get(LEGACY_SETTINGS_DIR_ENV, "").strip()
    )
    if settings_dir:
        base = Path(settings_dir).expanduser()
        base.mkdir(parents=True, exist_ok=True)
        QtCore.QSettings.setPath(
            QtCore.QSettings.IniFormat,
            QtCore.QSettings.UserScope,
            str(base),
        )
        return QtCore.QSettings(
            QtCore.QSettings.IniFormat,
            QtCore.QSettings.UserScope,
            ORG_NAME,
            APP_NAME,
        )
    return QtCore.QSettings(ORG_NAME, APP_NAME)


if QtCore is not None:
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
else:  # pragma: no cover - importable en entornos sin Qt
    TaskThread = None


__all__ = ["TaskThread", "app_icon", "make_app_settings"]
