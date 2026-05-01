from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewRecipeMixin:
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
            self.edit_colprof_args.setText("-u -R")

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
        if "-u" not in args:
            extra.append("-u")
        if "-R" not in args:
            extra.append("-R")
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

    def _tone_curve_channel_key(self) -> str:
        combo = getattr(self, "combo_tone_curve_channel", None)
        key = str(combo.currentData() if combo is not None else self._tone_curve_active_channel)
        return key if key in {"luminance", "red", "green", "blue"} else "luminance"

    def _identity_tone_curve_points(self) -> list[tuple[float, float]]:
        return [(0.0, 0.0), (1.0, 1.0)]

    def _ensure_tone_curve_channel_state(self) -> None:
        channels = ("luminance", "red", "green", "blue")
        if not isinstance(getattr(self, "_tone_curve_channel_points", None), dict):
            self._tone_curve_channel_points = {}
        if not isinstance(getattr(self, "_tone_curve_channel_presets", None), dict):
            self._tone_curve_channel_presets = {}
        for channel in channels:
            points = self._coerce_tone_curve_points(self._tone_curve_channel_points.get(channel))
            self._tone_curve_channel_points[channel] = points or self._identity_tone_curve_points()
            preset = str(self._tone_curve_channel_presets.get(channel) or "linear")
            self._tone_curve_channel_presets[channel] = preset
        if getattr(self, "_tone_curve_active_channel", "luminance") not in channels:
            self._tone_curve_active_channel = "luminance"

    def _save_visible_tone_curve_channel_state(self, channel: str | None = None) -> None:
        self._ensure_tone_curve_channel_state()
        target = channel or self._tone_curve_channel_key()
        if target not in self._tone_curve_channel_points:
            target = "luminance"
        self._tone_curve_active_channel = target
        self._tone_curve_channel_points[target] = normalize_tone_curve_points(self.tone_curve_editor.points())
        self._tone_curve_channel_presets[target] = self._tone_curve_preset_key()

    def _load_tone_curve_channel_into_editor(self, channel: str) -> None:
        self._ensure_tone_curve_channel_state()
        key = channel if channel in self._tone_curve_channel_points else "luminance"
        self._tone_curve_active_channel = key
        preset = str(self._tone_curve_channel_presets.get(key) or "linear")
        points = self._tone_curve_channel_points.get(key) or self._tone_curve_preset_points(preset)
        self.combo_tone_curve_preset.blockSignals(True)
        self._set_combo_data(self.combo_tone_curve_preset, preset)
        self.combo_tone_curve_preset.blockSignals(False)
        self.tone_curve_editor.set_points(points, emit=False)
        if self._original_linear is not None:
            self.tone_curve_editor.set_histogram_from_image(self._original_linear, channel=key)
            self._tone_curve_histogram_key = None

    def _tone_curve_channel_points_state(self) -> dict[str, list[list[float]]]:
        self._save_visible_tone_curve_channel_state()
        return {
            channel: [[float(x), float(y)] for x, y in normalize_tone_curve_points(points)]
            for channel, points in self._tone_curve_channel_points.items()
            if channel in {"luminance", "red", "green", "blue"}
        }

    def _coerce_tone_curve_channel_points(self, value: Any) -> dict[str, list[tuple[float, float]]]:
        out: dict[str, list[tuple[float, float]]] = {}
        if not isinstance(value, dict):
            return out
        for channel in ("luminance", "red", "green", "blue"):
            points = self._coerce_tone_curve_points(value.get(channel))
            if points is not None:
                out[channel] = points
        return out

    def _set_tone_curve_controls_enabled(self, enabled: bool) -> None:
        self.combo_tone_curve_channel.setEnabled(bool(enabled))
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
        self.label_tone_curve_black.setText(self.tr("Negro curva:") + f" {self.slider_tone_curve_black.value() / 1000:.3f}")
        self.label_tone_curve_white.setText(self.tr("Blanco curva:") + f" {self.slider_tone_curve_white.value() / 1000:.3f}")
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
        if active and hasattr(self, "_set_mtf_roi_selection_active"):
            self._set_mtf_roi_selection_active(False)
        self._neutral_picker_active = bool(active)
        if hasattr(self, "btn_neutral_picker"):
            self.btn_neutral_picker.blockSignals(True)
            self.btn_neutral_picker.setChecked(self._neutral_picker_active)
            self.btn_neutral_picker.blockSignals(False)
        self._update_viewer_interaction_cursor()

    def _update_viewer_interaction_cursor(self) -> None:
        active = bool(self._neutral_picker_active or self._manual_chart_marking)
        cursor = QtCore.Qt.CrossCursor if active else None
        for panel_name in ("image_result_single", "image_result_compare"):
            if not hasattr(self, panel_name):
                continue
            panel = getattr(self, panel_name)
            if hasattr(panel, "set_interaction_cursor"):
                panel.set_interaction_cursor(cursor)
            elif cursor is not None:
                panel.setCursor(cursor)
            else:
                panel.unsetCursor()

    def _toggle_neutral_picker(self, checked: bool = False) -> None:
        if checked and self._original_linear is None:
            self._set_neutral_picker_active(False)
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Carga primero una imagen en el visor."))
            return
        self._set_neutral_picker_active(bool(checked))
        if self._neutral_picker_active:
            self._manual_chart_marking = False
            self._update_viewer_interaction_cursor()
            self._sync_manual_chart_overlay()
            self._set_status(self.tr("Cuentagotas neutro activo: haz clic en un gris/blanco sin saturar"))
        else:
            self._set_status(self.tr("Cuentagotas neutro desactivado"))

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
            QtWidgets.QMessageBox.information(self, self.tr("Punto neutro"), str(exc))
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
        self._set_status(self.tr("Balance neutro aplicado:") + f" {temperature} K, " + self.tr("matiz") + f" {tint:+.1f}")

    def _on_tone_curve_enabled_changed(self, enabled: bool) -> None:
        self._set_tone_curve_controls_enabled(enabled)
        self._on_render_control_change()

    def _on_tone_curve_channel_changed(self, _index: int) -> None:
        previous = getattr(self, "_tone_curve_active_channel", "luminance")
        current = self._tone_curve_channel_key()
        if previous != current:
            self._save_visible_tone_curve_channel_state(previous)
        self._load_tone_curve_channel_into_editor(current)
        self._on_render_control_change()

    def _on_tone_curve_preset_changed(self, _index: int) -> None:
        key = self._tone_curve_preset_key()
        if key != "custom":
            self.tone_curve_editor.set_points(self._tone_curve_preset_points(key), emit=False)
        self._save_visible_tone_curve_channel_state()
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
        self._save_visible_tone_curve_channel_state()
        self._on_render_control_change()

    def _on_render_control_change(self) -> None:
        if self._original_linear is not None:
            self._schedule_preview_refresh()

    def _reset_tone_curve(self) -> None:
        self.check_tone_curve_enabled.setChecked(False)
        self._tone_curve_channel_points = {
            "luminance": self._identity_tone_curve_points(),
            "red": self._identity_tone_curve_points(),
            "green": self._identity_tone_curve_points(),
            "blue": self._identity_tone_curve_points(),
        }
        self._tone_curve_channel_presets = {
            "luminance": "linear",
            "red": "linear",
            "green": "linear",
            "blue": "linear",
        }
        self._tone_curve_active_channel = "luminance"
        if hasattr(self, "combo_tone_curve_channel"):
            self._set_combo_data(self.combo_tone_curve_channel, "luminance")
        self._set_combo_data(self.combo_tone_curve_preset, "linear")
        self._set_tone_curve_range_controls(0.0, 1.0)
        self.tone_curve_editor.set_points(self._tone_curve_preset_points("linear"), emit=False)
        self._set_tone_curve_controls_enabled(False)
        self._on_render_control_change()

    def _reset_color_adjustments(self, *_args: object, refresh: bool = True) -> None:
        self._set_neutral_picker_active(False)
        if hasattr(self, "label_neutral_picker"):
            self.label_neutral_picker.setText(self.tr("Punto neutro: sin muestra"))
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

    def _preview_colorimetric_u8(self, fallback_u8: np.ndarray | None) -> np.ndarray | None:
        source = getattr(self, "_preview_srgb", None)
        if source is None:
            return fallback_u8
        try:
            source_rgb = np.asarray(source)
            if fallback_u8 is not None:
                fallback = np.asarray(fallback_u8)
                if source_rgb.shape[:2] != fallback.shape[:2]:
                    return fallback_u8
            return srgb_to_display_u8(source_rgb, None)
        except Exception:
            return fallback_u8

    def _preview_histogram_source_label(self) -> str:
        if (
            hasattr(self, "chk_apply_profile")
            and self.chk_apply_profile.isChecked()
            and hasattr(self, "path_profile_active")
            and self.path_profile_active.text().strip()
        ):
            return self.tr("Histograma: sRGB colorimétrico tras ICC de entrada, antes del ICC del monitor.")
        return self.tr("Histograma: sRGB de preview, antes del ICC del monitor.")

    def _update_viewer_histogram(self, colorimetric_u8: np.ndarray | None) -> None:
        if not hasattr(self, "viewer_histogram"):
            return
        self.viewer_histogram.set_image_u8(
            colorimetric_u8,
            source_label=self._preview_histogram_source_label() if colorimetric_u8 is not None else None,
        )
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
            self.histogram_shadow_label.setText(self.tr("Sombras: --"))
            self.histogram_highlight_label.setText(self.tr("Luces: --"))
            self.histogram_shadow_label.setStyleSheet("font-size: 12px; color: #6b7280;")
            self.histogram_highlight_label.setStyleSheet("font-size: 12px; color: #6b7280;")
            return

        shadow_pct = float(metrics.get("shadow_any", 0.0)) * 100.0
        highlight_pct = float(metrics.get("highlight_any", 0.0)) * 100.0
        self.histogram_shadow_label.setText(self.tr("Sombras:") + f" {shadow_pct:.2f}%")
        self.histogram_highlight_label.setText(self.tr("Luces:") + f" {highlight_pct:.2f}%")
        alert_pct = float(VIEWER_HISTOGRAM_CLIP_ALERT_RATIO) * 100.0
        shadow_alert = shadow_pct > alert_pct
        highlight_alert = highlight_pct > alert_pct
        self.histogram_shadow_label.setStyleSheet(
            "font-size: 12px; color: #60a5fa;" if shadow_alert else "font-size: 12px; color: #94a3b8;"
        )
        self.histogram_highlight_label.setStyleSheet(
            "font-size: 12px; color: #f87171;" if highlight_alert else "font-size: 12px; color: #94a3b8;"
        )

    def _normalize_recipe_output_for_color_management(self, recipe: Recipe) -> Recipe:
        if is_generic_output_space(recipe.output_space):
            profile = generic_output_profile(recipe.output_space)
            recipe.output_linear = False
            if str(recipe.tone_curve or "").strip().lower() == "linear":
                recipe.tone_curve = "srgb" if profile.key == "srgb" else f"gamma:{profile.gamma:.3g}"
        elif self._is_camera_output_space(recipe.output_space):
            recipe.output_linear = True
            recipe.tone_curve = "linear"
        return recipe

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
        return self._normalize_recipe_output_for_color_management(recipe)

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
        if "-u" not in args:
            args.append("-u")
        if "-R" not in args:
            args.append("-R")
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
