from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image, ImageCms

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

import iccraw.gui as gui_module  # noqa: E402
from iccraw.core.models import Recipe  # noqa: E402
from iccraw.gui import ICCRawMainWindow  # noqa: E402
from iccraw.provenance.c2pa import C2PASignConfig  # noqa: E402
from iccraw.provenance.nexoraw_proof import NexoRawProofConfig, NexoRawProofResult  # noqa: E402
from iccraw.raw import pipeline  # noqa: E402
from iccraw.session import create_session, load_session  # noqa: E402
from iccraw.sidecar import load_raw_sidecar, raw_sidecar_path  # noqa: E402


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


def test_activate_session_sanitizes_profile_reference_outputs_and_rejected_profile(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session_root"
    window = ICCRawMainWindow()
    monkeypatch.setattr(window, "_is_legacy_temp_output_path", lambda _value: False)
    paths = window._session_paths_from_root(root)
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    export_tiff_dir = paths["exports"] / "tiff"
    export_tiff_dir.mkdir(parents=True, exist_ok=True)
    raw_file = paths["raw"] / "chart_01.NEF"
    derived_tiff = export_tiff_dir / "chart_01.tiff"
    raw_file.write_bytes(b"raw bytes")
    derived_tiff.write_bytes(b"derived tiff bytes")

    profile = paths["profiles"] / "case_a.icc"
    profile.write_bytes(b"icc bytes")
    profile.with_suffix(".profile.json").write_text('{"profile_status": "rejected"}', encoding="utf-8")

    payload = {
        "version": 1,
        "metadata": {"name": "case_a"},
        "directories": {key: str(path) for key, path in paths.items()},
        "state": {
            "profile_charts_dir": str(export_tiff_dir),
            "profile_chart_files": [str(derived_tiff), str(raw_file)],
            "profile_active_path": str(profile),
            "preview_apply_profile": True,
        },
        "queue": [],
    }

    try:
        window._activate_session(root, payload)

        assert window.profile_charts_dir.text() == str(paths["raw"])
        assert window._selected_chart_files == [raw_file]
        assert window.path_profile_active.text() == ""
        assert not window.chk_apply_profile.isChecked()

        saved_state = load_session(root)["state"]
        assert saved_state["profile_charts_dir"] == str(paths["raw"])
        assert saved_state["profile_chart_files"] == [str(raw_file)]
        assert saved_state["profile_active_path"] == ""
        assert saved_state["preview_apply_profile"] is False
    finally:
        window.close()


def test_create_session_does_not_inherit_previous_project_images_or_profiles(tmp_path: Path, qapp):
    old_root = tmp_path / "old_session"
    old_raw = old_root / "raw"
    old_raw.mkdir(parents=True)
    old_image = old_raw / "old_capture.tif"
    Image.new("RGB", (16, 16), (80, 120, 160)).save(old_image)

    old_payload = create_session(
        old_root,
        name="old",
        state={
            "profile_charts_dir": str(old_raw),
            "profile_chart_files": [str(old_image)],
            "batch_input_dir": str(old_raw),
            "development_profiles": [{"id": "old-profile", "name": "Old profile"}],
            "active_development_profile_id": "old-profile",
        },
        queue=[{"source": str(old_image), "status": "pending"}],
    )
    new_root = tmp_path / "new_session"

    window = ICCRawMainWindow()
    try:
        window._activate_session(old_root, old_payload)
        window._set_current_directory(old_raw)
        assert window.file_list.count() == 1

        window.session_root_path.setText(str(new_root))
        window.session_name_edit.setText("new")
        window._on_create_session()

        new_paths = window._session_paths_from_root(new_root)
        saved = load_session(new_root)
        serialized = gui_module.json.dumps(saved)

        assert window._active_session_root == new_root.resolve()
        assert window._current_dir == new_paths["raw"]
        assert window.file_list.count() == 0
        assert window.profile_charts_dir.text() == str(new_paths["charts"])
        assert window.batch_input_dir.text() == str(new_paths["raw"])
        assert window._selected_chart_files == []
        assert window._develop_queue == []
        assert window._development_profiles == []
        assert str(old_root) not in serialized
    finally:
        window.close()


def test_activate_session_rejects_existing_state_paths_outside_project_root(tmp_path: Path, qapp):
    old_root = tmp_path / "old_session"
    old_raw = old_root / "raw"
    old_raw.mkdir(parents=True)
    old_image = old_raw / "old_chart.tif"
    Image.new("RGB", (16, 16), (80, 120, 160)).save(old_image)

    new_root = tmp_path / "new_session"
    window = ICCRawMainWindow()
    paths = window._session_paths_from_root(new_root)
    payload = create_session(
        new_root,
        name="new",
        state={
            "profile_charts_dir": str(old_raw),
            "profile_chart_files": [str(old_image)],
            "batch_input_dir": str(old_raw),
        },
    )

    try:
        window._activate_session(new_root, payload)

        assert window._current_dir == paths["raw"]
        assert window.file_list.count() == 0
        assert window.profile_charts_dir.text() == str(paths["charts"])
        assert window.batch_input_dir.text() == str(paths["raw"])
        assert window._selected_chart_files == []
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
        assert labels == ["Explorador", "Visor", "Análisis", "Metadatos", "Log"]
        assert window.viewer_splitter.count() == 2
        assert window.viewer_splitter.widget(0) is window.viewer_stack
        assert hasattr(window, "thumbnail_size_slider")
        if hasattr(QtWidgets.QFileSystemModel, "DontWatchForChanges"):
            assert not window._dir_model.testOption(QtWidgets.QFileSystemModel.DontWatchForChanges)
    finally:
        window.close()


def test_main_window_omits_redundant_app_title_header(qapp):
    window = ICCRawMainWindow()
    try:
        label_texts = [label.text() for label in window.centralWidget().findChildren(QtWidgets.QLabel)]
        assert gui_module.APP_NAME not in label_texts
        assert not any("RAW -> ajuste por archivo" in text for text in label_texts)
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
        assert window.file_list.flow() == QtWidgets.QListView.LeftToRight
        assert not window.file_list.isWrapping()
        assert window.file_list.horizontalScrollBarPolicy() == QtCore.Qt.ScrollBarAsNeeded
        assert window.file_list.verticalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff
        window.thumbnail_size_slider.setValue(180)
        assert window.file_list.iconSize().width() == 180
        assert window.file_list.gridSize().width() > 180
        assert int(window._settings.value("view/thumbnail_size")) == 180
    finally:
        window.close()


def test_thumbnail_resize_keeps_cache_and_existing_icons(tmp_path: Path, qapp):
    image_path = tmp_path / "patch.png"
    Image.new("RGB", (96, 48), (20, 120, 220)).save(image_path)

    window = ICCRawMainWindow()
    try:
        assert window._thumbnail_cache_key(image_path, 72) == window._thumbnail_cache_key(image_path, 180)

        def fail_placeholder_reset():
            raise AssertionError("thumbnail resize must keep existing preview icons")

        window._set_file_list_placeholder_icons = fail_placeholder_reset
        window._on_thumbnail_size_changed(180)
        assert window.file_list.iconSize().width() == 180
    finally:
        window.close()


def test_legacy_raw_directory_selection_maps_to_new_org_directory(tmp_path: Path, qapp):
    root = tmp_path / "project"
    raw_dir = root / "01_ORG"
    raw_dir.mkdir(parents=True)
    (root / "00_configuraciones").mkdir()
    (root / "02_DRV").mkdir()
    raw_path = raw_dir / "capture.NEF"
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._active_session_root = root
        window._set_current_directory(root / "raw")

        assert window._current_dir == raw_dir.resolve()
        assert window.file_list.count() == 1
        assert Path(window.file_list.item(0).data(QtCore.Qt.UserRole)) == raw_path.resolve()
    finally:
        window.close()


def test_project_root_selection_opens_org_directory_for_browsing(tmp_path: Path, qapp):
    root = tmp_path / "project"
    raw_dir = root / "01_ORG"
    raw_dir.mkdir(parents=True)
    (root / "00_configuraciones").mkdir()
    (root / "02_DRV").mkdir()
    raw_path = raw_dir / "capture.NEF"
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._set_current_directory(root)

        assert window._current_dir == raw_dir.resolve()
        assert window.file_list.count() == 1
        assert Path(window.file_list.item(0).data(QtCore.Qt.UserRole)) == raw_path.resolve()
    finally:
        window.close()


def test_use_current_dir_as_session_root_promotes_org_directory_to_project_root(tmp_path: Path, qapp):
    root = tmp_path / "project"
    raw_dir = root / "01_ORG"
    raw_dir.mkdir(parents=True)
    (root / "00_configuraciones").mkdir()
    (root / "02_DRV").mkdir()

    window = ICCRawMainWindow()
    try:
        window._set_current_directory(raw_dir)
        window._use_current_dir_as_session_root()

        assert Path(window.session_root_path.text()) == root.resolve()
        assert window.session_name_edit.text() == root.name
        assert Path(window.session_dir_raw.text()) == root.resolve() / "01_ORG"
    finally:
        window.close()


def test_legacy_raw_thumbnail_item_maps_to_existing_org_file(tmp_path: Path, qapp):
    root = tmp_path / "project"
    raw_dir = root / "01_ORG"
    raw_dir.mkdir(parents=True)
    (root / "00_configuraciones").mkdir()
    (root / "02_DRV").mkdir()
    raw_path = raw_dir / "capture.NEF"
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._active_session_root = root
        stale_path = root / "raw" / raw_path.name
        item = QtWidgets.QListWidgetItem(raw_path.name)
        item.setData(QtCore.Qt.UserRole, str(stale_path))
        window.file_list.addItem(item)
        item.setSelected(True)
        window.file_list.setCurrentItem(item)
        window._on_file_selection_changed()
        window._selection_load_timer.stop()
        window._metadata_timer.stop()

        assert window._selected_file == raw_path.resolve()
        assert Path(item.data(QtCore.Qt.UserRole)) == raw_path.resolve()
        assert str(raw_path) in window.selected_file_label.text()
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
    assert max(rgb.shape[:2]) <= gui_module.MAX_THUMBNAIL_SIZE
    assert rgb.shape[2] == 3


def test_raw_thumbnail_payload_uses_fast_raw_fallback_when_embedded_preview_is_missing(tmp_path: Path, monkeypatch, qapp):
    raw_path = tmp_path / "capture.NEF"
    raw_path.write_bytes(b"not a real raw but enough for the thumbnail test")

    monkeypatch.setattr(gui_module, "extract_embedded_preview", lambda _path: None)
    fallback = gui_module.np.full((80, 120, 3), (0.18, 0.36, 0.72), dtype=gui_module.np.float32)
    monkeypatch.setattr(gui_module, "develop_image_array", lambda _path, _recipe, half_size=False: fallback)

    payloads = ICCRawMainWindow._build_thumbnail_payloads([raw_path], 64)

    assert len(payloads) == 1
    raw_path_text, key, rgb = payloads[0]
    assert raw_path_text == str(raw_path)
    assert str(raw_path) in key
    assert rgb.dtype.name == "uint8"
    assert max(rgb.shape[:2]) <= gui_module.MAX_THUMBNAIL_SIZE
    assert rgb.shape[2] == 3


def test_thumbnail_disk_cache_restores_icon(tmp_path: Path, qapp):
    window = ICCRawMainWindow()
    try:
        window._disk_cache_dirs = lambda _path=None, _kind="thumbnails": [tmp_path / "thumb-cache"]
        key = "example|123|thumb-v2"
        rgb = gui_module.np.full((24, 16, 3), (20, 120, 220), dtype=gui_module.np.uint8)

        window._write_thumbnail_to_disk_cache(key, rgb)
        window._image_thumb_cache.clear()

        icon = window._cached_thumbnail_icon(key)

        assert icon is not None
        assert not icon.pixmap(16, 16).isNull()
        assert key in window._image_thumb_cache
    finally:
        window.close()


def test_session_thumbnail_cache_uses_relative_project_key(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_path = root / "01_ORG" / "capture.NEF"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._active_session_root = root.resolve()
        key = window._thumbnail_cache_key(raw_path, 64)
        rgb = gui_module.np.full((24, 16, 3), (20, 120, 220), dtype=gui_module.np.uint8)

        window._write_thumbnail_to_disk_cache(key, rgb, path=raw_path)
        window._image_thumb_cache.clear()
        icon = window._cached_thumbnail_icon(key, path=raw_path)

        assert key.startswith("session:01_ORG/capture.NEF|")
        assert icon is not None
        assert list((root / "00_configuraciones" / "work" / "cache" / "thumbnails").glob("*/*.png"))
    finally:
        window.close()


def test_session_preview_cache_survives_memory_clear(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_path = root / "01_ORG" / "capture.NEF"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._active_session_root = root.resolve()
        key = window._preview_cache_key(
            selected=raw_path,
            recipe=Recipe(),
            fast_raw=True,
            max_preview_side=900,
        )
        image = gui_module.np.linspace(0.0, 1.0, 8 * 6 * 3, dtype=gui_module.np.float32).reshape(8, 6, 3)

        window._cache_preview_image(key, image, selected=raw_path)
        window._preview_cache.clear()
        window._preview_cache_order.clear()

        restored = window._cached_preview_image(key, selected=raw_path)

        assert key.startswith("session:01_ORG/capture.NEF|")
        assert restored is not None
        assert gui_module.np.allclose(restored, image)
        assert list((root / "00_configuraciones" / "work" / "cache" / "previews").glob("*/*.npy"))
    finally:
        window.close()


def test_raw_preview_uses_balanced_fast_mode_outside_compare(tmp_path: Path, monkeypatch, qapp):
    raw_path = tmp_path / "sample.NEF"
    raw_path.write_bytes(b"raw")
    captured: dict[str, object] = {}

    def fake_load_image_for_preview(_path, *, recipe, fast_raw, max_preview_side):
        captured["demosaic"] = recipe.demosaic_algorithm
        captured["fast_raw"] = bool(fast_raw)
        captured["max_preview_side"] = int(max_preview_side)
        return gui_module.np.zeros((24, 32, 3), dtype=gui_module.np.float32), "ok"

    monkeypatch.setattr(gui_module, "load_image_for_preview", fake_load_image_for_preview)

    window = ICCRawMainWindow()
    try:
        window._start_background_task = lambda _label, task, on_success: on_success(task())
        window._selected_file = raw_path
        window._set_combo_data(window.combo_demosaic, "linear")
        window.chk_compare.setChecked(False)

        window._on_load_selected(show_message=False)

        assert captured["fast_raw"] is True
        assert captured["demosaic"] == "dcb"
        assert captured["max_preview_side"] == int(window.spin_preview_max_side.value())
    finally:
        window.close()


def test_compare_toggle_switches_raw_preview_between_fast_and_max_quality(tmp_path: Path, monkeypatch, qapp):
    raw_path = tmp_path / "sample.NEF"
    raw_path.write_bytes(b"raw")
    calls: list[bool] = []

    def fake_load_image_for_preview(_path, *, recipe, fast_raw, max_preview_side):
        _ = recipe, max_preview_side
        calls.append(bool(fast_raw))
        return gui_module.np.full((24, 32, 3), 0.5, dtype=gui_module.np.float32), "ok"

    monkeypatch.setattr(gui_module, "load_image_for_preview", fake_load_image_for_preview)

    window = ICCRawMainWindow()
    try:
        window._start_background_task = lambda _label, task, on_success: on_success(task())
        window._selected_file = raw_path
        window.chk_compare.setChecked(False)
        window._on_load_selected(show_message=False)
        assert calls[-1] is True

        window.chk_compare.setChecked(True)
        qapp.processEvents()
        assert calls[-1] is False
        assert "|0|" in (window._last_loaded_preview_key or "")

        window.chk_compare.setChecked(False)
        qapp.processEvents()
        assert "|1|" in (window._last_loaded_preview_key or "")
    finally:
        window.close()


def test_thumbnail_batch_limits_background_work(tmp_path: Path, qapp):
    window = ICCRawMainWindow()
    try:
        paths = []
        for index in range(gui_module.THUMBNAIL_BATCH_SIZE + 5):
            path = tmp_path / f"image_{index:02d}.png"
            path.write_bytes(b"placeholder")
            paths.append(path)

        batch = window._next_thumbnail_batch(paths, 64)

        assert len(batch) == gui_module.THUMBNAIL_BATCH_SIZE
        assert batch == paths[: gui_module.THUMBNAIL_BATCH_SIZE]
        assert window._thumbnail_scan_index == gui_module.THUMBNAIL_BATCH_SIZE
    finally:
        window.close()


def test_selected_color_reference_images_update_reference_label_without_profile_marker(tmp_path: Path, qapp):
    image_path = tmp_path / "reference.tiff"
    Image.new("RGB", (96, 48), (20, 120, 220)).save(image_path)

    window = ICCRawMainWindow()
    try:
        window._set_current_directory(tmp_path)
        base_icon = window._icon_from_thumbnail_array(
            gui_module.np.full((64, 64, 3), (48, 48, 48), dtype=gui_module.np.uint8)
        )
        window._image_thumb_cache[window._thumbnail_cache_key(image_path, 72)] = base_icon
        window._apply_cached_thumbnails([image_path], 72)

        item = window.file_list.item(0)
        item.setSelected(True)
        window.file_list.setCurrentItem(item)
        window._use_selected_files_as_profile_charts()

        assert window._profile_chart_files_or_none() == [image_path]
        assert "Referencias colorimétricas seleccionadas: 1" in window.profile_chart_selection_label.text()
        assert "Referencia colorimétrica seleccionada" in item.toolTip()

        pixmap = item.icon().pixmap(window.file_list.iconSize())
        image = pixmap.toImage().convertToFormat(QtGui.QImage.Format_RGB32)
        top = QtGui.QColor(image.pixel(image.width() // 2, 1))
        bottom = QtGui.QColor(image.pixel(image.width() // 2, image.height() - 2))
        assert not (top.blue() > 160 and top.red() < 120)
        assert not (bottom.blue() > 160 and bottom.red() < 120)
        assert not (bottom.green() > 160 and bottom.red() < 120 and bottom.blue() < 140)
    finally:
        window.close()


def test_manual_development_profile_is_saved_relative_to_session(tmp_path: Path, qapp):
    root = tmp_path / "session"
    payload = create_session(root, name="Sesion perfiles")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window.development_profile_name_edit.setText("Luz norte")
        window.spin_exposure.setValue(0.65)
        window.slider_brightness.setValue(12)

        window._save_current_development_profile()

        assert len(window._development_profiles) == 1
        profile = window._development_profiles[0]
        assert profile["id"] == "luz-norte"
        assert profile["recipe_path"] == "00_configuraciones/development_profiles/luz-norte/recipe.yml"
        assert profile["manifest_path"] == "00_configuraciones/development_profiles/luz-norte/development_profile.json"
        assert (root / profile["recipe_path"]).exists()
        assert (root / profile["manifest_path"]).exists()

        saved_state = load_session(root)["state"]
        assert saved_state["active_development_profile_id"] == "luz-norte"
        assert saved_state["development_profiles"][0]["id"] == "luz-norte"
    finally:
        window.close()


def test_manual_development_profile_can_use_generic_icc_without_chart(tmp_path: Path, monkeypatch, qapp):
    standard_profiles = tmp_path / "standard-profiles"
    standard_profiles.mkdir()
    (standard_profiles / "ProPhoto.icm").write_bytes(b"p" * 256)
    monkeypatch.setenv("NEXORAW_STANDARD_ICC_DIR", str(standard_profiles))
    root = tmp_path / "session"
    payload = create_session(root, name="Sesion sin carta")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window.development_profile_name_edit.setText("A ojo ProPhoto")
        index = window.development_output_space_combo.findData("prophoto_rgb")
        assert index >= 0
        window.development_output_space_combo.setCurrentIndex(index)
        window.spin_exposure.setValue(0.35)

        window._save_current_development_profile()

        profile = window._development_profiles[0]
        manifest = load_session(root)["state"]["development_profiles"][0]
        manifest_path = root / profile["manifest_path"]
        payload = gui_module.json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["kind"] == "manual"
        assert payload["recipe"]["output_space"] == "prophoto_rgb"
        assert payload["recipe"]["output_linear"] is False
        assert payload["generic_output_space"] == "prophoto_rgb"
        assert payload["icc_profile_path"] == ""
        assert payload["output_icc_profile_path"] == "00_configuraciones/profiles/standard/ProPhoto.icm"
        assert (root / payload["output_icc_profile_path"]).exists()
        assert manifest["generic_output_space"] == "prophoto_rgb"
    finally:
        window.close()


def test_development_profile_applies_to_controls_and_queue(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion perfiles")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window.development_profile_name_edit.setText("Ajuste base")
        window.spin_exposure.setValue(0.4)
        window.slider_noise_luma.setValue(18)
        window._save_current_development_profile()
        profile_id = window._active_development_profile_id

        window.spin_exposure.setValue(-0.6)
        window.slider_noise_luma.setValue(0)
        window._apply_development_profile_to_controls(profile_id)
        assert abs(window.spin_exposure.value() - 0.4) < 0.001
        assert window.slider_noise_luma.value() == 18

        window._queue_add_files([raw])
        assert window._develop_queue[0]["development_profile_id"] == profile_id
        saved_queue = load_session(root)["queue"]
        assert saved_queue[0]["development_profile_id"] == profile_id
    finally:
        window.close()


def test_queue_assignment_writes_and_reuses_raw_sidecar(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion mochila")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window.development_profile_name_edit.setText("Carta base")
        window.spin_exposure.setValue(0.35)
        window._save_current_development_profile()
        profile_id = window._active_development_profile_id

        window._queue_add_files([raw])
        window.queue_table.selectRow(0)
        window._queue_assign_active_development_profile()

        assert raw_sidecar_path(raw).exists()
        sidecar = load_raw_sidecar(raw)
        assert sidecar["development_profile"]["id"] == profile_id
        assert sidecar["recipe"]["exposure_compensation"] == 0.35

        window._develop_queue = []
        window._active_development_profile_id = ""
        window._queue_add_files([raw])
        assert window._develop_queue[0]["development_profile_id"] == profile_id
    finally:
        window.close()


def test_chart_profile_assignment_marks_raw_as_advanced_and_can_be_pasted(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_dir = root / "01_ORG"
    source = raw_dir / "chart.NEF"
    target = raw_dir / "target.NEF"
    raw_dir.mkdir(parents=True)
    source.write_bytes(b"chart raw")
    target.write_bytes(b"target raw")
    payload = create_session(root, name="Sesion carta")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._set_current_directory(raw_dir)

        paths = window._session_paths_from_root(root)
        profile_path = paths["profiles"] / "session.icc"
        profile_report = paths["config"] / "profile_report.json"
        recipe_path = paths["config"] / "recipe_calibrated.yml"
        manifest_path = paths["config"] / "development_profile.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_report.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_bytes(b"icc")
        profile_report.write_text("{}", encoding="utf-8")
        gui_module.save_recipe(Recipe(exposure_compensation=0.45), recipe_path)
        manifest_path.write_text("{}", encoding="utf-8")

        profile_id = window._register_chart_development_profile(
            name="Carta D50",
            development_profile_path=manifest_path,
            calibrated_recipe_path=recipe_path,
            icc_profile_path=profile_path,
            profile_report_path=profile_report,
        )
        assert window._assign_development_profile_to_raw_files(profile_id, [source]) == 1

        source_sidecar = load_raw_sidecar(source)
        assert source_sidecar["development_profile"]["kind"] == "chart"
        assert source_sidecar["development_profile"]["profile_type"] == "advanced"
        marked = window._display_icon_for_path(
            source,
            window._icon_from_thumbnail_array(gui_module.np.full((48, 48, 3), 96, dtype=gui_module.np.uint8)),
        )
        pixmap = marked.pixmap(window.file_list.iconSize())
        image = pixmap.toImage().convertToFormat(QtGui.QImage.Format_RGB32)
        marker = QtGui.QColor(image.pixel(image.width() // 2, image.height() - 2))
        assert marker.blue() > 160
        assert marker.red() < 120

        source_item = next(
            window.file_list.item(row)
            for row in range(window.file_list.count())
            if window.file_list.item(row).data(QtCore.Qt.UserRole) == str(source)
        )
        target_item = next(
            window.file_list.item(row)
            for row in range(window.file_list.count())
            if window.file_list.item(row).data(QtCore.Qt.UserRole) == str(target)
        )
        window.file_list.clearSelection()
        source_item.setSelected(True)
        window.file_list.setCurrentItem(source_item)
        window._selection_load_timer.stop()
        window._metadata_timer.stop()
        window._copy_development_settings_from_selected()

        window.file_list.clearSelection()
        target_item.setSelected(True)
        window.file_list.setCurrentItem(target_item)
        window._selection_load_timer.stop()
        window._metadata_timer.stop()
        window._paste_development_settings_to_selected()

        pasted = load_raw_sidecar(target)
        assert pasted["development_profile"]["kind"] == "chart"
        assert pasted["development_profile"]["profile_type"] == "advanced"
        assert pasted["recipe"]["exposure_compensation"] == 0.45
        assert "Perfil de ajuste avanzado" in target_item.toolTip()
    finally:
        window.close()


def test_generate_profile_uses_explicit_color_reference_selection(tmp_path: Path, monkeypatch, qapp):
    chart_01 = tmp_path / "chart_01.tiff"
    chart_02 = tmp_path / "chart_02.tiff"
    Image.new("RGB", (16, 16), (20, 120, 220)).save(chart_01)
    Image.new("RGB", (16, 16), (220, 120, 20)).save(chart_02)

    captured: dict[str, object] = {}

    def fake_auto_generate_profile_from_charts(**kwargs):
        captured.update(kwargs)
        return {"chart_captures_used": 2}

    def run_task(_label, task, _on_success):
        captured["payload"] = task()

    monkeypatch.setattr(gui_module.ReferenceCatalog, "from_path", staticmethod(lambda _path: object()))
    monkeypatch.setattr(gui_module, "auto_generate_profile_from_charts", fake_auto_generate_profile_from_charts)

    window = ICCRawMainWindow()
    try:
        window._start_background_task = run_task
        window._selected_chart_files = [chart_02, chart_01]
        window.profile_charts_dir.setText(str(tmp_path / "unused"))

        window._on_generate_profile()

        assert captured["chart_capture_files"] == [chart_02, chart_01]
        assert captured["chart_captures_dir"] == tmp_path / "unused"
    finally:
        window.close()


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


def test_thumbnail_copy_paste_development_settings_writes_raw_sidecars(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_dir = root / "01_ORG"
    source = raw_dir / "source.NEF"
    target = raw_dir / "target.NEF"
    raw_dir.mkdir(parents=True)
    source.write_bytes(b"source raw")
    target.write_bytes(b"target raw")
    payload = create_session(root, name="Sesion copiar pegar")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._set_current_directory(raw_dir)

        source_item = next(
            window.file_list.item(row)
            for row in range(window.file_list.count())
            if window.file_list.item(row).data(QtCore.Qt.UserRole) == str(source)
        )
        target_item = next(
            window.file_list.item(row)
            for row in range(window.file_list.count())
            if window.file_list.item(row).data(QtCore.Qt.UserRole) == str(target)
        )

        window.file_list.clearSelection()
        source_item.setSelected(True)
        window.file_list.setCurrentItem(source_item)
        window._selection_load_timer.stop()
        window._metadata_timer.stop()
        window.spin_exposure.setValue(0.75)
        window.slider_brightness.setValue(22)
        window._save_current_development_settings_to_selected()

        assert raw_sidecar_path(source).exists()
        source_sidecar = load_raw_sidecar(source)
        assert source_sidecar["development_profile"]["profile_type"] == "basic"
        assert "Perfil de ajuste básico" in source_item.toolTip()
        marked = window._display_icon_for_path(
            source,
            window._icon_from_thumbnail_array(gui_module.np.full((48, 48, 3), 96, dtype=gui_module.np.uint8)),
        )
        pixmap = marked.pixmap(window.file_list.iconSize())
        image = pixmap.toImage().convertToFormat(QtGui.QImage.Format_RGB32)
        marker = QtGui.QColor(image.pixel(image.width() // 2, image.height() - 2))
        assert marker.green() > 160
        assert marker.red() < 120
        assert marker.blue() < 140

        window._copy_development_settings_from_selected()

        window.file_list.clearSelection()
        target_item.setSelected(True)
        window.file_list.setCurrentItem(target_item)
        window._selection_load_timer.stop()
        window._metadata_timer.stop()
        window.spin_exposure.setValue(-0.5)
        window.slider_brightness.setValue(0)
        window._paste_development_settings_to_selected()

        pasted = load_raw_sidecar(target)
        assert pasted["development_profile"]["profile_type"] == "basic"
        assert pasted["recipe"]["exposure_compensation"] == 0.75
        assert pasted["render_adjustments"]["brightness_ev"] == 0.22
        assert "Perfil de ajuste básico" in target_item.toolTip()
    finally:
        window.close()


def test_raw_adjustment_groups_follow_editor_flow(qapp):
    window = ICCRawMainWindow()
    try:
        panel_labels = [window.config_tabs.itemText(i) for i in range(window.config_tabs.count())]
        assert panel_labels[:6] == [
            "Brillo y contraste",
            "Color",
            "Nitidez",
            "Gestión de color y calibración",
            "RAW Global",
            "Exportar derivados",
        ]
        assert "Calibrar sesión" not in panel_labels
        assert "Corrección básica" not in panel_labels
        assert isinstance(window._advanced_raw_config, QtWidgets.QGroupBox)
        assert window._advanced_raw_config.title() == "Criterios RAW globales"
    finally:
        window.close()


def test_development_profile_controls_live_in_color_management_flow(qapp):
    window = ICCRawMainWindow()
    try:
        panel_labels = [window.config_tabs.itemText(i) for i in range(window.config_tabs.count())]
        assert "Gestión de color y calibración" in panel_labels
        assert "Perfiles de revelado" not in panel_labels
        assert window.config_tabs.indexOf("Nitidez") == panel_labels.index("Nitidez")

        def is_descendant(widget: QtWidgets.QWidget, ancestor: QtWidgets.QWidget) -> bool:
            parent = widget.parentWidget()
            while parent is not None:
                if parent is ancestor:
                    return True
                parent = parent.parentWidget()
            return False

        assert is_descendant(window.development_profile_combo, window.config_tabs)
        assert not is_descendant(window.development_profile_combo, window.main_tabs.widget(0))
    finally:
        window.close()


def test_global_configuration_dialog_owns_non_image_settings(qapp):
    window = ICCRawMainWindow()
    try:
        panel_labels = [window.config_tabs.itemText(i) for i in range(window.config_tabs.count())]
        assert "Nitidez" in panel_labels
        assert "Detalle" not in panel_labels

        global_tabs = [
            window.global_settings_tabs.tabText(i)
            for i in range(window.global_settings_tabs.count())
        ]
        assert "Firma / C2PA" in global_tabs
        assert "Preview / monitor" in global_tabs

        def is_descendant(widget: QtWidgets.QWidget, ancestor: QtWidgets.QWidget) -> bool:
            parent = widget.parentWidget()
            while parent is not None:
                if parent is ancestor:
                    return True
                parent = parent.parentWidget()
            return False

        assert is_descendant(window.batch_c2pa_cert_path, window.global_settings_dialog)
        assert is_descendant(window.check_fast_raw_preview, window.global_settings_dialog)
        assert is_descendant(window.path_display_profile, window.global_settings_dialog)
        assert not is_descendant(window.batch_c2pa_cert_path, window.config_tabs)
        assert not is_descendant(window.check_fast_raw_preview, window.config_tabs)
        assert not is_descendant(window.path_display_profile, window.config_tabs)
    finally:
        window.close()


def test_display_color_management_defaults_to_system_profile(tmp_path: Path, monkeypatch, qapp):
    profile = tmp_path / "system-monitor.icc"
    srgb_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    profile.write_bytes(srgb_profile.tobytes())
    monkeypatch.setattr(gui_module, "detect_system_display_profile", lambda: profile)

    window = ICCRawMainWindow()
    try:
        assert window.check_display_color_management.isChecked()
        assert window.path_display_profile.text() == str(profile)
        assert "Monitor:" in window.display_profile_status.text()
    finally:
        window.close()


def test_display_color_settings_migrate_old_disabled_default(tmp_path: Path, monkeypatch, qapp):
    profile = tmp_path / "system-monitor.icc"
    srgb_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    profile.write_bytes(srgb_profile.tobytes())
    settings = gui_module._make_app_settings()
    settings.setValue("display/color_management_enabled", False)
    settings.remove("display/system_profile_default_v1")
    settings.sync()
    monkeypatch.setattr(gui_module, "detect_system_display_profile", lambda: profile)

    window = ICCRawMainWindow()
    try:
        assert window.check_display_color_management.isChecked()
        assert window.path_display_profile.text() == str(profile)
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
        qapp.processEvents()
        assert not window.config_tabs.isItemExpanded(0)
        assert window.config_tabs.isItemExpanded(1)
        first_section = window.config_tabs._items[0]["section"]
        first_header = window.config_tabs._items[0]["header"]
        assert first_section.maximumHeight() <= first_header.sizeHint().height() + 4
        assert window.config_tabs._items[0]["body"].isHidden()
    finally:
        window.close()


def test_advanced_tone_curve_is_persisted_in_render_state(qapp):
    window = ICCRawMainWindow()
    try:
        window.check_tone_curve_enabled.setChecked(True)
        window._set_tone_curve_range_controls(0.08, 0.92)
        window.tone_curve_editor.set_points([(0.0, 0.0), (0.5, 0.72), (1.0, 1.0)])

        state = window._render_adjustment_state()
        kwargs = window._render_adjustment_kwargs()

        assert state["tone_curve_enabled"] is True
        assert state["tone_curve_preset"] == "custom"
        assert state["tone_curve_black_point"] == 0.08
        assert state["tone_curve_white_point"] == 0.92
        assert state["tone_curve_points"][1] == [0.5, 0.72]
        assert kwargs["tone_curve_points"] == state["tone_curve_points"]
        assert kwargs["tone_curve_black_point"] == 0.08
        assert kwargs["tone_curve_white_point"] == 0.92
        assert window.tone_curve_editor.sizeHint().width() == window.tone_curve_editor.sizeHint().height()
        assert window.tone_curve_editor.hasHeightForWidth()
    finally:
        window.close()


def test_neutral_eyedropper_updates_temperature_and_tint(qapp):
    window = ICCRawMainWindow()
    try:
        sample = gui_module.np.array([0.18, 0.24, 0.34], dtype=gui_module.np.float32)
        window._original_linear = gui_module.np.tile(sample.reshape((1, 1, 3)), (24, 24, 1))

        window.btn_neutral_picker.click()
        assert window._neutral_picker_active is True

        window._on_result_image_click(12, 12)
        kwargs = window._render_adjustment_kwargs()
        corrected = gui_module.apply_render_adjustments(window._original_linear, **kwargs)[12, 12]

        assert window._neutral_picker_active is False
        assert window.combo_illuminant_render.currentText() == "Personalizado"
        assert "Punto neutro: RGB" in window.label_neutral_picker.text()
        assert float(gui_module.np.std(corrected)) < float(gui_module.np.std(sample)) * 0.4
    finally:
        window.close()


def test_manual_chart_marks_clear_when_selected_image_changes(tmp_path: Path, qapp):
    first = tmp_path / "chart_01.tiff"
    second = tmp_path / "chart_02.tiff"
    Image.new("RGB", (32, 32), (180, 180, 180)).save(first)
    Image.new("RGB", (32, 32), (90, 90, 90)).save(second)

    window = ICCRawMainWindow()
    try:
        window._set_current_directory(tmp_path)
        first_item = window.file_list.item(0)
        second_item = window.file_list.item(1)
        assert first_item is not None
        assert second_item is not None

        window.file_list.setCurrentItem(first_item)
        qapp.processEvents()
        window._original_linear = gui_module.np.ones((32, 32, 3), dtype=gui_module.np.float32)
        window._begin_manual_chart_marking()
        window._on_manual_chart_click(4, 4)
        window._on_manual_chart_click(24, 4)

        assert len(window._manual_chart_points) == 2
        assert len(window.image_result_single._overlay_points) == 2

        window.file_list.setCurrentItem(second_item)
        qapp.processEvents()

        assert window._manual_chart_points == []
        assert window._manual_chart_points_source is None
        assert window.image_result_single._overlay_points == []
        assert window.manual_chart_points_label.text() == "Puntos: 0/4"
    finally:
        window.close()


def test_preview_reuses_detail_adjustment_cache_for_tonal_changes(qapp, monkeypatch):
    calls = {"detail": 0}

    def fake_apply_adjustments(image, **_kwargs):
        calls["detail"] += 1
        return image.copy()

    monkeypatch.setattr(gui_module, "apply_adjustments", fake_apply_adjustments)

    window = ICCRawMainWindow()
    try:
        window._original_linear = gui_module.np.full((48, 64, 3), 0.25, dtype=gui_module.np.float32)
        window._last_loaded_preview_key = "unit-preview"

        window._refresh_preview()
        assert calls["detail"] == 1

        window.slider_brightness.setValue(12)
        window._preview_refresh_timer.stop()
        window._refresh_preview()
        assert calls["detail"] == 1

        window.slider_sharpen.setValue(30)
        window._preview_refresh_timer.stop()
        window._refresh_preview()
        assert calls["detail"] == 2
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


def test_gui_c2pa_config_reads_controls_without_persisting_passphrase(tmp_path: Path, qapp):
    cert_path = tmp_path / "nexoraw-cert.pem"
    key_path = tmp_path / "nexoraw-key.pem"
    manifest_path = tmp_path / "profile_report.json"
    cert_path.write_text("certificate", encoding="utf-8")
    key_path.write_text("private key", encoding="utf-8")
    manifest_path.write_text("{}", encoding="utf-8")

    window = ICCRawMainWindow()
    try:
        window.profile_report_out.setText(str(manifest_path))
        window.session_name_edit.setText("unit-session")
        window.batch_c2pa_cert_path.setText(str(cert_path))
        window.batch_c2pa_key_path.setText(str(key_path))
        window.batch_c2pa_key_passphrase.setText("test-passphrase")
        window.batch_c2pa_timestamp_url.setText("http://tsa.example.test")
        window.batch_c2pa_signer_name.setText("NexoRAW Test")
        window._set_combo_text(window.batch_c2pa_alg, "ps384")

        config = window._c2pa_config_from_controls()
        assert config is not None
        assert config.cert_path == cert_path
        assert config.key_path == key_path
        assert config.key_passphrase == "test-passphrase"
        assert config.alg == "ps384"
        assert config.timestamp_url == "http://tsa.example.test"
        assert config.signer_name == "NexoRAW Test"
        assert config.technical_manifest_path == manifest_path
        assert config.session_id == "unit-session"

        window._save_c2pa_settings()
        assert window._settings.value("c2pa/cert_path") == str(cert_path)
        assert window._settings.value("c2pa/key_path") == str(key_path)
        assert window._settings.value("c2pa/key_passphrase") is None
    finally:
        window.close()


def test_process_batch_files_passes_gui_c2pa_config_to_signer(tmp_path: Path, monkeypatch, qapp):
    image_path = tmp_path / "frame.png"
    out_dir = tmp_path / "out"
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    Image.new("RGB", (16, 16), (80, 120, 160)).save(image_path)
    cert_path.write_text("certificate", encoding="utf-8")
    key_path.write_text("private key", encoding="utf-8")
    c2pa_config = C2PASignConfig(cert_path=cert_path, key_path=key_path)
    proof_config = NexoRawProofConfig(private_key_path=key_path, public_key_path=None)
    captured: dict[str, object] = {}

    def fake_write_signed_profiled_tiff(out_tiff, image_linear_rgb, **kwargs):
        captured["c2pa_config"] = kwargs["c2pa_config"]
        captured["source_raw"] = kwargs["source_raw"]
        captured["render_adjustments"] = kwargs["render_adjustments"]
        Path(out_tiff).parent.mkdir(parents=True, exist_ok=True)
        Path(out_tiff).write_bytes(b"signed tiff")
        return "embedded_profile", NexoRawProofResult(
            proof_path=str(Path(out_tiff).with_suffix(".proof.json")),
            proof_sha256="proof-sha",
            output_tiff_sha256="tiff-sha",
            raw_sha256="raw-sha",
            signer_public_key_sha256="pub-sha",
        )

    monkeypatch.setattr(gui_module, "write_signed_profiled_tiff", fake_write_signed_profiled_tiff)

    window = ICCRawMainWindow()
    try:
        payload = window._process_batch_files(
            files=[image_path],
            out_dir=out_dir,
            recipe=Recipe(),
            apply_adjust=False,
            use_profile=False,
            profile_path=None,
            denoise_luma=0.0,
            denoise_color=0.0,
            sharpen_amount=0.0,
            sharpen_radius=0.0,
            lateral_ca_red_scale=1.0,
            lateral_ca_blue_scale=1.0,
            render_adjustments={},
            c2pa_config=c2pa_config,
            proof_config=proof_config,
        )

        assert payload["errors"] == []
        assert len(payload["outputs"]) == 1
        assert captured["c2pa_config"] is c2pa_config
        assert captured["source_raw"] == image_path
        assert captured["render_adjustments"] == {"applied": False}
    finally:
        window.close()
