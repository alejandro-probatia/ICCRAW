from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .chart.detection import detect_chart, draw_detection_overlay
from .chart.sampling import ReferenceCatalog, sample_chart
from .core.models import PatchSample, Recipe, SampleSet, to_json_dict, write_json
from .core.recipe import load_recipe, save_recipe
from .core.utils import RAW_EXTENSIONS
from .profile.builder import build_profile
from .profile.development import build_development_profile
from .profile.export import batch_develop
from .raw.pipeline import develop_controlled


IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}


def auto_generate_profile_from_charts(
    chart_captures_dir: Path,
    recipe: Recipe,
    reference: ReferenceCatalog,
    profile_out: Path,
    profile_report_out: Path,
    work_dir: Path,
    development_profile_out: Path | None = None,
    calibrated_recipe_out: Path | None = None,
    calibrate_development: bool = True,
    chart_type: str = "colorchecker24",
    min_confidence: float = 0.35,
    allow_fallback_detection: bool = False,
    camera_model: str | None = None,
    lens_model: str | None = None,
    chart_capture_files: list[Path] | None = None,
) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    chart_dev_dir = work_dir / "chart_developed"
    detect_dir = work_dir / "detections"
    sample_dir = work_dir / "samples"
    overlay_dir = work_dir / "overlays"

    for d in (chart_dev_dir, detect_dir, sample_dir, overlay_dir):
        d.mkdir(parents=True, exist_ok=True)

    chart_files = (
        _normalize_chart_capture_files(chart_capture_files)
        if chart_capture_files is not None
        else _list_chart_capture_files(chart_captures_dir)
    )
    if not chart_files:
        source = "la selección explícita" if chart_capture_files is not None else str(chart_captures_dir)
        raise RuntimeError(f"No se encontraron capturas de carta en: {source}")

    initial_pass = _collect_chart_samples(
        chart_files=chart_files,
        recipe=recipe,
        reference=reference,
        chart_type=chart_type,
        min_confidence=min_confidence,
        allow_fallback_detection=allow_fallback_detection,
        chart_dev_dir=chart_dev_dir,
        detect_dir=detect_dir,
        sample_dir=sample_dir,
        overlay_dir=overlay_dir,
        pass_name="development_profile_source",
    )
    accepted_samples = initial_pass["accepted_samples"]
    skipped: list[dict[str, Any]] = list(initial_pass["skipped"])

    if not accepted_samples:
        raise RuntimeError(
            "No hubo capturas de carta válidas para construir perfil. "
            "Revisa exposición, encuadre de carta y min_confidence."
        )

    aggregated_initial = _aggregate_samples(accepted_samples, strategy=recipe.sampling_strategy)
    write_json(work_dir / "samples_aggregated_development_source.json", aggregated_initial)

    profile_recipe = recipe
    development_profile_path: str | None = None
    calibrated_recipe_path: str | None = None
    development_payload: dict[str, Any] | None = None

    if calibrate_development:
        development = build_development_profile(samples=aggregated_initial, base_recipe=recipe)
        development_profile_file = development_profile_out or (work_dir / "development_profile.json")
        calibrated_recipe_file = calibrated_recipe_out or (work_dir / "recipe_calibrated.yml")
        write_json(development_profile_file, development)
        save_recipe(development.calibrated_recipe, calibrated_recipe_file)
        development_profile_path = str(development_profile_file)
        calibrated_recipe_path = str(calibrated_recipe_file)
        development_payload = to_json_dict(development)
        profile_recipe = development.calibrated_recipe

        calibrated_pass = _collect_chart_samples(
            chart_files=chart_files,
            recipe=profile_recipe,
            reference=reference,
            chart_type=chart_type,
            min_confidence=min_confidence,
            allow_fallback_detection=allow_fallback_detection,
            existing_detections=initial_pass["detections"],
            chart_dev_dir=work_dir / "chart_developed_calibrated",
            detect_dir=work_dir / "detections_calibrated",
            sample_dir=work_dir / "samples_calibrated",
            overlay_dir=work_dir / "overlays_calibrated",
            pass_name="icc_profile_source",
        )
        accepted_samples = calibrated_pass["accepted_samples"]
        skipped.extend(calibrated_pass["skipped"])
        if not accepted_samples:
            raise RuntimeError(
                "No hubo capturas válidas tras aplicar el perfil de revelado. "
                "Revisa el JSON de desarrollo y los overlays calibrados."
            )

    aggregated_samples = _aggregate_samples(accepted_samples, strategy=profile_recipe.sampling_strategy)
    aggregated_samples_path = work_dir / "samples_aggregated.json"
    write_json(aggregated_samples_path, aggregated_samples)

    profile_result = build_profile(
        samples=aggregated_samples,
        recipe=profile_recipe,
        out_icc=profile_out,
        camera_model=camera_model,
        lens_model=lens_model,
    )
    write_json(profile_report_out, profile_result)

    return {
        "chart_captures_total": len(chart_files),
        "chart_captures_used": len(accepted_samples),
        "chart_captures_skipped": skipped,
        "development_profile_path": development_profile_path,
        "calibrated_recipe_path": calibrated_recipe_path,
        "development_profile": development_payload,
        "aggregated_samples": str(aggregated_samples_path),
        "profile": to_json_dict(profile_result),
        "profile_report_path": str(profile_report_out),
    }


