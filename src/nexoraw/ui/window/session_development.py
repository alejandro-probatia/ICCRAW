from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class SessionDevelopmentMixin:
    def _profile_timestamp(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _slug_for_development_profile(self, name: str) -> str:
        raw = "".join(ch.lower() if ch.isalnum() else "-" for ch in name.strip())
        slug = "-".join(part for part in raw.split("-") if part) or "perfil"
        return slug[:48]

    def _unique_development_profile_id(self, name: str) -> str:
        base = self._slug_for_development_profile(name)
        existing = {str(profile.get("id") or "") for profile in self._development_profiles}
        if base not in existing:
            return base
        index = 2
        while f"{base}-{index}" in existing:
            index += 1
        return f"{base}-{index}"

    def _development_profile_dir(self, profile_id: str) -> Path:
        root = self._active_session_root or Path(self.session_root_path.text().strip() or Path.cwd())
        return self._session_paths_from_root(root)["config"] / "development_profiles" / profile_id

    def _session_generic_profile_dir(self) -> Path | None:
        root = self._active_session_root
        if root is None and hasattr(self, "session_root_path"):
            text = self.session_root_path.text().strip()
            root = Path(text).expanduser() if text else None
        if root is None:
            return None
        return self._session_paths_from_root(Path(root).expanduser())["profiles"] / "standard"

    def _render_profile_path_for_recipe(
        self,
        recipe: Recipe,
        *,
        input_profile_path: Path | None,
        color_management_mode: str,
    ) -> Path | None:
        try:
            return profile_path_for_render_settings(
                recipe,
                input_profile_path=input_profile_path,
                color_management_mode=color_management_mode,
                generic_profile_dir=self._session_generic_profile_dir(),
            )
        except Exception:
            return input_profile_path

    @staticmethod
    def _is_camera_output_space(output_space: str | None) -> bool:
        return str(output_space or "").strip().lower() in CAMERA_OUTPUT_SPACES

    def _color_management_issue_for_recipe(
        self,
        recipe: Recipe,
        *,
        input_profile_path: Path | None,
    ) -> str | None:
        output_space = str(recipe.output_space or "").strip()
        if is_generic_output_space(output_space):
            if recipe.output_linear:
                return self.tr(
                    "Los espacios de salida estándar requieren salida no lineal para "
                    "incrustar un perfil ICC estándar. Vuelve a seleccionar sRGB, "
                    "Adobe RGB o ProPhoto para sincronizar la receta."
                )
            return None

        if self._is_camera_output_space(output_space):
            if input_profile_path is None:
                return self.tr(
                    "La receta está en RGB de cámara, pero no hay un perfil ICC de entrada "
                    "activo. Genera o carga un ICC de sesión y activa 'Aplicar perfil ICC', "
                    "o elige sRGB, Adobe RGB o ProPhoto como espacio estándar sin carta."
                )
            if not input_profile_path.exists():
                return self.tr("No existe el perfil ICC de entrada activo:") + f" {input_profile_path}"
            return None

        return self.tr("Espacio de salida no soportado para gestión ICC:") + f" {output_space or '<vacío>'}"

    def _require_color_managed_recipe_for_ui(
        self,
        recipe: Recipe,
        *,
        input_profile_path: Path | None,
        title: str | None = None,
    ) -> bool:
        issue = self._color_management_issue_for_recipe(
            recipe,
            input_profile_path=input_profile_path,
        )
        if issue is None:
            return True
        QtWidgets.QMessageBox.warning(
            self,
            title or self.tr("Gestión de color incompleta"),
            issue,
        )
        self._set_status(self.tr("Gestión de color incompleta"))
        return False

    def _configured_color_profile_for_recipe(self, recipe: Recipe) -> tuple[Path | None, Path | None, str]:
        input_profile_path = self._active_session_icc_for_settings()
        issue = self._color_management_issue_for_recipe(
            recipe,
            input_profile_path=input_profile_path,
        )
        if issue is not None:
            raise RuntimeError(issue)
        if is_generic_output_space(recipe.output_space):
            output_profile = ensure_generic_output_profile(
                recipe.output_space,
                directory=self._session_generic_profile_dir(),
            )
            mode = (
                f"standard_{generic_output_profile(recipe.output_space).key}_output_icc"
                if input_profile_path is None
                else f"converted_{generic_output_profile(recipe.output_space).key}"
            )
            if generic_output_profile(recipe.output_space).key == "srgb" and input_profile_path is not None:
                mode = "converted_srgb"
            return input_profile_path, output_profile, mode
        if input_profile_path is not None:
            return input_profile_path, input_profile_path, "camera_rgb_with_input_icc"
        raise RuntimeError(self.tr("Gestión de color incompleta"))

    def _development_profile_by_id(self, profile_id: str) -> dict[str, Any] | None:
        for profile in self._development_profiles:
            if str(profile.get("id") or "") == profile_id:
                return profile
        return None

    @staticmethod
    def _adjustment_profile_type_for_kind(kind: str) -> str:
        return "advanced" if str(kind or "").strip().lower() in {"chart", "advanced"} else "basic"

    def _development_profile_label(self, profile_id: str) -> str:
        if not profile_id:
            return "Actual"
        profile = self._development_profile_by_id(profile_id)
        if profile is None:
            return profile_id
        return str(profile.get("name") or profile_id)

    def _refresh_development_profile_combo(self) -> None:
        if not hasattr(self, "development_profile_combo"):
            return
        current = self._active_development_profile_id
        self.development_profile_combo.blockSignals(True)
        self.development_profile_combo.clear()
        self.development_profile_combo.addItem(self.tr("Ajustes actuales"), "")
        for profile in self._development_profiles:
            profile_id = str(profile.get("id") or "").strip()
            if not profile_id:
                continue
            label = str(profile.get("name") or profile_id)
            kind = str(profile.get("kind") or "manual")
            self.development_profile_combo.addItem(f"{label} ({kind})", profile_id)
        index = self.development_profile_combo.findData(current)
        self.development_profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self.development_profile_combo.blockSignals(False)
        if hasattr(self, "development_profile_status_label"):
            active = self._development_profile_label(current)
            self.development_profile_status_label.setText(
                f"Perfiles de ajuste: {len(self._development_profiles)} | Activo: {active}"
            )

    def _on_development_output_space_changed(self) -> None:
        if not hasattr(self, "development_output_space_combo") or not hasattr(self, "combo_output_space"):
            return
        output_space = str(self.development_output_space_combo.currentData() or "scene_linear_camera_rgb")
        self.combo_output_space.blockSignals(True)
        self._set_combo_text(self.combo_output_space, output_space)
        self.combo_output_space.blockSignals(False)
        self._apply_output_space_defaults_to_controls(output_space)
        if self._original_linear is not None:
            self._schedule_preview_refresh()

    def _on_output_space_changed(self) -> None:
        if not hasattr(self, "combo_output_space"):
            return
        output_space = self.combo_output_space.currentText().strip()
        self._sync_development_output_space_combo(output_space)
        self._apply_output_space_defaults_to_controls(output_space)
        if self._original_linear is not None:
            self._schedule_preview_refresh()

    def _on_output_linear_toggled(self, checked: bool) -> None:
        if not hasattr(self, "combo_output_space"):
            return
        output_space = self.combo_output_space.currentText().strip()
        if checked and is_generic_output_space(output_space):
            self.check_output_linear.blockSignals(True)
            self.check_output_linear.setChecked(False)
            self.check_output_linear.blockSignals(False)
            self._set_status(self.tr("Los espacios estándar se exportan con salida no lineal e ICC estándar."))
        elif not checked and self._is_camera_output_space(output_space):
            self.check_output_linear.blockSignals(True)
            self.check_output_linear.setChecked(True)
            self.check_output_linear.blockSignals(False)
            self._set_status(self.tr("RGB de cámara se mantiene lineal para el ICC de entrada de sesión."))
        if self._original_linear is not None:
            self._schedule_preview_refresh()

    def _apply_output_space_defaults_to_controls(self, output_space: str) -> None:
        if not all(hasattr(self, name) for name in ("check_output_linear", "combo_tone_curve", "spin_gamma")):
            return
        if self._is_camera_output_space(output_space):
            self.check_output_linear.blockSignals(True)
            self.check_output_linear.setChecked(True)
            self.check_output_linear.blockSignals(False)
            self._set_combo_data(self.combo_tone_curve, "linear")
            return
        if not is_generic_output_space(output_space):
            return
        profile = generic_output_profile(output_space)
        self.check_output_linear.blockSignals(True)
        self.check_output_linear.setChecked(False)
        self.check_output_linear.blockSignals(False)
        if profile.key == "srgb":
            self._set_combo_data(self.combo_tone_curve, "srgb")
            self.spin_gamma.setValue(2.2)
        else:
            self._set_combo_data(self.combo_tone_curve, "gamma")
            self.spin_gamma.setValue(float(profile.gamma))

    def _sync_development_output_space_combo(self, output_space: str) -> None:
        if not hasattr(self, "development_output_space_combo"):
            return
        target = output_space if is_generic_output_space(output_space) else "scene_linear_camera_rgb"
        index = self.development_output_space_combo.findData(target)
        if index >= 0 and self.development_output_space_combo.currentIndex() != index:
            self.development_output_space_combo.blockSignals(True)
            self.development_output_space_combo.setCurrentIndex(index)
            self.development_output_space_combo.blockSignals(False)

    def _register_development_profile(self, descriptor: dict[str, Any], *, activate: bool = True) -> None:
        profile_id = str(descriptor.get("id") or "").strip()
        if not profile_id:
            return
        now = self._profile_timestamp()
        descriptor = dict(descriptor)
        descriptor.setdefault("created_at", now)
        descriptor["updated_at"] = now
        replaced = False
        for idx, existing in enumerate(self._development_profiles):
            if str(existing.get("id") or "") == profile_id:
                merged = dict(existing)
                merged.update(descriptor)
                self._development_profiles[idx] = merged
                replaced = True
                break
        if not replaced:
            self._development_profiles.append(descriptor)
        self._development_profiles.sort(key=lambda item: str(item.get("name") or item.get("id") or ""))
        if activate:
            self._active_development_profile_id = profile_id
        self._refresh_development_profile_combo()
        self._save_active_session(silent=True)

    def _development_profile_manifest(self, profile: dict[str, Any]) -> dict[str, Any]:
        manifest_path = self._session_stored_path(profile.get("manifest_path"))
        if manifest_path is None or not manifest_path.exists():
            return {}
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _development_profile_recipe(self, profile: dict[str, Any], manifest: dict[str, Any]) -> Recipe:
        recipe_path = self._session_stored_path(profile.get("recipe_path") or manifest.get("render_recipe_path"))
        if recipe_path is not None and recipe_path.exists():
            return load_recipe(recipe_path)
        recipe_payload = manifest.get("recipe") or manifest.get("calibrated_recipe")
        if isinstance(recipe_payload, dict):
            allowed = set(Recipe.__dataclass_fields__.keys())
            filtered = {k: v for k, v in recipe_payload.items() if k in allowed}
            return Recipe(**filtered)
        return self._build_effective_recipe()

    def _development_profile_settings(self, profile_id: str) -> dict[str, Any]:
        profile = self._development_profile_by_id(profile_id) if profile_id else None
        if profile is None:
            detail_state = self._detail_adjustment_state()
            render_state = self._render_adjustment_state()
            profile_path = self._active_session_icc_for_settings()
            return {
                "id": "",
                "name": "Ajustes actuales",
                "kind": "manual",
                "profile_type": "basic",
                "recipe": self._build_effective_recipe(),
                "detail_adjustments": detail_state,
                "render_adjustments": render_state,
                "icc_profile_path": profile_path,
                "output_icc_profile_path": None,
            }

        manifest = self._development_profile_manifest(profile)
        detail_state = manifest.get("detail_adjustments") if isinstance(manifest.get("detail_adjustments"), dict) else {}
        render_state = manifest.get("render_adjustments") if isinstance(manifest.get("render_adjustments"), dict) else {}
        icc_profile_path = self._session_stored_path(profile.get("icc_profile_path") or manifest.get("icc_profile_path"))
        output_icc_profile_path = self._session_stored_path(
            profile.get("output_icc_profile_path") or manifest.get("output_icc_profile_path")
        )
        kind = str(profile.get("kind") or manifest.get("kind") or "manual")
        profile_type = str(profile.get("profile_type") or manifest.get("profile_type") or "")
        if profile_type not in {"advanced", "basic"}:
            profile_type = self._adjustment_profile_type_for_kind(kind)
        return {
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or profile.get("id") or ""),
            "kind": kind,
            "profile_type": profile_type,
            "recipe": self._development_profile_recipe(profile, manifest),
            "detail_adjustments": detail_state or self._detail_adjustment_state(),
            "render_adjustments": render_state or self._render_adjustment_state(),
            "icc_profile_path": icc_profile_path,
            "output_icc_profile_path": output_icc_profile_path,
        }

    def _recipe_from_payload(self, payload: Any) -> Recipe | None:
        if not isinstance(payload, dict):
            return None
        try:
            allowed = set(Recipe.__dataclass_fields__.keys())
            filtered = {k: v for k, v in payload.items() if k in allowed}
            return Recipe(**filtered)
        except Exception:
            return None

    def _development_profile_from_sidecar(self, path: Path) -> str:
        try:
            payload = load_raw_sidecar(path)
        except Exception:
            return ""
        profile = payload.get("development_profile") if isinstance(payload, dict) else {}
        profile_id = str(profile.get("id") or "") if isinstance(profile, dict) else ""
        if profile_id and self._development_profile_by_id(profile_id) is not None:
            return profile_id
        return ""

    def _development_profile_payload_for_active_settings(self) -> dict[str, str]:
        profile_id = self._active_development_profile_id
        if not profile_id and hasattr(self, "development_profile_combo"):
            profile_id = str(self.development_profile_combo.currentData() or "")
        profile = self._development_profile_by_id(profile_id) if profile_id else None
        if profile is None:
            return {"id": "", "name": "Ajustes actuales", "kind": "manual", "profile_type": "basic"}
        kind = str(profile.get("kind") or "manual")
        return {
            "id": profile_id,
            "name": str(profile.get("name") or profile_id),
            "kind": kind,
            "profile_type": str(profile.get("profile_type") or self._adjustment_profile_type_for_kind(kind)),
        }

    def _profile_payload_from_development_settings(self, settings: dict[str, Any]) -> dict[str, str]:
        kind = str(settings.get("kind") or "manual")
        profile_type = str(settings.get("profile_type") or self._adjustment_profile_type_for_kind(kind))
        return {
            "id": str(settings.get("id") or ""),
            "name": str(settings.get("name") or "Ajustes actuales"),
            "kind": kind,
            "profile_type": profile_type,
        }

    def _render_profile_and_mode_for_development_settings(
        self,
        settings: dict[str, Any],
    ) -> tuple[Path | None, str]:
        recipe = settings["recipe"]
        stored_input_profile = settings.get("icc_profile_path")
        input_profile = (
            stored_input_profile
            if isinstance(stored_input_profile, Path) and stored_input_profile.exists()
            else None
        )
        issue = self._color_management_issue_for_recipe(
            recipe,
            input_profile_path=input_profile,
        )
        if issue is not None:
            raise RuntimeError(issue)
        if is_generic_output_space(recipe.output_space):
            rendered_profile = ensure_generic_output_profile(
                recipe.output_space,
                directory=self._session_generic_profile_dir(),
            )
            generic_key = generic_output_profile(recipe.output_space).key
            if input_profile is not None:
                mode = "converted_srgb" if generic_key == "srgb" else f"converted_{generic_key}"
            else:
                mode = f"standard_{generic_key}_output_icc"
            return rendered_profile, mode
        if input_profile is not None:
            return input_profile, "camera_rgb_with_input_icc"
        raise RuntimeError(self.tr("Gestión de color incompleta"))

    def _assign_development_profile_to_raw_files(
        self,
        profile_id: str,
        files: list[Path],
        *,
        status: str = "assigned",
    ) -> int:
        if not profile_id:
            return 0
        settings = self._development_profile_settings(profile_id)
        rendered_profile, mode = self._render_profile_and_mode_for_development_settings(settings)
        development_profile = self._profile_payload_from_development_settings(settings)
        written = 0
        for path in files:
            if path.suffix.lower() not in RAW_EXTENSIONS:
                continue
            try:
                sidecar = self._write_raw_settings_sidecar(
                    path,
                    recipe=settings["recipe"],
                    development_profile=development_profile,
                    detail_adjustments=settings["detail_adjustments"],
                    render_adjustments=settings["render_adjustments"],
                    profile_path=rendered_profile,
                    color_management_mode=mode,
                    status=status,
                )
            except Exception as exc:
                self._log_preview(f"No se pudo escribir mochila NexoRAW para {path.name}: {exc}")
                continue
            if sidecar is not None:
                written += 1
        if written:
            self._refresh_color_reference_thumbnail_markers()
        return written

    def _active_session_icc_for_settings(self) -> Path | None:
        if not hasattr(self, "path_profile_active") or not hasattr(self, "chk_apply_profile"):
            return None
        if not self.chk_apply_profile.isChecked():
            return None
        text = self.path_profile_active.text().strip()
        if not text:
            return None
        path = Path(text).expanduser()
        return path if path.exists() else None

    def _write_current_development_settings_to_raw(self, path: Path, *, status: str = "configured") -> Path | None:
        recipe = self._build_effective_recipe()
        _input_profile, rendered_profile, mode = self._configured_color_profile_for_recipe(recipe)
        sidecar = self._write_raw_settings_sidecar(
            path,
            recipe=recipe,
            development_profile=self._development_profile_payload_for_active_settings(),
            detail_adjustments=self._detail_adjustment_state(),
            render_adjustments=self._render_adjustment_state(),
            profile_path=rendered_profile,
            color_management_mode=mode,
            status=status,
        )
        if sidecar is not None:
            self._refresh_color_reference_thumbnail_markers()
        return sidecar

    def _raw_sidecar_development_summary(self, path: Path) -> str:
        try:
            payload = load_raw_sidecar(path)
        except Exception:
            return ""
        profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
        profile_type = self._adjustment_profile_type_from_sidecar(payload)
        name = str(profile.get("name") or profile.get("id") or "").strip()
        status = str(payload.get("status") or "").strip()
        label = "Perfil de ajuste avanzado" if profile_type == "advanced" else "Perfil de ajuste básico"
        if name:
            return f"{label}: {name}"
        if isinstance(payload.get("recipe"), dict):
            return f"{label} guardado"
        return f"Mochila NexoRAW: {status}" if status else ""

    def _has_raw_development_settings(self, path: Path) -> bool:
        if path.suffix.lower() not in RAW_EXTENSIONS:
            return False
        return bool(self._raw_sidecar_development_summary(path))

    def _adjustment_profile_type_from_sidecar(self, payload: dict[str, Any]) -> str:
        profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
        profile_type = str(profile.get("profile_type") or "").strip().lower()
        if profile_type in {"advanced", "basic"}:
            return profile_type
        kind = str(profile.get("kind") or "").strip().lower()
        if kind in {"chart", "advanced"}:
            return "advanced"
        return "basic" if isinstance(payload.get("recipe"), dict) else ""

    def _raw_adjustment_profile_type(self, path: Path) -> str:
        if path.suffix.lower() not in RAW_EXTENSIONS:
            return ""
        try:
            payload = load_raw_sidecar(path)
        except Exception:
            return ""
        return self._adjustment_profile_type_from_sidecar(payload)

    def _development_settings_payload_from_sidecar(self, source: Path, sidecar: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": str(source),
            "recipe": sidecar.get("recipe") if isinstance(sidecar.get("recipe"), dict) else {},
            "development_profile": sidecar.get("development_profile")
            if isinstance(sidecar.get("development_profile"), dict)
            else {},
            "detail_adjustments": sidecar.get("detail_adjustments")
            if isinstance(sidecar.get("detail_adjustments"), dict)
            else {},
            "render_adjustments": sidecar.get("render_adjustments")
            if isinstance(sidecar.get("render_adjustments"), dict)
            else {},
            "color_management": sidecar.get("color_management")
            if isinstance(sidecar.get("color_management"), dict)
            else {},
        }

    def _selected_or_current_file_paths(self) -> list[Path]:
        files = self._collect_selected_file_paths()
        if files:
            return files
        if self._selected_file is not None and self._selected_file.exists():
            return [self._selected_file]
        return []

    def _save_current_development_settings_to_selected(self) -> None:
        files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona uno o más RAW para guardar un perfil básico."))
            return
        written = 0
        errors: list[tuple[Path, Exception]] = []
        for path in files:
            try:
                if self._write_current_development_settings_to_raw(path) is not None:
                    written += 1
            except Exception as exc:
                errors.append((path, exc))
        if self._selected_file is not None and any(self._normalized_path_key(self._selected_file) == self._normalized_path_key(p) for p in files):
            self._apply_raw_sidecar_to_controls(self._selected_file)
        if errors:
            first_path, first_error = errors[0]
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("No se pudo escribir mochila"),
                self.tr("Fallaron") + f" {len(errors)} " + self.tr("archivo(s). Primer error:")
                + f"\n{first_path}\n{first_error}",
            )
        self._set_status(self.tr("Perfil básico guardado en") + f" {written} " + self.tr("imagen(es)"))

    def _copy_development_settings_from_selected(self) -> None:
        files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona un RAW con perfil de ajuste."))
            return
        source = files[0]
        try:
            sidecar = load_raw_sidecar(source)
        except FileNotFoundError:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("Esta imagen todavía no tiene perfil de ajuste guardado. Usa primero 'Guardar perfil básico en imagen' o genera un perfil con carta."),
            )
            return
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Mochila no válida"), str(exc))
            return
        self._development_settings_clipboard = self._development_settings_payload_from_sidecar(source, sidecar)
        profile_type = self._adjustment_profile_type_from_sidecar(sidecar)
        label = self.tr("avanzado") if profile_type == "advanced" else self.tr("básico")
        self._set_status(self.tr("Perfil de ajuste") + f" {label} " + self.tr("copiado:") + f" {source.name}")

    def _icc_profile_path_from_copied_settings(self, copied: dict[str, Any]) -> Path | None:
        color = copied.get("color_management") if isinstance(copied.get("color_management"), dict) else {}
        raw_path = str(color.get("icc_profile_path") or "").strip()
        if not raw_path:
            return None
        stored = self._session_stored_path(raw_path)
        if stored is not None and stored.exists():
            return stored
        path = Path(raw_path).expanduser()
        return path if path.exists() else None

    def _paste_development_settings_to_selected(self) -> None:
        copied = self._development_settings_clipboard
        if not copied:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "Copia primero un perfil de ajuste desde una miniatura.")
            return
        files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "Selecciona uno o más RAW de destino.")
            return
        recipe = self._recipe_from_payload(copied.get("recipe"))
        if recipe is None:
            QtWidgets.QMessageBox.warning(self, self.tr("Mochila no válida"), "El perfil de ajuste copiado no contiene una receta válida.")
            return
        profile = copied.get("development_profile") if isinstance(copied.get("development_profile"), dict) else {}
        detail = copied.get("detail_adjustments") if isinstance(copied.get("detail_adjustments"), dict) else {}
        render = copied.get("render_adjustments") if isinstance(copied.get("render_adjustments"), dict) else {}
        icc_path = self._icc_profile_path_from_copied_settings(copied)
        mode = str((copied.get("color_management") or {}).get("mode") or "")
        input_profile_for_issue = icc_path if not is_generic_output_space(recipe.output_space) else None
        if not self._require_color_managed_recipe_for_ui(
            recipe,
            input_profile_path=input_profile_for_issue,
            title=self.tr("Perfil de ajuste incompleto"),
        ):
            return
        written = 0
        errors: list[tuple[Path, Exception]] = []
        targets = {self._normalized_path_key(path) for path in files}
        profile_id = str(profile.get("id") or "")
        for path in files:
            try:
                sidecar = self._write_raw_settings_sidecar(
                    path,
                    recipe=recipe,
                    development_profile=profile,
                    detail_adjustments=detail,
                    render_adjustments=render,
                    profile_path=icc_path,
                    color_management_mode=mode or ("camera_rgb_with_input_icc" if icc_path is not None else "no_profile"),
                    status="configured",
                )
            except Exception as exc:
                errors.append((path, exc))
                sidecar = None
            if sidecar is not None:
                written += 1
            if profile_id:
                for item in self._develop_queue:
                    if self._normalized_path_key(Path(str(item.get("source") or ""))) == self._normalized_path_key(path):
                        item["development_profile_id"] = profile_id
                        item["status"] = "pending"
                        item["message"] = ""
        self._refresh_queue_table()
        self._refresh_color_reference_thumbnail_markers()
        self._save_active_session(silent=True)
        if self._selected_file is not None and self._normalized_path_key(self._selected_file) in targets:
            self._apply_raw_sidecar_to_controls(self._selected_file)
            if self._original_linear is not None:
                self._on_load_selected(show_message=False)
        if errors:
            first_path, first_error = errors[0]
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("No se pudo escribir mochila"),
                self.tr("Fallaron") + f" {len(errors)} " + self.tr("archivo(s). Primer error:")
                + f"\n{first_path}\n{first_error}",
            )
        self._set_status(self.tr("Perfil de ajuste pegado en") + f" {written} " + self.tr("imagen(es)"))

    def _apply_raw_sidecar_to_controls(self, path: Path) -> bool:
        try:
            payload = load_raw_sidecar(path)
        except FileNotFoundError:
            return False
        except Exception as exc:
            self._log_preview(f"Aviso: no se pudo leer mochila NexoRAW ({raw_sidecar_path(path).name}): {exc}")
            return False

        recipe = self._recipe_from_payload(payload.get("recipe"))
        if recipe is not None:
            self._apply_recipe_to_controls(recipe)
        detail_state = payload.get("detail_adjustments")
        if isinstance(detail_state, dict):
            self._apply_detail_adjustment_state(detail_state)
        render_state = payload.get("render_adjustments")
        if isinstance(render_state, dict):
            self._apply_render_adjustment_state(render_state)

        profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
        profile_id = str(profile.get("id") or "")
        if profile_id and self._development_profile_by_id(profile_id) is not None:
            self._active_development_profile_id = profile_id
            self._refresh_development_profile_combo()

        color = payload.get("color_management") if isinstance(payload.get("color_management"), dict) else {}
        icc_path = self._session_stored_path(color.get("icc_profile_path")) if color else None
        icc_role = str(color.get("icc_profile_role") or "") if color else ""
        if icc_role == "session_input_icc" and icc_path is not None and icc_path.exists() and self._profile_can_be_active(icc_path):
            self.path_profile_active.setText(str(icc_path))
            self.chk_apply_profile.setChecked(True)

        self._invalidate_preview_cache()
        self._log_preview(f"Mochila NexoRAW aplicada: {raw_sidecar_path(path).name}")
        return True

    def _write_raw_settings_sidecar(
        self,
        source: Path,
        *,
        recipe: Recipe,
        development_profile: dict[str, Any] | None,
        detail_adjustments: dict[str, Any],
        render_adjustments: dict[str, Any],
        profile_path: Path | None,
        color_management_mode: str | None = None,
        output_tiff: Path | None = None,
        proof_path: Path | None = None,
        status: str = "configured",
    ) -> Path | None:
        if source.suffix.lower() not in RAW_EXTENSIONS:
            return None
        session_name = self.session_name_edit.text().strip() if hasattr(self, "session_name_edit") else ""
        return write_raw_sidecar(
            source,
            recipe=recipe,
            development_profile=development_profile,
            detail_adjustments=detail_adjustments,
            render_adjustments=render_adjustments,
            icc_profile_path=profile_path,
            color_management_mode=color_management_mode,
            session_root=self._active_session_root,
            session_name=session_name,
            output_tiff=output_tiff,
            proof_path=proof_path,
            status=status,
        )

    def _save_current_development_profile(self) -> None:
        if self._active_session_root is None:
            self._on_create_session()
            if self._active_session_root is None:
                return
        name = self.development_profile_name_edit.text().strip() or "Perfil manual"
        profile_id = self._unique_development_profile_id(name)
        recipe = self._build_effective_recipe()
        active_icc = self._active_session_icc_for_settings()
        if not self._require_color_managed_recipe_for_ui(
            recipe,
            input_profile_path=active_icc,
            title=self.tr("Perfil de ajuste incompleto"),
        ):
            return
        output_icc = None
        if is_generic_output_space(recipe.output_space):
            try:
                output_icc = ensure_generic_output_profile(recipe.output_space, directory=self._session_generic_profile_dir())
            except Exception as exc:
                QtWidgets.QMessageBox.warning(
                    self,
                    self.tr("Perfil ICC estándar no disponible"),
                    str(exc),
                )
                return
        profile_dir = self._development_profile_dir(profile_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        recipe_path = profile_dir / "recipe.yml"
        manifest_path = profile_dir / "development_profile.json"
        save_recipe(recipe, recipe_path)
        manifest = {
            "id": profile_id,
            "name": name,
            "kind": "manual",
            "profile_type": "basic",
            "created_at": self._profile_timestamp(),
            "recipe_path": self._session_relative_or_absolute(recipe_path),
            "recipe": asdict(recipe),
            "detail_adjustments": self._detail_adjustment_state(),
            "render_adjustments": self._render_adjustment_state(),
            "icc_profile_path": self._session_relative_or_absolute(active_icc) if active_icc and active_icc.exists() else "",
            "generic_output_space": generic_output_profile(recipe.output_space).key if is_generic_output_space(recipe.output_space) else "",
            "output_icc_profile_path": self._session_relative_or_absolute(output_icc) if output_icc and output_icc.exists() else "",
        }
        write_json(manifest_path, manifest)
        self._register_development_profile(
            {
                "id": profile_id,
                "name": name,
                "kind": "manual",
                "profile_type": "basic",
                "recipe_path": self._session_relative_or_absolute(recipe_path),
                "manifest_path": self._session_relative_or_absolute(manifest_path),
                "icc_profile_path": manifest["icc_profile_path"],
                "generic_output_space": manifest["generic_output_space"],
                "output_icc_profile_path": manifest["output_icc_profile_path"],
            },
            activate=True,
        )
        self._set_status(self.tr("Perfil de ajuste básico guardado:") + f" {name}")

    def _activate_selected_development_profile(self) -> None:
        profile_id = str(self.development_profile_combo.currentData() or "")
        self._apply_development_profile_to_controls(profile_id)

    def _apply_development_profile_to_controls(self, profile_id: str) -> None:
        settings = self._development_profile_settings(profile_id)
        self._apply_recipe_to_controls(settings["recipe"])
        profile = self._development_profile_by_id(profile_id) if profile_id else None
        recipe_path = self._session_stored_path(profile.get("recipe_path")) if profile else None
        if recipe_path is not None:
            self.path_recipe.setText(str(recipe_path))
        self._apply_detail_adjustment_state(settings["detail_adjustments"])
        self._apply_render_adjustment_state(settings["render_adjustments"])
        icc_path = settings.get("icc_profile_path")
        if isinstance(icc_path, Path) and icc_path.exists() and self._profile_can_be_active(icc_path):
            self.path_profile_active.setText(str(icc_path))
            self.chk_apply_profile.setChecked(True)
        elif is_generic_output_space(settings["recipe"].output_space):
            self.path_profile_active.clear()
            self.chk_apply_profile.setChecked(False)
        self._active_development_profile_id = profile_id
        self._refresh_development_profile_combo()
        self._invalidate_preview_cache()
        self._save_active_session(silent=True)
        self._set_status(self.tr("Perfil de ajuste activo:") + f" {settings['name']}")

    def _register_chart_development_profile(
        self,
        *,
        name: str,
        development_profile_path: Path,
        calibrated_recipe_path: Path,
        icc_profile_path: Path,
        profile_report_path: Path,
    ) -> str:
        if self._active_session_root is None:
            return ""
        base_id = self._slug_for_development_profile(name)
        existing = self._development_profile_by_id(base_id)
        profile_id = base_id if existing is None else str(existing.get("id") or base_id)
        try:
            payload = json.loads(development_profile_path.read_text(encoding="utf-8")) if development_profile_path.exists() else {}
            if not isinstance(payload, dict):
                payload = {}
            payload.update(
                {
                    "id": profile_id,
                    "name": name,
                    "kind": "chart",
                    "profile_type": "advanced",
                    "recipe_path": self._session_relative_or_absolute(calibrated_recipe_path),
                    "icc_profile_path": self._session_relative_or_absolute(icc_profile_path),
                    "profile_report_path": self._session_relative_or_absolute(profile_report_path),
                    "detail_adjustments": self._detail_adjustment_state(),
                    "render_adjustments": self._render_adjustment_state(),
                }
            )
            write_json(development_profile_path, payload)
        except Exception:
            pass
        self._register_development_profile(
            {
                "id": profile_id,
                "name": name,
                "kind": "chart",
                "profile_type": "advanced",
                "recipe_path": self._session_relative_or_absolute(calibrated_recipe_path),
                "manifest_path": self._session_relative_or_absolute(development_profile_path),
                "icc_profile_path": self._session_relative_or_absolute(icc_profile_path),
                "profile_report_path": self._session_relative_or_absolute(profile_report_path),
            },
            activate=True,
        )
        return profile_id

    def _queue_assign_active_development_profile(self) -> None:
        profile_id = self._active_development_profile_id
        if not profile_id and hasattr(self, "development_profile_combo"):
            profile_id = str(self.development_profile_combo.currentData() or "")
        if not profile_id:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "Activa o guarda primero un perfil de ajuste.")
            return
        try:
            settings = self._development_profile_settings(profile_id)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Perfil de ajuste no válido"), str(exc))
            return
        rows = sorted({i.row() for i in self.queue_table.selectionModel().selectedRows()})
        if not rows:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "Selecciona filas de la cola.")
            return
        try:
            rendered_profile, mode = self._render_profile_and_mode_for_development_settings(settings)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Perfil de ajuste incompleto"), str(exc))
            return
        development_profile = self._profile_payload_from_development_settings(settings)
        errors: list[tuple[Path, Exception]] = []
        for row in rows:
            if 0 <= row < len(self._develop_queue):
                self._develop_queue[row]["development_profile_id"] = profile_id
                self._develop_queue[row]["status"] = "pending"
                self._develop_queue[row]["message"] = ""
                source_path = Path(str(self._develop_queue[row].get("source") or ""))
                try:
                    self._write_raw_settings_sidecar(
                        source_path,
                        recipe=settings["recipe"],
                        development_profile=development_profile,
                        detail_adjustments=settings["detail_adjustments"],
                        render_adjustments=settings["render_adjustments"],
                        profile_path=rendered_profile,
                        color_management_mode=mode,
                        status="assigned",
                    )
                except Exception as exc:
                    errors.append((source_path, exc))
        self._refresh_queue_table()
        self._refresh_color_reference_thumbnail_markers()
        self._save_active_session(silent=True)
        if errors:
            first_path, first_error = errors[0]
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("No se pudo escribir mochila"),
                self.tr("Fallaron") + f" {len(errors)} " + self.tr("archivo(s). Primer error:")
                + f"\n{first_path}\n{first_error}",
            )
        self._set_status(self.tr("Perfil asignado a") + f" {len(rows)} " + self.tr("elemento(s) de cola"))
