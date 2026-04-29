from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewMenuMixin:
    def _toggle_compare(self, enabled: bool) -> None:
        self.viewer_stack.setCurrentIndex(1 if enabled else 0)
        if hasattr(self, "_action_compare"):
            self._action_compare.blockSignals(True)
            self._action_compare.setChecked(enabled)
            self._action_compare.blockSignals(False)
        selected = self._selected_file
        if selected is not None and selected.suffix.lower() in RAW_EXTENSIONS:
            self._last_loaded_preview_key = None
            self._on_load_selected(show_message=False)
            return
        if self._original_linear is not None:
            self._schedule_preview_refresh()

    def _menu_toggle_compare(self, checked: bool) -> None:
        self.chk_compare.setChecked(checked)
        self._toggle_compare(checked)

    def _menu_check_updates(self) -> None:
        self._start_update_check(
            on_success=self._on_manual_update_check_success,
            on_error=self._on_manual_update_check_error,
        )

    def _on_manual_update_check_success(self, payload: dict[str, Any]) -> None:
        self._update_check_last = payload
        status_text = self._update_status_summary(payload)
        if payload.get("error"):
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Actualizaciones"),
                status_text,
            )
            return
        QtWidgets.QMessageBox.information(self, self.tr("Actualizaciones"), status_text)

    def _on_manual_update_check_error(self, message: str) -> None:
        QtWidgets.QMessageBox.warning(self, self.tr("Actualizaciones"), message)

    def _menu_about(self) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.tr("Acerca de ") + APP_NAME)
        dialog.setModal(True)
        dialog.resize(640, 360)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QtWidgets.QLabel(APP_NAME)
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QtWidgets.QLabel(
            self.tr("Revelado RAW tecnico, trazable y reproducible para entornos cientificos.")
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 12px; color: #4b5563;")
        layout.addWidget(subtitle)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        def add_row(row: int, label: str, value: str) -> QtWidgets.QLabel:
            k = QtWidgets.QLabel(label)
            k.setStyleSheet("font-weight: 600; color: #374151;")
            v = QtWidgets.QLabel(value)
            v.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            v.setWordWrap(True)
            grid.addWidget(k, row, 0)
            grid.addWidget(v, row, 1)
            return v

        add_row(0, self.tr("Director del proyecto:"), PROJECT_DIRECTOR_NAME)
        add_row(1, self.tr("Version en ejecucion:"), __version__)
        add_row(2, self.tr("Backend:"), "LibRaw/rawpy + ArgyllCMS")
        amaze_info = self._amaze_status_summary()
        add_row(3, self.tr("Soporte AMaZE:"), amaze_info)
        latest_label = add_row(4, self.tr("Estado de version:"), self.tr("Sin comprobar"))

        layout.addLayout(grid)

        status_note = QtWidgets.QLabel(
            self.tr("La comprobacion usa GitHub Releases; la actualizacion automatica descarga y ejecuta el instalador.")
        )
        status_note.setWordWrap(True)
        status_note.setStyleSheet("font-size: 12px; color: #6b7280;")
        layout.addWidget(status_note)

        button_row = QtWidgets.QHBoxLayout()
        btn_check = QtWidgets.QPushButton(self.tr("Comprobar ultima version"))
        btn_update = QtWidgets.QPushButton(self.tr("Actualizar automaticamente"))
        btn_release = QtWidgets.QPushButton(self.tr("Abrir releases"))
        btn_close = QtWidgets.QPushButton(self.tr("Cerrar"))
        btn_update.setEnabled(False)
        button_row.addWidget(btn_check)
        button_row.addWidget(btn_update)
        button_row.addStretch(1)
        button_row.addWidget(btn_release)
        button_row.addWidget(btn_close)
        layout.addLayout(button_row)

        state: dict[str, Any] = {"payload": self._update_check_last}

        def refresh_about_payload(payload: dict[str, Any] | None) -> None:
            p = payload or {}
            latest_label.setText(self._update_status_summary(p))
            latest_label.setStyleSheet("color: #dc2626;" if p.get("error") else "color: #1f2937;")
            can_auto = bool(p.get("update_available") and p.get("asset_url"))
            btn_update.setEnabled(can_auto)

        def open_release_page() -> None:
            payload = state.get("payload") or {}
            url = str(payload.get("release_url") or f"https://github.com/{os.environ.get('NEXORAW_RELEASE_REPOSITORY', self.tr('alejandro-probatia/NexoRAW'))}/releases")
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

        def run_check() -> None:
            btn_check.setEnabled(False)
            latest_label.setText(self.tr("Comprobando version mas reciente..."))

            def ok(payload: dict[str, Any]) -> None:
                state["payload"] = payload
                self._update_check_last = payload
                refresh_about_payload(payload)
                btn_check.setEnabled(True)

            def fail(message: str) -> None:
                btn_check.setEnabled(True)
                fallback = {"error": message}
                state["payload"] = fallback
                refresh_about_payload(fallback)

            self._start_update_check(on_success=ok, on_error=fail)

        def run_auto_update() -> None:
            payload = state.get("payload")
            if not isinstance(payload, dict):
                QtWidgets.QMessageBox.information(dialog, self.tr("Actualizacion"), self.tr("Primero comprueba la ultima version."))
                return
            if payload.get("error"):
                QtWidgets.QMessageBox.warning(dialog, self.tr("Actualizacion"), str(payload.get("error")))
                return
            if not payload.get("update_available"):
                QtWidgets.QMessageBox.information(dialog, self.tr("Actualizacion"), self.tr("Ya estas en la ultima version."))
                return
            if not payload.get("asset_url"):
                QtWidgets.QMessageBox.information(
                    dialog,
                    self.tr("Actualizacion"),
                    self.tr("No hay instalador automatico para esta plataforma en la release detectada."),
                )
                return
            answer = QtWidgets.QMessageBox.question(
                dialog,
                self.tr("Actualizar automaticamente"),
                self.tr("Se descargara el instalador mas reciente y se ejecutara en modo silencioso.\nDeseas continuar?"),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return

            btn_update.setEnabled(False)
            btn_check.setEnabled(False)
            latest_label.setText(self.tr("Descargando e iniciando actualizacion..."))

            def task() -> dict[str, Any]:
                fresh_check = check_latest_release()
                check_payload = asdict(fresh_check)
                if fresh_check.error:
                    raise RuntimeError(str(fresh_check.error))
                if not fresh_check.update_available:
                    raise RuntimeError("No hay una version mas reciente disponible.")
                installer = auto_update(check=fresh_check, silent=True)
                return {"installer_path": str(installer), "check": check_payload}

            def ok(result: dict[str, Any]) -> None:
                installer_path = str(result.get("installer_path") or "")
                latest_label.setText(self.tr("Instalador lanzado correctamente."))
                QtWidgets.QMessageBox.information(
                    dialog,
                    self.tr("Actualizacion iniciada"),
                    self.tr("Se ha iniciado el instalador de actualizacion:") + f"\n{installer_path}\n\n"
                    + self.tr("Cierra NexoRAW cuando el instalador lo solicite."),
                )
                btn_check.setEnabled(True)
                btn_update.setEnabled(True)

            def fail(message: str) -> None:
                latest_label.setText(self.tr("No se pudo iniciar la actualizacion automatica."))
                QtWidgets.QMessageBox.warning(dialog, self.tr("Actualizacion"), message)
                btn_check.setEnabled(True)
                btn_update.setEnabled(True)

            self._run_lightweight_task(task, on_success=ok, on_error=fail)

        btn_check.clicked.connect(run_check)
        btn_update.clicked.connect(run_auto_update)
        btn_release.clicked.connect(open_release_page)
        btn_close.clicked.connect(dialog.accept)

        refresh_about_payload(state.get("payload"))
        dialog.exec()

    def _update_status_summary(self, payload: dict[str, Any]) -> str:
        if not payload:
            return "Sin comprobar"
        error = payload.get("error")
        if error:
            return f"No se pudo comprobar la version: {error}"
        latest = str(payload.get("latest_version") or "desconocida")
        current = str(payload.get("current_version") or __version__)
        if bool(payload.get("update_available")):
            return f"Actualizacion disponible: {latest} (actual: {current})"
        if payload.get("is_latest") is True:
            return f"Estas en la ultima version: {current}"
        return f"Version actual: {current}. Ultima detectada: {latest}"

    def _amaze_status_summary(self) -> str:
        try:
            payload = check_amaze_backend()
        except Exception as exc:
            return f"No disponible ({exc})"
        supported = bool(payload.get("amaze_supported"))
        rawpy_name = str(payload.get("rawpy_demosaic_distribution") or payload.get("rawpy_distribution") or "rawpy")
        return "Activo" if supported else f"No activo ({rawpy_name})"

    def _start_update_check(self, *, on_success, on_error) -> None:
        def task() -> dict[str, Any]:
            return asdict(check_latest_release())

        self._run_lightweight_task(task, on_success=on_success, on_error=on_error)

    def _run_lightweight_task(self, task, *, on_success, on_error) -> None:
        thread = TaskThread(task)
        self._threads.append(thread)

        def cleanup() -> None:
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()

        def ok(payload) -> None:
            try:
                on_success(payload)
            finally:
                cleanup()

        def fail(trace: str) -> None:
            try:
                message = trace.strip().splitlines()[-1] if trace.strip() else "Error"
                on_error(message)
            finally:
                cleanup()

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _menu_check_tools(self) -> None:
        result = check_external_tools()
        self.profile_output.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
        missing = result.get("missing_required", [])
        if hasattr(self, "profile_summary_label"):
            if missing:
                self.profile_summary_label.setText(
                    self.tr("Diagnostico herramientas: faltan") + " " + ", ".join(str(name) for name in missing)
                )
            else:
                self.profile_summary_label.setText(self.tr("Diagnostico herramientas: entorno externo completo"))
        if missing:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Diagnostico herramientas"),
                self.tr("Faltan herramientas requeridas en PATH:") + " " + ", ".join(str(name) for name in missing),
            )
            self._set_status(self.tr("Faltan herramientas externas requeridas"))
        else:
            self._set_status(self.tr("Herramientas externas disponibles"))

    def _menu_load_profile(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Selecciona perfil ICC"),
            self.path_profile_active.text().strip(),
            "ICC Profiles (*.icc *.icm);;Todos (*)",
        )
        if not path:
            return
        profile_path = Path(path).expanduser()
        if not self._profile_can_be_active(profile_path):
            status = self._profile_status_for_path(profile_path) or self.tr("no disponible")
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Perfil no activable"),
                self.tr("No se activa el perfil porque su estado QA es") + f" '{status}'. "
                + self.tr("Regenera el perfil con referencias RAW/DNG originales."),
            )
            return
        self.path_profile_active.setText(path)
        self.chk_apply_profile.setChecked(True)
        profile_id = self._register_icc_profile(
            {
                "name": profile_path.stem,
                "source": "loaded",
                "path": str(profile_path),
                "status": self._profile_status_for_path(profile_path) or "unknown",
            },
            activate=True,
            save=False,
        )
        if profile_id:
            self._active_icc_profile_id = profile_id
            self._refresh_profile_management_views()
        self._set_status(self.tr("Perfil activo:") + f" {path}")
        self._refresh_preview()
        self._save_active_session(silent=True)

    def _menu_compare_qa_reports(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            self.tr("Comparar reportes QA de sesion"),
            str(self._current_dir),
            "Reportes JSON (*.json);;Todos (*)",
        )
        if not paths:
            return
        try:
            comparison = compare_qa_reports([Path(path) for path in paths])
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Comparacion QA"), str(exc))
            return
        self.profile_output.setPlainText(json.dumps(comparison, indent=2, ensure_ascii=False))
        if hasattr(self, "profile_summary_label"):
            self.profile_summary_label.setText(self._qa_comparison_summary(comparison))
        self._set_status(self.tr("Comparados") + f" {comparison.get('report_count', len(paths))} " + self.tr("reportes QA"))

    def _qa_comparison_summary(self, comparison: dict[str, Any]) -> str:
        status_counts = comparison.get("status_counts") if isinstance(comparison.get("status_counts"), dict) else {}
        best = comparison.get("best_validation_mean_delta_e2000")
        worst = comparison.get("worst_validation_mean_delta_e2000")
        parts = [
            f"Reportes QA comparados: {comparison.get('report_count', 0)}",
            "Estados: " + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())),
        ]
        if isinstance(best, dict) and best.get("validation_mean_delta_e2000") is not None:
            parts.append(
                f"Mejor validación: {best.get('label')} "
                f"media {float(best['validation_mean_delta_e2000']):.2f}"
            )
        if isinstance(worst, dict) and worst.get("validation_mean_delta_e2000") is not None:
            parts.append(
                f"Peor validación: {worst.get('label')} "
                f"media {float(worst['validation_mean_delta_e2000']):.2f}"
            )
        return "\n".join(parts)

    def _menu_load_recipe(self) -> None:
        start = self.path_recipe.text().strip() or str(Path.cwd())
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Selecciona receta",
            start,
            "Recetas (*.yml *.yaml *.json);;Todos (*)",
        )
        if not path:
            return
        recipe_path = Path(path)
        recipe = load_recipe(recipe_path)
        self.path_recipe.setText(str(recipe_path))
        self._apply_recipe_to_controls(recipe)
        self._set_status(self.tr("Receta cargada:") + f" {recipe_path}")
        self._save_active_session(silent=True)

    def _menu_save_recipe(self) -> None:
        start = self.path_recipe.text().strip() or str(Path.cwd() / "recipe.yml")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self.tr("Guardar receta"),
            start,
            "YAML (*.yml *.yaml);;JSON (*.json)",
        )
        if not path:
            return
        out = Path(path)
        recipe = self._build_effective_recipe()
        payload = asdict(recipe)
        out.parent.mkdir(parents=True, exist_ok=True)

        if out.suffix.lower() in {".yaml", ".yml"}:
            out.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        else:
            out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self.path_recipe.setText(str(out))
        self._set_status(self.tr("Receta guardada:") + f" {out}")
        self._save_active_session(silent=True)

    def _menu_reset_recipe(self) -> None:
        self._apply_recipe_to_controls(Recipe())
        self._set_status(self.tr("Receta restablecida a valores por defecto"))
        self._save_active_session(silent=True)
