from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class ProfileWorkflowMixin:
    def _use_current_dir_as_profile_charts(self) -> None:
        accepted = self._set_profile_reference_dir(self._current_dir)
        self._selected_chart_files = []
        self._sync_profile_chart_selection_label()
        self._refresh_color_reference_thumbnail_markers()
        if accepted:
            self._set_status(self.tr("Directorio de referencias colorimétricas:") + f" {self._current_dir}")
        self._save_active_session(silent=True)

    def _use_selected_files_as_profile_charts(self) -> None:
        candidates = [
            p for p in self._collect_selected_file_paths()
            if p.suffix.lower() in PROFILE_CHART_EXTENSIONS
        ]
        files, rejected = self._filter_profile_reference_files(candidates)
        if not files:
            if rejected:
                reason = rejected[0][1]
                QtWidgets.QMessageBox.information(
                    self,
                    self.tr("Referencias no válidas"),
                    self.tr("Las referencias colorimétricas deben ser RAW/DNG o TIFFs originales de carta, no")
                    + f" {reason}. " + self.tr("Selecciona las capturas en 01_ORG."),
                )
                fallback = self._preferred_profile_reference_dir()
                if fallback is not None:
                    self.profile_charts_dir.setText(str(fallback))
                self._selected_chart_files = []
                self._sync_profile_chart_selection_label()
                self._refresh_color_reference_thumbnail_markers()
                self._save_active_session(silent=True)
                return
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("Selecciona una o más capturas RAW/DNG/TIFF como referencias colorimétricas."),
            )
            return
        self._selected_chart_files = sorted(set(files), key=lambda p: str(p))
        parents = {p.parent for p in self._selected_chart_files}
        if len(parents) == 1:
            self.profile_charts_dir.setText(str(next(iter(parents))))
        self._sync_profile_chart_selection_label()
        self._refresh_color_reference_thumbnail_markers()
        suffix = ("; " + self.tr("ignoradas") + f" {len(rejected)} " + self.tr("no válidas")) if rejected else ""
        self._set_status(self.tr("Referencias colorimétricas seleccionadas:") + f" {len(self._selected_chart_files)}{suffix}")
        self._save_active_session(silent=True)

    def _sync_profile_chart_selection_label(self) -> None:
        if not hasattr(self, "profile_chart_selection_label"):
            return
        if not self._selected_chart_files:
            self.profile_chart_selection_label.setText(self.tr("Referencias colorimétricas: todas las compatibles de la carpeta indicada"))
            self._refresh_color_reference_thumbnail_markers()
            return
        preview = ", ".join(p.name for p in self._selected_chart_files[:4])
        if len(self._selected_chart_files) > 4:
            preview += f" (+{len(self._selected_chart_files) - 4} más)"
        self.profile_chart_selection_label.setText(
            self.tr("Referencias colorimétricas seleccionadas:") + f" {len(self._selected_chart_files)} - {preview}"
        )
        self._refresh_color_reference_thumbnail_markers()

    def _profile_chart_files_or_none(self) -> list[Path] | None:
        files, rejected = self._filter_profile_reference_files(
            [p for p in self._selected_chart_files if p.suffix.lower() in PROFILE_CHART_EXTENSIONS]
        )
        if rejected:
            self._selected_chart_files = files
            self._sync_profile_chart_selection_label()
        return files if files else None

    def _infer_profile_chart_files(self) -> list[Path] | None:
        files = self._profile_chart_files_or_none()
        if files:
            return files

        selected = [
            p for p in self._collect_selected_file_paths()
            if p.suffix.lower() in PROFILE_CHART_EXTENSIONS
        ]
        selected, rejected = self._filter_profile_reference_files(selected)
        if selected:
            self._selected_chart_files = sorted(set(selected), key=lambda p: str(p))
            self._sync_profile_chart_selection_label()
            parents = {p.parent for p in self._selected_chart_files}
            if len(parents) == 1:
                self.profile_charts_dir.setText(str(next(iter(parents))))
            self._refresh_color_reference_thumbnail_markers()
            self._set_status(self.tr("Referencias colorimétricas tomadas de la selección:") + f" {len(self._selected_chart_files)}")
            return list(self._selected_chart_files)

        if (
            self._selected_file is not None
            and self._selected_file.suffix.lower() in PROFILE_CHART_EXTENSIONS
            and self._profile_reference_rejection_reason(self._selected_file) is None
        ):
            self._selected_chart_files = [self._selected_file]
            self.profile_charts_dir.setText(str(self._selected_file.parent))
            self._sync_profile_chart_selection_label()
            self._refresh_color_reference_thumbnail_markers()
            self._set_status(self.tr("Referencia colorimétrica tomada del archivo cargado:") + f" {self._selected_file.name}")
            return list(self._selected_chart_files)

        if rejected:
            fallback = self._preferred_profile_reference_dir()
            if fallback is not None:
                self.profile_charts_dir.setText(str(fallback))
            self._set_status(self.tr("Se ignoraron referencias colorimétricas no válidas en carpetas operativas."))

        return None

    def _manual_detections_for_profile(self, chart_files: list[Path] | None) -> dict[Path, Any] | None:
        if not self._manual_chart_detections:
            return None
        if chart_files:
            selected_keys = {str(p.expanduser().resolve()) for p in chart_files}
            matches = {
                Path(path): detection
                for path, detection in self._manual_chart_detections.items()
                if path in selected_keys
            }
        else:
            matches = {Path(path): detection for path, detection in self._manual_chart_detections.items()}
        return matches or None

    def _pending_manual_detection_request(self, chart_files: list[Path] | None) -> dict[str, Any] | None:
        if self._selected_file is None or self._original_linear is None or len(self._manual_chart_points) != 4:
            return None

        source = self._selected_file.expanduser().resolve()
        if not self._manual_chart_points_match_selected_file():
            return None
        if chart_files:
            selected = {str(p.expanduser().resolve()) for p in chart_files}
            if str(source) not in selected:
                return None

        if str(source) in self._manual_chart_detections:
            return None

        preview_h, preview_w = self._manual_chart_point_space_shape()
        return {
            "source": source,
            "points_preview": list(self._manual_chart_points),
            "preview_shape": (int(preview_h), int(preview_w)),
        }

    def _manual_chart_point_space_shape(self) -> tuple[int, int]:
        panels = []
        if self._compare_view_active() and hasattr(self, "image_result_compare"):
            panels.append(self.image_result_compare)
        if hasattr(self, "image_result_single"):
            panels.append(self.image_result_single)
        if hasattr(self, "image_result_compare"):
            panels.append(self.image_result_compare)
        for panel in panels:
            size = panel.image_size()
            if size is None:
                continue
            width, height = size
            if width > 0 and height > 0:
                return int(height), int(width)
        if self._preview_srgb is not None:
            return int(self._preview_srgb.shape[0]), int(self._preview_srgb.shape[1])
        if self._adjusted_linear is not None:
            return int(self._adjusted_linear.shape[0]), int(self._adjusted_linear.shape[1])
        return int(self._original_linear.shape[0]), int(self._original_linear.shape[1])

    def _build_pending_manual_detection(
        self,
        request: dict[str, Any],
        *,
        recipe: Recipe,
        chart_type: str,
        workdir: Path,
    ) -> tuple[Path, Any]:
        source = Path(str(request["source"])).expanduser().resolve()
        points_preview = [(float(x), float(y)) for x, y in request["points_preview"]]
        preview_h, preview_w = request["preview_shape"]

        manual_dir = workdir / "manual_detections"
        manual_dir.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() in RAW_EXTENSIONS:
            target_image = manual_dir / f"{source.stem}.manual_for_profile.tiff"
            full_image = develop_image_array(source, recipe)
            write_tiff16(target_image, full_image)
        else:
            target_image = source
            full_image = read_image(target_image)

        full_h, full_w = full_image.shape[:2]
        sx = full_w / max(1, int(preview_w))
        sy = full_h / max(1, int(preview_h))
        corners = [(x * sx, y * sy) for x, y in points_preview]
        detection = detect_chart_from_corners_array(full_image, corners=corners, chart_type=chart_type)

        detection_path = manual_dir / f"{source.stem}.manual_for_profile.json"
        overlay_path = manual_dir / f"{source.stem}.manual_for_profile.overlay.png"
        write_json(detection_path, detection)
        draw_detection_overlay_array(full_image, detection, overlay_path)
        return source, detection

    def _directory_has_chart_captures(self, folder: Path) -> bool:
        try:
            return folder.exists() and folder.is_dir() and any(
                p.is_file() and p.suffix.lower() in PROFILE_CHART_EXTENSIONS
                for p in folder.iterdir()
            )
        except Exception:
            return False

    def _raw_files_for_chart_profile_assignment(
        self,
        charts: Path,
        chart_capture_files: list[Path] | None,
    ) -> list[Path]:
        candidates = list(chart_capture_files or [])
        if not candidates:
            try:
                candidates = [
                    p for p in sorted(charts.iterdir())
                    if p.is_file() and p.suffix.lower() in PROFILE_CHART_EXTENSIONS
                ]
            except Exception:
                candidates = []
        return [p for p in candidates if p.suffix.lower() in RAW_EXTENSIONS and p.exists()]

    def _use_current_dir_as_batch_input(self) -> None:
        self.batch_input_dir.setText(str(self._current_dir))
        self._set_status(self.tr("Directorio lote:") + f" {self._current_dir}")
        self._save_active_session(silent=True)

    def _on_generate_profile(self) -> None:
        self._ensure_session_output_controls()
        charts = Path(self.profile_charts_dir.text().strip())
        chart_capture_files = self._infer_profile_chart_files()
        if chart_capture_files is None:
            reason = self._profile_reference_rejection_reason(charts)
            if reason is not None:
                fallback = self._preferred_profile_reference_dir()
                if fallback is not None:
                    charts = fallback
                    self.profile_charts_dir.setText(str(charts))
                    self._set_status(
                        f"No se usan {reason} como referencias colorimétricas; se usa {charts}"
                    )
                else:
                    QtWidgets.QMessageBox.information(
                        self,
                        self.tr("Referencias no válidas"),
                        self.tr("La generación de perfil no puede usar carpetas operativas de la sesión")
                        + f" ({reason}). " + self.tr("Selecciona capturas RAW/DNG originales en 01_ORG."),
                    )
                    return
        if chart_capture_files is None and not self._directory_has_chart_captures(charts):
            if (
                self._profile_reference_rejection_reason(self._current_dir) is None
                and self._directory_has_chart_captures(self._current_dir)
            ):
                charts = self._current_dir
                self.profile_charts_dir.setText(str(charts))
            else:
                QtWidgets.QMessageBox.information(
                    self,
                    self.tr("Sin capturas de carta"),
                    self.tr("Selecciona una o mas miniaturas con carta, carga una carta en el visor o abre una carpeta con capturas RAW/DNG/TIFF."),
                )
                return
        manual_detections = self._manual_detections_for_profile(chart_capture_files)
        pending_manual_detection = self._pending_manual_detection_request(chart_capture_files)
        reference_path = Path(self.path_reference.text().strip())
        profile_out = Path(self.profile_out_path_edit.text().strip())
        ext = self.combo_profile_format.currentText().strip().lower() or ".icc"
        if profile_out.suffix.lower() != ext:
            profile_out = profile_out.with_suffix(ext)
            self.profile_out_path_edit.setText(str(profile_out))
        profile_report = Path(self.profile_report_out.text().strip())
        workdir = Path(self.profile_workdir.text().strip())
        development_profile_out = Path(self.develop_profile_out.text().strip())
        calibrated_recipe_out = Path(self.calibrated_recipe_out.text().strip())
        validation_report_out = profile_report.with_name("qa_session_report.json")
        validation_holdout_count = 1 if self._profile_chart_candidate_count(charts, chart_capture_files) >= 2 else 0
        chart_type = self.profile_chart_type.currentText()
        min_confidence = float(self.profile_min_conf.value())
        allow_fallback_detection = bool(self.profile_allow_fallback.isChecked())
        camera = self.profile_camera.text().strip() or None
        lens = self.profile_lens.text().strip() or None
        recipe = self._build_effective_recipe()

        # Sync profile output path with RAW tab profile controls.
        self.path_profile_out.setText(str(profile_out))

        def task():
            task_manual_detections = dict(manual_detections or {})
            if pending_manual_detection is not None:
                source, detection = self._build_pending_manual_detection(
                    pending_manual_detection,
                    recipe=recipe,
                    chart_type=chart_type,
                    workdir=workdir,
                )
                task_manual_detections[source] = detection

            reference = ReferenceCatalog.from_path(reference_path)
            return auto_generate_profile_from_charts(
                chart_captures_dir=charts,
                chart_capture_files=chart_capture_files,
                recipe=recipe,
                reference=reference,
                profile_out=profile_out,
                profile_report_out=profile_report,
                validation_report_out=validation_report_out,
                work_dir=workdir,
                development_profile_out=development_profile_out,
                calibrated_recipe_out=calibrated_recipe_out,
                calibrate_development=True,
                chart_type=chart_type,
                min_confidence=min_confidence,
                allow_fallback_detection=allow_fallback_detection,
                camera_model=camera,
                lens_model=lens,
                manual_detections=task_manual_detections or None,
                validation_holdout_count=validation_holdout_count,
            )

        def on_success(payload) -> None:
            self.profile_output.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
            normalizations = payload.get("recipe_profiling_normalizations")
            if isinstance(normalizations, list) and normalizations:
                summary = ", ".join(
                    f"{c.get('field')}: {c.get('from')} -> {c.get('to')}"
                    for c in normalizations
                    if isinstance(c, dict)
                )
                self._log_preview(f"Receta normalizada para perfilado cientifico: {summary}")
            profile_status = payload.get("profile_status") if isinstance(payload.get("profile_status"), dict) else {}
            status = str(profile_status.get("status") or "draft")
            if status == "validated":
                self.path_profile_active.setText(str(profile_out))
                self.chk_apply_profile.setChecked(True)
            else:
                self.path_profile_active.clear()
                self.chk_apply_profile.setChecked(False)
                if status == "draft":
                    reasons = profile_status.get("reasons") if isinstance(profile_status.get("reasons"), list) else []
                    detail = f" ({', '.join(str(r) for r in reasons[:3])})" if reasons else ""
                    self._log_preview(f"Perfil generado en estado draft{detail}; no se activa automaticamente.")
                else:
                    self._log_preview(f"Perfil no activado por estado: {status}")
            if payload.get("calibrated_recipe_path"):
                calibrated_recipe_path = Path(str(payload["calibrated_recipe_path"]))
                self.path_recipe.setText(str(calibrated_recipe_path))
                try:
                    self._apply_recipe_to_controls(load_recipe(calibrated_recipe_path))
                    self._invalidate_preview_cache()
                    QtCore.QTimer.singleShot(0, lambda: self._on_load_selected(show_message=False))
                except Exception as exc:
                    self._log_preview(f"No se pudo cargar receta calibrada en la GUI: {exc}")
            if payload.get("development_profile_path") and payload.get("calibrated_recipe_path"):
                chart_profile_name = f"{self.session_name_edit.text().strip() or profile_out.stem} - carta"
                profile_id = self._register_chart_development_profile(
                    name=chart_profile_name,
                    development_profile_path=Path(str(payload["development_profile_path"])),
                    calibrated_recipe_path=Path(str(payload["calibrated_recipe_path"])),
                    icc_profile_path=profile_out,
                    profile_report_path=profile_report,
                )
                assigned = self._assign_development_profile_to_raw_files(
                    profile_id,
                    self._raw_files_for_chart_profile_assignment(charts, chart_capture_files),
                    status="assigned",
                )
                if assigned:
                    self._log_preview(f"Perfil de ajuste avanzado asignado a {assigned} RAW de carta")
            if hasattr(self, "profile_summary_label"):
                self.profile_summary_label.setText(self._profile_success_summary(payload, profile_out))
            self._log_preview(f"Perfil de ajuste avanzado: {payload.get('development_profile_path')}")
            self._log_preview(f"Perfil ICC de entrada generado: {profile_out}")
            self._set_status(self.tr("Perfil avanzado con carta + ICC de entrada generado:") + f" {profile_out}")
            self._save_active_session(silent=True)

        self._start_background_task(self.tr("Generacion de perfil avanzado con carta + ICC"), task, on_success)

    def _profile_chart_candidate_count(self, charts: Path, chart_capture_files: list[Path] | None) -> int:
        if chart_capture_files is not None:
            return len(chart_capture_files)
        try:
            return sum(
                1
                for p in charts.iterdir()
                if p.is_file() and p.suffix.lower() in PROFILE_CHART_EXTENSIONS
            )
        except Exception:
            return 0

    def _profile_success_summary(self, payload: dict[str, Any], profile_out: Path) -> str:
        profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
        error_summary = profile.get("error_summary") if isinstance(profile.get("error_summary"), dict) else {}
        de00 = error_summary.get("mean_delta_e2000")
        max_de00 = error_summary.get("max_delta_e2000")
        profile_status = payload.get("profile_status") if isinstance(payload.get("profile_status"), dict) else {}
        status = str(profile_status.get("status") or "draft")
        parts = [
            f"Estado perfil: {status}",
            f"ICC de entrada generado: {profile_out}",
            f"Entrenamiento: {payload.get('chart_captures_used', 0)}/{payload.get('training_captures_total', payload.get('chart_captures_total', 0))}",
            f"Receta calibrada: {payload.get('calibrated_recipe_path') or 'no generada'}",
        ]
        if isinstance(de00, (int, float)) and isinstance(max_de00, (int, float)):
            parts.append(f"DeltaE2000 entrenamiento: media {float(de00):.2f}, max {float(max_de00):.2f}")
        validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else None
        if validation:
            qa = validation.get("qa_report") if isinstance(validation.get("qa_report"), dict) else {}
            v_error = qa.get("validation_error_summary") if isinstance(qa.get("validation_error_summary"), dict) else {}
            status = qa.get("status", "sin_estado")
            parts.append(
                f"Validación: {validation.get('validation_captures_used', 0)}/"
                f"{validation.get('validation_captures_total', 0)} ({status})"
            )
            mean_val = v_error.get("mean_delta_e2000")
            max_val = v_error.get("max_delta_e2000")
            if isinstance(mean_val, (int, float)) and isinstance(max_val, (int, float)):
                parts.append(f"DeltaE2000 validación: media {float(mean_val):.2f}, max {float(max_val):.2f}")
            checks = qa.get("checks") if isinstance(qa.get("checks"), list) else []
            failed_warnings = [
                str(check.get("id"))
                for check in checks
                if isinstance(check, dict)
                and check.get("severity") == "warning"
                and check.get("passed") is False
            ]
            if failed_warnings:
                parts.append(f"QA captura: {len(failed_warnings)} avisos ({', '.join(failed_warnings[:3])})")
        skipped = payload.get("chart_captures_skipped")
        if isinstance(skipped, list) and skipped:
            parts.append(f"Avisos/omisiones: {len(skipped)}")
        return "\n".join(parts)

    def _start_manual_chart_marking(self) -> None:
        if self._original_linear is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Carga primero la captura de carta en el visor."))
            return
        if self._selected_file is None or self._selected_file.suffix.lower() not in PROFILE_CHART_EXTENSIONS:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Referencia no compatible"),
                self.tr("El marcado manual para perfilado cientifico solo acepta RAW/DNG/TIFF."),
            )
            return
        self._begin_manual_chart_marking()

    def _begin_manual_chart_marking(self) -> None:
        if self._original_linear is None:
            return
        self._set_neutral_picker_active(False)
        self._manual_chart_marking = True
        self._manual_chart_points = []
        self._manual_chart_points_source = self._selected_file.expanduser().resolve(strict=False) if self._selected_file else None
        self._update_viewer_interaction_cursor()
        self._sync_manual_chart_overlay()
        self._set_status(self.tr("Marcado manual activo sobre preview de revelado: selecciona 4 esquinas en el visor"))

    def _clear_manual_chart_points(self) -> None:
        self._manual_chart_marking = False
        self._manual_chart_points = []
        self._manual_chart_points_source = None
        self._update_viewer_interaction_cursor()
        self._sync_manual_chart_overlay()
        self._set_status(self.tr("Marcado manual limpiado"))

    def _clear_manual_chart_points_for_file_change(self) -> None:
        if not self._manual_chart_points and not self._manual_chart_marking and self._manual_chart_points_source is None:
            return
        self._manual_chart_marking = False
        self._manual_chart_marking_after_reload = False
        self._manual_chart_points = []
        self._manual_chart_points_source = None
        self._update_viewer_interaction_cursor()
        self._sync_manual_chart_overlay()

    def _manual_chart_points_match_selected_file(self) -> bool:
        if not self._manual_chart_points:
            return True
        if self._selected_file is None or self._manual_chart_points_source is None:
            return False
        return self._normalized_path_key(self._manual_chart_points_source) == self._normalized_path_key(self._selected_file)

    def _on_result_image_click(self, x: float, y: float) -> None:
        if self._neutral_picker_active:
            self._apply_neutral_picker_at(x, y)
            return
        self._on_manual_chart_click(x, y)

    def _on_manual_chart_click(self, x: float, y: float) -> None:
        if not self._manual_chart_marking:
            return
        if not self._manual_chart_points_match_selected_file():
            self._manual_chart_points = []
            self._manual_chart_points_source = self._selected_file.expanduser().resolve(strict=False) if self._selected_file else None
        if len(self._manual_chart_points) >= 4:
            self._manual_chart_points = []
        self._manual_chart_points.append((float(x), float(y)))
        if len(self._manual_chart_points) == 4:
            self._manual_chart_marking = False
            self._update_viewer_interaction_cursor()
            self._set_status(self.tr("Cuatro esquinas marcadas; revisa y guarda la deteccion"))
        else:
            self._set_status(self.tr("Punto") + f" {len(self._manual_chart_points)}/4 " + self.tr("marcado"))
        self._sync_manual_chart_overlay()

    def _sync_manual_chart_overlay(self) -> None:
        points = self._manual_chart_points if self._manual_chart_points_match_selected_file() else []
        if hasattr(self, "manual_chart_points_label"):
            if points:
                coords = " | ".join(f"{idx}:{x:.0f},{y:.0f}" for idx, (x, y) in enumerate(points, start=1))
                self.manual_chart_points_label.setText(self.tr("Puntos:") + f" {len(points)}/4 - {coords}")
            else:
                self.manual_chart_points_label.setText(self.tr("Puntos: 0/4"))
        if hasattr(self, "image_result_single"):
            self.image_result_single.set_overlay_points(points)
        if hasattr(self, "image_result_compare"):
            self.image_result_compare.set_overlay_points(points)

    def _save_manual_chart_detection(self) -> None:
        if self._selected_file is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona primero una captura de carta."))
            return
        if self._selected_file.suffix.lower() not in PROFILE_CHART_EXTENSIONS:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Referencia no compatible"),
                self.tr("Las detecciones de carta para perfilado cientifico solo aceptan RAW/DNG/TIFF."),
            )
            return
        if self._original_linear is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Carga primero la captura de carta en el visor."))
            return
        if len(self._manual_chart_points) != 4:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Marca exactamente 4 esquinas antes de guardar."))
            return
        if not self._manual_chart_points_match_selected_file():
            self._clear_manual_chart_points_for_file_change()
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Marcado no valido"),
                self.tr("El marcado manual pertenecia a otra imagen. Marca de nuevo la carta en la captura actual."),
            )
            return

        workdir = Path(self.profile_workdir.text().strip() or "/tmp/nexoraw_profile_work")
        default_dir = workdir / "manual_detections"
        default_dir.mkdir(parents=True, exist_ok=True)
        default_path = default_dir / f"{self._selected_file.stem}.manual_detection.json"
        out_text, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self.tr("Guardar deteccion manual"),
            str(default_path),
            "JSON (*.json)",
        )
        if not out_text:
            return

        selected = self._selected_file
        points_preview = list(self._manual_chart_points)
        preview_h, preview_w = self._manual_chart_point_space_shape()
        out_json = Path(out_text)
        chart_type = self.profile_chart_type.currentText()
        recipe = self._build_effective_recipe()

        def task():
            out_json.parent.mkdir(parents=True, exist_ok=True)
            overlay_path = out_json.with_name(f"{out_json.stem}.overlay.png")
            if selected.suffix.lower() in RAW_EXTENSIONS:
                target_image = out_json.with_name(f"{out_json.stem}.developed.tiff")
                full_image = develop_image_array(selected, recipe)
                write_tiff16(target_image, full_image)
            else:
                target_image = selected
                full_image = read_image(target_image)

            full_h, full_w = full_image.shape[:2]
            sx = full_w / max(1, preview_w)
            sy = full_h / max(1, preview_h)
            corners = [(x * sx, y * sy) for x, y in points_preview]
            detection = detect_chart_from_corners_array(full_image, corners=corners, chart_type=chart_type)
            write_json(out_json, detection)
            draw_detection_overlay_array(full_image, detection, overlay_path)
            return {
                "detection_json": str(out_json),
                "overlay": str(overlay_path),
                "image": str(target_image),
                "corners": corners,
                "source_raw": str(selected),
                "detection": to_json_dict(detection),
            }

        def on_success(payload) -> None:
            self.profile_output.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
            source = Path(str(payload["source_raw"])).expanduser().resolve()
            self._manual_chart_detections[str(source)] = payload["detection"]
            if source not in {p.expanduser().resolve() for p in self._selected_chart_files}:
                self._selected_chart_files.append(source)
                self._selected_chart_files = sorted(set(self._selected_chart_files), key=lambda p: str(p))
                self._sync_profile_chart_selection_label()
            self.profile_charts_dir.setText(str(source.parent))
            self._log_preview(f"Detección manual guardada: {payload['detection_json']}")
            self._set_status(self.tr("Deteccion manual asociada a carta:") + f" {source.name}")

        self._start_background_task(self.tr("Deteccion manual de carta"), task, on_success)
