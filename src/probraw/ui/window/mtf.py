from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class MTFAnalysisMixin:
    MTF_EXTENDED_ANALYSIS_MAX_FREQUENCY = 1.0

    def _build_mtf_analysis_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.mtf_graph_tabs = QtWidgets.QTabWidget()
        self.mtf_graph_tabs.setDocumentMode(True)
        self.mtf_plot_esf = MTFPlotWidget("esf")
        self.mtf_plot_lsf = MTFPlotWidget("lsf")
        self.mtf_plot_mtf = MTFPlotWidget("mtf")
        self.mtf_metrics_table = self._make_mtf_result_table()
        self.mtf_context_table = self._make_mtf_result_table()
        self.mtf_details_table = self.mtf_context_table
        self.mtf_graph_tabs.addTab(self.mtf_plot_esf, "ESF")
        self.mtf_graph_tabs.addTab(self.mtf_plot_lsf, "LSF")
        self.mtf_graph_tabs.addTab(self.mtf_plot_mtf, "MTF")
        self.mtf_graph_tabs.addTab(self.mtf_metrics_table, self.tr("Métricas MTF"))
        self.mtf_graph_tabs.addTab(self.mtf_context_table, self.tr("Contexto técnico"))
        self.mtf_result_tabs = self.mtf_graph_tabs
        self.mtf_graph_tabs.setMinimumHeight(320)
        self.mtf_graph_tabs.setMaximumHeight(430)
        layout.addWidget(self.mtf_graph_tabs, 1)

        tools = QtWidgets.QHBoxLayout()
        self.btn_mtf_select_roi = QtWidgets.QPushButton(self.tr("Seleccionar borde"))
        self.btn_mtf_select_roi.setCheckable(True)
        self.btn_mtf_select_roi.clicked.connect(self._toggle_mtf_roi_selection)
        tools.addWidget(self.btn_mtf_select_roi)
        tools.addWidget(self._button(self.tr("Actualizar"), self._recalculate_mtf_analysis))
        tools.addWidget(self._button(self.tr("Ampliar"), self._show_mtf_expanded_dialog))
        tools.addWidget(self._button(self.tr("Copiar datos"), self._copy_mtf_analysis_data))
        tools.addWidget(self._button(self.tr("Exportar CSV"), self._export_mtf_analysis_csv))
        tools.addWidget(self._button(self.tr("Limpiar"), self._clear_mtf_roi))
        layout.addLayout(tools)

        options = QtWidgets.QGridLayout()
        self.check_mtf_auto_update = QtWidgets.QCheckBox(self.tr("Actualizar MTF con los ajustes"))
        self.check_mtf_auto_update.setChecked(True)
        options.addWidget(self.check_mtf_auto_update, 0, 0, 1, 2)

        options.addWidget(QtWidgets.QLabel(self.tr("Sensor ancho (mm)")), 1, 0)
        self.spin_mtf_sensor_width_mm = QtWidgets.QDoubleSpinBox()
        self.spin_mtf_sensor_width_mm.setRange(0.0, 200.0)
        self.spin_mtf_sensor_width_mm.setDecimals(3)
        self.spin_mtf_sensor_width_mm.setSingleStep(0.1)
        self.spin_mtf_sensor_width_mm.setSpecialValueText(self.tr("sin dato"))
        self.spin_mtf_sensor_width_mm.valueChanged.connect(self._on_mtf_manual_sensor_size_changed)
        options.addWidget(self.spin_mtf_sensor_width_mm, 1, 1)

        options.addWidget(QtWidgets.QLabel(self.tr("Sensor alto (mm)")), 2, 0)
        self.spin_mtf_sensor_height_mm = QtWidgets.QDoubleSpinBox()
        self.spin_mtf_sensor_height_mm.setRange(0.0, 200.0)
        self.spin_mtf_sensor_height_mm.setDecimals(3)
        self.spin_mtf_sensor_height_mm.setSingleStep(0.1)
        self.spin_mtf_sensor_height_mm.setSpecialValueText(self.tr("sin dato"))
        self.spin_mtf_sensor_height_mm.valueChanged.connect(self._on_mtf_manual_sensor_size_changed)
        options.addWidget(self.spin_mtf_sensor_height_mm, 2, 1)

        options.addWidget(QtWidgets.QLabel(self.tr("Tamaño de píxel (µm)")), 3, 0)
        self.spin_mtf_pixel_pitch_um = QtWidgets.QDoubleSpinBox()
        self.spin_mtf_pixel_pitch_um.setRange(0.0, 50.0)
        self.spin_mtf_pixel_pitch_um.setDecimals(3)
        self.spin_mtf_pixel_pitch_um.setSingleStep(0.1)
        self.spin_mtf_pixel_pitch_um.setSpecialValueText(self.tr("sin dato"))
        self.spin_mtf_pixel_pitch_um.valueChanged.connect(self._on_mtf_pixel_pitch_changed)
        options.addWidget(self.spin_mtf_pixel_pitch_um, 3, 1)
        self.mtf_pixel_pitch_source_label = QtWidgets.QLabel(self.tr("Pitch: pendiente de metadatos"))
        self.mtf_pixel_pitch_source_label.setWordWrap(True)
        self.mtf_pixel_pitch_source_label.setStyleSheet("font-size: 11px; color: #94a3b8;")
        options.addWidget(self.mtf_pixel_pitch_source_label, 4, 0, 1, 2)
        layout.addLayout(options)

        self.mtf_metrics_label = QtWidgets.QLabel(self.tr("MTF: selecciona una ROI con un borde inclinado."))
        self.mtf_metrics_label.setWordWrap(True)
        self.mtf_metrics_label.setStyleSheet("font-size: 12px; color: #cbd5e1;")
        layout.addWidget(self.mtf_metrics_label)
        return panel

    def _make_mtf_result_table(self) -> QtWidgets.QTableWidget:
        table = QtWidgets.QTableWidget(0, 2)
        table.setHorizontalHeaderLabels([self.tr("Dato"), self.tr("Valor")])
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        return table

    def _auto_update_mtf_pixel_pitch_from_file(self, path: Path | None = None) -> None:
        selected = path or getattr(self, "_selected_file", None)
        if selected is None or self._original_linear is None:
            return
        try:
            h, w = int(self._original_linear.shape[0]), int(self._original_linear.shape[1])
        except Exception:
            h, w = 0, 0
        image_dimensions = self._mtf_analysis_image_dimensions()
        if image_dimensions is None and self._effective_preview_max_side() <= 0 and w and h:
            image_dimensions = (w, h)
        try:
            estimated = estimate_pixel_pitch_um(Path(selected), image_dimensions=image_dimensions)
        except Exception:
            estimated = None
        if estimated is None:
            if self._apply_mtf_manual_sensor_size_pitch():
                return
            if (
                getattr(self, "_mtf_pixel_pitch_auto_source", None) == "manual_pixel_pitch"
                and hasattr(self, "spin_mtf_pixel_pitch_um")
                and self.spin_mtf_pixel_pitch_um.value() > 0.0
            ):
                if hasattr(self, "mtf_pixel_pitch_source_label"):
                    self.mtf_pixel_pitch_source_label.setText(self.tr("Pitch: manual"))
                self._update_mtf_result_widgets()
                return
            if hasattr(self, "spin_mtf_pixel_pitch_um"):
                self.spin_mtf_pixel_pitch_um.blockSignals(True)
                self.spin_mtf_pixel_pitch_um.setValue(0.0)
                self.spin_mtf_pixel_pitch_um.blockSignals(False)
            self._mtf_pixel_pitch_auto_source = None
            if hasattr(self, "mtf_pixel_pitch_source_label"):
                self.mtf_pixel_pitch_source_label.setText(self.tr("Pitch: no disponible en metadatos"))
            self._update_mtf_result_widgets()
            return
        pitch, source = estimated
        if hasattr(self, "spin_mtf_pixel_pitch_um"):
            self.spin_mtf_pixel_pitch_um.blockSignals(True)
            self.spin_mtf_pixel_pitch_um.setValue(float(pitch))
            self.spin_mtf_pixel_pitch_um.blockSignals(False)
        self._mtf_pixel_pitch_auto_source = str(source)
        if hasattr(self, "mtf_pixel_pitch_source_label"):
            self.mtf_pixel_pitch_source_label.setText(
                self.tr("Pitch estimado desde metadatos") + f": {float(pitch):.3f} µm ({self._mtf_pitch_source_label(source)})"
            )
        self._update_mtf_result_widgets()

    def _on_mtf_pixel_pitch_changed(self, value: float) -> None:
        self._mtf_pixel_pitch_auto_source = "manual_pixel_pitch" if float(value) > 0.0 else None
        if hasattr(self, "mtf_pixel_pitch_source_label"):
            if float(value) > 0.0:
                self.mtf_pixel_pitch_source_label.setText(self.tr("Pitch: manual"))
            else:
                self.mtf_pixel_pitch_source_label.setText(self.tr("Pitch: pendiente de metadatos"))
        self._update_mtf_result_widgets()

    def _on_mtf_manual_sensor_size_changed(self, _value: float) -> None:
        if self._apply_mtf_manual_sensor_size_pitch():
            return
        if getattr(self, "_mtf_pixel_pitch_auto_source", None) == "manual_sensor_size":
            self._mtf_pixel_pitch_auto_source = None
            if hasattr(self, "spin_mtf_pixel_pitch_um"):
                self.spin_mtf_pixel_pitch_um.blockSignals(True)
                self.spin_mtf_pixel_pitch_um.setValue(0.0)
                self.spin_mtf_pixel_pitch_um.blockSignals(False)
            if hasattr(self, "mtf_pixel_pitch_source_label"):
                self.mtf_pixel_pitch_source_label.setText(self.tr("Pitch: pendiente de metadatos"))
            self._update_mtf_result_widgets()

    def _apply_mtf_manual_sensor_size_pitch(self) -> bool:
        dimensions = self._mtf_analysis_image_dimensions()
        if dimensions is None and self._effective_preview_max_side() <= 0:
            dimensions = self._mtf_current_image_dimensions()
        if dimensions is None or not hasattr(self, "spin_mtf_pixel_pitch_um"):
            return False
        width_px, height_px = dimensions
        sensor_width = self.spin_mtf_sensor_width_mm.value() if hasattr(self, "spin_mtf_sensor_width_mm") else 0.0
        sensor_height = self.spin_mtf_sensor_height_mm.value() if hasattr(self, "spin_mtf_sensor_height_mm") else 0.0
        candidates: list[float] = []
        if sensor_width > 0.0 and width_px > 0:
            candidates.append(float(sensor_width) * 1000.0 / float(width_px))
        if sensor_height > 0.0 and height_px > 0:
            candidates.append(float(sensor_height) * 1000.0 / float(height_px))
        candidates = [value for value in candidates if 0.1 <= value <= 50.0]
        if not candidates:
            return False
        pitch = float(sum(candidates) / len(candidates))
        self.spin_mtf_pixel_pitch_um.blockSignals(True)
        self.spin_mtf_pixel_pitch_um.setValue(pitch)
        self.spin_mtf_pixel_pitch_um.blockSignals(False)
        self._mtf_pixel_pitch_auto_source = "manual_sensor_size"
        if hasattr(self, "mtf_pixel_pitch_source_label"):
            self.mtf_pixel_pitch_source_label.setText(
                self.tr("Pitch calculado desde sensor manual")
                + f": {pitch:.3f} µm ({width_px}x{height_px} px)"
            )
        self._update_mtf_result_widgets()
        return True

    def _mtf_current_image_dimensions(self) -> tuple[int, int] | None:
        image = getattr(self, "_original_linear", None)
        if image is None:
            image = self._mtf_source_image()
        if image is None:
            return None
        try:
            height, width = int(image.shape[0]), int(image.shape[1])
        except Exception:
            return None
        if width <= 0 or height <= 0:
            return None
        return width, height

    def _mtf_analysis_image_dimensions(self) -> tuple[int, int] | None:
        dimensions = getattr(self, "_mtf_last_analysis_image_dimensions", None)
        if isinstance(dimensions, (list, tuple)) and len(dimensions) >= 2:
            try:
                width = int(dimensions[0])
                height = int(dimensions[1])
            except (TypeError, ValueError):
                return None
            if width > 0 and height > 0:
                return width, height
        return None

    def _mtf_pitch_source_label(self, source: str) -> str:
        labels = {
            "sensor_width_height": self.tr("tamaño de sensor"),
            "sensor_width": self.tr("anchura de sensor"),
            "sensor_height": self.tr("altura de sensor"),
            "focal_plane_resolution": self.tr("resolución de plano focal"),
            "35mm_equivalent": self.tr("equivalencia 35 mm"),
            "manual_pixel_pitch": self.tr("manual"),
            "manual_sensor_size": self.tr("sensor manual"),
            "sidecar": self.tr("sidecar"),
        }
        return labels.get(str(source), str(source))

    def _toggle_mtf_roi_selection(self, checked: bool = False) -> None:
        if checked and self._original_linear is None:
            self._set_mtf_roi_selection_active(False)
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Carga primero una imagen en el visor."))
            return
        self._set_mtf_roi_selection_active(bool(checked))
        if checked:
            self._manual_chart_marking = False
            self._set_neutral_picker_active(False)
            if hasattr(self, "_sync_manual_chart_overlay"):
                self._sync_manual_chart_overlay()
            self._set_status(self.tr("MTF: arrastra un rectángulo alrededor de un borde inclinado"))
        else:
            self._set_status(self.tr("Selección MTF desactivada"))

    def _set_mtf_roi_selection_active(self, active: bool) -> None:
        self._mtf_roi_selection_active = bool(active)
        if hasattr(self, "btn_mtf_select_roi"):
            self.btn_mtf_select_roi.blockSignals(True)
            self.btn_mtf_select_roi.setChecked(self._mtf_roi_selection_active)
            self.btn_mtf_select_roi.blockSignals(False)
        for panel_name in ("image_result_single", "image_result_compare"):
            panel = getattr(self, panel_name, None)
            if panel is not None and hasattr(panel, "set_roi_selection_enabled"):
                panel.set_roi_selection_enabled(self._mtf_roi_selection_active)

    def _on_mtf_roi_selected(self, x: float, y: float, width: float, height: float) -> None:
        self._mtf_roi = (
            int(round(float(x))),
            int(round(float(y))),
            int(round(float(width))),
            int(round(float(height))),
        )
        self._set_mtf_roi_selection_active(False)
        self._sync_mtf_roi_overlay()
        self._recalculate_mtf_analysis()

    def _sync_mtf_roi_overlay(self) -> None:
        for panel_name in ("image_result_single", "image_result_compare"):
            panel = getattr(self, panel_name, None)
            if panel is not None and hasattr(panel, "set_roi_rect"):
                panel.set_roi_rect(self._mtf_roi)

    def _clear_mtf_roi(self) -> None:
        self._mtf_roi = None
        self._mtf_last_result = None
        self._mtf_last_analysis_image_dimensions = None
        self._mtf_last_display_dimensions = None
        self._mtf_last_display_roi = None
        self._set_mtf_roi_selection_active(False)
        for panel_name in ("image_result_single", "image_result_compare"):
            panel = getattr(self, panel_name, None)
            if panel is not None and hasattr(panel, "clear_roi_rect"):
                panel.clear_roi_rect()
        self._update_mtf_result_widgets()

    def _clear_mtf_roi_for_file_change(self) -> None:
        if (
            getattr(self, "_mtf_roi", None) is not None
            or getattr(self, "_mtf_last_result", None) is not None
            or bool(getattr(self, "_mtf_roi_selection_active", False))
        ):
            self._clear_mtf_roi()

    def _restore_persisted_mtf_analysis_for_selected(self, path: Path | None = None) -> None:
        selected = path or getattr(self, "_selected_file", None)
        if selected is None:
            return
        payload = self._load_persisted_mtf_analysis(Path(selected))
        if payload is None:
            return
        result = self._mtf_result_from_payload(payload)
        if result is None:
            return
        summary = self._mtf_payload_summary(payload)
        analysis_dimensions = self._mtf_payload_dimensions(summary.get("image_dimensions_px"))
        stored_display_dimensions = self._mtf_payload_dimensions(summary.get("display_dimensions_px"))
        current_display_dimensions = self._mtf_current_image_dimensions()
        display_dimensions = current_display_dimensions or stored_display_dimensions
        stored_display_roi = self._mtf_payload_roi(summary.get("display_roi"))
        display_roi = None
        if (
            stored_display_roi is not None
            and stored_display_dimensions is not None
            and current_display_dimensions == stored_display_dimensions
        ):
            display_roi = stored_display_roi
        if display_roi is None:
            display_roi = self._mtf_display_roi_from_analysis_roi(result.roi, analysis_dimensions)
        if display_roi == result.roi and current_display_dimensions is None and stored_display_roi is not None:
            display_roi = stored_display_roi
        self._restore_mtf_pixel_pitch_from_payload(payload)
        self._mtf_last_analysis_image_dimensions = analysis_dimensions
        self._mtf_last_display_dimensions = display_dimensions
        self._mtf_last_display_roi = display_roi
        self._mtf_roi = display_roi
        self._mtf_last_result = result
        self._set_mtf_roi_selection_active(False)
        self._sync_mtf_roi_overlay()
        self._update_mtf_result_widgets()
        self._set_status(self.tr("MTF recuperada del sidecar:") + f" {Path(selected).name}")

    def _mtf_result_from_payload(self, payload: dict[str, Any]) -> MTFResult | None:
        summary = self._mtf_payload_summary(payload)
        roi = self._mtf_payload_roi(summary.get("roi"))
        if roi is None:
            return None
        roi_shape = self._mtf_payload_roi_shape(summary.get("roi_shape"), roi)
        curves = payload.get("curves") if isinstance(payload.get("curves"), dict) else {}
        esf_distance, esf = self._mtf_payload_curve(curves.get("esf"), "distance_px", "signal")
        lsf_distance, lsf = self._mtf_payload_curve(curves.get("lsf"), "distance_px", "derivative")
        frequency, mtf = self._mtf_payload_curve(curves.get("mtf"), "frequency_cycles_per_pixel", "modulation")
        frequency_extended, mtf_extended = self._mtf_payload_curve(
            curves.get("mtf_extended"),
            "frequency_cycles_per_pixel",
            "modulation",
        )
        warnings_value = summary.get("warnings")
        warnings = [str(value) for value in warnings_value] if isinstance(warnings_value, list) else []
        return MTFResult(
            roi=roi,
            roi_shape=roi_shape,
            edge_angle_degrees=self._mtf_payload_float(summary.get("edge_angle_degrees"), default=0.0),
            edge_contrast=self._mtf_payload_float(summary.get("edge_contrast"), default=0.0),
            overshoot=self._mtf_payload_float(summary.get("overshoot"), default=0.0),
            undershoot=self._mtf_payload_float(summary.get("undershoot"), default=0.0),
            mtf50=self._mtf_payload_optional_float(summary.get("mtf50")),
            mtf30=self._mtf_payload_optional_float(summary.get("mtf30")),
            mtf10=self._mtf_payload_optional_float(summary.get("mtf10")),
            acutance=self._mtf_payload_float(summary.get("acutance"), default=0.0),
            esf_distance=esf_distance,
            esf=esf,
            lsf_distance=lsf_distance,
            lsf=lsf,
            frequency=frequency,
            mtf=mtf,
            frequency_extended=frequency_extended,
            mtf_extended=mtf_extended,
            warnings=warnings,
        )

    def _restore_mtf_pixel_pitch_from_payload(self, payload: dict[str, Any]) -> None:
        if not hasattr(self, "spin_mtf_pixel_pitch_um"):
            return
        summary = self._mtf_payload_summary(payload)
        pitch = self._mtf_payload_optional_float(summary.get("pixel_pitch_um"))
        if pitch is None or pitch <= 0.0:
            return
        source = summary.get("pixel_pitch_source")
        self.spin_mtf_pixel_pitch_um.blockSignals(True)
        self.spin_mtf_pixel_pitch_um.setValue(float(pitch))
        self.spin_mtf_pixel_pitch_um.blockSignals(False)
        self._mtf_pixel_pitch_auto_source = str(source) if source else "sidecar"
        if hasattr(self, "mtf_pixel_pitch_source_label"):
            self.mtf_pixel_pitch_source_label.setText(
                self.tr("Pitch recuperado de MTF guardada")
                + f": {float(pitch):.3f} µm ({self._mtf_pitch_source_label(self._mtf_pixel_pitch_auto_source)})"
            )

    def _mtf_payload_roi(self, value: Any) -> tuple[int, int, int, int] | None:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return None
        try:
            x, y, width, height = [int(round(float(v))) for v in value]
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        return x, y, width, height

    def _mtf_payload_roi_shape(self, value: Any, roi: tuple[int, int, int, int]) -> tuple[int, int]:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                height = int(round(float(value[0])))
                width = int(round(float(value[1])))
                if height > 0 and width > 0:
                    return height, width
            except (TypeError, ValueError):
                pass
        return int(roi[3]), int(roi[2])

    def _mtf_payload_dimensions(self, value: Any) -> tuple[int, int] | None:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        try:
            width = int(round(float(value[0])))
            height = int(round(float(value[1])))
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        return width, height

    def _mtf_payload_curve(self, value: Any, x_key: str, y_key: str) -> tuple[list[float], list[float]]:
        if not isinstance(value, list):
            return [], []
        x_values: list[float] = []
        y_values: list[float] = []
        for point in value:
            if not isinstance(point, dict):
                continue
            x = self._mtf_payload_optional_float(point.get(x_key))
            y = self._mtf_payload_optional_float(point.get(y_key))
            if x is None or y is None:
                continue
            x_values.append(x)
            y_values.append(y)
        return x_values, y_values

    def _mtf_payload_float(self, value: Any, *, default: float) -> float:
        parsed = self._mtf_payload_optional_float(value)
        return float(default) if parsed is None else parsed

    def _mtf_payload_optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if np.isfinite(number) else None

    def _mtf_source_image(self) -> np.ndarray | None:
        if self._preview_srgb is not None:
            return np.asarray(self._preview_srgb, dtype=np.float32)
        if self._adjusted_linear is not None:
            return linear_to_srgb_display(self._adjusted_linear)
        if self._original_linear is not None:
            return linear_to_srgb_display(self._original_linear)
        return None

    def _mtf_full_resolution_base_image(self) -> np.ndarray | None:
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            return None
        path = Path(selected).expanduser()
        if not path.exists() or not path.is_file():
            return None
        if path.suffix.lower() in RAW_EXTENSIONS:
            recipe = self._build_effective_recipe()
            if is_standard_output_space(recipe.output_space):
                image = develop_standard_output_array(path, recipe, half_size=False)
            else:
                image = develop_image_array(path, recipe, half_size=False)
        else:
            image = read_image(path)
        image = np.asarray(image, dtype=np.float32)
        if image.ndim == 2:
            image = np.repeat(image[..., None], 3, axis=2)
        if image.ndim != 3 or image.shape[2] < 3:
            raise ValueError(f"Imagen inesperada para MTF: shape={image.shape}")
        return np.clip(image[..., :3], 0.0, 1.0).astype(np.float32, copy=False)

    def _mtf_full_resolution_analysis_image(self) -> np.ndarray | None:
        base = self._mtf_full_resolution_base_image()
        if base is None:
            return None
        nl = self.slider_noise_luma.value() / 100.0 if hasattr(self, "slider_noise_luma") else 0.0
        nc = self.slider_noise_color.value() / 100.0 if hasattr(self, "slider_noise_color") else 0.0
        sharpen = self.slider_sharpen.value() / 100.0 if hasattr(self, "slider_sharpen") else 0.0
        radius = self.slider_radius.value() / 10.0 if hasattr(self, "slider_radius") else 1.0
        ca_red, ca_blue = self._ca_scale_factors() if hasattr(self, "_ca_scale_factors") else (1.0, 1.0)
        adjusted = apply_adjustments(
            base,
            denoise_luminance=float(nl),
            denoise_color=float(nc),
            sharpen_amount=float(sharpen),
            sharpen_radius=float(radius),
            lateral_ca_red_scale=float(ca_red),
            lateral_ca_blue_scale=float(ca_blue),
        )
        render_kwargs = self._render_adjustment_kwargs() if hasattr(self, "_render_adjustment_kwargs") else {}
        adjusted = apply_render_adjustments(adjusted, **render_kwargs)
        return linear_to_srgb_display(adjusted)

    def _mtf_roi_for_analysis_image(
        self,
        roi: tuple[int, int, int, int],
        analysis_dimensions: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        display_dimensions = self._mtf_current_image_dimensions()
        if display_dimensions is None or display_dimensions == analysis_dimensions:
            return roi
        display_w, display_h = display_dimensions
        analysis_w, analysis_h = analysis_dimensions
        if display_w <= 0 or display_h <= 0 or analysis_w <= 0 or analysis_h <= 0:
            return roi
        scale_x = float(analysis_w) / float(display_w)
        scale_y = float(analysis_h) / float(display_h)
        x, y, width, height = roi
        return (
            int(round(float(x) * scale_x)),
            int(round(float(y) * scale_y)),
            max(1, int(round(float(width) * scale_x))),
            max(1, int(round(float(height) * scale_y))),
        )

    def _mtf_display_roi_from_analysis_roi(
        self,
        roi: tuple[int, int, int, int],
        analysis_dimensions: tuple[int, int] | None,
    ) -> tuple[int, int, int, int]:
        display_dimensions = self._mtf_current_image_dimensions()
        if analysis_dimensions is None or display_dimensions is None or analysis_dimensions == display_dimensions:
            return roi
        analysis_w, analysis_h = analysis_dimensions
        display_w, display_h = display_dimensions
        if analysis_w <= 0 or analysis_h <= 0 or display_w <= 0 or display_h <= 0:
            return roi
        scale_x = float(display_w) / float(analysis_w)
        scale_y = float(display_h) / float(analysis_h)
        x, y, width, height = roi
        return (
            int(round(float(x) * scale_x)),
            int(round(float(y) * scale_y)),
            max(1, int(round(float(width) * scale_x))),
            max(1, int(round(float(height) * scale_y))),
        )

    def _recalculate_mtf_analysis(self) -> None:
        if getattr(self, "_mtf_roi", None) is None:
            self._update_mtf_result_widgets(error=self.tr("MTF: selecciona una ROI de borde inclinado."))
            return
        self._set_status(self.tr("MTF: cargando fuente a resolución real..."))
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        image = self._mtf_full_resolution_analysis_image()
        if image is None:
            self._update_mtf_result_widgets(error=self.tr("MTF: no se pudo cargar la imagen a resolución real."))
            return
        analysis_dimensions = (int(image.shape[1]), int(image.shape[0]))
        display_dimensions = self._mtf_current_image_dimensions()
        display_roi = self._mtf_roi
        analysis_roi = self._mtf_roi_for_analysis_image(display_roi, analysis_dimensions)
        self._mtf_last_analysis_image_dimensions = analysis_dimensions
        self._mtf_last_display_dimensions = display_dimensions
        self._mtf_last_display_roi = display_roi
        if getattr(self, "_mtf_pixel_pitch_auto_source", None) in {None, "manual_sensor_size"}:
            self._apply_mtf_manual_sensor_size_pitch()
        try:
            result = analyze_slanted_edge_mtf(image, analysis_roi)
        except Exception as exc:
            self._mtf_last_result = None
            self._update_mtf_result_widgets(error=f"MTF: {exc}")
            return
        self._mtf_last_result = result
        self._update_mtf_result_widgets()
        self._persist_mtf_analysis_for_selected()

    def _maybe_update_mtf_after_preview(self) -> None:
        if getattr(self, "_mtf_roi", None) is None:
            return
        if not hasattr(self, "check_mtf_auto_update") or not self.check_mtf_auto_update.isChecked():
            return
        delay = 320 if self._is_preview_interaction_active() else 80
        self._mtf_refresh_timer.start(delay)

    def _update_mtf_result_widgets(self, *, error: str | None = None) -> None:
        result = getattr(self, "_mtf_last_result", None)
        for plot_name in ("mtf_plot_esf", "mtf_plot_lsf", "mtf_plot_mtf"):
            plot = getattr(self, plot_name, None)
            if plot is not None:
                plot.set_result(result)
        self._update_mtf_details_table(result, error=error)
        if not hasattr(self, "mtf_metrics_label"):
            return
        if error:
            self.mtf_metrics_label.setText(error)
            return
        if result is None:
            self.mtf_metrics_label.setText(self.tr("MTF: selecciona una ROI con un borde inclinado."))
            return
        suggestion = self._mtf_suggestion(result)
        details = [suggestion]
        if hasattr(self, "spin_mtf_pixel_pitch_um") and self.spin_mtf_pixel_pitch_um.value() > 0.0:
            details.append(self.tr("lp/mm válido solo si la ROI está a escala 1:1."))
        if result.warnings:
            details.extend(result.warnings)
        self.mtf_metrics_label.setText(" ".join(details))

    def _format_mtf_frequency(self, value: float | None) -> str:
        if value is None:
            return self.tr("no cruza")
        pitch = self.spin_mtf_pixel_pitch_um.value() if hasattr(self, "spin_mtf_pixel_pitch_um") else 0.0
        base = f"{float(value):.3f} c/p"
        if pitch > 0.0:
            lpmm = float(value) * 1000.0 / float(pitch)
            base += f" · {lpmm:.1f} lp/mm"
        return base

    def _format_mtf_cycles(self, value: float | None) -> str:
        if value is None:
            return self.tr("no cruza")
        return f"{float(value):.6f} c/p"

    def _mtf_pixel_pitch_um_value(self) -> float | None:
        if not hasattr(self, "spin_mtf_pixel_pitch_um"):
            return None
        pitch = float(self.spin_mtf_pixel_pitch_um.value())
        return pitch if pitch > 0.0 else None

    def _mtf_lpmm(self, cycles_per_pixel: float | None) -> float | None:
        if cycles_per_pixel is None:
            return None
        pitch = self._mtf_pixel_pitch_um_value()
        if pitch is None:
            return None
        return float(cycles_per_pixel) * 1000.0 / float(pitch)

    def _format_mtf_lpmm(self, cycles_per_pixel: float | None) -> str:
        lpmm = self._mtf_lpmm(cycles_per_pixel)
        return "sin pitch" if lpmm is None else f"{lpmm:.2f} lp/mm"

    def _update_mtf_details_table(self, result: MTFResult | None, *, error: str | None = None) -> None:
        metrics_table = getattr(self, "mtf_metrics_table", None)
        context_table = getattr(self, "mtf_context_table", None)
        if metrics_table is None or context_table is None:
            return
        if error:
            self._populate_mtf_details_table(metrics_table, [(self.tr("Estado"), error)])
            self._populate_mtf_details_table(context_table, [])
            return
        if result is None:
            self._populate_mtf_details_table(metrics_table, [(self.tr("Estado"), self.tr("Sin medición MTF"))])
            self._populate_mtf_details_table(context_table, [])
            return
        self._populate_mtf_details_table(metrics_table, self._mtf_metric_rows(result))
        self._populate_mtf_details_table(context_table, self._mtf_context_rows(result))

    def _populate_mtf_details_table(self, table: QtWidgets.QTableWidget, rows: list[tuple[str, str]]) -> None:
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(rows))
            for row, (key, value) in enumerate(rows):
                key_item = QtWidgets.QTableWidgetItem(str(key))
                value_item = QtWidgets.QTableWidgetItem(str(value))
                key_item.setFlags(key_item.flags() & ~QtCore.Qt.ItemIsEditable)
                value_item.setFlags(value_item.flags() & ~QtCore.Qt.ItemIsEditable)
                table.setItem(row, 0, key_item)
                table.setItem(row, 1, value_item)
        finally:
            table.setUpdatesEnabled(True)

    def _mtf_metric_rows(self, result: MTFResult) -> list[tuple[str, str]]:
        post = self._mtf_post_nyquist_metrics(result)
        rows: list[tuple[str, str]] = [
            (self.tr("MTF50"), f"{self._format_mtf_cycles(result.mtf50)} | {self._format_mtf_lpmm(result.mtf50)}"),
            (self.tr("MTF30"), f"{self._format_mtf_cycles(result.mtf30)} | {self._format_mtf_lpmm(result.mtf30)}"),
            (self.tr("MTF10"), f"{self._format_mtf_cycles(result.mtf10)} | {self._format_mtf_lpmm(result.mtf10)}"),
            (self.tr("Nyquist"), f"0.500000 c/p | {self._format_mtf_lpmm(0.5)}"),
            (self.tr("Acutancia"), f"{float(result.acutance):.6f}"),
            (self.tr("Ángulo de borde"), f"{float(result.edge_angle_degrees):.3f}°"),
            (self.tr("Contraste de borde"), f"{float(result.edge_contrast):.6f}"),
            (self.tr("Sobreimpulso / subimpulso"), f"{float(result.overshoot) * 100.0:.3f}% / {float(result.undershoot) * 100.0:.3f}%"),
        ]
        if post["samples"] > 0:
            rows.extend(
                [
                    (
                        self.tr("Post-Nyquist rango"),
                        f"{post['min_frequency']:.6f} - {post['max_frequency']:.6f} c/p ({int(post['samples'])} muestras)",
                    ),
                    (
                        self.tr("Post-Nyquist pico"),
                        f"{post['peak_modulation']:.6f} @ {post['peak_frequency']:.6f} c/p | {self._format_mtf_lpmm(post['peak_frequency'])}",
                    ),
                    (self.tr("Post-Nyquist media"), f"{post['mean_modulation']:.6f}"),
                    (self.tr("Post-Nyquist RMS"), f"{post['rms_modulation']:.6f}"),
                    (self.tr("Energía post/Nyquist"), f"{post['energy_ratio']:.6f}"),
                ]
            )
        else:
            rows.append((self.tr("Post-Nyquist"), self.tr("sin muestras extendidas")))
        return rows

    def _mtf_context_rows(self, result: MTFResult) -> list[tuple[str, str]]:
        pitch = self._mtf_pixel_pitch_um_value()
        image_dimensions = self._mtf_analysis_image_dimensions() or self._mtf_current_image_dimensions()
        display_dimensions = getattr(self, "_mtf_last_display_dimensions", None) or self._mtf_current_image_dimensions()
        source = getattr(self, "_selected_file", None)
        roi_x, roi_y, roi_w, roi_h = result.roi
        rows: list[tuple[str, str]] = [
            (self.tr("Fuente"), str(source) if source is not None else self.tr("preview actual")),
            (self.tr("Imagen análisis"), f"{image_dimensions[0]} x {image_dimensions[1]} px" if image_dimensions else self.tr("no disponible")),
            (self.tr("Imagen visor"), f"{display_dimensions[0]} x {display_dimensions[1]} px" if display_dimensions else self.tr("no disponible")),
            (self.tr("ROI"), f"x={roi_x}, y={roi_y}, w={roi_w}, h={roi_h} px"),
            (self.tr("ROI muestras"), f"{int(result.roi_shape[1])} x {int(result.roi_shape[0])} px ({int(result.roi_shape[0]) * int(result.roi_shape[1])})"),
            (self.tr("Pitch píxel"), f"{pitch:.6f} µm ({self._mtf_pixel_pitch_auto_source or 'manual'})" if pitch is not None else self.tr("sin dato")),
            (self.tr("Muestras ESF"), str(len(result.esf))),
            (self.tr("Muestras LSF"), str(len(result.lsf))),
            (self.tr("Muestras MTF"), str(len(result.mtf))),
            (self.tr("Muestras MTF extendida"), str(len(self._mtf_limited_extended_frequencies(result)))),
            (self.tr("Rango frecuencia MTF"), self._mtf_frequency_range_label(result)),
            (self.tr("Rango frecuencia extendida"), self._mtf_extended_frequency_range_label(result)),
            (self.tr("Nota post-Nyquist"), self.tr("diagnóstico exploratorio; no interpretar como resolución real por encima del límite de muestreo")),
            (self.tr("Advertencias"), " | ".join(result.warnings) if result.warnings else self.tr("ninguna")),
        ]
        display_roi = getattr(self, "_mtf_last_display_roi", None)
        if display_roi is not None and tuple(display_roi) != tuple(result.roi):
            x, y, w, h = [int(v) for v in display_roi]
            rows.insert(4, (self.tr("ROI visor"), f"x={x}, y={y}, w={w}, h={h} px"))
        return rows

    def _mtf_frequency_range_label(self, result: MTFResult) -> str:
        values = [float(v) for v in result.frequency if np.isfinite(float(v))]
        if not values:
            return self.tr("sin datos")
        return f"{min(values):.6f} - {max(values):.6f} c/p"

    def _mtf_extended_frequency_range_label(self, result: MTFResult) -> str:
        values = self._mtf_limited_extended_frequencies(result)
        if not values:
            return self.tr("sin datos")
        return f"{min(values):.6f} - {max(values):.6f} c/p"

    def _mtf_limited_extended_frequencies(self, result: MTFResult) -> list[float]:
        max_extended = float(self.MTF_EXTENDED_ANALYSIS_MAX_FREQUENCY)
        return [
            float(v)
            for v in getattr(result, "frequency_extended", [])
            if np.isfinite(float(v)) and float(v) <= max_extended
        ]

    def _mtf_post_nyquist_metrics(self, result: MTFResult) -> dict[str, float | int]:
        freq = np.asarray(getattr(result, "frequency_extended", []) or [], dtype=np.float64)
        mtf = np.asarray(getattr(result, "mtf_extended", []) or [], dtype=np.float64)
        valid = np.isfinite(freq) & np.isfinite(mtf)
        freq = freq[valid]
        mtf = mtf[valid]
        max_extended = float(self.MTF_EXTENDED_ANALYSIS_MAX_FREQUENCY)
        post_mask = (freq > 0.5) & (freq <= max_extended)
        if int(np.count_nonzero(post_mask)) == 0:
            return {"samples": 0}
        post_freq = freq[post_mask]
        post_mtf = np.clip(mtf[post_mask], 0.0, 2.0)
        peak_idx = int(np.argmax(post_mtf))
        in_mask = freq <= 0.5
        in_energy = float(np.trapezoid(np.clip(mtf[in_mask], 0.0, 2.0), freq[in_mask])) if int(np.count_nonzero(in_mask)) > 1 else 0.0
        post_energy = float(np.trapezoid(post_mtf, post_freq)) if post_freq.size > 1 else 0.0
        return {
            "samples": int(post_freq.size),
            "min_frequency": float(np.min(post_freq)),
            "max_frequency": float(np.max(post_freq)),
            "peak_frequency": float(post_freq[peak_idx]),
            "peak_modulation": float(post_mtf[peak_idx]),
            "mean_modulation": float(np.mean(post_mtf)),
            "rms_modulation": float(np.sqrt(np.mean(post_mtf * post_mtf))),
            "energy": post_energy,
            "energy_ratio": post_energy / in_energy if in_energy > 1e-12 else 0.0,
        }

    def _mtf_analysis_payload(self, *, include_curves: bool = True) -> dict[str, Any] | None:
        result = getattr(self, "_mtf_last_result", None)
        if result is None:
            return None
        pitch = self._mtf_pixel_pitch_um_value()
        image_dimensions = self._mtf_analysis_image_dimensions() or self._mtf_current_image_dimensions()
        display_dimensions = getattr(self, "_mtf_last_display_dimensions", None) or self._mtf_current_image_dimensions()
        selected = getattr(self, "_selected_file", None)
        summary = result.summary()
        post_nyquist = self._mtf_post_nyquist_metrics(result)
        limited_extended_frequencies = self._mtf_limited_extended_frequencies(result)
        display_roi = getattr(self, "_mtf_last_display_roi", None) or getattr(self, "_mtf_roi", None)
        summary.update(
            {
                "source": str(selected) if selected is not None else "",
                "measured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "image_dimensions_px": list(image_dimensions) if image_dimensions else None,
                "display_dimensions_px": list(display_dimensions) if display_dimensions else None,
                "display_roi": list(display_roi) if display_roi is not None else None,
                "pixel_pitch_um": pitch,
                "pixel_pitch_source": self._mtf_pixel_pitch_auto_source,
                "nyquist_cycles_per_pixel": 0.5,
                "nyquist_lp_per_mm": self._mtf_lpmm(0.5),
                "mtf50_lp_per_mm": self._mtf_lpmm(result.mtf50),
                "mtf30_lp_per_mm": self._mtf_lpmm(result.mtf30),
                "mtf10_lp_per_mm": self._mtf_lpmm(result.mtf10),
                "esf_samples": len(result.esf),
                "lsf_samples": len(result.lsf),
                "mtf_samples": len(result.mtf),
                "mtf_extended_samples": len(limited_extended_frequencies),
                "frequency_range_cycles_per_pixel": [
                    min(result.frequency) if result.frequency else None,
                    max(result.frequency) if result.frequency else None,
                ],
                "extended_frequency_range_cycles_per_pixel": [
                    min(limited_extended_frequencies) if limited_extended_frequencies else None,
                    max(limited_extended_frequencies) if limited_extended_frequencies else None,
                ],
                "post_nyquist": post_nyquist,
                "analysis_source": "full_resolution_image_data",
                "scale_note": "MTF is calculated from full-resolution image data; lp/mm depends on the pixel pitch value",
                "post_nyquist_note": "values above 0.5 cycles/pixel are exploratory diagnostics for aliasing, harmonics or processing artifacts; they are not physical resolution beyond sampling Nyquist",
            }
        )
        payload: dict[str, Any] = {"summary": summary}
        if include_curves:
            payload["curves"] = {
                "esf": [
                    {"distance_px": x, "signal": y}
                    for x, y in zip(result.esf_distance, result.esf, strict=False)
                ],
                "lsf": [
                    {"distance_px": x, "derivative": y}
                    for x, y in zip(result.lsf_distance, result.lsf, strict=False)
                ],
                "mtf": [
                    {"frequency_cycles_per_pixel": x, "modulation": y, "frequency_lp_per_mm": self._mtf_lpmm(x)}
                    for x, y in zip(result.frequency, result.mtf, strict=False)
                ],
                "mtf_extended": [
                    {
                        "frequency_cycles_per_pixel": x,
                        "modulation": y,
                        "frequency_lp_per_mm": self._mtf_lpmm(x),
                        "post_nyquist": bool(float(x) > 0.5),
                    }
                    for x, y in zip(
                        getattr(result, "frequency_extended", []) or [],
                        getattr(result, "mtf_extended", []) or [],
                        strict=False,
                    )
                    if float(x) <= float(self.MTF_EXTENDED_ANALYSIS_MAX_FREQUENCY)
                ],
            }
        return payload

    def _persist_mtf_analysis_for_selected(self) -> None:
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            return
        payload = self._mtf_analysis_payload(include_curves=True)
        if payload is None:
            return
        session_name = self.session_name_edit.text().strip() if hasattr(self, "session_name_edit") else ""
        try:
            write_raw_mtf_analysis(
                Path(selected),
                payload,
                session_root=getattr(self, "_active_session_root", None),
                session_name=session_name,
            )
        except Exception as exc:
            self._log_preview(f"Aviso: no se pudo guardar MTF en sidecar: {exc}")
            return
        self._refresh_mtf_sidecar_indicator_for_path(Path(selected))
        self._set_status(self.tr("MTF guardada en sidecar:") + f" {Path(selected).name}")

    def _refresh_mtf_sidecar_indicator_for_path(self, path: Path) -> None:
        if not hasattr(self, "file_list"):
            return
        key = self._normalized_path_key(path)
        item = self._file_items_by_key.get(key)
        if item is None or self.file_list.row(item) < 0:
            return
        item.setToolTip(self._file_item_tooltip(path))

    def _load_persisted_mtf_analysis(self, path: Path) -> dict[str, Any] | None:
        try:
            sidecar = load_raw_sidecar(path)
        except Exception:
            return None
        payload = sidecar.get("mtf_analysis")
        return payload if isinstance(payload, dict) else None

    def _raw_sidecar_mtf_summary(self, path: Path) -> str:
        payload = self._load_persisted_mtf_analysis(path)
        summary = payload.get("summary") if isinstance(payload, dict) and isinstance(payload.get("summary"), dict) else {}
        if not summary:
            return ""
        mtf50 = self._format_persisted_mtf_number(summary.get("mtf50"), decimals=3, suffix=" c/p")
        mtf50_lpmm = self._format_persisted_mtf_number(summary.get("mtf50_lp_per_mm"), decimals=1, suffix=" lp/mm")
        parts = [part for part in (mtf50, mtf50_lpmm) if part]
        return self.tr("MTF guardada") + (": MTF50 " + " | ".join(parts) if parts else "")

    def _format_persisted_mtf_number(self, value: Any, *, decimals: int, suffix: str = "") -> str:
        if value is None:
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return ""
        if not np.isfinite(number):
            return ""
        return f"{number:.{decimals}f}{suffix}"

    def _compare_mtf_for_selected_thumbnails(self) -> None:
        files = self._collect_selected_file_paths() if hasattr(self, "_collect_selected_file_paths") else []
        if len(files) != 2:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Comparar MTF"),
                self.tr("Selecciona exactamente dos miniaturas con datos MTF guardados."),
            )
            return
        left_path, right_path = files
        left_payload = self._load_persisted_mtf_analysis(left_path)
        right_payload = self._load_persisted_mtf_analysis(right_path)
        missing = [
            path.name
            for path, payload in ((left_path, left_payload), (right_path, right_payload))
            if payload is None
        ]
        if missing:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Comparar MTF"),
                self.tr("No hay MTF guardada para:") + " " + ", ".join(missing),
            )
            return
        self._show_mtf_comparison_dialog(left_path, left_payload, right_path, right_payload)

    def _show_mtf_comparison_dialog(
        self,
        left_path: Path,
        left_payload: dict[str, Any],
        right_path: Path,
        right_payload: dict[str, Any],
    ) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.tr("Comparación MTF"))
        dialog.resize(860, 560)
        layout = QtWidgets.QVBoxLayout(dialog)
        tabs = QtWidgets.QTabWidget()
        table = QtWidgets.QTableWidget(0, 4)
        table.setHorizontalHeaderLabels([
            self.tr("Dato"),
            left_path.name,
            right_path.name,
            self.tr("Diferencia segunda - primera"),
        ])
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        rows = self._mtf_comparison_rows(left_path, left_payload, right_path, right_payload)
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                table.setItem(row, column, item)
        tabs.addTab(table, self.tr("Métricas MTF"))
        for label, curve in (("ESF", "esf"), ("LSF", "lsf"), ("MTF", "mtf")):
            plot = MTFComparisonPlotWidget(curve)
            plot.set_payloads([(left_path.name, left_payload), (right_path.name, right_payload)])
            tabs.addTab(plot, label)
        layout.addWidget(tabs, 1)
        close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    def _mtf_comparison_rows(
        self,
        left_path: Path,
        left_payload: dict[str, Any],
        right_path: Path,
        right_payload: dict[str, Any],
    ) -> list[tuple[str, str, str, str]]:
        left_summary = self._mtf_payload_summary(left_payload)
        right_summary = self._mtf_payload_summary(right_payload)
        rows: list[tuple[str, str, str, str]] = [
            (self.tr("Archivo"), left_path.name, right_path.name, ""),
            (
                self.tr("Medición"),
                str(left_summary.get("measured_at") or self.tr("sin dato")),
                str(right_summary.get("measured_at") or self.tr("sin dato")),
                "",
            ),
            (
                self.tr("ROI"),
                self._format_mtf_comparison_roi(left_summary.get("roi")),
                self._format_mtf_comparison_roi(right_summary.get("roi")),
                "",
            ),
        ]
        specs: list[tuple[str, tuple[str, ...], int, str, float]] = [
            (self.tr("MTF50"), ("mtf50",), 6, " c/p", 1.0),
            (self.tr("MTF50"), ("mtf50_lp_per_mm",), 2, " lp/mm", 1.0),
            (self.tr("MTF30"), ("mtf30",), 6, " c/p", 1.0),
            (self.tr("MTF30"), ("mtf30_lp_per_mm",), 2, " lp/mm", 1.0),
            (self.tr("MTF10"), ("mtf10",), 6, " c/p", 1.0),
            (self.tr("MTF10"), ("mtf10_lp_per_mm",), 2, " lp/mm", 1.0),
            (self.tr("Nyquist"), ("nyquist_lp_per_mm",), 2, " lp/mm", 1.0),
            (self.tr("Acutancia"), ("acutance",), 6, "", 1.0),
            (self.tr("Ángulo de borde"), ("edge_angle_degrees",), 3, "°", 1.0),
            (self.tr("Contraste de borde"), ("edge_contrast",), 6, "", 1.0),
            (self.tr("Sobreimpulso"), ("overshoot",), 3, "%", 100.0),
            (self.tr("Subimpulso"), ("undershoot",), 3, "%", 100.0),
            (self.tr("Post-Nyquist pico"), ("post_nyquist", "peak_frequency"), 6, " c/p", 1.0),
            (self.tr("Post-Nyquist pico"), ("post_nyquist", "peak_modulation"), 6, "", 1.0),
            (self.tr("Energía post/Nyquist"), ("post_nyquist", "energy_ratio"), 6, "", 1.0),
        ]
        for label, key_path, decimals, suffix, factor in specs:
            left_value = self._mtf_nested_number(left_summary, key_path)
            right_value = self._mtf_nested_number(right_summary, key_path)
            rows.append(
                (
                    f"{label} ({suffix.strip()})" if suffix.strip() else label,
                    self._format_mtf_comparison_value(left_value, decimals=decimals, suffix=suffix, factor=factor),
                    self._format_mtf_comparison_value(right_value, decimals=decimals, suffix=suffix, factor=factor),
                    self._format_mtf_comparison_delta(left_value, right_value, decimals=decimals, suffix=suffix, factor=factor),
                )
            )
        return rows

    def _mtf_payload_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary = payload.get("summary") if isinstance(payload, dict) else None
        return summary if isinstance(summary, dict) else {}

    def _mtf_nested_number(self, summary: dict[str, Any], key_path: tuple[str, ...]) -> float | None:
        value: Any = summary
        for key in key_path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if np.isfinite(number) else None

    def _format_mtf_comparison_roi(self, value: Any) -> str:
        if isinstance(value, (list, tuple)) and len(value) == 4:
            try:
                x, y, w, h = [int(round(float(v))) for v in value]
            except (TypeError, ValueError):
                return str(value)
            return f"x={x}, y={y}, w={w}, h={h} px"
        return self.tr("sin dato")

    def _format_mtf_comparison_value(
        self,
        value: float | None,
        *,
        decimals: int,
        suffix: str,
        factor: float,
    ) -> str:
        if value is None:
            return self.tr("sin dato")
        return f"{float(value) * float(factor):.{decimals}f}{suffix}"

    def _format_mtf_comparison_delta(
        self,
        left: float | None,
        right: float | None,
        *,
        decimals: int,
        suffix: str,
        factor: float,
    ) -> str:
        if left is None or right is None:
            return ""
        return f"{(float(right) - float(left)) * float(factor):+.{decimals}f}{suffix}"

    def _copy_mtf_analysis_data(self) -> None:
        payload = self._mtf_analysis_payload(include_curves=True)
        if payload is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("No hay medición MTF para copiar."))
            return
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        app.clipboard().setText(json.dumps(payload, indent=2, ensure_ascii=False))
        self._set_status(self.tr("Datos MTF copiados al portapapeles"))

    def _export_mtf_analysis_csv(self) -> None:
        payload = self._mtf_analysis_payload(include_curves=True)
        if payload is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("No hay medición MTF para exportar."))
            return
        default = self._mtf_default_export_path()
        path_text, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self.tr("Exportar MTF CSV"),
            str(default),
            "CSV (*.csv);;Todos (*)",
        )
        if not path_text:
            return
        path = Path(path_text).expanduser()
        path.write_text(self._mtf_payload_to_csv(payload), encoding="utf-8")
        self._set_status(self.tr("Datos MTF exportados:") + f" {path}")

    def _mtf_default_export_path(self) -> Path:
        selected = getattr(self, "_selected_file", None)
        stem = Path(selected).stem if selected is not None else "mtf"
        if getattr(self, "_active_session_root", None) is not None:
            try:
                return self._session_paths_from_root(self._active_session_root)["work"] / f"{stem}_mtf.csv"
            except Exception:
                pass
        return Path.cwd() / f"{stem}_mtf.csv"

    def _mtf_payload_to_csv(self, payload: dict[str, Any]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["section", "index", "x", "y", "key", "value"])
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        for key, value in summary.items():
            writer.writerow(["summary", "", "", "", key, json.dumps(value, ensure_ascii=False)])
        curves = payload.get("curves") if isinstance(payload.get("curves"), dict) else {}
        for idx, point in enumerate(curves.get("esf", []) or []):
            writer.writerow(["esf", idx, point.get("distance_px"), point.get("signal"), "", ""])
        for idx, point in enumerate(curves.get("lsf", []) or []):
            writer.writerow(["lsf", idx, point.get("distance_px"), point.get("derivative"), "", ""])
        for idx, point in enumerate(curves.get("mtf", []) or []):
            writer.writerow([
                "mtf",
                idx,
                point.get("frequency_cycles_per_pixel"),
                point.get("modulation"),
                "frequency_lp_per_mm",
                point.get("frequency_lp_per_mm"),
            ])
        for idx, point in enumerate(curves.get("mtf_extended", []) or []):
            writer.writerow([
                "mtf_extended",
                idx,
                point.get("frequency_cycles_per_pixel"),
                point.get("modulation"),
                "post_nyquist",
                point.get("post_nyquist"),
            ])
        return output.getvalue()

    def _mtf_suggestion(self, result: MTFResult) -> str:
        halo = max(float(result.overshoot), float(result.undershoot))
        if halo > 0.10:
            return self.tr("Sugerencia: reduce acutancia o radio; hay halo/sobreimpulso.")
        if result.mtf50 is not None and result.mtf50 < 0.15 and halo < 0.04:
            return self.tr("Sugerencia: puedes probar más acutancia con radio bajo.")
        return self.tr("Sugerencia: ajuste equilibrado para esta ROI.")

    def _show_mtf_expanded_dialog(self) -> None:
        result = getattr(self, "_mtf_last_result", None)
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.tr("Análisis MTF"))
        dialog.resize(980, 720)
        layout = QtWidgets.QVBoxLayout(dialog)
        tabs = QtWidgets.QTabWidget()
        for label, curve in (("ESF", "esf"), ("LSF", "lsf"), ("MTF", "mtf")):
            plot = MTFPlotWidget(curve)
            plot.setMinimumHeight(560)
            plot.set_result(result)
            tabs.addTab(plot, label)
        layout.addWidget(tabs, 1)
        summary = QtWidgets.QLabel(self.mtf_metrics_label.text() if hasattr(self, "mtf_metrics_label") else "")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()
