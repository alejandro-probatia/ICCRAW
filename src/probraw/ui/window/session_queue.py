from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class SessionQueueMixin:
    def _queue_add_files(self, files: list[Path]) -> int:
        existing = {item["source"] for item in self._develop_queue if item.get("source")}
        added = 0
        for src in files:
            source = str(src)
            if source in existing:
                continue
            profile_id = self._development_profile_from_sidecar(src) or self._active_development_profile_id
            self._develop_queue.append(
                {
                    "source": source,
                    "development_profile_id": profile_id,
                    "status": "pending",
                    "output_tiff": "",
                    "message": "",
                }
            )
            existing.add(source)
            added += 1

        if added:
            self._refresh_queue_table()
            self._save_active_session(silent=True)
        return added

    def _queue_add_selected(self) -> None:
        files = self._collect_selected_file_paths()
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("No hay seleccion para anadir a la cola."))
            return
        added = self._queue_add_files(files)
        self._set_status(self.tr("Cola actualizada:") + f" {added} " + self.tr("elementos anadidos"))

    def _queue_add_session_raws(self) -> None:
        source_dir = Path(self.batch_input_dir.text().strip() or self._current_dir)
        if not source_dir.exists() or not source_dir.is_dir():
            QtWidgets.QMessageBox.information(self, self.tr("Info"), f"Directorio inválido: {source_dir}")
            return
        files = [
            p for p in sorted(source_dir.iterdir())
            if p.is_file() and p.suffix.lower() in BROWSABLE_EXTENSIONS
        ]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("No hay RAW/imagenes compatibles en el directorio."))
            return
        added = self._queue_add_files(files)
        self._set_status(self.tr("Cola actualizada:") + f" {added} " + self.tr("archivos anadidos desde") + f" {source_dir}")

    def _queue_remove_selected(self) -> None:
        if not self._develop_queue:
            return
        rows = sorted({i.row() for i in self.queue_table.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "Selecciona filas de la cola para quitar.")
            return
        for row in rows:
            if 0 <= row < len(self._develop_queue):
                self._develop_queue.pop(row)
        self._refresh_queue_table()
        self._save_active_session(silent=True)

    def _queue_clear(self) -> None:
        self._develop_queue = []
        self._refresh_queue_table()
        self._save_active_session(silent=True)
        self._set_status(self.tr("Cola vaciada"))

    def _refresh_queue_table(self) -> None:
        if not hasattr(self, "queue_table"):
            return

        self.queue_table.setRowCount(0)
        pending = 0
        done = 0
        errors = 0

        for item in self._develop_queue:
            status = str(item.get("status") or "pending")
            if status == "done":
                done += 1
            elif status == "error":
                errors += 1
            else:
                pending += 1

            row = self.queue_table.rowCount()
            self.queue_table.insertRow(row)
            self.queue_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(item.get("source") or "")))
            self.queue_table.setItem(row, 1, QtWidgets.QTableWidgetItem(self._development_profile_label(str(item.get("development_profile_id") or ""))))
            self.queue_table.setItem(row, 2, QtWidgets.QTableWidgetItem(status))
            self.queue_table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(item.get("output_tiff") or "")))
            self.queue_table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(item.get("message") or "")))

        self.queue_status_label.setText(
            f"Elementos: {len(self._develop_queue)} | Pendientes: {pending} | OK: {done} | Error: {errors}"
        )
        self._refresh_session_statistics()

    def _queue_process(self) -> None:
        if not self._develop_queue:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "No hay elementos en cola.")
            return

        valid_entries: list[tuple[dict[str, str], Path]] = []
        for item in self._develop_queue:
            src = Path(str(item.get("source") or ""))
            if src.exists() and src.is_file() and src.suffix.lower() in BROWSABLE_EXTENSIONS:
                valid_entries.append((item, src))
            else:
                item["status"] = "error"
                item["message"] = "Archivo no encontrado o extensión incompatible"
                item["output_tiff"] = ""

        if not valid_entries:
            self._refresh_queue_table()
            self._save_active_session(silent=True)
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "No hay archivos válidos para procesar en la cola.")
            return

        valid_sources = {str(p) for _item, p in valid_entries}
        for item in self._develop_queue:
            source = str(item.get("source") or "")
            if source and source in valid_sources:
                item["status"] = "pending"
                item["message"] = ""
                item["output_tiff"] = ""
        self._refresh_queue_table()

        self._ensure_session_output_controls()
        out_dir = Path(self.batch_out_dir.text().strip())
        apply_adjust = bool(self.batch_apply_adjustments.isChecked())
        embed_profile = bool(self.batch_embed_profile.isChecked())
        groups: dict[str, list[Path]] = {}
        for item, src in valid_entries:
            profile_id = str(item.get("development_profile_id") or "")
            groups.setdefault(profile_id, []).append(src)
        try:
            settings_by_profile = {
                profile_id: self._development_profile_settings(profile_id)
                for profile_id in groups
            }
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Perfil de ajuste no válido"), str(exc))
            return
        try:
            proof_config = self._resolve_proof_config_for_gui()
            c2pa_config = self._resolve_c2pa_config_for_gui()
        except Exception as exc:
            self._show_signature_config_error(exc)
            return

        def task():
            combined = {"input_files": len(valid_entries), "output_dir": str(out_dir), "outputs": [], "errors": [], "profiles": []}
            for profile_id, group_files in groups.items():
                settings = settings_by_profile[profile_id]
                detail = self._detail_adjustment_kwargs_from_state(settings["detail_adjustments"])
                profile_path = settings.get("icc_profile_path")
                use_profile = bool(embed_profile and isinstance(profile_path, Path) and str(profile_path))
                payload = self._process_batch_files(
                    files=group_files,
                    out_dir=out_dir,
                    recipe=settings["recipe"],
                    apply_adjust=apply_adjust,
                    use_profile=use_profile,
                    profile_path=profile_path if use_profile else None,
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
                    development_profile={
                        "id": settings["id"],
                        "name": settings["name"],
                        "kind": str((self._development_profile_by_id(settings["id"]) or {}).get("kind") or ""),
                    },
                )
                combined["outputs"].extend(payload.get("outputs", []))
                combined["errors"].extend(payload.get("errors", []))
                combined["profiles"].append({"id": settings["id"], "name": settings["name"], "files": len(group_files)})
            combined["task"] = "Cola de revelado"
            return combined

        def on_success(payload) -> None:
            ok_by_source = {str(o["source"]): str(o["output"]) for o in payload.get("outputs", [])}
            err_by_source = {str(e["source"]): str(e["error"]) for e in payload.get("errors", [])}

            for item in self._develop_queue:
                source = str(item.get("source") or "")
                if source in ok_by_source:
                    item["status"] = "done"
                    item["output_tiff"] = ok_by_source[source]
                    item["message"] = "OK"
                elif source in err_by_source:
                    item["status"] = "error"
                    item["output_tiff"] = ""
                    item["message"] = err_by_source[source]

            self._refresh_queue_table()
            self._save_active_session(silent=True)
            self._set_status(
                f"Cola procesada: {len(payload.get('outputs', []))} OK / {len(payload.get('errors', []))} errores"
            )

        self._start_background_task(self.tr("Procesar cola de revelado"), task, on_success)
