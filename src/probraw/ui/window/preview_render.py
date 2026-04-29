from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewRenderMixin:
    def _on_slider_change(self) -> None:
        if self._original_linear is not None:
            self._schedule_preview_refresh()

    def _on_slider_release(self) -> None:
        if self._original_linear is not None:
            self._schedule_preview_refresh()

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
            "slider_midtone",
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
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        max_side = max(h, w)
        if max_side <= int(max_side_limit):
            return rgb
        scale = float(max_side_limit) / float(max_side)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        return np.clip(
            cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA),
            0.0,
            1.0,
        ).astype(np.float32)

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
                f"mt={float(render_state.get('midtone', 1.0)):.3f}",
                f"te={int(bool(render_state.get('tone_curve_enabled', False)))}",
                f"tb={float(render_state.get('tone_curve_black_point', 0.0)):.4f}",
                f"tw={float(render_state.get('tone_curve_white_point', 1.0)):.4f}",
                f"tp={tone_sig}",
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
        if self._precision_detail_preview_enabled() or float(self._viewer_zoom) >= 1.0:
            return 0
        return int(PREVIEW_PROFILE_APPLY_MAX_SIDE)

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
        ],
    ) -> None:
        request_key, _source_key, _source_linear, _detail_kwargs, _render_kwargs, _compare_enabled, _bypass, _max_side_limit, _apply_detail, _include_analysis = request
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
        ) = request

        def task():
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
            result_srgb = linear_to_srgb_display(adjusted)
            analysis_text = preview_analysis_text(source, adjusted) if include_analysis else None
            return (
                request_key,
                source_key,
                np.asarray(result_srgb, dtype=np.float32),
                bool(compare_enabled),
                bool(bypass_display_profile),
                analysis_text,
            )

        thread = TaskThread(task)
        started_at = time.perf_counter()
        self._interactive_preview_task_active = True
        self._interactive_preview_inflight_key = request_key
        self._set_interactive_preview_busy(True)
        self._threads.append(thread)

        def cleanup() -> None:
            self._interactive_preview_task_active = False
            self._interactive_preview_inflight_key = None
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
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
                    payload_compare_enabled,
                    payload_bypass_display_profile,
                    analysis_text,
                ) = payload
                applied = False
                if key != self._interactive_preview_expected_key:
                    return
                if payload_source_key is not None and payload_source_key != self._last_loaded_preview_key:
                    return
                self._preview_srgb = np.asarray(candidate, dtype=np.float32)
                display_u8 = self._display_u8_for_screen(
                    self._preview_srgb,
                    bypass_profile=bool(payload_bypass_display_profile),
                )
                self._set_result_display_u8(
                    display_u8,
                    compare_enabled=bool(payload_compare_enabled and self.chk_compare.isChecked()),
                )
                applied = True
                if applied:
                    if isinstance(analysis_text, str) and hasattr(self, "preview_analysis"):
                        self.preview_analysis.setPlainText(analysis_text)
                    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                    self._interactive_preview_last_ms = float(max(elapsed_ms, 0.0))
                    self._update_interactive_preview_time_label()
            finally:
                cleanup()

        def fail(_trace: str) -> None:
            cleanup()

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _reset_adjustments(self) -> None:
        self.slider_sharpen.setValue(0)
        self.slider_radius.setValue(10)
        self.slider_noise_luma.setValue(0)
        self.slider_noise_color.setValue(0)
        self.slider_ca_red.setValue(0)
        self.slider_ca_blue.setValue(0)
        if self._original_linear is not None:
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._original_linear is None:
            return
        self._preview_refresh_timer.stop()
        try:
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
            histogram_key = self._last_loaded_preview_key or str(id(self._original_linear))
            if not interactive and self._tone_curve_histogram_key != histogram_key:
                self.tone_curve_editor.set_histogram_from_image(self._original_linear)
                self._tone_curve_histogram_key = histogram_key

            compare_enabled = bool(self.chk_compare.isChecked())
            if compare_enabled:
                self._ensure_original_compare_panel(bypass_profile=bypass_display_profile)

            source_key = self._last_loaded_preview_key or str(id(self._original_linear))
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
                    )
                )
                return

            self._interactive_preview_expected_key = None
            self._interactive_preview_pending_request = None
            self._set_interactive_preview_busy(False)

            if self._should_async_final_preview():
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
                        int(self._effective_preview_max_side()),
                        True,
                        True,
                    )
                )
                return

            preview_source = self._interactive_preview_source(
                self._original_linear,
                max_side_limit=int(self._effective_preview_max_side()),
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
            result_srgb = linear_to_srgb_display(adjusted)
            should_apply_profile = (
                self.chk_apply_profile.isChecked()
                and self.path_profile_active.text().strip() != ""
            )
            if should_apply_profile:
                p = Path(self.path_profile_active.text().strip())
                if not self._profile_can_be_active(p):
                    status = self._profile_status_for_path(p) or "no disponible"
                    self._log_preview(
                        f"Aviso: perfil ICC no aplicado porque su estado QA es {status}."
                    )
                    self.path_profile_active.clear()
                    self.chk_apply_profile.setChecked(False)
                    self._profile_preview_expected_key = None
                elif p.exists():
                    request_key = self._profile_preview_request_key(p)
                    self._profile_preview_expected_key = request_key
                    cached_profile = self._cached_profile_preview_image(request_key)
                    if cached_profile is not None:
                        result_srgb = cached_profile
                    else:
                        self._queue_profile_preview_request(
                            request_key,
                            p,
                            adjusted,
                            (int(adjusted.shape[0]), int(adjusted.shape[1])),
                        )
                else:
                    self._profile_preview_expected_key = None
                    self._log_preview(
                        f"Aviso: perfil activo no encontrado ({p}). Se muestra vista sin perfil."
                    )
            else:
                self._profile_preview_expected_key = None

            self._preview_srgb = np.asarray(result_srgb, dtype=np.float32)
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
        if bool(getattr(self, "chk_apply_profile", None) and self.chk_apply_profile.isChecked()):
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
