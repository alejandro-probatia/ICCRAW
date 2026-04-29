from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewExportMixin:
    def _on_save_preview(self) -> None:
        if self._preview_srgb is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "No hay preview para guardar.")
            return
        self._ensure_session_output_controls()
        default_out = str(self._session_default_outputs()["preview"])
        out_text, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self.tr("Guardar preview PNG"),
            default_out,
            "PNG (*.png)",
        )
        if not out_text:
            return
        out = Path(out_text)
        if out.suffix.lower() != ".png":
            out = out.with_suffix(".png")
        out.parent.mkdir(parents=True, exist_ok=True)
        bgr = np.clip(np.round(self._preview_srgb[..., ::-1] * 255.0), 0, 255).astype(np.uint8)
        ok = cv2.imwrite(str(out), bgr)
        if not ok:
            QtWidgets.QMessageBox.critical(self, self.tr("Error"), self.tr("No se pudo guardar:") + f" {out}")
            return
        self._log_preview(f"Preview guardada en: {out}")
        self._set_status(self.tr("Preview guardada:") + f" {out}")
        self._save_active_session(silent=True)

    def _on_develop_selected(self) -> None:
        if self._selected_file is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona un archivo para revelar."))
            return

        in_path = self._selected_file
        recipe = self._build_effective_recipe()
        profile_path = self._active_session_icc_for_settings()
        if not self._require_color_managed_recipe_for_ui(
            recipe,
            input_profile_path=profile_path,
            title=self.tr("Revelado sin gestión de color"),
        ):
            return
        defaults = self._session_default_outputs()
        default_out = str(defaults["tiff_dir"] / f"{in_path.stem}.tiff")
        out_text, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Guardar TIFF revelado",
            default_out,
            "TIFF (*.tif *.tiff)",
        )
        if not out_text:
            return
        requested_out_path = Path(out_text)
        out_path = versioned_output_path(requested_out_path)

        nl = self.slider_noise_luma.value() / 100.0
        nc = self.slider_noise_color.value() / 100.0
        sharpen = self.slider_sharpen.value() / 100.0
        radius = self.slider_radius.value() / 10.0
        ca_red, ca_blue = self._ca_scale_factors()
        render_adjustments = self._render_adjustment_kwargs()
        c2pa_render_adjustments = {"applied": True, **render_adjustments}
        detail_adjustments = {
            "applied": True,
            "denoise_luminance": nl,
            "denoise_color": nc,
            "sharpen_amount": sharpen,
            "sharpen_radius": radius,
            "lateral_ca_red_scale": ca_red,
            "lateral_ca_blue_scale": ca_blue,
        }
        try:
            proof_config = self._resolve_proof_config_for_gui()
            c2pa_config = self._resolve_c2pa_config_for_gui()
        except Exception as exc:
            self._show_signature_config_error(exc)
            return

        def task():
            image = (
                develop_standard_output_array(in_path, recipe)
                if profile_path is None and is_generic_output_space(recipe.output_space)
                else develop_image_array(in_path, recipe)
            )
            image = self._apply_output_adjustments(
                image,
                denoise_luma=nl,
                denoise_color=nc,
                sharpen_amount=sharpen,
                sharpen_radius=radius,
                lateral_ca_red_scale=ca_red,
                lateral_ca_blue_scale=ca_blue,
                render_adjustments=render_adjustments,
            )
            mode, proof_result = write_signed_profiled_tiff(
                out_path,
                image,
                source_raw=in_path,
                recipe=recipe,
                profile_path=profile_path,
                c2pa_config=c2pa_config,
                proof_config=proof_config,
                detail_adjustments=detail_adjustments,
                render_adjustments=c2pa_render_adjustments,
                render_context={"entrypoint": "gui_single_develop"},
                generic_profile_dir=self._session_generic_profile_dir(),
            )
            rendered_profile_path = self._render_profile_path_for_recipe(
                recipe,
                input_profile_path=profile_path,
                color_management_mode=mode,
            )
            profile_id = self._active_development_profile_id
            development_profile = None
            if profile_id:
                profile_descriptor = self._development_profile_by_id(profile_id) or {}
                kind = str(profile_descriptor.get("kind") or "manual")
                development_profile = {
                    "id": profile_id,
                    "name": str(profile_descriptor.get("name") or profile_id),
                    "kind": kind,
                    "profile_type": str(profile_descriptor.get("profile_type") or self._adjustment_profile_type_for_kind(kind)),
                }
            sidecar = self._write_raw_settings_sidecar(
                in_path,
                recipe=recipe,
                development_profile=development_profile,
                detail_adjustments=self._detail_adjustment_state(),
                render_adjustments=self._render_adjustment_state(),
                profile_path=rendered_profile_path,
                color_management_mode=mode,
                output_tiff=out_path,
                proof_path=Path(proof_result.proof_path),
                status="rendered",
            )
            return {
                "output_tiff": str(out_path),
                "requested_tiff": str(requested_out_path),
                "proof": proof_result.proof_path,
                "raw_sidecar": str(sidecar) if sidecar is not None else "",
            }

        def on_success(payload) -> None:
            if payload.get("requested_tiff") != payload.get("output_tiff"):
                self._log_preview(f"Salida existente preservada; nueva version: {payload['output_tiff']}")
            self._log_preview(f"TIFF revelado: {payload['output_tiff']}")
            self._log_preview(f"NexoRAW Proof: {payload['proof']}")
            if payload.get("raw_sidecar"):
                self._log_preview(f"Mochila NexoRAW: {payload['raw_sidecar']}")
            self._refresh_color_reference_thumbnail_markers()
            self._set_status(self.tr("Revelado completado:") + f" {payload['output_tiff']}")
            self._save_active_session(silent=True)

        self._start_background_task(self.tr("Revelado a TIFF"), task, on_success)