def auto_profile_batch(
    chart_captures_dir: Path,
    target_captures_dir: Path,
    recipe: Recipe,
    reference: ReferenceCatalog,
    profile_out: Path,
    profile_report_out: Path,
    batch_out_dir: Path,
    work_dir: Path,
    development_profile_out: Path | None = None,
    calibrated_recipe_out: Path | None = None,
    calibrate_development: bool = True,
    chart_type: str = "colorchecker24",
    min_confidence: float = 0.35,
    allow_fallback_detection: bool = False,
    camera_model: str | None = None,
    lens_model: str | None = None,
    chart_capture_files: list[Path] | None = None,
) -> dict[str, Any]:
    profile_payload = auto_generate_profile_from_charts(
        chart_captures_dir=chart_captures_dir,
        recipe=recipe,
        reference=reference,
        profile_out=profile_out,
        profile_report_out=profile_report_out,
        work_dir=work_dir,
        development_profile_out=development_profile_out,
        calibrated_recipe_out=calibrated_recipe_out,
        calibrate_development=calibrate_development,
        chart_type=chart_type,
        min_confidence=min_confidence,
        allow_fallback_detection=allow_fallback_detection,
        camera_model=camera_model,
        lens_model=lens_model,
        chart_capture_files=chart_capture_files,
    )

    batch_recipe = recipe
    calibrated_path = profile_payload.get("calibrated_recipe_path")
    if isinstance(calibrated_path, str) and calibrated_path:
        batch_recipe = load_recipe(Path(calibrated_path))

    manifest = batch_develop(
        raws_dir=target_captures_dir,
        recipe=batch_recipe,
        profile_path=profile_out,
        out_dir=batch_out_dir,
    )
    manifest_path = batch_out_dir / "batch_manifest.json"
    write_json(manifest_path, manifest)

    return {
        "chart_captures_total": profile_payload["chart_captures_total"],
        "chart_captures_used": profile_payload["chart_captures_used"],
        "chart_captures_skipped": profile_payload["chart_captures_skipped"],
        "development_profile_path": profile_payload.get("development_profile_path"),
        "calibrated_recipe_path": profile_payload.get("calibrated_recipe_path"),
        "development_profile": profile_payload.get("development_profile"),
        "aggregated_samples": profile_payload["aggregated_samples"],
        "profile": profile_payload["profile"],
        "profile_report_path": profile_payload["profile_report_path"],
        "batch_manifest": to_json_dict(manifest),
        "batch_manifest_path": str(manifest_path),
    }


def _aggregate_samples(sample_sets: list[SampleSet], strategy: str) -> SampleSet:
    grouped: dict[str, list[PatchSample]] = defaultdict(list)
    for sset in sample_sets:
        for sample in sset.samples:
            grouped[sample.patch_id].append(sample)

    if not grouped:
        raise RuntimeError("No hay parches para agregar")

    aggregated_samples: list[PatchSample] = []
    for patch_id in sorted(grouped.keys(), key=_patch_sort_key):
        items = grouped[patch_id]
        measured = np.asarray([s.measured_rgb for s in items], dtype=np.float64)
        measured_med = np.median(measured, axis=0)

        excluded = float(np.median([s.excluded_pixel_ratio for s in items]))
        saturated = float(np.median([s.saturated_pixel_ratio for s in items]))

        ref_rgb = next((s.reference_rgb for s in items if s.reference_rgb is not None), None)
        ref_lab = next((s.reference_lab for s in items if s.reference_lab is not None), None)

        aggregated_samples.append(
            PatchSample(
                patch_id=patch_id,
                measured_rgb=[float(v) for v in measured_med.tolist()],
                reference_rgb=ref_rgb,
                reference_lab=ref_lab,
                excluded_pixel_ratio=excluded,
                saturated_pixel_ratio=saturated,
            )
        )

    first = sample_sets[0]
    missing = [
        p.patch_id for p in aggregated_samples if p.reference_lab is None
    ]

    return SampleSet(
        chart_name=first.chart_name,
        chart_version=first.chart_version,
        illuminant=first.illuminant,
        strategy=f"aggregate_median({first.strategy or strategy})",
        samples=aggregated_samples,
        missing_reference_patches=missing,
    )


