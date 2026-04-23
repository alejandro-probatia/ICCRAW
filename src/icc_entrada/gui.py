from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .chart_detection import detect_chart, draw_detection_overlay
from .cli import APP_VERSION
from .export import batch_develop
from .models import to_json_dict, write_json
from .pipeline import develop_controlled
from .profiling import build_profile, validate_profile
from .raw import raw_info
from .recipe import load_recipe
from .reporting import gather_run_context
from .sampling import ReferenceCatalog, chart_detection_from_json, sample_chart, sampleset_from_json
from .workflow import auto_profile_batch


class ICCRawGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ICCRAW - Interfaz Técnica")
        self.root.geometry("1200x860")

        self.status_var = tk.StringVar(value="Listo")

        self._build_header()
        self._build_tabs()
        self._build_status_bar()

    def _build_header(self) -> None:
        frame = ttk.Frame(self.root, padding=(12, 12, 12, 4))
        frame.pack(fill="x")

        title = ttk.Label(
            frame,
            text="ICCRAW",
            font=("TkDefaultFont", 15, "bold"),
        )
        title.pack(anchor="w")

        subtitle = ttk.Label(
            frame,
            text="Interfaz simple para pipeline reproducible RAW -> carta -> perfil ICC -> lote",
        )
        subtitle.pack(anchor="w")

    def _build_tabs(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=8)

        self.tab_raw = ttk.Frame(notebook)
        self.tab_develop = ttk.Frame(notebook)
        self.tab_chart = ttk.Frame(notebook)
        self.tab_profile = ttk.Frame(notebook)
        self.tab_batch = ttk.Frame(notebook)
        self.tab_auto = ttk.Frame(notebook)

        notebook.add(self.tab_raw, text="RAW Info")
        notebook.add(self.tab_develop, text="Develop")
        notebook.add(self.tab_chart, text="Detect + Sample")
        notebook.add(self.tab_profile, text="Build + Validate Profile")
        notebook.add(self.tab_batch, text="Batch Develop")
        notebook.add(self.tab_auto, text="Auto Workflow")

        self._build_tab_raw()
        self._build_tab_develop()
        self._build_tab_chart()
        self._build_tab_profile()
        self._build_tab_batch()
        self._build_tab_auto()

    def _build_status_bar(self) -> None:
        frame = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        frame.pack(fill="x")
        ttk.Separator(frame).pack(fill="x", pady=(0, 8))
        ttk.Label(frame, textvariable=self.status_var).pack(anchor="w")

    def _build_tab_raw(self) -> None:
        self.raw_input = tk.StringVar(value="testdata/raw/mock_capture.nef")
        self.raw_output = self._build_form_and_output(self.tab_raw)

        form = self.raw_output["form"]
        output = self.raw_output["output"]

        self._path_row(form, 0, "Input RAW", self.raw_input, file_select=True)
        self._action_row(
            form,
            1,
            [
                ("Leer metadatos", lambda: self._run_raw_info(output)),
            ],
        )

    def _build_tab_develop(self) -> None:
        self.dev_input = tk.StringVar(value="testdata/charts/synthetic_colorchecker.tiff")
        self.dev_recipe = tk.StringVar(value="testdata/recipes/scientific_recipe.yml")
        self.dev_out = tk.StringVar(value="/tmp/session_chart.tiff")
        self.dev_audit = tk.StringVar(value="/tmp/session_chart_linear.tiff")

        tab = self._build_form_and_output(self.tab_develop)
        form, output = tab["form"], tab["output"]

        self._path_row(form, 0, "Input RAW/Imagen", self.dev_input, file_select=True)
        self._path_row(form, 1, "Recipe YAML/JSON", self.dev_recipe, file_select=True)
        self._path_row(form, 2, "Output TIFF", self.dev_out, save_select=True)
        self._path_row(form, 3, "Audit TIFF (opcional)", self.dev_audit, save_select=True)
        self._action_row(form, 4, [("Ejecutar develop", lambda: self._run_develop(output))])

    def _build_tab_chart(self) -> None:
        self.chart_input = tk.StringVar(value="/tmp/session_chart.tiff")
        self.chart_detect_out = tk.StringVar(value="/tmp/detection.json")
        self.chart_preview_out = tk.StringVar(value="/tmp/overlay.png")
        self.chart_reference = tk.StringVar(value="testdata/references/colorchecker24_reference.json")
        self.chart_samples_out = tk.StringVar(value="/tmp/samples.json")
        self.chart_type = tk.StringVar(value="colorchecker24")

        tab = self._build_form_and_output(self.tab_chart)
        form, output = tab["form"], tab["output"]

        self._path_row(form, 0, "Input TIFF", self.chart_input, file_select=True)
        self._path_row(form, 1, "Detection JSON", self.chart_detect_out, save_select=True)
        self._path_row(form, 2, "Preview PNG (opcional)", self.chart_preview_out, save_select=True)

        ttk.Label(form, text="Tipo de carta").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            form,
            textvariable=self.chart_type,
            values=["colorchecker24", "it8"],
            state="readonly",
            width=20,
        ).grid(row=3, column=1, sticky="w", pady=4)

        self._path_row(form, 4, "Referencia JSON", self.chart_reference, file_select=True)
        self._path_row(form, 5, "Samples JSON", self.chart_samples_out, save_select=True)

        self._action_row(
            form,
            6,
            [
                ("Detectar carta", lambda: self._run_detect_chart(output)),
                ("Muestrear carta", lambda: self._run_sample_chart(output)),
            ],
        )

    def _build_tab_profile(self) -> None:
        self.profile_samples = tk.StringVar(value="/tmp/samples.json")
        self.profile_recipe = tk.StringVar(value="testdata/recipes/scientific_recipe.yml")
        self.profile_icc = tk.StringVar(value="/tmp/camera_profile.icc")
        self.profile_report = tk.StringVar(value="/tmp/profile_report.json")
        self.profile_validation = tk.StringVar(value="/tmp/validation.json")
        self.profile_camera = tk.StringVar(value="")
        self.profile_lens = tk.StringVar(value="")

        tab = self._build_form_and_output(self.tab_profile)
        form, output = tab["form"], tab["output"]

        self._path_row(form, 0, "Samples JSON", self.profile_samples, file_select=True)
        self._path_row(form, 1, "Recipe YAML/JSON", self.profile_recipe, file_select=True)
        self._path_row(form, 2, "Output ICC", self.profile_icc, save_select=True)
        self._path_row(form, 3, "Report JSON", self.profile_report, save_select=True)
        self._path_row(form, 4, "Validation JSON", self.profile_validation, save_select=True)

        self._entry_row(form, 5, "Camera model (opcional)", self.profile_camera)
        self._entry_row(form, 6, "Lens model (opcional)", self.profile_lens)

        self._action_row(
            form,
            7,
            [
                ("Construir perfil ICC", lambda: self._run_build_profile(output)),
                ("Validar perfil", lambda: self._run_validate_profile(output)),
            ],
        )

    def _build_tab_batch(self) -> None:
        self.batch_input = tk.StringVar(value="testdata/batch_images")
        self.batch_recipe = tk.StringVar(value="testdata/recipes/scientific_recipe.yml")
        self.batch_profile = tk.StringVar(value="/tmp/camera_profile.icc")
        self.batch_out = tk.StringVar(value="/tmp/batch_tiffs")

        tab = self._build_form_and_output(self.tab_batch)
        form, output = tab["form"], tab["output"]

        self._path_row(form, 0, "Directorio input (RAW o TIFF)", self.batch_input, dir_select=True)
        self._path_row(form, 1, "Recipe YAML/JSON", self.batch_recipe, file_select=True)
        self._path_row(form, 2, "Perfil ICC", self.batch_profile, file_select=True)
        self._path_row(form, 3, "Directorio output", self.batch_out, dir_select=True)

        self._action_row(form, 4, [("Ejecutar batch", lambda: self._run_batch(output))])

    def _build_tab_auto(self) -> None:
        self.auto_charts = tk.StringVar(value="testdata/batch_images")
        self.auto_targets = tk.StringVar(value="testdata/batch_images")
        self.auto_recipe = tk.StringVar(value="testdata/recipes/scientific_recipe.yml")
        self.auto_reference = tk.StringVar(value="testdata/references/colorchecker24_reference.json")
        self.auto_profile_out = tk.StringVar(value="/tmp/camera_profile_auto.icc")
        self.auto_profile_report = tk.StringVar(value="/tmp/profile_report_auto.json")
        self.auto_out = tk.StringVar(value="/tmp/batch_tiffs_auto")
        self.auto_workdir = tk.StringVar(value="/tmp/iccraw_auto_work")
        self.auto_chart_type = tk.StringVar(value="colorchecker24")
        self.auto_min_conf = tk.StringVar(value="0.35")
        self.auto_camera = tk.StringVar(value="")
        self.auto_lens = tk.StringVar(value="")

        tab = self._build_form_and_output(self.tab_auto)
        form, output = tab["form"], tab["output"]

        self._path_row(form, 0, "Capturas carta (dir RAW/imagen)", self.auto_charts, dir_select=True)
        self._path_row(form, 1, "Capturas objetivo (dir RAW/imagen)", self.auto_targets, dir_select=True)
        self._path_row(form, 2, "Recipe YAML/JSON", self.auto_recipe, file_select=True)
        self._path_row(form, 3, "Referencia carta JSON", self.auto_reference, file_select=True)
        self._path_row(form, 4, "Perfil ICC salida", self.auto_profile_out, save_select=True)
        self._path_row(form, 5, "Reporte perfil JSON", self.auto_profile_report, save_select=True)
        self._path_row(form, 6, "Output batch TIFF dir", self.auto_out, dir_select=True)
        self._path_row(form, 7, "Workdir intermedio", self.auto_workdir, dir_select=True)

        ttk.Label(form, text="Tipo de carta").grid(row=8, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            form,
            textvariable=self.auto_chart_type,
            values=["colorchecker24", "it8"],
            state="readonly",
            width=20,
        ).grid(row=8, column=1, sticky="w", pady=4)

        self._entry_row(form, 9, "Min confidence (0-1)", self.auto_min_conf)
        self._entry_row(form, 10, "Camera model (opcional)", self.auto_camera)
        self._entry_row(form, 11, "Lens model (opcional)", self.auto_lens)

        self._action_row(
            form,
            12,
            [("Ejecutar flujo automático completo", lambda: self._run_auto_workflow(output))],
        )

    def _build_form_and_output(self, parent: ttk.Frame) -> dict:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        form = ttk.Frame(parent, padding=12)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        output_frame = ttk.Frame(parent, padding=(12, 0, 12, 12))
        output_frame.grid(row=1, column=0, sticky="nsew")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        text = tk.Text(output_frame, wrap="none", height=20)
        ybar = ttk.Scrollbar(output_frame, orient="vertical", command=text.yview)
        xbar = ttk.Scrollbar(output_frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

        text.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")

        return {"form": form, "output": text}

    def _entry_row(self, parent: ttk.Frame, row: int, label: str, var: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=4)

    def _path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        var: tk.StringVar,
        *,
        file_select: bool = False,
        save_select: bool = False,
        dir_select: bool = False,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=4)

        if file_select:
            ttk.Button(parent, text="...", width=3, command=lambda: self._pick_file(var)).grid(
                row=row, column=2, padx=(8, 0), pady=4
            )
        elif save_select:
            ttk.Button(parent, text="...", width=3, command=lambda: self._pick_save(var)).grid(
                row=row, column=2, padx=(8, 0), pady=4
            )
        elif dir_select:
            ttk.Button(parent, text="...", width=3, command=lambda: self._pick_dir(var)).grid(
                row=row, column=2, padx=(8, 0), pady=4
            )

    def _action_row(self, parent: ttk.Frame, row: int, actions: list[tuple[str, callable]]) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        for i, (label, callback) in enumerate(actions):
            ttk.Button(frame, text=label, command=callback).grid(row=0, column=i, padx=(0, 8))

    def _pick_file(self, var: tk.StringVar) -> None:
        value = filedialog.askopenfilename()
        if value:
            var.set(value)

    def _pick_save(self, var: tk.StringVar) -> None:
        value = filedialog.asksaveasfilename()
        if value:
            var.set(value)

    def _pick_dir(self, var: tk.StringVar) -> None:
        value = filedialog.askdirectory()
        if value:
            var.set(value)

    def _render_json(self, output: tk.Text, payload: dict) -> None:
        output.delete("1.0", tk.END)
        output.insert("1.0", json.dumps(payload, indent=2, ensure_ascii=False))

    def _run_task(self, task, on_success, context_label: str) -> None:
        self.status_var.set(f"Ejecutando: {context_label}...")

        def worker() -> None:
            try:
                result = task()
                self.root.after(0, lambda: self._on_task_success(result, on_success, context_label))
            except Exception as exc:
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._on_task_error(exc, tb, context_label))

        threading.Thread(target=worker, daemon=True).start()

    def _on_task_success(self, result, on_success, context_label: str) -> None:
        on_success(result)
        self.status_var.set(f"Completado: {context_label}")

    def _on_task_error(self, exc: Exception, tb: str, context_label: str) -> None:
        self.status_var.set(f"Error en: {context_label}")
        messagebox.showerror("Error", f"{exc}\n\n{tb}")

    def _run_raw_info(self, output: tk.Text) -> None:
        path = Path(self.raw_input.get().strip())

        def task():
            return raw_info(path)

        def on_success(result):
            self._render_json(output, to_json_dict(result))

        self._run_task(task, on_success, "raw-info")

    def _run_develop(self, output: tk.Text) -> None:
        in_path = Path(self.dev_input.get().strip())
        recipe_path = Path(self.dev_recipe.get().strip())
        out_path = Path(self.dev_out.get().strip())
        audit_str = self.dev_audit.get().strip()
        audit_path = Path(audit_str) if audit_str else None

        def task():
            recipe = load_recipe(recipe_path)
            result = develop_controlled(in_path, recipe, out_path, audit_path)
            return {
                "run_context": gather_run_context(APP_VERSION),
                "develop": to_json_dict(result),
            }

        def on_success(payload):
            self._render_json(output, payload)

        self._run_task(task, on_success, "develop")

    def _run_detect_chart(self, output: tk.Text) -> None:
        in_path = Path(self.chart_input.get().strip())
        detect_out = Path(self.chart_detect_out.get().strip())
        preview_out = self.chart_preview_out.get().strip()
        chart_type = self.chart_type.get().strip()

        def task():
            result = detect_chart(in_path, chart_type=chart_type)
            write_json(detect_out, result)
            if preview_out:
                draw_detection_overlay(in_path, result, Path(preview_out))
            return to_json_dict(result)

        def on_success(payload):
            self._render_json(output, payload)

        self._run_task(task, on_success, "detect-chart")

    def _run_sample_chart(self, output: tk.Text) -> None:
        in_path = Path(self.chart_input.get().strip())
        detection_path = Path(self.chart_detect_out.get().strip())
        reference_path = Path(self.chart_reference.get().strip())
        samples_out = Path(self.chart_samples_out.get().strip())

        def task():
            detection = chart_detection_from_json(detection_path)
            reference = ReferenceCatalog.from_path(reference_path)
            samples = sample_chart(in_path, detection, reference)
            write_json(samples_out, samples)
            return to_json_dict(samples)

        def on_success(payload):
            self._render_json(output, payload)

        self._run_task(task, on_success, "sample-chart")

    def _run_build_profile(self, output: tk.Text) -> None:
        samples_path = Path(self.profile_samples.get().strip())
        recipe_path = Path(self.profile_recipe.get().strip())
        icc_path = Path(self.profile_icc.get().strip())
        report_path = Path(self.profile_report.get().strip())
        camera = self.profile_camera.get().strip() or None
        lens = self.profile_lens.get().strip() or None

        def task():
            samples = sampleset_from_json(samples_path)
            recipe = load_recipe(recipe_path)
            result = build_profile(samples, recipe, icc_path, camera_model=camera, lens_model=lens)
            write_json(report_path, result)
            return to_json_dict(result)

        def on_success(payload):
            self._render_json(output, payload)

        self._run_task(task, on_success, "build-profile")

    def _run_validate_profile(self, output: tk.Text) -> None:
        samples_path = Path(self.profile_samples.get().strip())
        icc_path = Path(self.profile_icc.get().strip())
        validation_out = Path(self.profile_validation.get().strip())

        def task():
            samples = sampleset_from_json(samples_path)
            result = validate_profile(samples, icc_path)
            write_json(validation_out, result)
            return to_json_dict(result)

        def on_success(payload):
            self._render_json(output, payload)

        self._run_task(task, on_success, "validate-profile")

    def _run_batch(self, output: tk.Text) -> None:
        input_dir = Path(self.batch_input.get().strip())
        recipe_path = Path(self.batch_recipe.get().strip())
        profile_path = Path(self.batch_profile.get().strip())
        out_dir = Path(self.batch_out.get().strip())

        def task():
            recipe = load_recipe(recipe_path)
            manifest = batch_develop(input_dir, recipe, profile_path, out_dir)
            write_json(out_dir / "batch_manifest.json", manifest)
            return to_json_dict(manifest)

        def on_success(payload):
            self._render_json(output, payload)

        self._run_task(task, on_success, "batch-develop")

    def _run_auto_workflow(self, output: tk.Text) -> None:
        charts_dir = Path(self.auto_charts.get().strip())
        targets_dir = Path(self.auto_targets.get().strip())
        recipe_path = Path(self.auto_recipe.get().strip())
        reference_path = Path(self.auto_reference.get().strip())
        profile_out = Path(self.auto_profile_out.get().strip())
        profile_report = Path(self.auto_profile_report.get().strip())
        out_dir = Path(self.auto_out.get().strip())
        workdir = Path(self.auto_workdir.get().strip())
        chart_type = self.auto_chart_type.get().strip()
        min_conf = float(self.auto_min_conf.get().strip() or "0.35")
        camera = self.auto_camera.get().strip() or None
        lens = self.auto_lens.get().strip() or None

        def task():
            recipe = load_recipe(recipe_path)
            reference = ReferenceCatalog.from_path(reference_path)
            result = auto_profile_batch(
                chart_captures_dir=charts_dir,
                target_captures_dir=targets_dir,
                recipe=recipe,
                reference=reference,
                profile_out=profile_out,
                profile_report_out=profile_report,
                batch_out_dir=out_dir,
                work_dir=workdir,
                chart_type=chart_type,
                min_confidence=min_conf,
                camera_model=camera,
                lens_model=lens,
            )
            return result

        def on_success(payload):
            self._render_json(output, payload)

        self._run_task(task, on_success, "auto-profile-batch")


def main() -> int:
    root = tk.Tk()
    ICCRawGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
