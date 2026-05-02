from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class DisplayControlsMixin:
    def _init_fs_model(self) -> None:
        self._dir_model = QtWidgets.QFileSystemModel(self)
        for option in (
            "DontResolveSymlinks",
            "DontUseCustomDirectoryIcons",
            "DontWatchForChanges",
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
        candidate = Path(folder).expanduser()
        try:
            candidate = candidate.resolve(strict=False)
        except Exception:
            pass

        active_root = getattr(self, "_active_session_root", None)
        if active_root is not None:
            try:
                active_root = Path(active_root).expanduser().resolve(strict=False)
                candidate.relative_to(active_root)
                return str(active_root)
            except Exception:
                pass

        project_root = None
        if hasattr(self, "_project_root_for_path"):
            try:
                project_root = self._project_root_for_path(candidate)
            except Exception:
                project_root = None
        if project_root is not None:
            return str(project_root)

        return str(candidate)

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
        channel_points = self._tone_curve_channel_points_state()
        luminance_points = channel_points.get(
            "luminance",
            [[float(x), float(y)] for x, y in normalize_tone_curve_points(self.tone_curve_editor.points())],
        )
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
            "tone_curve_channel": self._tone_curve_channel_key(),
            "tone_curve_black_point": self.slider_tone_curve_black.value() / 1000.0,
            "tone_curve_white_point": self.slider_tone_curve_white.value() / 1000.0,
            "tone_curve_points": luminance_points,
            "tone_curve_channel_points": channel_points,
            "tone_curve_channel_presets": dict(getattr(self, "_tone_curve_channel_presets", {})),
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
            "tone_curve_channel_points": state.get("tone_curve_channel_points") if state.get("tone_curve_enabled") else None,
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
        channel_points = self._coerce_tone_curve_channel_points(state.get("tone_curve_channel_points"))
        if curve_points is not None and "luminance" not in channel_points:
            channel_points["luminance"] = curve_points
        if not channel_points:
            channel_points["luminance"] = self._tone_curve_preset_points(curve_preset)
        presets = state.get("tone_curve_channel_presets")
        self._ensure_tone_curve_channel_state()
        for channel, points in channel_points.items():
            self._tone_curve_channel_points[channel] = points
        if isinstance(presets, dict):
            for channel in ("luminance", "red", "green", "blue"):
                preset = str(presets.get(channel) or "")
                if preset:
                    self._tone_curve_channel_presets[channel] = preset
        self._tone_curve_channel_presets["luminance"] = str(
            self._tone_curve_channel_presets.get("luminance") or curve_preset
        )
        active_channel = str(state.get("tone_curve_channel") or "luminance")
        if active_channel not in {"luminance", "red", "green", "blue"}:
            active_channel = "luminance"
        curve_black = float(state.get("tone_curve_black_point", 0.0))
        curve_white = float(state.get("tone_curve_white_point", 1.0))
        self.combo_tone_curve_channel.blockSignals(True)
        self._set_combo_data(self.combo_tone_curve_channel, active_channel)
        self.combo_tone_curve_channel.blockSignals(False)
        self._tone_curve_active_channel = active_channel
        self.combo_tone_curve_preset.blockSignals(True)
        self._set_combo_data(self.combo_tone_curve_preset, self._tone_curve_channel_presets.get(active_channel, curve_preset))
        self.combo_tone_curve_preset.blockSignals(False)
        self._set_tone_curve_range_controls(curve_black, curve_white)
        self.tone_curve_editor.set_points(
            self._tone_curve_channel_points.get(active_channel)
            or curve_points
            or self._tone_curve_preset_points(curve_preset),
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
        key = f"{key}|shape={tuple(np.asarray(image).shape)}"
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
        self._interactive_source_cache_key = None
        self._interactive_source_cache_image = None

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
        browse = QtWidgets.QPushButton(self.tr("..."))
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
            path = QtWidgets.QFileDialog.getExistingDirectory(self, self.tr("Selecciona directorio"), start)
            if path:
                target.setText(path)
                target.editingFinished.emit()
            return
        if save_mode:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, self.tr("Guardar como"), start)
            if path:
                target.setText(path)
                target.editingFinished.emit()
            return
        if file_mode:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, self.tr("Selecciona archivo"), start)
            if path:
                target.setText(path)
                target.editingFinished.emit()

    def _detect_display_profile(self) -> None:
        detected = detect_system_display_profile()
        if detected is None:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("No se pudo detectar automaticamente el perfil ICC del monitor. Seleccionalo manualmente."),
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

    def _profiled_display_u8_for_screen(
        self,
        image_rgb: np.ndarray,
        source_profile: Path,
        *,
        bypass_profile: bool = False,
    ) -> np.ndarray:
        monitor_profile = None if bypass_profile else self._active_display_profile_path()
        try:
            return profiled_float_to_display_u8(image_rgb, source_profile, monitor_profile)
        except Exception as exc:
            key = f"{source_profile}|{monitor_profile}|{exc}"
            if self._display_color_error_key != key:
                self._display_color_error_key = key
                self._log_preview(f"Aviso: conversion ICC directa a monitor no disponible: {exc}")
                self._update_display_profile_status(error=str(exc))
            try:
                return profiled_float_to_display_u8(image_rgb, source_profile, None)
            except Exception:
                return srgb_to_display_u8(image_rgb, None)

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
        colorimetric_u8 = self._preview_colorimetric_u8(display_u8)
        if bool(compare_enabled and self._compare_view_active()):
            self.image_result_compare.set_rgb_u8_image(display_u8)
            self._apply_clip_overlay_to_panel(self.image_result_compare, colorimetric_u8)
        else:
            self.image_result_single.set_rgb_u8_image(display_u8)
            self._apply_clip_overlay_to_panel(self.image_result_single, colorimetric_u8)
        self._update_viewer_histogram(colorimetric_u8)
        if hasattr(self, "_sync_mtf_roi_overlay"):
            self._sync_mtf_roi_overlay()
        if hasattr(self, "_maybe_update_mtf_after_preview"):
            self._maybe_update_mtf_after_preview()

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
            self.display_profile_status.setText(self.tr("Monitor: error de perfil; mostrando sRGB"))
            return
        profile_path = self._active_display_profile_path()
        if profile_path is None:
            if hasattr(self, "check_display_color_management") and not self.check_display_color_management.isChecked():
                self.display_profile_status.setText(self.tr("Monitor: gestion ICC desactivada"))
            else:
                self.display_profile_status.setText(self.tr("Monitor: sRGB (sin perfil de sistema detectado)"))
            return
        if not profile_path.exists():
            self.display_profile_status.setText(self.tr("Monitor: perfil no encontrado") + f" ({profile_path.name})")
            return
        self.display_profile_status.setText(self.tr("Monitor:") + f" {display_profile_label(profile_path)}")