def _collect_chart_samples(
    *,
    chart_files: list[Path],
    recipe: Recipe,
    reference: ReferenceCatalog,
    chart_type: str,
    min_confidence: float,
    allow_fallback_detection: bool,
    chart_dev_dir: Path,
    detect_dir: Path,
    sample_dir: Path,
    overlay_dir: Path,
    pass_name: str,
    existing_detections: dict[Path, Any] | None = None,
) -> dict[str, Any]:
    for d in (chart_dev_dir, detect_dir, sample_dir, overlay_dir):
        d.mkdir(parents=True, exist_ok=True)

    accepted_samples: list[SampleSet] = []
    skipped: list[dict[str, Any]] = []
    detections: dict[Path, Any] = {}

    for idx, chart_file in enumerate(chart_files, start=1):
        prefix = f"{idx:03d}_{chart_file.stem}"
        developed_tiff = chart_dev_dir / f"{prefix}.tiff"
        detection_path = detect_dir / f"{prefix}.json"
        overlay_path = overlay_dir / f"{prefix}.png"
        sample_path = sample_dir / f"{prefix}.json"

        try:
            develop_controlled(chart_file, recipe, developed_tiff, None)
            detection = existing_detections.get(chart_file) if existing_detections else None
            if detection is None:
                detection = detect_chart(developed_tiff, chart_type=chart_type)
            else:
                detection.warnings = list(detection.warnings) + [
                    "geometria de carta reutilizada desde pasada de perfil de revelado"
                ]
            write_json(detection_path, detection)
            draw_detection_overlay(developed_tiff, detection, overlay_path)
            detections[chart_file] = detection

            if detection.detection_mode == "fallback" and not allow_fallback_detection:
                skipped.append(
                    {
                        "pass": pass_name,
                        "capture": str(chart_file),
                        "reason": "fallback_detection",
                        "confidence": float(detection.confidence_score),
                        "detection_json": str(detection_path),
                    }
                )
                continue

            if detection.confidence_score < float(min_confidence):
                skipped.append(
                    {
                        "pass": pass_name,
                        "capture": str(chart_file),
                        "reason": "low_confidence",
                        "confidence": float(detection.confidence_score),
                        "min_confidence": float(min_confidence),
                        "detection_json": str(detection_path),
                    }
                )
                continue

            samples = sample_chart(
                developed_tiff,
                detection,
                reference,
                strategy=recipe.sampling_strategy,
                trim_percent=recipe.sampling_trim_percent,
                reject_saturated=recipe.sampling_reject_saturated,
            )
            write_json(sample_path, samples)
            accepted_samples.append(samples)

        except Exception as exc:
            skipped.append(
                {
                    "pass": pass_name,
                    "capture": str(chart_file),
                    "reason": "processing_error",
                    "error": str(exc),
                }
            )

    return {"accepted_samples": accepted_samples, "skipped": skipped, "detections": detections}


def _patch_sort_key(patch_id: str) -> tuple[int, str]:
    digits = "".join(ch for ch in patch_id if ch.isdigit())
    if digits:
        return int(digits), patch_id
    return 10_000, patch_id


def _list_chart_capture_files(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        raise RuntimeError(f"Directorio inválido: {folder}")

    files = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in RAW_EXTENSIONS.union(IMAGE_EXTENSIONS)
    ]
    files.sort()
    return files


def _normalize_chart_capture_files(files: list[Path]) -> list[Path]:
    supported = RAW_EXTENSIONS.union(IMAGE_EXTENSIONS)
    normalized: list[Path] = []
    invalid: list[str] = []

    for item in files:
        p = Path(item).expanduser()
        if not p.exists() or not p.is_file() or p.suffix.lower() not in supported:
            invalid.append(str(p))
            continue
        normalized.append(p)

    if invalid:
        preview = ", ".join(invalid[:5])
        suffix = "" if len(invalid) <= 5 else f" (+{len(invalid) - 5} más)"
        raise RuntimeError(f"Capturas de carta inválidas o incompatibles: {preview}{suffix}")

    return sorted(set(normalized), key=lambda p: str(p))
