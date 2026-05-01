from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class BatchWorkflowMixin:
    def _collect_selected_file_paths(self) -> list[Path]:
        files: list[Path] = []
        for item in self.file_list.selectedItems():
            value = item.data(QtCore.Qt.UserRole)
            if not value:
                continue
            stale_path = Path(str(value))
            p = self._resolve_existing_browsable_path(stale_path)
            if p is not None:
                if self._normalized_path_key(p) != self._normalized_path_key(stale_path):
                    self._update_file_item_path(item, p)
                files.append(p)
        files.sort()
        return files

    def _on_batch_develop_selected(self) -> None:
        files = self._collect_selected_file_paths()
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "Selecciona uno o más archivos para el lote.")
            return
        self._start_batch_develop(files, "Lote desde selección")

    def _on_batch_develop_directory(self) -> None:
        folder = Path(self.batch_input_dir.text().strip())
        if not folder.exists() or not folder.is_dir():
            QtWidgets.QMessageBox.information(self, self.tr("Info"), f"Directorio inválido: {folder}")
            return
        files = [
            p for p in sorted(folder.iterdir())
            if p.is_file() and p.suffix.lower() in BROWSABLE_EXTENSIONS
        ]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "No hay RAW/imagenes compatibles en el directorio.")
            return
        self._start_batch_develop(files, "Lote desde directorio")

    def _batch_worker_count(self, total_items: int) -> int:
        return resolve_batch_workers(total_items)

    @staticmethod
    def _versioned_output_path_with_reservations(
        requested_path: Path,
        reserved_paths: set[str],
    ) -> Path:
        requested = Path(requested_path)
        candidate = requested
        candidate_key = str(candidate)
        if not candidate.exists() and candidate_key not in reserved_paths:
            reserved_paths.add(candidate_key)
            return candidate
        for index in range(2, 10000):
            candidate = requested.with_name(f"{requested.stem}_v{index:03d}{requested.suffix}")
            candidate_key = str(candidate)
            if not candidate.exists() and candidate_key not in reserved_paths:
                reserved_paths.add(candidate_key)
                return candidate
        raise RuntimeError(f"No se pudo generar salida versionada para {requested.name}")

    def _process_batch_files(
        self,
        *,
        files: list[Path],
        out_dir: Path,
        recipe: Recipe,
        apply_adjust: bool,
        use_profile: bool,
        profile_path: Path | None,
        denoise_luma: float,
        denoise_color: float,
        sharpen_amount: float,
        sharpen_radius: float,
        lateral_ca_red_scale: float,
        lateral_ca_blue_scale: float,
        render_adjustments: dict[str, Any],
        c2pa_config: C2PASignConfig | None,
        proof_config: ProbRawProofConfig,
        sidecar_detail_adjustments: dict[str, Any] | None = None,
        sidecar_render_adjustments: dict[str, Any] | None = None,
        development_profile: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[dict[str, str]] = []
        errors: list[dict[str, str]] = []

        if profile_path is not None and not profile_path.exists():
            raise RuntimeError(f"No existe perfil ICC activo: {profile_path}")
        recipe = self._visible_export_recipe_for_color_management(
            recipe,
            input_profile_path=profile_path,
        )

        detail_adjustments = {
            "applied": bool(apply_adjust),
            "denoise_luminance": denoise_luma if apply_adjust else 0.0,
            "denoise_color": denoise_color if apply_adjust else 0.0,
            "sharpen_amount": sharpen_amount if apply_adjust else 0.0,
            "sharpen_radius": sharpen_radius if apply_adjust else 0.0,
            "lateral_ca_red_scale": lateral_ca_red_scale if apply_adjust else 1.0,
            "lateral_ca_blue_scale": lateral_ca_blue_scale if apply_adjust else 1.0,
        }
        c2pa_render_adjustments = {"applied": True, **render_adjustments} if apply_adjust else {"applied": False}
        sidecar_detail_state = sidecar_detail_adjustments or {
            "sharpen": int(round((sharpen_amount if apply_adjust else 0.0) * 100)),
            "radius": int(round((sharpen_radius if apply_adjust else 1.0) * 10)),
            "noise_luma": int(round((denoise_luma if apply_adjust else 0.0) * 100)),
            "noise_color": int(round((denoise_color if apply_adjust else 0.0) * 100)),
            "ca_red": int(round(((lateral_ca_red_scale if apply_adjust else 1.0) - 1.0) * 10000)),
            "ca_blue": int(round(((lateral_ca_blue_scale if apply_adjust else 1.0) - 1.0) * 10000)),
        }
        sidecar_render_state = sidecar_render_adjustments or render_adjustments

        generic_profile_dir = (
            self._session_paths_from_root(self._active_session_root)["profiles"] / "standard"
            if self._active_session_root is not None
            else None
        )
        session_name = ""
        metadata_payload = (
            self._active_session_payload.get("metadata", {})
            if isinstance(self._active_session_payload, dict)
            else {}
        )
        if isinstance(metadata_payload, dict):
            session_name = str(metadata_payload.get("name") or "")
        if not session_name and self._active_session_root is not None:
            session_name = self._active_session_root.name

        planned: list[tuple[int, Path, Path, Path]] = []
        reserved_outputs: set[str] = set()
        for idx, src in enumerate(files):
            requested_out_path = out_dir / f"{src.stem}.tiff"
            out_path = self._versioned_output_path_with_reservations(requested_out_path, reserved_outputs)
            planned.append((idx, src, requested_out_path, out_path))

        output_slots: list[dict[str, str] | None] = [None] * len(planned)
        error_slots: list[dict[str, str] | None] = [None] * len(planned)

        def process_one(
            index: int,
            src: Path,
            requested_out_path: Path,
            out_path: Path,
        ) -> tuple[int, dict[str, str] | None, dict[str, str] | None]:
            try:
                if src.suffix.lower() in RAW_EXTENSIONS:
                    image = (
                        develop_standard_output_array(src, recipe)
                        if not use_profile and is_generic_output_space(recipe.output_space)
                        else develop_image_array(src, recipe)
                    )
                else:
                    image = read_image(src)

                if apply_adjust:
                    image = self._apply_output_adjustments(
                        image,
                        denoise_luma=denoise_luma,
                        denoise_color=denoise_color,
                        sharpen_amount=sharpen_amount,
                        sharpen_radius=sharpen_radius,
                        lateral_ca_red_scale=lateral_ca_red_scale,
                        lateral_ca_blue_scale=lateral_ca_blue_scale,
                        render_adjustments=render_adjustments,
                    )

                mode, proof_result = write_signed_profiled_tiff(
                    out_path,
                    image,
                    source_raw=src,
                    recipe=recipe,
                    profile_path=profile_path if use_profile else None,
                    c2pa_config=c2pa_config,
                    proof_config=proof_config,
                    detail_adjustments=detail_adjustments,
                    render_adjustments=c2pa_render_adjustments,
                    render_context={"entrypoint": "gui_batch_develop", "apply_adjustments": bool(apply_adjust)},
                    generic_profile_dir=generic_profile_dir,
                )
                rendered_profile_path = profile_path_for_render_settings(
                    recipe,
                    input_profile_path=profile_path if use_profile else None,
                    color_management_mode=mode,
                    generic_profile_dir=generic_profile_dir,
                )

                output = {"source": str(src), "output": str(out_path), "proof": proof_result.proof_path}
                if development_profile:
                    output["development_profile_id"] = str(development_profile.get("id") or "")
                    output["development_profile_name"] = str(development_profile.get("name") or "")
                if out_path != requested_out_path:
                    output["requested_output"] = str(requested_out_path)

                if src.suffix.lower() in RAW_EXTENSIONS:
                    sidecar_path = write_raw_sidecar(
                        src,
                        recipe=recipe,
                        development_profile=development_profile,
                        detail_adjustments=sidecar_detail_state,
                        render_adjustments=sidecar_render_state,
                        icc_profile_path=rendered_profile_path,
                        color_management_mode=mode,
                        session_root=self._active_session_root,
                        session_name=session_name,
                        output_tiff=out_path,
                        proof_path=Path(proof_result.proof_path),
                        status="rendered",
                    )
                    output["raw_sidecar"] = str(sidecar_path)
                return index, output, None
            except Exception as exc:
                return index, None, {"source": str(src), "error": str(exc)}

        worker_count = self._batch_worker_count(len(planned))
        if worker_count <= 1:
            for idx, src, requested_out_path, out_path in planned:
                i, output, error = process_one(idx, src, requested_out_path, out_path)
                output_slots[i] = output
                error_slots[i] = error
        else:
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="probraw-batch") as executor:
                futures = [
                    executor.submit(process_one, idx, src, requested_out_path, out_path)
                    for idx, src, requested_out_path, out_path in planned
                ]
                for future in as_completed(futures):
                    i, output, error = future.result()
                    output_slots[i] = output
                    error_slots[i] = error

        outputs.extend([output for output in output_slots if output is not None])
        errors.extend([error for error in error_slots if error is not None])

        return {
            "input_files": len(files),
            "output_dir": str(out_dir),
            "outputs": outputs,
            "errors": errors,
            "development_profile": development_profile or {},
            "workers": worker_count,
        }

    def _start_batch_develop(self, files: list[Path], task_label: str) -> None:
        self._ensure_session_output_controls()
        out_dir = Path(self.batch_out_dir.text().strip())
        apply_adjust = bool(self.batch_apply_adjustments.isChecked())
        embed_profile = bool(self.batch_embed_profile.isChecked())
        settings = self._development_profile_settings(self._active_development_profile_id)
        detail = self._detail_adjustment_kwargs_from_state(settings["detail_adjustments"])
        stored_profile_path = settings.get("icc_profile_path")
        profile_path = (
            stored_profile_path
            if isinstance(stored_profile_path, Path) and stored_profile_path.exists()
            else None
        )
        use_profile = bool(embed_profile and profile_path is not None)
        recipe = self._visible_export_recipe_for_color_management(
            settings["recipe"],
            input_profile_path=profile_path if use_profile else None,
        )
        if not self._require_color_managed_recipe_for_ui(
            recipe,
            input_profile_path=profile_path if use_profile else None,
            title=self.tr("Lote sin gestión de color"),
        ):
            return
        try:
            proof_config = self._resolve_proof_config_for_gui()
            c2pa_config = self._resolve_c2pa_config_for_gui()
        except Exception as exc:
            self._show_signature_config_error(exc)
            return

        def task():
            payload = self._process_batch_files(
                files=files,
                out_dir=out_dir,
                recipe=recipe,
                apply_adjust=apply_adjust,
                use_profile=use_profile,
                profile_path=profile_path,
                denoise_luma=detail["denoise_luma"],
                denoise_color=detail["denoise_color"],
                sharpen_amount=detail["sharpen_amount"],
                sharpen_radius=detail["sharpen_radius"],
                lateral_ca_red_scale=detail["lateral_ca_red_scale"],
                lateral_ca_blue_scale=detail["lateral_ca_blue_scale"],
                render_adjustments=self._render_adjustment_kwargs_from_state(settings["render_adjustments"]),
                sidecar_detail_adjustments=settings["detail_adjustments"],
                sidecar_render_adjustments=settings["render_adjustments"],
                c2pa_config=c2pa_config,
                proof_config=proof_config,
                development_profile=self._profile_payload_from_development_settings(settings),
            )
            payload["task"] = task_label
            return payload

        def on_success(payload) -> None:
            self.batch_output.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
            ok_count = len(payload.get("outputs", []))
            error_count = len(payload.get("errors", []))
            self._log_preview(
                f"Lote finalizado: {ok_count}/{payload['input_files']} completados "
                f"({error_count} errores)"
            )
            self._set_status(
                self.tr("Lote finalizado en") + f" {payload['output_dir']} "
                f"(OK={ok_count}, " + self.tr("errores") + f"={error_count})"
            )
            self._refresh_color_reference_thumbnail_markers()
            self._save_active_session(silent=True)

        self._start_background_task(task_label, task, on_success)

    def _use_generated_profile_as_active(self) -> None:
        p = self._normalized_profile_out_path()
        if not p.exists():
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "El perfil ICC de entrada aún no existe.")
            return
        if not self._profile_can_be_active(p):
            status = self._profile_status_for_path(p) or self.tr("no disponible")
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Perfil no activable"),
                self.tr("No se activa el perfil generado porque su estado QA es") + f" '{status}'. "
                + self.tr("Regenera el perfil con referencias RAW/DNG originales."),
            )
            self.path_profile_active.clear()
            self.chk_apply_profile.setChecked(False)
            self._save_active_session(silent=True)
            return
        self.path_profile_active.setText(str(p))
        recipe_path = Path(self.calibrated_recipe_out.text().strip())
        if recipe_path.exists():
            self.path_recipe.setText(str(recipe_path))
            try:
                self._apply_recipe_to_controls(load_recipe(recipe_path))
            except Exception as exc:
                self._log_preview(f"No se pudo activar receta calibrada: {exc}")
        self.chk_apply_profile.setChecked(True)
        self._register_icc_profile(
            {
                "name": p.stem,
                "source": "generated",
                "path": str(p),
                "recipe_path": str(recipe_path) if recipe_path.exists() else "",
                "status": self._profile_status_for_path(p) or "unknown",
            },
            activate=True,
            save=False,
        )
        self._invalidate_preview_cache()
        self._schedule_preview_refresh()
        self._set_status(self.tr("Perfil activo:") + f" {p}")
        self._save_active_session(silent=True)
