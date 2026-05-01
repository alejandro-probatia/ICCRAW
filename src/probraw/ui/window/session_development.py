from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class SessionDevelopmentMixin:
    def _profile_timestamp(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _icc_profile_suffixes(self) -> set[str]:
        return {str(suffix).lower() for suffix in PROFILE_FORMAT_OPTIONS}

    def _profile_file_timestamp(self, path: Path) -> str:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat()
        except Exception:
            return self._profile_timestamp()

    def _icc_profile_id_for_path(self, path: Path) -> str:
        stored = self._session_relative_or_absolute(path)
        digest = hashlib.sha1(stored.encode("utf-8")).hexdigest()[:12]
        slug = self._slug_for_development_profile(Path(path).stem)
        return f"icc-{slug}-{digest}"

    def _icc_profile_by_id(self, profile_id: str) -> dict[str, Any] | None:
        for profile in self._icc_profiles:
            if str(profile.get("id") or "") == profile_id:
                return profile
        return None

    def _icc_profile_by_path(self, path: Path) -> dict[str, Any] | None:
        try:
            target = path.expanduser().resolve(strict=False)
        except Exception:
            target = path.expanduser()
        for profile in self._icc_profiles:
            stored = self._session_stored_path(profile.get("path"))
            if stored is None:
                continue
            try:
                candidate = stored.expanduser().resolve(strict=False)
            except Exception:
                candidate = stored.expanduser()
            if candidate == target:
                return profile
        return None

    def _normalize_icc_profile_descriptor(self, descriptor: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(descriptor, dict):
            return None
        raw_path = (
            descriptor.get("path")
            or descriptor.get("icc_profile_path")
            or descriptor.get("profile_path")
        )
        path = self._session_stored_path(raw_path)
        if path is None or path.suffix.lower() not in self._icc_profile_suffixes() or not path.exists():
            return None

        report_path = self._session_stored_path(descriptor.get("profile_report_path"))
        development_profile_path = self._session_stored_path(descriptor.get("development_profile_path"))
        recipe_path = self._session_stored_path(descriptor.get("recipe_path"))
        status = str(descriptor.get("status") or self._profile_status_for_path(path) or "").strip().lower()
        if not status:
            status = "unknown"
        created_at = str(descriptor.get("created_at") or self._profile_file_timestamp(path))
        updated_at = str(descriptor.get("updated_at") or created_at)
        name = str(descriptor.get("name") or path.stem).strip() or path.stem

        normalized = {
            "id": str(descriptor.get("id") or self._icc_profile_id_for_path(path)),
            "name": name,
            "source": str(descriptor.get("source") or "generated"),
            "path": self._session_relative_or_absolute(path),
            "profile_report_path": self._session_relative_or_absolute(report_path) if report_path is not None else "",
            "development_profile_id": str(descriptor.get("development_profile_id") or ""),
            "development_profile_path": self._session_relative_or_absolute(development_profile_path)
            if development_profile_path is not None
            else "",
            "recipe_path": self._session_relative_or_absolute(recipe_path) if recipe_path is not None else "",
            "status": status,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        return normalized

    def _sort_icc_profiles(self) -> None:
        self._icc_profiles.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("name") or item.get("id") or ""),
            ),
            reverse=True,
        )

    def _coalesce_icc_profile_descriptors(self, descriptors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        by_path: dict[str, str] = {}
        for descriptor in descriptors:
            normalized = self._normalize_icc_profile_descriptor(descriptor)
            if normalized is None:
                continue
            profile_id = str(normalized.get("id") or "")
            path_key = str(normalized.get("path") or "")
            target_id = by_path.get(path_key, profile_id)
            if target_id in by_id:
                merged = dict(by_id[target_id])
                for key, value in normalized.items():
                    if value not in ("", None):
                        if key == "status" and value == "unknown" and merged.get("status"):
                            continue
                        if key == "created_at" and merged.get("created_at"):
                            continue
                        if key == "source" and value == "generated" and merged.get("source") not in ("", None, "generated"):
                            continue
                        merged[key] = value
                by_id[target_id] = merged
                by_path[path_key] = target_id
            else:
                by_id[profile_id] = normalized
                by_path[path_key] = profile_id
        result = list(by_id.values())
        result.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("name") or item.get("id") or ""),
            ),
            reverse=True,
        )
        return result

    def _session_icc_profile_scan_descriptors(self, *, paths: dict[str, Path] | None = None) -> list[dict[str, Any]]:
        if paths is None:
            if self._active_session_root is None:
                return []
            paths = self._session_paths_from_root(self._active_session_root)
        profiles_dir = paths.get("profiles")
        if profiles_dir is None or not profiles_dir.exists():
            return []
        descriptors: list[dict[str, Any]] = []
        try:
            candidates = sorted(
                p for p in profiles_dir.iterdir()
                if p.is_file() and p.suffix.lower() in self._icc_profile_suffixes()
            )
        except Exception:
            candidates = []
        for path in candidates:
            descriptors.append(
                {
                    "name": path.stem,
                    "source": "generated",
                    "path": str(path),
                    "created_at": self._profile_file_timestamp(path),
                    "updated_at": self._profile_file_timestamp(path),
                }
            )
        return descriptors

    def _icc_profile_descriptors_from_session_state(
        self,
        state: dict[str, Any],
        *,
        paths: dict[str, Path],
        defaults: dict[str, Path],
    ) -> list[dict[str, Any]]:
        descriptors: list[dict[str, Any]] = []
        raw_profiles = state.get("icc_profiles")
        if isinstance(raw_profiles, list):
            descriptors.extend(profile for profile in raw_profiles if isinstance(profile, dict))

        for key, source in (
            ("profile_active_path", "active"),
            ("profile_output_path", "generated"),
        ):
            path = self._session_stored_path(state.get(key))
            if path is not None and path.exists():
                descriptors.append({"path": str(path), "source": source, "name": path.stem})

        if defaults["profile_out"].exists():
            descriptors.append(
                {
                    "path": str(defaults["profile_out"]),
                    "source": "generated",
                    "name": defaults["profile_out"].stem,
                }
            )

        raw_development_profiles = state.get("development_profiles")
        if isinstance(raw_development_profiles, list):
            for profile in raw_development_profiles:
                if not isinstance(profile, dict):
                    continue
                icc_path = self._session_stored_path(profile.get("icc_profile_path"))
                if icc_path is None or not icc_path.exists():
                    continue
                descriptors.append(
                    {
                        "path": str(icc_path),
                        "source": "generated",
                        "name": str(profile.get("name") or icc_path.stem),
                        "development_profile_id": str(profile.get("id") or ""),
                        "development_profile_path": str(profile.get("manifest_path") or ""),
                        "profile_report_path": str(profile.get("profile_report_path") or ""),
                        "recipe_path": str(profile.get("recipe_path") or ""),
                    }
                )

        descriptors.extend(self._session_icc_profile_scan_descriptors(paths=paths))
        return descriptors

    def _load_session_icc_profiles(
        self,
        state: dict[str, Any],
        *,
        paths: dict[str, Path],
        defaults: dict[str, Path],
    ) -> None:
        self._icc_profiles = self._coalesce_icc_profile_descriptors(
            self._icc_profile_descriptors_from_session_state(state, paths=paths, defaults=defaults)
        )
        requested_active_id = str(state.get("active_icc_profile_id") or "")
        self._active_icc_profile_id = requested_active_id if self._icc_profile_by_id(requested_active_id) else ""

    def _sync_session_icc_profiles_from_disk(self) -> None:
        descriptors = list(self._icc_profiles)
        if self._active_session_root is not None:
            descriptors.extend(self._session_icc_profile_scan_descriptors())
        active = self.path_profile_active.text().strip() if hasattr(self, "path_profile_active") else ""
        if active:
            descriptors.append({"path": active, "source": "active", "name": Path(active).stem})
        self._icc_profiles = self._coalesce_icc_profile_descriptors(descriptors)
        self._sync_active_icc_profile_id_from_path()
        self._refresh_profile_management_views()

    def _sync_active_icc_profile_id_from_path(self) -> None:
        if not hasattr(self, "path_profile_active"):
            return
        text = self.path_profile_active.text().strip()
        if not text:
            self._active_icc_profile_id = ""
            return
        profile = self._icc_profile_by_path(Path(text).expanduser())
        self._active_icc_profile_id = str(profile.get("id") or "") if profile else ""

    def _session_icc_profiles_snapshot(self) -> list[dict[str, Any]]:
        return [dict(profile) for profile in self._icc_profiles]

    def _icc_profile_combo_label(self, profile: dict[str, Any]) -> str:
        name = str(profile.get("name") or profile.get("id") or "ICC")
        status = str(profile.get("status") or "").strip()
        source = str(profile.get("source") or "generated")
        suffixes = []
        if status and status != "unknown":
            suffixes.append(status)
        if source and source not in {"generated", "active"}:
            suffixes.append(source)
        if suffixes:
            return f"{name} ({', '.join(suffixes)})"
        return name

    def _refresh_icc_profile_combo(self) -> None:
        if not hasattr(self, "icc_profile_combo"):
            return
        current = self._active_icc_profile_id
        self.icc_profile_combo.blockSignals(True)
        self.icc_profile_combo.clear()
        self.icc_profile_combo.addItem(self.tr("Sin perfil ICC activo"), "")
        for profile in self._icc_profiles:
            profile_id = str(profile.get("id") or "")
            if not profile_id:
                continue
            self.icc_profile_combo.addItem(self._icc_profile_combo_label(profile), profile_id)
        index = self.icc_profile_combo.findData(current)
        self.icc_profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self.icc_profile_combo.blockSignals(False)
        if hasattr(self, "icc_profile_status_label"):
            active = self._icc_profile_by_id(current)
            active_label = self._icc_profile_combo_label(active) if active is not None else self.tr("ninguno")
            self.icc_profile_status_label.setText(
                f"Perfiles ICC de sesión: {len(self._icc_profiles)} | Activo: {active_label}"
            )

    def _managed_gamut_profile_items(self) -> list[tuple[str, str]]:
        return [
            (self.tr("Sesión:") + f" {self._icc_profile_combo_label(profile)}", f"managed:{profile.get('id')}")
            for profile in self._icc_profiles
            if str(profile.get("id") or "")
        ]

    def _refresh_gamut_profile_combos(self) -> None:
        for attr, default_key in (
            ("gamut_profile_a_combo", f"managed:{self._active_icc_profile_id}" if self._active_icc_profile_id else "generated"),
            ("gamut_profile_b_combo", "standard:srgb"),
        ):
            combo = getattr(self, attr, None)
            if combo is not None:
                self._populate_gamut_profile_combo(combo, default_key=default_key)
        if hasattr(self, "_sync_gamut_custom_controls"):
            self._sync_gamut_custom_controls()

    def _refresh_profile_management_views(self) -> None:
        self._refresh_icc_profile_combo()
        self._refresh_gamut_profile_combos()

    def _register_icc_profile(self, descriptor: dict[str, Any], *, activate: bool, save: bool = True) -> str:
        normalized = self._normalize_icc_profile_descriptor(descriptor)
        if normalized is None:
            return ""
        profile_id = str(normalized.get("id") or "")
        replaced = False
        for idx, existing in enumerate(self._icc_profiles):
            same_id = str(existing.get("id") or "") == profile_id
            same_path = str(existing.get("path") or "") == str(normalized.get("path") or "")
            if same_id or same_path:
                merged = dict(existing)
                for key, value in normalized.items():
                    if value in ("", None):
                        continue
                    if key == "status" and value == "unknown" and merged.get("status"):
                        continue
                    if key == "created_at" and merged.get("created_at"):
                        continue
                    if key == "source" and value == "generated" and merged.get("source") not in ("", None, "generated"):
                        continue
                    merged[key] = value
                self._icc_profiles[idx] = merged
                profile_id = str(merged.get("id") or profile_id)
                replaced = True
                break
        if not replaced:
            self._icc_profiles.append(normalized)
        self._sort_icc_profiles()
        if activate:
            self._activate_icc_profile_id(profile_id, save=False, refresh_preview=False)
        else:
            self._refresh_profile_management_views()
        if save:
            self._save_active_session(silent=True)
        return profile_id

    def _activate_icc_profile_id(
        self,
        profile_id: str,
        *,
        save: bool = True,
        refresh_preview: bool = True,
    ) -> bool:
        if not profile_id:
            self._active_icc_profile_id = ""
            if hasattr(self, "path_profile_active"):
                self.path_profile_active.clear()
            if hasattr(self, "chk_apply_profile"):
                self.chk_apply_profile.setChecked(False)
            self._refresh_profile_management_views()
            self._refresh_chart_diagnostics_from_session(focus=False)
            if save:
                self._save_active_session(silent=True)
            return True

        profile = self._icc_profile_by_id(profile_id)
        path = self._session_stored_path(profile.get("path")) if profile else None
        if profile is None or path is None or not path.exists() or not self._profile_can_be_active(path):
            return False
        self._active_icc_profile_id = profile_id
        self.path_profile_active.setText(str(path))
        self.chk_apply_profile.setChecked(True)
        self._refresh_profile_management_views()
        self._refresh_chart_diagnostics_from_session(focus=False)
        if refresh_preview:
            self._invalidate_preview_cache()
            self._schedule_preview_refresh()
        if save:
            self._save_active_session(silent=True)
        return True

    def _activate_selected_icc_profile(self) -> None:
        profile_id = str(self.icc_profile_combo.currentData() or "") if hasattr(self, "icc_profile_combo") else ""
        if not profile_id:
            self._activate_icc_profile_id("", save=True)
            self._set_status(self.tr("Perfil ICC activo desactivado"))
            return
        profile = self._icc_profile_by_id(profile_id)
        path = self._session_stored_path(profile.get("path")) if profile else None
        if profile is None or path is None or not path.exists() or not self._profile_can_be_active(path):
            status = self._profile_status_for_path(path) if path is not None else self.tr("no disponible")
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Perfil no activable"),
                self.tr("No se activa el perfil porque su estado QA es") + f" '{status}'.",
            )
            self._refresh_icc_profile_combo()
            return
        self._activate_icc_profile_id(profile_id, save=True)
        self._set_status(self.tr("Perfil activo:") + f" {path}")

    def _strip_version_suffix(self, stem: str) -> str:
        if len(stem) > 5 and stem[-5:-3] == "_v" and stem[-3:].isdigit():
            return stem[:-5]
        return stem

    def _next_generated_icc_profile_path(self, requested: Path) -> Path:
        requested = Path(requested).expanduser()
        base = requested.with_name(f"{self._strip_version_suffix(requested.stem)}{requested.suffix}")
        return versioned_output_path(base)

    def _profile_artifact_paths_for_generation(
        self,
        *,
        requested_profile_out: Path,
        requested_profile_report: Path,
        requested_workdir: Path,
        requested_development_profile: Path,
        requested_calibrated_recipe: Path,
    ) -> dict[str, Path]:
        profile_out = self._next_generated_icc_profile_path(requested_profile_out)
        if self._active_session_root is None:
            return {
                "profile_out": profile_out,
                "profile_report": versioned_output_path(requested_profile_report),
                "workdir": requested_workdir,
                "development_profile": versioned_output_path(requested_development_profile),
                "calibrated_recipe": versioned_output_path(requested_calibrated_recipe),
            }

        paths = self._session_paths_from_root(self._active_session_root)
        run_dir = paths["config"] / "profile_runs" / profile_out.stem
        return {
            "profile_out": profile_out,
            "profile_report": run_dir / "profile_report.json",
            "workdir": paths["work"] / "profile_generation" / profile_out.stem,
            "development_profile": run_dir / "development_profile.json",
            "calibrated_recipe": run_dir / "recipe_calibrated.yml",
        }

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

    @staticmethod
    def _recipe_uses_identity_fixed_wb(recipe: Recipe) -> bool:
        if str(recipe.white_balance_mode or "").strip().lower() != "fixed":
            return False
        values = [float(v) for v in (recipe.wb_multipliers or [])]
        if len(values) < 3:
            return False
        return all(abs(v - 1.0) <= 1e-6 for v in values[:4])

    def _visible_export_recipe_for_color_management(
        self,
        recipe: Recipe,
        *,
        input_profile_path: Path | None,
    ) -> Recipe:
        export_recipe = Recipe(**asdict(recipe))
        if input_profile_path is None and not is_generic_output_space(export_recipe.output_space):
            profile = generic_output_profile("prophoto_rgb")
            export_recipe.output_space = profile.key
            export_recipe.output_linear = False
            export_recipe.tone_curve = f"gamma:{profile.gamma:.3g}"
            export_recipe.profiling_mode = False

        export_recipe = self._normalize_recipe_output_for_color_management(export_recipe)
        if input_profile_path is None and is_generic_output_space(export_recipe.output_space):
            if bool(getattr(export_recipe, "profiling_mode", False)):
                export_recipe.profiling_mode = False
            if self._recipe_uses_identity_fixed_wb(export_recipe):
                export_recipe.white_balance_mode = "camera_metadata"
        return export_recipe

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
        if hasattr(self, "check_profiling_mode"):
            self.check_profiling_mode.setChecked(False)
        if (
            hasattr(self, "combo_wb_mode")
            and hasattr(self, "edit_wb_multipliers")
            and str(self.combo_wb_mode.currentData() or "").strip().lower() == "fixed"
            and self._recipe_uses_identity_fixed_wb(self._build_effective_recipe())
        ):
            self._set_combo_data(self.combo_wb_mode, "camera_metadata")
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

    def _development_settings_from_raw_sidecar(self, path: Path) -> dict[str, Any] | None:
        try:
            payload = load_raw_sidecar(path)
        except Exception:
            return None
        recipe = self._recipe_from_payload(payload.get("recipe"))
        if recipe is None:
            return None

        detail_state = payload.get("detail_adjustments")
        render_state = payload.get("render_adjustments")
        profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
        kind = str(profile.get("kind") or "manual")
        profile_type = str(profile.get("profile_type") or "").strip().lower()
        if profile_type not in {"advanced", "basic"}:
            profile_type = self._adjustment_profile_type_for_kind(kind)

        color = payload.get("color_management") if isinstance(payload.get("color_management"), dict) else {}
        icc_role = str(color.get("icc_profile_role") or "")
        color_mode = str(color.get("mode") or "")
        icc_path = self._session_stored_path(color.get("icc_profile_path")) if color else None
        input_profile_path = (
            icc_path
            if icc_path is not None
            and icc_path.exists()
            and (
                icc_role == "session_input_icc"
                or color_mode == "camera_rgb_with_input_icc"
                or self._is_camera_output_space(recipe.output_space)
            )
            else None
        )
        return {
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or raw_sidecar_path(path).name),
            "kind": kind,
            "profile_type": profile_type,
            "recipe": recipe,
            "detail_adjustments": detail_state if isinstance(detail_state, dict) else self._default_detail_adjustment_state(),
            "render_adjustments": render_state if isinstance(render_state, dict) else self._default_render_adjustment_state(),
            "icc_profile_path": input_profile_path,
            "output_icc_profile_path": None,
        }

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
                self._log_preview(f"No se pudo escribir mochila ProbRAW para {path.name}: {exc}")
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
        if isinstance(payload.get("mtf_analysis"), dict):
            return ""
        return f"Mochila ProbRAW: {status}" if status else ""

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

    def _default_unconfigured_recipe(self) -> Recipe:
        recipe = Recipe(
            white_balance_mode="camera_metadata",
            output_space="prophoto_rgb",
            profiling_mode=False,
        )
        return self._normalize_recipe_output_for_color_management(recipe)

    def _clear_active_input_profile_for_unconfigured_file(self) -> None:
        if hasattr(self, "path_profile_active"):
            self.path_profile_active.clear()
        if hasattr(self, "chk_apply_profile"):
            self.chk_apply_profile.setChecked(False)
        self._active_icc_profile_id = ""
        self._refresh_profile_management_views()

    def _reset_development_controls_for_unconfigured_file(self) -> None:
        self._apply_recipe_to_controls(self._default_unconfigured_recipe())
        self._apply_detail_adjustment_state(self._default_detail_adjustment_state())
        self._apply_render_adjustment_state(self._default_render_adjustment_state())
        self._active_development_profile_id = ""
        self._refresh_development_profile_combo()
        self._clear_active_input_profile_for_unconfigured_file()
        self._invalidate_preview_cache()

    def _apply_raw_sidecar_to_controls(self, path: Path) -> bool:
        try:
            payload = load_raw_sidecar(path)
        except FileNotFoundError:
            return False
        except Exception as exc:
            self._log_preview(f"Aviso: no se pudo leer mochila ProbRAW ({raw_sidecar_path(path).name}): {exc}")
            return False

        color = payload.get("color_management") if isinstance(payload.get("color_management"), dict) else {}
        icc_path = self._session_stored_path(color.get("icc_profile_path")) if color else None
        icc_role = str(color.get("icc_profile_role") or "") if color else ""
        input_profile_for_recipe = (
            icc_path
            if icc_role == "session_input_icc"
            and icc_path is not None
            and icc_path.exists()
            and self._profile_can_be_active(icc_path)
            else None
        )
        recipe = self._recipe_from_payload(payload.get("recipe")) or self._default_unconfigured_recipe()
        recipe = self._visible_export_recipe_for_color_management(
            recipe,
            input_profile_path=input_profile_for_recipe,
        )
        self._apply_recipe_to_controls(recipe)
        detail_state = payload.get("detail_adjustments")
        self._apply_detail_adjustment_state(
            detail_state if isinstance(detail_state, dict) else self._default_detail_adjustment_state()
        )
        render_state = payload.get("render_adjustments")
        self._apply_render_adjustment_state(
            render_state if isinstance(render_state, dict) else self._default_render_adjustment_state()
        )

        profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
        profile_id = str(profile.get("id") or "")
        if profile_id and self._development_profile_by_id(profile_id) is not None:
            self._active_development_profile_id = profile_id
            self._refresh_development_profile_combo()
        else:
            self._active_development_profile_id = ""
            self._refresh_development_profile_combo()

        if icc_role == "session_input_icc" and icc_path is not None and icc_path.exists() and self._profile_can_be_active(icc_path):
            self.path_profile_active.setText(str(icc_path))
            self.chk_apply_profile.setChecked(True)
            self._sync_active_icc_profile_id_from_path()
            self._refresh_profile_management_views()
        else:
            self._clear_active_input_profile_for_unconfigured_file()

        self._invalidate_preview_cache()
        self._log_preview(f"Mochila ProbRAW aplicada: {raw_sidecar_path(path).name}")
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
        input_profile = settings.get("icc_profile_path")
        recipe = self._visible_export_recipe_for_color_management(
            settings["recipe"],
            input_profile_path=input_profile if isinstance(input_profile, Path) and input_profile.exists() else None,
        )
        self._apply_recipe_to_controls(recipe)
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
            self._sync_active_icc_profile_id_from_path()
            self._refresh_profile_management_views()
        elif is_generic_output_space(settings["recipe"].output_space):
            self.path_profile_active.clear()
            self.chk_apply_profile.setChecked(False)
            self._sync_active_icc_profile_id_from_path()
            self._refresh_profile_management_views()
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
        profile_id = self._unique_development_profile_id(name)
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
