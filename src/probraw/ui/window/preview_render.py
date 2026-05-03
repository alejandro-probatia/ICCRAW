from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewRenderMixin:
    def _on_slider_change(self) -> None:
        if (
            int(getattr(self, "_suspend_render_adjustment_autosave", 0) or 0) > 0
            or int(getattr(self, "_suspend_detail_adjustment_autosave", 0) or 0) > 0
        ):
            return
        if self._original_linear is not None:
            self._schedule_preview_refresh()
        sender = self.sender()
        detail_sliders = (
            getattr(self, "slider_sharpen", None),
            getattr(self, "slider_radius", None),
            getattr(self, "slider_noise_luma", None),
            getattr(self, "slider_noise_color", None),
            getattr(self, "slider_ca_red", None),
            getattr(self, "slider_ca_blue", None),
        )
        if sender in detail_sliders:
            if hasattr(self, "_set_active_named_adjustment_profile_id"):
                self._set_active_named_adjustment_profile_id("detail", "")
            if hasattr(self, "_refresh_named_adjustment_profile_combo"):
                self._refresh_named_adjustment_profile_combo("detail")
            if hasattr(self, "_schedule_detail_adjustment_sidecar_persist"):
                self._schedule_detail_adjustment_sidecar_persist()
        if hasattr(self, "_schedule_mtf_refresh"):
            self._schedule_mtf_refresh(interactive=self._is_preview_interaction_active())

    def _on_slider_release(self) -> None:
        if (
            int(getattr(self, "_suspend_render_adjustment_autosave", 0) or 0) > 0
            or int(getattr(self, "_suspend_detail_adjustment_autosave", 0) or 0) > 0
        ):
            return
        if self._original_linear is not None:
            self._schedule_preview_refresh()
        sender = self.sender()
        render_sliders = (
            getattr(self, "slider_brightness", None),
            getattr(self, "slider_black_point", None),
            getattr(self, "slider_white_point", None),
            getattr(self, "slider_contrast", None),
            getattr(self, "slider_highlights", None),
            getattr(self, "slider_shadows", None),
            getattr(self, "slider_whites", None),
            getattr(self, "slider_blacks", None),
            getattr(self, "slider_midtone", None),
            getattr(self, "slider_vibrance", None),
            getattr(self, "slider_saturation", None),
            getattr(self, "slider_grade_midtones_hue", None),
            getattr(self, "slider_grade_midtones_sat", None),
            getattr(self, "slider_grade_shadows_hue", None),
            getattr(self, "slider_grade_shadows_sat", None),
            getattr(self, "slider_grade_highlights_hue", None),
            getattr(self, "slider_grade_highlights_sat", None),
            getattr(self, "slider_grade_blending", None),
            getattr(self, "slider_grade_balance", None),
            getattr(self, "slider_tone_curve_black", None),
            getattr(self, "slider_tone_curve_white", None),
        )
        detail_sliders = (
            getattr(self, "slider_sharpen", None),
            getattr(self, "slider_radius", None),
            getattr(self, "slider_noise_luma", None),
            getattr(self, "slider_noise_color", None),
            getattr(self, "slider_ca_red", None),
            getattr(self, "slider_ca_blue", None),
        )
        if sender in render_sliders and hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist(immediate=True)
        if sender in detail_sliders and hasattr(self, "_schedule_detail_adjustment_sidecar_persist"):
            self._schedule_detail_adjustment_sidecar_persist(immediate=True)
        if hasattr(self, "_schedule_mtf_refresh"):
            self._schedule_mtf_refresh(interactive=False)

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
            "slider_highlights",
            "slider_shadows",
            "slider_whites",
            "slider_blacks",
            "slider_midtone",
            "slider_vibrance",
            "slider_saturation",
            "slider_grade_midtones_hue",
            "slider_grade_midtones_sat",
            "slider_grade_shadows_hue",
            "slider_grade_shadows_sat",
            "slider_grade_highlights_hue",
            "slider_grade_highlights_sat",
            "slider_grade_blending",
            "slider_grade_balance",
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
        cache_key = (
            id(image),
            tuple(int(v) for v in rgb.shape),
            str(rgb.dtype),
            int(max_side_limit),
        )
        if (
            getattr(self, "_interactive_source_cache_key", None) == cache_key
            and getattr(self, "_interactive_source_cache_image", None) is not None
        ):
            return self._interactive_source_cache_image
        cache_images = getattr(self, "_interactive_source_cache_images", None)
        if isinstance(cache_images, dict):
            cached = cache_images.get(cache_key)
            if cached is not None:
                self._interactive_source_cache_key = cache_key
                self._interactive_source_cache_image = cached
                return cached
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        max_side = max(h, w)
        if max_side <= int(max_side_limit):
            return rgb
        scale = float(max_side_limit) / float(max_side)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        resized = np.clip(
            cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA),
            0.0,
            1.0,
        ).astype(np.float32)
        self._interactive_source_cache_key = cache_key
        self._interactive_source_cache_image = resized
        if isinstance(cache_images, dict):
            cache_images[cache_key] = resized
            while len(cache_images) > 4:
                cache_images.pop(next(iter(cache_images)))
        return resized

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
        tone_channel_points = render_state.get("tone_curve_channel_points")
        channel_sig_parts: list[str] = []
        if isinstance(tone_channel_points, dict):
            for channel in ("luminance", "red", "green", "blue"):
                points = tone_channel_points.get(channel) or []
                channel_points = normalize_tone_curve_points(
                    [
                        (p[0], p[1])
                        for p in points
                        if isinstance(p, (list, tuple)) and len(p) >= 2
                    ]
                )
                channel_sig_parts.append(
                    channel
                    + "="
                    + ",".join(f"{float(x):.4f}:{float(y):.4f}" for x, y in channel_points)
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
                f"hi={float(render_state.get('highlights', 0.0)):.3f}",
                f"shd={float(render_state.get('shadows', 0.0)):.3f}",
                f"wh={float(render_state.get('whites', 0.0)):.3f}",
                f"bl={float(render_state.get('blacks', 0.0)):.3f}",
                f"mt={float(render_state.get('midtone', 1.0)):.3f}",
                f"vib={float(render_state.get('vibrance', 0.0)):.3f}",
                f"sat={float(render_state.get('saturation', 0.0)):.3f}",
                f"gsh={float(render_state.get('grade_shadows_hue', 240.0)):.2f}:{float(render_state.get('grade_shadows_saturation', 0.0)):.3f}",
                f"gmi={float(render_state.get('grade_midtones_hue', 45.0)):.2f}:{float(render_state.get('grade_midtones_saturation', 0.0)):.3f}",
                f"ghi={float(render_state.get('grade_highlights_hue', 50.0)):.2f}:{float(render_state.get('grade_highlights_saturation', 0.0)):.3f}",
                f"gbl={float(render_state.get('grade_blending', 0.5)):.3f}",
                f"gba={float(render_state.get('grade_balance', 0.0)):.3f}",
                f"te={int(bool(render_state.get('tone_curve_enabled', False)))}",
                f"tb={float(render_state.get('tone_curve_black_point', 0.0)):.4f}",
                f"tw={float(render_state.get('tone_curve_white_point', 1.0)):.4f}",
                f"tp={tone_sig}",
                f"tc={render_state.get('tone_curve_channel', 'luminance')}",
                f"tcp={';'.join(channel_sig_parts)}",
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
        scale = self._viewer_display_scale()
        if (
            bool(getattr(self, "_viewer_full_detail_requested", False))
            or (scale is not None and float(scale) >= 0.98)
        ):
            return 0
        return int(PREVIEW_PROFILE_APPLY_MAX_SIDE)

    def _final_adjustment_preview_max_side(self) -> int:
        effective = int(self._effective_preview_max_side())
        if effective <= 0 or bool(getattr(self, "_viewer_full_detail_requested", False)):
            return effective
        compare_enabled = bool(getattr(self, "chk_compare", None) and self.chk_compare.isChecked())
        if compare_enabled or bool(getattr(self, "_manual_chart_marking_after_reload", False)):
            return effective
        return int(min(effective, PREVIEW_FINAL_ADJUSTMENT_MAX_SIDE))

    def _interactive_preview_timeout_ms(self, *, source_linear: np.ndarray, max_side_limit: int) -> int:
        try:
            pixels = int(source_linear.shape[0]) * int(source_linear.shape[1])
        except Exception:
            pixels = 0
        if int(max_side_limit) <= 0 or pixels > 20_000_000:
            return 90_000
        if pixels > 8_000_000:
            return 30_000
        return int(PREVIEW_INTERACTIVE_STUCK_TIMEOUT_MS)

    def _tone_curve_histogram_render_kwargs(self, render_kwargs: dict[str, Any]) -> dict[str, Any]:
        return dict(render_kwargs)

    def _tone_curve_points_signature(self, points: Any) -> str:
        if not isinstance(points, (list, tuple)):
            return ""
        normalized = normalize_tone_curve_points(
            [
                (point[0], point[1])
                for point in points
                if isinstance(point, (list, tuple)) and len(point) >= 2
            ]
        )
        return ",".join(f"{float(x):.4f}:{float(y):.4f}" for x, y in normalized)

    def _tone_curve_channel_points_signature(self, channel_points: Any) -> str:
        if not isinstance(channel_points, dict):
            return ""
        parts: list[str] = []
        for channel in ("luminance", "red", "green", "blue"):
            parts.append(f"{channel}={self._tone_curve_points_signature(channel_points.get(channel))}")
        return ";".join(parts)

    def _tone_curve_histogram_signature(self, source_key: str, render_kwargs: dict[str, Any]) -> str:
        return "|".join(
            [
                str(source_key),
                f"channel={self._tone_curve_channel_key()}",
                f"tk={float(render_kwargs.get('temperature_kelvin', 5003.0)):.3f}",
                f"tint={float(render_kwargs.get('tint', 0.0)):.3f}",
                f"bright={float(render_kwargs.get('brightness_ev', 0.0)):.4f}",
                f"black={float(render_kwargs.get('black_point', 0.0)):.4f}",
                f"white={float(render_kwargs.get('white_point', 1.0)):.4f}",
                f"contrast={float(render_kwargs.get('contrast', 0.0)):.4f}",
                f"highlights={float(render_kwargs.get('highlights', 0.0)):.4f}",
                f"shadows={float(render_kwargs.get('shadows', 0.0)):.4f}",
                f"whites={float(render_kwargs.get('whites', 0.0)):.4f}",
                f"blacks={float(render_kwargs.get('blacks', 0.0)):.4f}",
                f"midtone={float(render_kwargs.get('midtone', 1.0)):.4f}",
                f"vibrance={float(render_kwargs.get('vibrance', 0.0)):.4f}",
                f"saturation={float(render_kwargs.get('saturation', 0.0)):.4f}",
                f"grade_shadows={float(render_kwargs.get('grade_shadows_hue', 240.0)):.2f}:{float(render_kwargs.get('grade_shadows_saturation', 0.0)):.4f}",
                f"grade_midtones={float(render_kwargs.get('grade_midtones_hue', 45.0)):.2f}:{float(render_kwargs.get('grade_midtones_saturation', 0.0)):.4f}",
                f"grade_highlights={float(render_kwargs.get('grade_highlights_hue', 50.0)):.2f}:{float(render_kwargs.get('grade_highlights_saturation', 0.0)):.4f}",
                f"grade_blending={float(render_kwargs.get('grade_blending', 0.5)):.4f}",
                f"grade_balance={float(render_kwargs.get('grade_balance', 0.0)):.4f}",
                f"curve_black={float(render_kwargs.get('tone_curve_black_point', 0.0)):.4f}",
                f"curve_white={float(render_kwargs.get('tone_curve_white_point', 1.0)):.4f}",
                f"curve={self._tone_curve_points_signature(render_kwargs.get('tone_curve_points'))}",
                f"channel_curves={self._tone_curve_channel_points_signature(render_kwargs.get('tone_curve_channel_points'))}",
            ]
        )

    def _update_tone_curve_histogram(
        self,
        source: np.ndarray,
        render_kwargs: dict[str, Any],
        *,
        source_key: str,
        force: bool = False,
    ) -> None:
        if not hasattr(self, "tone_curve_editor"):
            return
        key = self._tone_curve_histogram_signature(source_key, render_kwargs)
        if not force and self._tone_curve_histogram_key == key:
            return
        try:
            histogram_source = apply_render_adjustments(
                np.asarray(source, dtype=np.float32),
                **self._tone_curve_histogram_render_kwargs(render_kwargs),
            )
            self.tone_curve_editor.set_histogram_from_image(
                histogram_source,
                channel=self._tone_curve_channel_key(),
            )
            self._tone_curve_histogram_key = key
        except Exception as exc:
            self._tone_curve_histogram_key = None
            self._log_preview(f"Aviso: no se pudo actualizar histograma de curva: {exc}")

    def _tone_curve_histogram_enabled(self) -> bool:
        checkbox = getattr(self, "check_tone_curve_enabled", None)
        return bool(checkbox is not None and checkbox.isChecked() and hasattr(self, "tone_curve_editor"))

    def _tone_curve_histogram_interaction_active(self) -> bool:
        if not self._tone_curve_histogram_enabled():
            return False
        editor = getattr(self, "tone_curve_editor", None)
        if editor is not None and bool(editor.is_dragging()):
            return True
        for name in ("slider_tone_curve_black", "slider_tone_curve_white"):
            slider = getattr(self, name, None)
            if slider is not None and bool(slider.isSliderDown()):
                return True
        return False

    def _update_tone_curve_histogram_for_current_controls(
        self,
        *,
        max_side_limit: int = PREVIEW_INTERACTIVE_TONAL_MAX_SIDE,
        force: bool = False,
    ) -> None:
        if self._original_linear is None:
            return
        if not force and not self._tone_curve_histogram_enabled():
            return
        source_key = self._last_loaded_preview_key or str(id(self._original_linear))
        source = self._interactive_preview_source(
            self._original_linear,
            max_side_limit=int(max_side_limit),
        )
        self._update_tone_curve_histogram(
            source,
            self._render_adjustment_kwargs(),
            source_key=source_key,
            force=force,
        )

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

    def _source_profile_for_preview_recipe(self, recipe: Recipe) -> Path | None:
        profile_path = self._active_session_icc_for_settings()
        if profile_path is not None:
            return profile_path
        if not is_generic_output_space(recipe.output_space):
            return None
        try:
            return ensure_generic_output_profile(
                recipe.output_space,
                directory=self._session_generic_profile_dir(),
            )
        except Exception as exc:
            key = f"generic-preview-profile|{recipe.output_space}|{exc}"
            if self._profile_preview_error_key != key:
                self._profile_preview_error_key = key
                self._log_preview(f"Aviso: perfil ICC estandar no disponible para preview directa: {exc}")
            return None

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
            bool,
            str,
            Path | None,
            Path | None,
        ],
    ) -> None:
        (
            request_key,
            _source_key,
            _source_linear,
            _detail_kwargs,
            _render_kwargs,
            _compare_enabled,
            _bypass,
            _max_side_limit,
            _apply_detail,
            _include_analysis,
            _output_space,
            _source_profile,
            _monitor_profile,
        ) = request
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
            bool,
            str,
            Path | None,
            Path | None,
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
            include_analysis,
            output_space,
            source_profile,
            monitor_profile,
        ) = request
        self._interactive_preview_task_token = int(getattr(self, "_interactive_preview_task_token", 0)) + 1
        task_token = int(self._interactive_preview_task_token)

        def task():
            warnings: list[str] = []

            def srgb_display_u8(image_srgb: np.ndarray) -> np.ndarray:
                try:
                    return srgb_to_display_u8(image_srgb, monitor_profile)
                except Exception as exc:
                    warnings.append(
                        f"Aviso: gestion ICC de monitor no disponible en preview; se usa sRGB: {exc}"
                    )
                    return srgb_to_display_u8(image_srgb, None)

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
            if source_profile is not None:
                try:
                    result_srgb = (
                        profiled_float_to_display_u8(adjusted, source_profile, None).astype(np.float32) / 255.0
                    )
                except Exception as exc:
                    warnings.append(f"Aviso: no se pudo convertir preview ICC a sRGB tecnico: {exc}")
                    result_srgb = standard_profile_to_srgb_display(adjusted, output_space)
                try:
                    display_u8 = profiled_float_to_display_u8(adjusted, source_profile, monitor_profile)
                except Exception as exc:
                    warnings.append(f"Aviso: no se pudo convertir preview ICC directa a monitor; se usa fallback sRGB: {exc}")
                    display_u8 = srgb_display_u8(result_srgb)
            else:
                result_srgb = standard_profile_to_srgb_display(adjusted, output_space)
                display_u8 = srgb_display_u8(result_srgb)
            analysis_text = preview_analysis_text(source, adjusted) if include_analysis else None
            return (
                request_key,
                source_key,
                np.asarray(result_srgb, dtype=np.float32),
                np.asarray(display_u8, dtype=np.uint8),
                bool(compare_enabled),
                bool(bypass_display_profile),
                analysis_text,
                "; ".join(dict.fromkeys(warnings)) if warnings else None,
            )

        thread = TaskThread(task)
        started_at = time.perf_counter()
        self._interactive_preview_task_active = True
        self._interactive_preview_inflight_key = request_key
        self._set_interactive_preview_busy(True)
        self._threads.append(thread)

        def cleanup() -> None:
            stale = (
                int(getattr(self, "_interactive_preview_task_token", 0)) != task_token
                or self._interactive_preview_inflight_key != request_key
            )
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
            if stale:
                return
            self._interactive_preview_task_active = False
            self._interactive_preview_inflight_key = None
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
                    display_u8,
                    payload_compare_enabled,
                    payload_bypass_display_profile,
                    analysis_text,
                    warning,
                ) = payload
                applied = False
                if key != self._interactive_preview_expected_key:
                    return
                if payload_source_key is not None and payload_source_key != self._last_loaded_preview_key:
                    return
                self._preview_srgb = np.asarray(candidate, dtype=np.float32)
                self._set_result_display_u8(
                    display_u8,
                    compare_enabled=bool(payload_compare_enabled and self.chk_compare.isChecked()),
                )
                applied = True
                if applied:
                    if warning:
                        key_warning = f"interactive-preview-profile|{warning}"
                        if self._profile_preview_error_key != key_warning:
                            self._profile_preview_error_key = key_warning
                            self._log_preview(warning)
                    if isinstance(analysis_text, str) and hasattr(self, "preview_analysis"):
                        self.preview_analysis.setPlainText(analysis_text)
                    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                    self._interactive_preview_last_ms = float(max(elapsed_ms, 0.0))
                    self._update_interactive_preview_time_label()
            finally:
                cleanup()

        def fail(trace: str) -> None:
            line = trace.strip().splitlines()[-1] if trace.strip() else "error desconocido"
            key = f"interactive-preview-failed|{request_key}|{line}"
            if self._profile_preview_error_key != key:
                self._profile_preview_error_key = key
                self._log_preview(f"Aviso: fallo en preview interactiva; se conserva la ultima vista: {line}")
                self._set_status(self.tr("Preview interactiva fallida; puedes seguir ajustando."))
            cleanup()

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()
        QtCore.QTimer.singleShot(
            self._interactive_preview_timeout_ms(
                source_linear=source_linear,
                max_side_limit=int(max_side_limit),
            ),
            lambda: self._abandon_stuck_interactive_preview(task_token, request_key),
        )

    def _abandon_stuck_interactive_preview(self, task_token: int, request_key: str) -> None:
        if not bool(getattr(self, "_interactive_preview_task_active", False)):
            return
        if int(getattr(self, "_interactive_preview_task_token", 0)) != int(task_token):
            return
        if getattr(self, "_interactive_preview_inflight_key", None) != request_key:
            return
        self._interactive_preview_task_token = int(getattr(self, "_interactive_preview_task_token", 0)) + 1
        self._interactive_preview_task_active = False
        self._interactive_preview_inflight_key = None
        pending = self._interactive_preview_pending_request
        self._interactive_preview_pending_request = None
        self._log_preview("Aviso: preview interactiva cancelada por tiempo de espera; se reanuda la cola de ajustes.")
        if pending is not None:
            self._start_interactive_preview_task(pending)
        else:
            self._interactive_preview_expected_key = None
            self._set_interactive_preview_busy(False)

    def _reset_adjustments(self) -> None:
        self.slider_sharpen.setValue(0)
        self.slider_radius.setValue(10)
        self.slider_noise_luma.setValue(0)
        self.slider_noise_color.setValue(0)
        self.slider_ca_red.setValue(0)
        self.slider_ca_blue.setValue(0)
        if self._original_linear is not None:
            self._refresh_preview()
        if hasattr(self, "_schedule_detail_adjustment_sidecar_persist"):
            self._schedule_detail_adjustment_sidecar_persist(immediate=True)

    def _refresh_preview(self) -> None:
        if self._original_linear is None:
            return
        self._preview_refresh_timer.stop()
        try:
            recipe = self._build_effective_recipe()
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

            compare_enabled = bool(self.chk_compare.isChecked())
            if compare_enabled:
                self._ensure_original_compare_panel(bypass_profile=bypass_display_profile)

            source_key = self._last_loaded_preview_key or str(id(self._original_linear))
            source_profile = self._source_profile_for_preview_recipe(recipe)
            monitor_profile = None if bypass_display_profile else self._active_display_profile_path()
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
                if self._tone_curve_histogram_interaction_active():
                    self._update_tone_curve_histogram_for_current_controls(
                        max_side_limit=int(max_side_limit),
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
                        False,
                        str(recipe.output_space),
                        source_profile,
                        monitor_profile,
                    )
                )
                return

            self._interactive_preview_expected_key = None
            self._interactive_preview_pending_request = None
            self._set_interactive_preview_busy(False)

            if self._should_async_final_preview():
                self._update_tone_curve_histogram_for_current_controls(
                    max_side_limit=PREVIEW_INTERACTIVE_TONAL_MAX_SIDE,
                )
                self._interactive_preview_request_seq += 1
                request_key = f"{source_key}|final|{self._interactive_preview_request_seq}"
                self._queue_interactive_preview_request(
                    (
                        request_key,
                        source_key,
                        self._original_linear,
                        detail_kwargs,
                        render_kwargs,
                        compare_enabled,
                        False,
                        int(self._final_adjustment_preview_max_side()),
                        True,
                        True,
                        str(recipe.output_space),
                        source_profile,
                        self._active_display_profile_path(),
                    )
                )
                return

            preview_source = self._interactive_preview_source(
                self._original_linear,
                max_side_limit=int(self._final_adjustment_preview_max_side()),
            )
            self._update_tone_curve_histogram_for_current_controls(
                max_side_limit=PREVIEW_INTERACTIVE_TONAL_MAX_SIDE,
            )
            detail_adjusted = self._detail_adjusted_preview(
                preview_source,
                denoise_luma=nl,
                denoise_color=nc,
                sharpen_amount=sharpen,
                sharpen_radius=radius,
                lateral_ca_red_scale=ca_red,
                lateral_ca_blue_scale=ca_blue,
            )
            adjusted = apply_render_adjustments(detail_adjusted, **render_kwargs)
            self._adjusted_linear = adjusted
            active_session_profile = self._active_session_icc_for_settings()
            raw_profile_text = self.path_profile_active.text().strip() if hasattr(self, "path_profile_active") else ""

            result_srgb = standard_profile_to_srgb_display(adjusted, recipe.output_space)
            if source_profile is not None:
                try:
                    result_srgb = profiled_float_to_display_u8(adjusted, source_profile, None).astype(np.float32) / 255.0
                except Exception as exc:
                    self._log_preview(f"Aviso: no se pudo calcular preview colorimetrica sRGB desde ICC: {exc}")

            if raw_profile_text and active_session_profile is None:
                p = Path(raw_profile_text).expanduser()
                status = self._profile_status_for_path(p) or "no disponible"
                self._log_preview(
                    f"Aviso: perfil ICC no aplicado porque su estado QA es {status}."
                )
                self.path_profile_active.clear()
                if hasattr(self, "chk_apply_profile"):
                    self.chk_apply_profile.setChecked(False)
                self._profile_preview_expected_key = None
            else:
                self._profile_preview_expected_key = None

            self._preview_srgb = np.asarray(result_srgb, dtype=np.float32)
            if source_profile is not None:
                display_u8 = self._profiled_display_u8_for_screen(
                    adjusted,
                    source_profile,
                    bypass_profile=bypass_display_profile,
                )
            else:
                display_u8 = self._display_u8_for_screen(
                    self._preview_srgb,
                    bypass_profile=bypass_display_profile,
                )
            self._set_result_display_u8(display_u8, compare_enabled=compare_enabled)
            self.preview_analysis.setPlainText(preview_analysis_text(preview_source, adjusted))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Aviso"), str(exc))

    def _schedule_preview_refresh(self) -> None:
        if self._original_linear is None:
            return
        if self._is_preview_interaction_active():
            if not self._preview_refresh_timer.isActive():
                self._preview_refresh_timer.start(PREVIEW_REFRESH_THROTTLE_MS)
            return
        self._preview_refresh_timer.start(PREVIEW_REFRESH_DEBOUNCE_MS)

    def _should_async_final_preview(self) -> bool:
        if self._original_linear is None:
            return False
        try:
            pixels = int(self._original_linear.shape[0]) * int(self._original_linear.shape[1])
        except Exception:
            return False
        return pixels > 2_000_000

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
