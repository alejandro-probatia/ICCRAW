from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6 import QtWidgets  # noqa: E402

import iccraw.gui as gui_module  # noqa: E402
from iccraw.core.models import Recipe  # noqa: E402
from iccraw.gui import ICCRawMainWindow  # noqa: E402
from iccraw.raw import pipeline  # noqa: E402
from iccraw.session import load_session  # noqa: E402


@pytest.fixture
def qapp(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ICCRAW_SETTINGS_DIR", str(tmp_path / "qt_settings"))
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
            "profile_charts_dir": str(tmp_path / "stale_pytest_paths" / "charts"),
            "profile_output_path": "/tmp/camera_profile_gui.icc",
            "profile_report_path": "/tmp/profile_report_gui.json",
            "profile_workdir": "/tmp/iccraw_profile_work",
            "development_profile_path": "/tmp/development_profile_gui.json",
            "calibrated_recipe_path": "/tmp/recipe_calibrated_gui.yml",
            "recipe_path": str(tmp_path / "stale_pytest_paths" / "config" / "recipe_calibrated.yml"),
            "profile_active_path": "/tmp/camera_profile_gui.icc",
            "batch_input_dir": str(tmp_path / "stale_pytest_paths" / "raw"),
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
        assert window.path_recipe.text() == str(defaults["recipe"])
        assert window.profile_charts_dir.text() == str(paths["charts"])
        assert window.batch_input_dir.text() == str(paths["raw"])
        assert window.batch_out_dir.text() == str(defaults["tiff_dir"])
        assert window.path_preview_png.text() == str(defaults["preview"])
        assert window.path_profile_active.text() == ""

        saved_state = load_session(root)["state"]
        assert saved_state["profile_output_path"] == str(defaults["profile_out"])
        assert saved_state["recipe_path"] == str(defaults["recipe"])
        assert saved_state["batch_output_dir"] == str(defaults["tiff_dir"])
    finally:
        window.close()


def test_file_icons_do_not_decode_image_data(tmp_path: Path, monkeypatch, qapp):
    image_path = tmp_path / "frame.tiff"
    raw_path = tmp_path / "capture.dng"
    image_path.write_bytes(b"not a real image")
    raw_path.write_bytes(b"not a real raw")

    def fail_read_image(*_args, **_kwargs):
        raise AssertionError("file-list icons must not decode image data")

    monkeypatch.setattr(gui_module, "read_image", fail_read_image)

    window = ICCRawMainWindow()
    try:
        assert not window._icon_for_file(image_path).isNull()
        assert not window._icon_for_file(raw_path).isNull()
    finally:
        window.close()


def test_raw_develop_layout_prioritizes_viewer_area(qapp):
    window = ICCRawMainWindow()
    try:
        assert window.left_tabs.tabPosition() == QtWidgets.QTabWidget.West
        labels = [window.left_tabs.tabText(i) for i in range(window.left_tabs.count())]
        assert labels == ["Explorador", "Visor", "Análisis", "Log"]
        assert window.viewer_splitter.count() == 2
        assert window.viewer_splitter.widget(0) is window.viewer_stack
        assert hasattr(window, "thumbnail_size_slider")
    finally:
        window.close()


def test_image_panels_use_neutral_gray_background(qapp):
    window = ICCRawMainWindow()
    try:
        stylesheet = window.image_result_single.styleSheet().lower()
        assert gui_module.IMAGE_PANEL_BACKGROUND == "#2b2b2b"
        assert "background-color: #2b2b2b" in stylesheet
        assert "#111827" not in stylesheet
    finally:
        window.close()


def test_thumbnail_size_control_resizes_file_list(qapp):
    window = ICCRawMainWindow()
    try:
        window.thumbnail_size_slider.setValue(180)
        assert window.file_list.iconSize().width() == 180
        assert window.file_list.gridSize().width() > 180
        assert int(window._settings.value("view/thumbnail_size")) == 180
    finally:
        window.close()


def test_image_thumbnail_payload_uses_real_preview(tmp_path: Path, qapp):
    image_path = tmp_path / "patch.png"
    Image.new("RGB", (96, 48), (20, 120, 220)).save(image_path)

    payloads = ICCRawMainWindow._build_thumbnail_payloads([image_path], 64)

    assert len(payloads) == 1
    raw_path, key, rgb = payloads[0]
    assert raw_path == str(image_path)
    assert str(image_path) in key
    assert rgb.dtype.name == "uint8"
    assert max(rgb.shape[:2]) <= 64
    assert rgb.shape[2] == 3


def test_app_icon_resource_is_packaged(qapp):
    icon_path = gui_module._app_icon_path()
    assert icon_path is not None
    assert icon_path.name == "nexoraw-icon.png"
    assert icon_path.exists()
    assert not gui_module._app_icon().isNull()


def test_window_uses_nexoraw_app_icon(qapp):
    window = ICCRawMainWindow()
    try:
        assert not window.windowIcon().isNull()
    finally:
        window.close()


def test_startup_memory_ignores_stale_paths_and_falls_back_to_home(tmp_path: Path, qapp):
    settings = gui_module._make_app_settings()
    settings.setValue("session/last_root", str(tmp_path / "missing_session"))
    settings.setValue("browser/last_dir", str(tmp_path / "missing_dir"))
    settings.sync()

    window = ICCRawMainWindow()
    try:
        assert window._current_dir == Path.home().expanduser().resolve()
        assert window._settings.value("session/last_root") is None
        assert Path(str(window._settings.value("browser/last_dir"))).expanduser().resolve() == Path.home().resolve()
    finally:
        window.close()


def test_raw_global_options_live_in_calibration_flow(qapp):
    window = ICCRawMainWindow()
    try:
        panel_labels = [window.config_tabs.itemText(i) for i in range(window.config_tabs.count())]
        assert "RAW global" not in panel_labels
        assert "Calibrar sesión" in panel_labels
        assert isinstance(window._advanced_raw_config, QtWidgets.QGroupBox)
        assert window._advanced_raw_config.title().startswith("RAW global")
    finally:
        window.close()


def test_right_column_uses_independent_collapsible_sections(qapp):
    window = ICCRawMainWindow()
    try:
        assert isinstance(window.config_tabs, gui_module.CollapsibleToolPanel)
        assert not isinstance(window.config_tabs, QtWidgets.QToolBox)

        window.config_tabs.setItemExpanded(0, True)
        window.config_tabs.setItemExpanded(1, True)
        assert window.config_tabs.isItemExpanded(0)
        assert window.config_tabs.isItemExpanded(1)

        window.config_tabs.setItemExpanded(0, False)
        assert not window.config_tabs.isItemExpanded(0)
        assert window.config_tabs.isItemExpanded(1)
    finally:
        window.close()


def test_gui_downgrades_amaze_when_gpl3_pack_is_missing(qapp, monkeypatch):
    monkeypatch.setattr(pipeline.rawpy, "flags", {"DEMOSAIC_PACK_GPL3": False})
    window = ICCRawMainWindow()
    try:
        window._apply_recipe_to_controls(Recipe(demosaic_algorithm="amaze"))
        recipe = window._build_effective_recipe()
        assert recipe.demosaic_algorithm == "dcb"
    finally:
        window.close()
