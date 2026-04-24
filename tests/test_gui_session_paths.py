from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6 import QtWidgets  # noqa: E402

from iccraw.gui import ICCRawMainWindow  # noqa: E402
from iccraw.session import load_session  # noqa: E402


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app


def test_activate_session_migrates_legacy_temp_outputs(tmp_path: Path, monkeypatch, qapp):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    root = tmp_path / "session_root"
    window = ICCRawMainWindow()
    paths = window._session_paths_from_root(root)
    directories = {key: str(path) for key, path in paths.items()}

    payload = {
        "version": 1,
        "metadata": {"name": "case_a"},
        "directories": directories,
        "state": {
            "profile_output_path": "/tmp/camera_profile_gui.icc",
            "profile_report_path": "/tmp/profile_report_gui.json",
            "profile_workdir": "/tmp/iccraw_profile_work",
            "development_profile_path": "/tmp/development_profile_gui.json",
            "calibrated_recipe_path": "/tmp/recipe_calibrated_gui.yml",
            "recipe_path": "/tmp/recipe_calibrated_gui.yml",
            "profile_active_path": "/tmp/camera_profile_gui.icc",
            "batch_output_dir": "/tmp/iccraw_batch_tiffs",
            "preview_png_path": "/tmp/iccraw_preview.png",
        },
        "queue": [],
    }

    try:
        window._activate_session(root, payload)
        defaults = window._session_default_outputs(paths=paths, session_name="case_a")

        assert window.profile_out_path_edit.text() == str(defaults["profile_out"])
        assert window.path_profile_out.text() == str(defaults["profile_out"])
        assert window.profile_report_out.text() == str(defaults["profile_report"])
        assert window.profile_workdir.text() == str(defaults["workdir"])
        assert window.develop_profile_out.text() == str(defaults["development_profile"])
        assert window.calibrated_recipe_out.text() == str(defaults["calibrated_recipe"])
        assert window.path_recipe.text() == str(defaults["calibrated_recipe"])
        assert window.batch_out_dir.text() == str(defaults["tiff_dir"])
        assert window.path_preview_png.text() == str(defaults["preview"])
        assert window.path_profile_active.text() == ""

        saved_state = load_session(root)["state"]
        assert saved_state["profile_output_path"] == str(defaults["profile_out"])
        assert saved_state["recipe_path"] == str(defaults["calibrated_recipe"])
        assert saved_state["batch_output_dir"] == str(defaults["tiff_dir"])
    finally:
        window.close()
