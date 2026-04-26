from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6 import QtGui, QtWidgets  # noqa: E402

import iccraw.gui as gui_module  # noqa: E402
from iccraw.core.models import Recipe  # noqa: E402
from iccraw.gui import ICCRawMainWindow  # noqa: E402
from iccraw.provenance.c2pa import C2PASignConfig  # noqa: E402
from iccraw.provenance.nexoraw_proof import NexoRawProofConfig, NexoRawProofResult  # noqa: E402
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


def test_raw_thumbnail_payload_falls_back_to_half_size_raw(tmp_path: Path, monkeypatch, qapp):
    raw_path = tmp_path / "capture.NEF"
    raw_path.write_bytes(b"not a real raw but enough for the fallback test")

    monkeypatch.setattr(gui_module, "extract_embedded_preview", lambda _path: None)
    monkeypatch.setattr(
        ICCRawMainWindow,
        "_rawpy_thumbnail_u8",
        staticmethod(lambda _path: gui_module.np.full((96, 48, 3), (24, 96, 180), dtype=gui_module.np.uint8)),
    )

    payloads = ICCRawMainWindow._build_thumbnail_payloads([raw_path], 64)

    assert len(payloads) == 1
    payload_path, key, rgb = payloads[0]
    assert payload_path == str(raw_path)
    assert str(raw_path) in key
    assert rgb.dtype.name == "uint8"
    assert max(rgb.shape[:2]) <= gui_module.MAX_THUMBNAIL_SIZE
    assert rgb.shape[2] == 3
    assert int(rgb[..., 2].max()) > int(rgb[..., 0].max())


def test_selected_color_reference_images_are_marked_in_thumbnail_list(tmp_path: Path, qapp):
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

        pixmap = item.icon().pixmap(window.file_list.iconSize())
        image = pixmap.toImage().convertToFormat(QtGui.QImage.Format_RGB32)
        color = QtGui.QColor(image.pixel(image.width() // 2, 1))
        assert color.green() > 160
        assert color.red() < 80
        assert color.blue() < 140
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
