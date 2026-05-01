from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewLoadMixin:
    def _load_selected_from_timer(self) -> None:
        if self._selected_file is None:
            return
        self._on_load_selected(show_message=False)

    def _preview_load_format_duration(self, seconds: float | None) -> str:
        if seconds is None:
            return "--"
        value = max(0.0, float(seconds))
        if value < 60.0:
            return f"{value:.1f}s"
        minutes = int(value // 60)
        rest = int(round(value - minutes * 60))
        return f"{minutes}m {rest:02d}s"

    def _preview_load_settings_float(self, key: str, default: float) -> float:
        try:
            value = float(self._settings.value(key, default))
        except Exception:
            return float(default)
        return value if np.isfinite(value) and value > 0.0 else float(default)

    def _record_preview_load_timing(self, seconds: float) -> None:
        value = float(seconds)
        if not np.isfinite(value) or value <= 0.0:
            return
        key = "performance/preview_load_seconds_ewma"
        try:
            previous = float(self._settings.value(key, 0.0))
        except Exception:
            previous = 0.0
        averaged = value if previous <= 0.0 else previous * 0.65 + value * 0.35
        try:
            self._settings.setValue(key, float(averaged))
            self._settings.sync()
        except Exception:
            pass

    def _preview_load_estimate_seconds(self, selected: Path, fast_raw: bool, max_preview_side: int) -> float:
        if selected.suffix.lower() not in RAW_EXTENSIONS:
            default = 0.6
        elif int(max_preview_side) <= 0:
            default = 3.0
        elif bool(fast_raw):
            default = 1.2
        else:
            default = 2.0
        return self._preview_load_settings_float("performance/preview_load_seconds_ewma", default)

    def _start_preview_load_progress(self, selected: Path, fast_raw: bool, max_preview_side: int) -> None:
        estimate = self._preview_load_estimate_seconds(selected, fast_raw, max_preview_side)
        self._preview_load_progress_started_at = time.perf_counter()
        self._preview_load_progress_estimated_seconds = float(estimate)
        self._preview_load_progress_label = self.tr("Preview: cargando") + f" {selected.name}"
        self._preview_load_progress_visible = bool(estimate >= 1.0)
        timer = getattr(self, "_preview_load_progress_timer", None)
        if timer is not None and not timer.isActive():
            timer.start()
        self._update_preview_load_progress_status()

    def _update_preview_load_progress_status(self) -> None:
        started = getattr(self, "_preview_load_progress_started_at", None)
        if started is None:
            return
        elapsed = max(0.0, time.perf_counter() - float(started))
        estimate = getattr(self, "_preview_load_progress_estimated_seconds", None)
        if not bool(getattr(self, "_preview_load_progress_visible", False)) and elapsed < 1.0:
            return
        self._preview_load_progress_visible = True
        label = str(getattr(self, "_preview_load_progress_label", "") or self.tr("Preview: cargando"))
        if estimate is not None and float(estimate) > 0.0:
            remaining = max(0.0, float(estimate) - elapsed)
            time_text = (
                self.tr("Transcurrido")
                + f" {self._preview_load_format_duration(elapsed)} | "
                + self.tr("estimado")
                + f" ~{self._preview_load_format_duration(float(estimate))} | "
                + self.tr("restante")
                + f" {self._preview_load_format_duration(remaining)}"
            )
            value = 95 if elapsed > float(estimate) else int(np.clip((elapsed / float(estimate)) * 90.0, 0.0, 90.0))
            self._set_global_operation_progress(
                "preview",
                label,
                time_text=time_text,
                phase_text=self.tr("RAW/archivo: activo | Preview: pendiente | Caché: pendiente"),
                minimum=0,
                maximum=100,
                value=value,
            )
        else:
            self._set_global_operation_progress(
                "preview",
                label,
                time_text=self.tr("Transcurrido") + f" {self._preview_load_format_duration(elapsed)}",
                phase_text=self.tr("RAW/archivo: activo | Preview: pendiente | Caché: pendiente"),
                minimum=0,
                maximum=0,
                value=0,
            )

    def _finish_preview_load_progress(self, *, success: bool, detail: str, elapsed_seconds: float | None = None) -> None:
        timer = getattr(self, "_preview_load_progress_timer", None)
        if timer is not None:
            timer.stop()
        started = getattr(self, "_preview_load_progress_started_at", None)
        elapsed = (
            float(elapsed_seconds)
            if elapsed_seconds is not None
            else (time.perf_counter() - float(started) if started is not None else None)
        )
        visible = bool(getattr(self, "_preview_load_progress_visible", False))
        self._preview_load_progress_started_at = None
        self._preview_load_progress_estimated_seconds = None
        self._preview_load_progress_label = ""
        self._preview_load_progress_visible = False
        if elapsed is not None:
            self._record_preview_load_timing(float(elapsed))
        if visible:
            self._set_global_operation_progress(
                "preview",
                detail,
                time_text=self.tr("Total:") + f" {self._preview_load_format_duration(elapsed)}",
                phase_text=(
                    self.tr("RAW/archivo: listo | Preview: lista | Caché: actualizada")
                    if success
                    else self.tr("RAW/archivo: error | Preview: detenida | Caché: sin actualizar")
                ),
                minimum=0,
                maximum=100,
                value=100 if success else 0,
            )
            QtCore.QTimer.singleShot(1800, lambda: self._reset_global_operation_progress(owner="preview"))

    def _on_load_selected(self, _checked: bool = False, *, show_message: bool = True) -> None:
        if self._selected_file is None:
            self._clear_viewer_histogram()
            if show_message:
                QtWidgets.QMessageBox.information(self, self.tr("Info"), "Selecciona primero un archivo.")
            return

        original_selected = self._selected_file
        selected = self._resolve_existing_browsable_path(original_selected)
        if selected is None:
            self._selection_load_timer.stop()
            self._metadata_timer.stop()
            self._selected_file = None
            self._last_loaded_preview_key = None
            self._clear_manual_chart_points_for_file_change()
            self._clear_mtf_roi_for_file_change()
            self.selected_file_label.setText(self.tr("Sin archivo seleccionado"))
            self._clear_metadata_view()
            self._clear_viewer_histogram()
            self._set_status(self.tr("Archivo no encontrado:") + f" {original_selected}")
            if show_message:
                QtWidgets.QMessageBox.information(self, self.tr("Info"), f"No existe el archivo:\n{original_selected}")
            return
        if self._normalized_path_key(selected) != self._normalized_path_key(original_selected):
            self._selected_file = selected
            self.selected_file_label.setText(str(selected))
        recipe = self._build_effective_recipe()
        max_quality_preview = self._preview_requires_max_quality()
        is_raw = selected.suffix.lower() in RAW_EXTENSIONS
        fast_raw = bool(is_raw and not max_quality_preview)
        if is_raw:
            # Preview policy: always use the most responsive demosaic path.
            # Final render keeps the recipe-selected algorithm (e.g. AMaZE).
            recipe.demosaic_algorithm = self._balanced_preview_demosaic()
        max_preview_side = self._effective_preview_max_side()
        base_signature = self._preview_base_signature(
            selected=selected,
            recipe=recipe,
        )
        cache_key = self._preview_cache_key(
            selected=selected,
            recipe=recipe,
            fast_raw=fast_raw,
            max_preview_side=max_preview_side,
        )

        if (
            self._original_linear is not None
            and self._loaded_preview_base_signature == base_signature
            and self._last_loaded_preview_key is not None
        ):
            current_side = int(max(self._original_linear.shape[0], self._original_linear.shape[1]))
            loaded_fast_raw = bool(self._loaded_preview_fast_raw)
            same_or_higher_quality = (
                (max_preview_side <= 0 and not loaded_fast_raw)
                or (max_preview_side > 0 and current_side >= int(max_preview_side))
            )
            # Never downgrade quality/source size implicitly while staying on
            # the same file + processing recipe.
            if (not loaded_fast_raw and fast_raw) or same_or_higher_quality:
                if self._manual_chart_marking_after_reload:
                    self._manual_chart_marking_after_reload = False
                    self._begin_manual_chart_marking()
                if cache_key == self._last_loaded_preview_key:
                    return
                self._refresh_preview()
                return

        if cache_key == self._last_loaded_preview_key and self._original_linear is not None:
            if self._manual_chart_marking_after_reload:
                self._manual_chart_marking_after_reload = False
                self._begin_manual_chart_marking()
            return

        cached = self._cached_preview_image(cache_key, selected=selected)
        if cached is not None:
            self._original_linear = cached.copy()
            self._adjusted_linear = self._original_linear.copy()
            self._last_loaded_preview_key = cache_key
            self._loaded_preview_base_signature = base_signature
            self._loaded_preview_fast_raw = bool(fast_raw)
            self._loaded_preview_source_max_side = int(max(self._original_linear.shape[0], self._original_linear.shape[1]))
            self._clear_adjustment_caches()
            self._clear_mtf_roi_for_file_change()
            self._auto_update_mtf_pixel_pitch_from_file(selected)
            self._refresh_preview()
            self._restore_persisted_mtf_analysis_for_selected(selected)
            self._log_preview(f"Preview cargada desde cache: {selected.name}")
            self._set_status(self.tr("Preview en cache:") + f" {selected.name}")
            if self._manual_chart_marking_after_reload:
                self._manual_chart_marking_after_reload = False
                self._begin_manual_chart_marking()
            return

        recipe_request = Recipe(**asdict(recipe))
        self._queue_preview_load_request((selected, recipe_request, fast_raw, max_preview_side, cache_key))

    def _queue_preview_load_request(
        self,
        request: tuple[Path, Recipe, bool, int, str],
    ) -> None:
        selected, _recipe, _fast_raw, _max_preview_side, cache_key = request
        if self._preview_load_task_active:
            if self._preview_load_inflight_key == cache_key:
                return
            self._preview_load_pending_request = request
            return
        self._preview_load_pending_request = None
        self._start_preview_load_task(request)
        self._set_status(self.tr("Cargando preview:") + f" {selected.name}")

    def _start_preview_load_task(
        self,
        request: tuple[Path, Recipe, bool, int, str],
    ) -> None:
        selected, recipe, fast_raw, max_preview_side, cache_key = request

        def task():
            started = time.perf_counter()
            image_linear, msg = load_image_for_preview(
                selected,
                recipe=recipe,
                fast_raw=fast_raw,
                max_preview_side=max_preview_side,
            )
            return selected, cache_key, image_linear, msg, float(time.perf_counter() - started)

        self._preview_load_task_active = True
        self._preview_load_inflight_key = cache_key
        self._start_preview_load_progress(selected, fast_raw, max_preview_side)
        thread: TaskThread | None = None

        def cleanup() -> None:
            self._preview_load_task_active = False
            self._preview_load_inflight_key = None
            if thread is not None and thread in self._threads:
                self._threads.remove(thread)
            if thread is not None:
                thread.deleteLater()
            pending = self._preview_load_pending_request
            self._preview_load_pending_request = None
            if pending is not None:
                self._start_preview_load_task(pending)

        def ok(payload) -> None:
            try:
                loaded_selected, loaded_key, image_linear, msg, elapsed = payload
                if self._selected_file != loaded_selected:
                    self._finish_preview_load_progress(
                        success=False,
                        detail=self.tr("Preview descartada:") + f" {loaded_selected.name}",
                        elapsed_seconds=elapsed,
                    )
                    return
                self._original_linear = np.asarray(image_linear, dtype=np.float32)
                self._adjusted_linear = self._original_linear.copy()
                self._last_loaded_preview_key = loaded_key
                self._loaded_preview_base_signature = self._preview_base_signature(
                    selected=selected,
                    recipe=recipe,
                )
                self._loaded_preview_fast_raw = bool(fast_raw)
                self._loaded_preview_source_max_side = int(
                    max(self._original_linear.shape[0], self._original_linear.shape[1])
                )
                self._clear_adjustment_caches()
                self._clear_mtf_roi_for_file_change()
                self._auto_update_mtf_pixel_pitch_from_file(loaded_selected)
                self._cache_preview_image(loaded_key, self._original_linear, selected=loaded_selected)
                self._refresh_preview()
                self._restore_persisted_mtf_analysis_for_selected(loaded_selected)
                self._log_preview(msg)
                self._set_status(self.tr("Preview cargada:") + f" {loaded_selected.name}")
                self._finish_preview_load_progress(
                    success=True,
                    detail=self.tr("Preview cargada:") + f" {loaded_selected.name}",
                    elapsed_seconds=elapsed,
                )
                if self._manual_chart_marking_after_reload:
                    self._manual_chart_marking_after_reload = False
                    self._begin_manual_chart_marking()
            finally:
                cleanup()

        def fail(trace: str) -> None:
            try:
                self._log_preview(trace[-1200:])
                if self._selected_file == selected:
                    self._set_status(self.tr("Error de preview:") + f" {selected.name}")
                self._finish_preview_load_progress(
                    success=False,
                    detail=self.tr("Error de preview:") + f" {selected.name}",
                )
            finally:
                cleanup()

        if self._run_preview_load_inline():
            try:
                ok(task())
            except Exception:
                fail(traceback.format_exc())
            return

        thread = TaskThread(task)
        self._threads.append(thread)
        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _on_precache_visible_previews(self, *, full_resolution: bool) -> None:
        files = [p for p in self._file_list_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "No hay RAW visibles para precache.")
            return
        mode_label = "1:1" if full_resolution else "normal"
        reply = QtWidgets.QMessageBox.question(
            self,
            self.tr("Precache de previews"),
            (
                self.tr("Se van a precalcular") + f" {len(files)} " + self.tr("previews RAW en modo") + f" {mode_label}.\n\n"
                + self.tr("Este proceso puede tardar, pero mejora la respuesta posterior.\nContinuar?")
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self._start_precache_visible_previews(files, full_resolution=full_resolution)

    def _start_precache_visible_previews(self, files: list[Path], *, full_resolution: bool) -> None:
        recipe_base = self._build_effective_recipe()
        recipe_base_payload = asdict(recipe_base)
        max_quality_preview = bool(full_resolution or self._preview_requires_max_quality())
        max_preview_side = 0 if full_resolution else int(PREVIEW_AUTO_BASE_MAX_SIDE)
        mode_label = "1:1" if full_resolution else "normal"

        def task():
            built = 0
            skipped = 0
            errors: list[dict[str, str]] = []
            for src in files:
                try:
                    recipe = Recipe(**recipe_base_payload)
                    is_raw = src.suffix.lower() in RAW_EXTENSIONS
                    fast_raw = bool(is_raw and not max_quality_preview)
                    if is_raw:
                        recipe.demosaic_algorithm = self._balanced_preview_demosaic()
                    cache_key = self._preview_cache_key(
                        selected=src,
                        recipe=recipe,
                        fast_raw=fast_raw,
                        max_preview_side=max_preview_side,
                    )
                    if self._read_preview_from_disk_cache(cache_key, selected=src) is not None:
                        skipped += 1
                        continue
                    image_linear, _msg = load_image_for_preview(
                        src,
                        recipe=recipe,
                        fast_raw=fast_raw,
                        max_preview_side=max_preview_side,
                    )
                    self._write_preview_to_disk_cache(
                        cache_key,
                        np.asarray(image_linear, dtype=np.float32),
                        selected=src,
                    )
                    built += 1
                except Exception as exc:
                    errors.append({"source": str(src), "error": str(exc)})
            return {
                "mode": mode_label,
                "total": len(files),
                "built": built,
                "skipped": skipped,
                "errors": errors,
            }

        def on_success(payload) -> None:
            total = int(payload.get("total", 0))
            built = int(payload.get("built", 0))
            skipped = int(payload.get("skipped", 0))
            errors = payload.get("errors", [])
            self._log_preview(
                f"Precache {payload.get('mode', self.tr('normal'))}: "
                f"{built} generadas, {skipped} ya en cache, {len(errors)} errores (total {total})."
            )
            self._set_status(
                f"Precache {payload.get('mode', self.tr('normal'))} completada: "
                f"{built} nuevas, {skipped} reutilizadas."
            )
            if full_resolution and self._selected_file is not None:
                self._last_loaded_preview_key = None
                self._on_load_selected(show_message=False)

        self._start_background_task(
            f"Precache previews RAW ({mode_label})",
            task,
            on_success,
        )
