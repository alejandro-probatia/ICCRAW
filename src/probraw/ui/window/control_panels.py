from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class ControlPanelsMixin:
    def _build_tab_color_adjustments(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        grid.addWidget(QtWidgets.QLabel(self.tr("Iluminante final")), 0, 0)
        self.combo_illuminant_render = QtWidgets.QComboBox()
        for label, temp, tint in ILLUMINANT_OPTIONS:
            self.combo_illuminant_render.addItem(self.tr(label), {"temperature": temp, "tint": tint})
        self.combo_illuminant_render.setCurrentIndex(1)
        self.combo_illuminant_render.currentIndexChanged.connect(self._on_illuminant_changed)
        grid.addWidget(self.combo_illuminant_render, 0, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Temperatura (K)")), 1, 0)
        self.spin_render_temperature = QtWidgets.QSpinBox()
        self.spin_render_temperature.setRange(2000, 12000)
        self.spin_render_temperature.setSingleStep(50)
        self.spin_render_temperature.setValue(5003)
        self.spin_render_temperature.valueChanged.connect(lambda _v: self._on_render_control_change())
        grid.addWidget(self.spin_render_temperature, 1, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Matiz")), 2, 0)
        self.spin_render_tint = QtWidgets.QDoubleSpinBox()
        self.spin_render_tint.setRange(-100.0, 100.0)
        self.spin_render_tint.setSingleStep(1.0)
        self.spin_render_tint.setDecimals(1)
        self.spin_render_tint.valueChanged.connect(lambda _v: self._on_render_control_change())
        grid.addWidget(self.spin_render_tint, 2, 1, 1, 2)

        neutral_row = QtWidgets.QHBoxLayout()
        self.btn_neutral_picker = QtWidgets.QPushButton(self.tr("Cuentagotas neutro"))
        self.btn_neutral_picker.setCheckable(True)
        self.btn_neutral_picker.clicked.connect(self._toggle_neutral_picker)
        neutral_row.addWidget(self.btn_neutral_picker)
        self.label_neutral_picker = QtWidgets.QLabel(self.tr("Punto neutro: sin muestra"))
        self.label_neutral_picker.setWordWrap(True)
        self.label_neutral_picker.setStyleSheet("font-size: 12px; color: #cbd5e1;")
        neutral_row.addWidget(self.label_neutral_picker, 1)
        grid.addLayout(neutral_row, 3, 0, 1, 3)

        grid.addWidget(self._button(self.tr("Restablecer color"), self._reset_color_adjustments), 4, 0, 1, 3)
        return tab

    def _build_tab_brightness_contrast(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        self.slider_brightness, self.label_brightness = self._slider(
            minimum=-200,
            maximum=200,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Brillo") + f": {v / 100:+.2f} EV",
        )
        grid.addWidget(self.label_brightness, 0, 0, 1, 3)
        grid.addWidget(self.slider_brightness, 1, 0, 1, 3)

        self.slider_black_point, self.label_black_point = self._slider(
            minimum=0,
            maximum=300,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Nivel negro") + f": {v / 1000:.3f}",
        )
        grid.addWidget(self.label_black_point, 2, 0, 1, 3)
        grid.addWidget(self.slider_black_point, 3, 0, 1, 3)

        self.slider_white_point, self.label_white_point = self._slider(
            minimum=500,
            maximum=1000,
            value=1000,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Nivel blanco") + f": {v / 1000:.3f}",
        )
        grid.addWidget(self.label_white_point, 4, 0, 1, 3)
        grid.addWidget(self.slider_white_point, 5, 0, 1, 3)

        self.slider_contrast, self.label_contrast = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Contraste") + f": {v / 100:+.2f}",
        )
        grid.addWidget(self.label_contrast, 6, 0, 1, 3)
        grid.addWidget(self.slider_contrast, 7, 0, 1, 3)

        self.slider_midtone, self.label_midtone = self._slider(
            minimum=50,
            maximum=200,
            value=100,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Curva medios") + f": {v / 100:.2f}",
        )
        grid.addWidget(self.label_midtone, 8, 0, 1, 3)
        grid.addWidget(self.slider_midtone, 9, 0, 1, 3)

        self.check_tone_curve_enabled = QtWidgets.QCheckBox(self.tr("Curva tonal avanzada"))
        self.check_tone_curve_enabled.setChecked(False)
        self.check_tone_curve_enabled.toggled.connect(self._on_tone_curve_enabled_changed)
        grid.addWidget(self.check_tone_curve_enabled, 10, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Canal curva")), 11, 0)
        self.combo_tone_curve_channel = QtWidgets.QComboBox()
        for label, key in (
            (self.tr("Luminosidad"), "luminance"),
            (self.tr("Rojo"), "red"),
            (self.tr("Verde"), "green"),
            (self.tr("Azul"), "blue"),
        ):
            self.combo_tone_curve_channel.addItem(label, key)
        self.combo_tone_curve_channel.currentIndexChanged.connect(self._on_tone_curve_channel_changed)
        grid.addWidget(self.combo_tone_curve_channel, 11, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Preset curva")), 12, 0)
        self.combo_tone_curve_preset = QtWidgets.QComboBox()
        for label, key, _points in TONE_CURVE_PRESETS:
            self.combo_tone_curve_preset.addItem(self.tr(label), key)
        self.combo_tone_curve_preset.currentIndexChanged.connect(self._on_tone_curve_preset_changed)
        grid.addWidget(self.combo_tone_curve_preset, 12, 1, 1, 2)

        self.slider_tone_curve_black, self.label_tone_curve_black = self._slider(
            minimum=0,
            maximum=950,
            value=0,
            on_change=self._on_tone_curve_range_changed,
            formatter=lambda v: self.tr("Negro curva") + f": {v / 1000:.3f}",
        )
        grid.addWidget(self.label_tone_curve_black, 13, 0, 1, 3)
        grid.addWidget(self.slider_tone_curve_black, 14, 0, 1, 3)

        self.slider_tone_curve_white, self.label_tone_curve_white = self._slider(
            minimum=50,
            maximum=1000,
            value=1000,
            on_change=self._on_tone_curve_range_changed,
            formatter=lambda v: self.tr("Blanco curva") + f": {v / 1000:.3f}",
        )
        grid.addWidget(self.label_tone_curve_white, 15, 0, 1, 3)
        grid.addWidget(self.slider_tone_curve_white, 16, 0, 1, 3)

        self.tone_curve_editor = ToneCurveEditor()
        self.tone_curve_editor.pointsChanged.connect(self._on_tone_curve_points_changed)
        self.tone_curve_editor.interactionFinished.connect(self._on_render_control_change)
        grid.addWidget(self.tone_curve_editor, 17, 0, 1, 3)
        grid.addWidget(self._button(self.tr("Restablecer curva"), self._reset_tone_curve), 18, 0, 1, 3)
        self._set_tone_curve_controls_enabled(False)

        grid.addWidget(self._button(self.tr("Restablecer brillo y contraste"), self._reset_tone_adjustments), 19, 0, 1, 3)
        return tab

    def _build_tab_preview_settings(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        self.slider_sharpen, self.label_sharpen = self._slider(
            minimum=0,
            maximum=300,
            value=0,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("Nitidez (amount)") + f": {v / 100:.2f}",
        )
        grid.addWidget(self.label_sharpen, 0, 0, 1, 3)
        grid.addWidget(self.slider_sharpen, 1, 0, 1, 3)

        self.slider_radius, self.label_radius = self._slider(
            minimum=1,
            maximum=80,
            value=10,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("Radio nitidez") + f": {v / 10:.1f}",
        )
        grid.addWidget(self.label_radius, 2, 0, 1, 3)
        grid.addWidget(self.slider_radius, 3, 0, 1, 3)

        self.slider_noise_luma, self.label_noise_luma = self._slider(
            minimum=0,
            maximum=100,
            value=0,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("Ruido luminancia") + f": {v / 100:.2f}",
        )
        grid.addWidget(self.label_noise_luma, 4, 0, 1, 3)
        grid.addWidget(self.slider_noise_luma, 5, 0, 1, 3)

        self.slider_noise_color, self.label_noise_color = self._slider(
            minimum=0,
            maximum=100,
            value=0,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("Ruido color") + f": {v / 100:.2f}",
        )
        grid.addWidget(self.label_noise_color, 6, 0, 1, 3)
        grid.addWidget(self.slider_noise_color, 7, 0, 1, 3)

        self.slider_ca_red, self.label_ca_red = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("CA lateral rojo/cian") + f": {1.0 + v / 10000:.4f}",
        )
        grid.addWidget(self.label_ca_red, 8, 0, 1, 3)
        grid.addWidget(self.slider_ca_red, 9, 0, 1, 3)

        self.slider_ca_blue, self.label_ca_blue = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("CA lateral azul/amarillo") + f": {1.0 + v / 10000:.4f}",
        )
        grid.addWidget(self.label_ca_blue, 10, 0, 1, 3)
        grid.addWidget(self.slider_ca_blue, 11, 0, 1, 3)

        self.check_precision_detail_preview = QtWidgets.QCheckBox(
            self.tr("Modo precision 1:1 para nitidez (mas lento)")
        )
        self.check_precision_detail_preview.setToolTip(
            self.tr("Aplica ajustes de nitidez/ruido/CA sobre fuente a resolucion real durante el arrastre.")
        )
        self.check_precision_detail_preview.setChecked(
            self._settings_bool("preview/precision_detail_1to1", False)
        )
        self.check_precision_detail_preview.toggled.connect(
            self._on_precision_detail_preview_toggled
        )
        grid.addWidget(self.check_precision_detail_preview, 12, 0, 1, 3)

        recipe_filter_note = QtWidgets.QLabel(
            self.tr(
                "Los filtros reales de nitidez, ruido y aberración cromática se aplican "
                "con los controles superiores. Los campos de receta quedan sólo como "
                "metadatos de compatibilidad."
            )
        )
        recipe_filter_note.setWordWrap(True)
        recipe_filter_note.setStyleSheet("font-size: 12px; color: #6b7280; padding-top: 6px;")
        grid.addWidget(recipe_filter_note, 13, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Denoise modo receta")), 14, 0)
        self.combo_recipe_denoise = QtWidgets.QComboBox()
        self.combo_recipe_denoise.addItems(FILTER_MODE_OPTIONS)
        self.combo_recipe_denoise.setEnabled(False)
        self.combo_recipe_denoise.setToolTip(self.tr("Metadato de receta; no modifica píxeles en la GUI."))
        grid.addWidget(self.combo_recipe_denoise, 14, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Sharpen modo receta")), 15, 0)
        self.combo_recipe_sharpen = QtWidgets.QComboBox()
        self.combo_recipe_sharpen.addItems(FILTER_MODE_OPTIONS)
        self.combo_recipe_sharpen.setEnabled(False)
        self.combo_recipe_sharpen.setToolTip(self.tr("Metadato de receta; no modifica píxeles en la GUI."))
        grid.addWidget(self.combo_recipe_sharpen, 15, 1, 1, 2)

        grid.addWidget(self._button(self.tr("Restablecer nitidez"), self._reset_adjustments), 16, 0, 1, 3)
        return tab

    def _build_tab_raw_config(self, title: str | None = None) -> QtWidgets.QWidget:
        tab = QtWidgets.QGroupBox(title) if title else QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        self.path_recipe = QtWidgets.QLineEdit("testdata/recipes/scientific_recipe.yml")
        self._add_path_row(grid, 0, self.tr("Receta YAML/JSON"), self.path_recipe, file_mode=True, save_mode=False, dir_mode=False)

        row_recipe = QtWidgets.QHBoxLayout()
        row_recipe.addWidget(self._button(self.tr("Cargar receta"), self._menu_load_recipe))
        row_recipe.addWidget(self._button(self.tr("Guardar receta"), self._menu_save_recipe))
        row_recipe.addWidget(self._button(self.tr("Receta por defecto"), self._menu_reset_recipe))
        grid.addLayout(row_recipe, 1, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Motor RAW")), 2, 0)
        self.combo_raw_developer = QtWidgets.QComboBox()
        self.combo_raw_developer.addItem(self.tr("LibRaw / rawpy"), "libraw")
        self.combo_raw_developer.setEnabled(False)
        grid.addWidget(self.combo_raw_developer, 2, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Demosaic/interpolacion")), 3, 0)
        self.combo_demosaic = QtWidgets.QComboBox()
        for label, opt in DEMOSAIC_OPTIONS:
            self.combo_demosaic.addItem(self.tr(label), opt)
        self._sync_demosaic_capabilities()
        grid.addWidget(self.combo_demosaic, 3, 1, 1, 2)

        note = QtWidgets.QLabel(
            self.tr(
                "LibRaw/rawpy es el único motor RAW. DCB es el preset instalable de alta calidad. "
                "AMaZE queda disponible solo cuando rawpy informa DEMOSAIC_PACK_GPL3=True."
            )
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 12px; color: #6b7280;")
        grid.addWidget(note, 4, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Balance de blancos")), 5, 0)
        self.combo_wb_mode = QtWidgets.QComboBox()
        for label, val in WB_MODE_OPTIONS:
            self.combo_wb_mode.addItem(self.tr(label), val)
        grid.addWidget(self.combo_wb_mode, 5, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("WB multiplicadores")), 6, 0)
        self.edit_wb_multipliers = QtWidgets.QLineEdit("1,1,1,1")
        self.edit_wb_multipliers.setToolTip(self.tr("Formato: R,G,B,G (o R,G,B)"))
        grid.addWidget(self.edit_wb_multipliers, 6, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Black level mode")), 7, 0)
        self.combo_black_mode = QtWidgets.QComboBox()
        for label, val in BLACK_MODE_OPTIONS:
            self.combo_black_mode.addItem(self.tr(label), val)
        grid.addWidget(self.combo_black_mode, 7, 1)
        self.spin_black_value = QtWidgets.QSpinBox()
        self.spin_black_value.setRange(0, 65535)
        self.spin_black_value.setValue(0)
        grid.addWidget(self.spin_black_value, 7, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Exposure compensation (EV)")), 8, 0)
        self.spin_exposure = QtWidgets.QDoubleSpinBox()
        self.spin_exposure.setRange(-8.0, 8.0)
        self.spin_exposure.setDecimals(2)
        self.spin_exposure.setSingleStep(0.1)
        grid.addWidget(self.spin_exposure, 8, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Tone curve")), 9, 0)
        self.combo_tone_curve = QtWidgets.QComboBox()
        for label, val in TONE_OPTIONS:
            self.combo_tone_curve.addItem(self.tr(label), val)
        grid.addWidget(self.combo_tone_curve, 9, 1)
        self.spin_gamma = QtWidgets.QDoubleSpinBox()
        self.spin_gamma.setRange(0.8, 4.0)
        self.spin_gamma.setDecimals(2)
        self.spin_gamma.setValue(2.2)
        grid.addWidget(self.spin_gamma, 9, 2)

        self.check_output_linear = QtWidgets.QCheckBox(self.tr("Salida lineal"))
        self.check_output_linear.setChecked(True)
        self.check_output_linear.toggled.connect(self._on_output_linear_toggled)
        grid.addWidget(self.check_output_linear, 10, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Working space (metadato)")), 11, 0)
        self.combo_working_space = QtWidgets.QComboBox()
        self.combo_working_space.addItems(SPACE_OPTIONS)
        self.combo_working_space.setEnabled(False)
        self.combo_working_space.setToolTip(
            self.tr("Campo guardado en receta y pruebas de procedencia; el revelado actual usa el espacio de salida.")
        )
        grid.addWidget(self.combo_working_space, 11, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Output space")), 12, 0)
        self.combo_output_space = QtWidgets.QComboBox()
        self.combo_output_space.addItems(SPACE_OPTIONS)
        self.combo_output_space.currentTextChanged.connect(self._on_output_space_changed)
        grid.addWidget(self.combo_output_space, 12, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Sampling strategy")), 13, 0)
        self.combo_sampling = QtWidgets.QComboBox()
        self.combo_sampling.addItems(SAMPLE_OPTIONS)
        grid.addWidget(self.combo_sampling, 13, 1, 1, 2)

        self.check_profiling_mode = QtWidgets.QCheckBox(self.tr("Profiling mode"))
        self.check_profiling_mode.setChecked(True)
        grid.addWidget(self.check_profiling_mode, 14, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Input color assumption (metadato)")), 15, 0)
        self.edit_input_color = QtWidgets.QLineEdit("camera_native")
        self.edit_input_color.setReadOnly(True)
        self.edit_input_color.setToolTip(
            self.tr("Campo declarativo de receta; no aplica una transformación de color adicional.")
        )
        grid.addWidget(self.edit_input_color, 15, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Illuminant metadata")), 16, 0)
        self.edit_illuminant = QtWidgets.QLineEdit("")
        grid.addWidget(self.edit_illuminant, 16, 1, 1, 2)

        scientific_note = QtWidgets.QLabel(
            self.tr(
                "Durante la generación de un perfil avanzado con carta, ProbRAW fuerza estos parámetros a "
                "modo objetivo: tone_curve=linear, salida lineal=on, output_space=scene_linear_camera_rgb. "
                "Denoise y sharpen quedan desactivados durante la medición de carta y se "
                "configuran en la pestaña Nitidez para el revelado final."
            )
        )
        scientific_note.setWordWrap(True)
        scientific_note.setStyleSheet("font-size: 12px; color: #6b7280; padding-top: 6px;")
        grid.addWidget(scientific_note, 17, 0, 1, 3)
        return tab

    def _build_tab_profile_config(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        grid.addWidget(QtWidgets.QLabel(self.tr("Perfil ICC de sesión")), 0, 0)
        self.icc_profile_combo = QtWidgets.QComboBox()
        self.icc_profile_combo.setToolTip(
            self.tr("Perfiles ICC registrados en la sesión. Permite activar versiones generadas anteriormente.")
        )
        grid.addWidget(self.icc_profile_combo, 0, 1, 1, 2)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self._button(self.tr("Activar seleccionado"), self._activate_selected_icc_profile))
        row.addWidget(self._button(self.tr("Cargar perfil activo"), self._menu_load_profile))
        row.addWidget(self._button(self.tr("Usar perfil generado"), self._use_generated_profile_as_active))
        grid.addLayout(row, 1, 0, 1, 3)

        self.path_profile_active = QtWidgets.QLineEdit("/tmp/camera_profile.icc")
        self._add_path_row(grid, 2, self.tr("Perfil ICC de entrada activo"), self.path_profile_active, file_mode=True, save_mode=False, dir_mode=False)

        self.icc_profile_status_label = QtWidgets.QLabel(self.tr("Sin perfiles ICC de sesión"))
        self.icc_profile_status_label.setWordWrap(True)
        self.icc_profile_status_label.setStyleSheet("font-size: 12px; color: #d1d5db;")
        grid.addWidget(self.icc_profile_status_label, 3, 0, 1, 3)

        self._refresh_icc_profile_combo()
        return tab

    def _build_tab_batch_config(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        grid = QtWidgets.QGridLayout()

        self.batch_input_dir = QtWidgets.QLineEdit(str(self._current_dir))
        self._add_path_row(grid, 0, self.tr("RAW a revelar (carpeta)"), self.batch_input_dir, file_mode=False, save_mode=False, dir_mode=True)

        self.batch_out_dir = QtWidgets.QLineEdit("/tmp/probraw_batch_tiffs")
        self._add_path_row(grid, 1, self.tr("Salida TIFF derivados"), self.batch_out_dir, file_mode=False, save_mode=False, dir_mode=True)

        self.batch_embed_profile = QtWidgets.QCheckBox(self.tr("Incrustar/aplicar ICC en TIFF"))
        self.batch_embed_profile.setChecked(True)
        self.batch_embed_profile.setEnabled(False)
        self.batch_embed_profile.setToolTip(
            self.tr(
                "Siempre activo: usa el ICC de entrada si la salida es RGB de cámara, "
                "o un ICC estándar si la salida es sRGB/Adobe RGB/ProPhoto."
            )
        )
        grid.addWidget(self.batch_embed_profile, 2, 0, 1, 3)

        self.batch_apply_adjustments = QtWidgets.QCheckBox(self.tr("Aplicar ajustes básicos y de nitidez"))
        self.batch_apply_adjustments.setChecked(True)
        grid.addWidget(self.batch_apply_adjustments, 3, 0, 1, 3)

        row_1 = QtWidgets.QHBoxLayout()
        row_1.addWidget(self._button(self.tr("Usar carpeta actual"), self._use_current_dir_as_batch_input))
        row_1.addWidget(self._button(self.tr("Aplicar a selección"), self._on_batch_develop_selected))
        row_1.addWidget(self._button(self.tr("Aplicar a carpeta"), self._on_batch_develop_directory))

        self.batch_output = QtWidgets.QPlainTextEdit()
        self.batch_output.setReadOnly(True)
        self.batch_output.setPlaceholderText(self.tr("Salida JSON de exportación de derivados"))

        layout.addLayout(grid)
        layout.addLayout(row_1)
        layout.addWidget(self.batch_output, 1)
        return tab
