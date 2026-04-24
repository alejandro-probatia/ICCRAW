from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .chart.detection import detect_chart, draw_detection_overlay
from .chart.sampling import ReferenceCatalog, sample_chart
from .core.models import (
    ChartDetectionResult,
    PatchDetection,
    PatchSample,
    Point2,
    Recipe,
    SampleSet,
    to_json_dict,
    write_json,
)
from .core.recipe import load_recipe, save_recipe
from .core.utils import RAW_EXTENSIONS
from .profile.builder import build_profile, validate_profile
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
    manual_detections: dict[Path, Any] | None = None,
    validation_holdout_count: int = 0,
    validation_report_out: Path | None = None,
    qa_mean_delta_e2000_max: float = 5.0,
    qa_max_delta_e2000_max: float = 10.0,
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
    manual_detection_map = _normalize_detection_map(manual_detections)
    training_files, validation_files = _split_training_validation_files(chart_files, validation_holdout_count)

    initial_pass = _collect_chart_samples(
        chart_files=training_files,
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
        existing_detections=manual_detection_map,
        existing_detection_note="geometria de carta desde deteccion manual guardada",
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
            chart_files=training_files,
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

    validation_payload: dict[str, Any] | None = None
    qa_report_path: str | None = None
    if validation_files:
        validation_detection_map = _validation_detection_map(
            validation_files=validation_files,
            manual_detection_map=manual_detection_map,
            recipe=recipe,
            chart_type=chart_type,
            min_confidence=min_confidence,
            allow_fallback_detection=allow_fallback_detection,
            work_dir=work_dir,
        )
        validation_pass = _collect_chart_samples(
            chart_files=validation_files,
            recipe=profile_recipe,
            reference=reference,
            chart_type=chart_type,
            min_confidence=min_confidence,
            allow_fallback_detection=allow_fallback_detection,
            chart_dev_dir=work_dir / "chart_developed_validation",
            detect_dir=work_dir / "detections_validation",
            sample_dir=work_dir / "samples_validation",
            overlay_dir=work_dir / "overlays_validation",
            pass_name="icc_validation_source",
            existing_detections=validation_detection_map,
            existing_detection_note="geometria de carta reutilizada desde pasada base de validacion",
        )
        validation_samples = validation_pass["accepted_samples"]
        skipped.extend(validation_pass["skipped"])

        validation_result_payload: dict[str, Any] | None = None
        validation_samples_path: str | None = None
        if validation_samples:
            aggregated_validation = _aggregate_samples(validation_samples, strategy=profile_recipe.sampling_strategy)
            aggregated_validation_path = work_dir / "samples_aggregated_validation.json"
            write_json(aggregated_validation_path, aggregated_validation)
            validation_samples_path = str(aggregated_validation_path)
            validation_result = validate_profile(samples=aggregated_validation, profile_path=profile_out)
            validation_result_payload = to_json_dict(validation_result)

        qa_report = _build_session_qa_report(
            training_files=training_files,
            validation_files=validation_files,
            training_samples=aggregated_samples,
            validation_samples=_aggregate_samples(validation_samples, strategy=profile_recipe.sampling_strategy)
            if validation_samples
            else None,
            training_profile_result=profile_result,
            validation_result=validation_result_payload,
            validation_skipped=validation_pass["skipped"],
            qa_mean_delta_e2000_max=qa_mean_delta_e2000_max,
            qa_max_delta_e2000_max=qa_max_delta_e2000_max,
        )
        qa_file = validation_report_out or (work_dir / "qa_session_report.json")
        write_json(qa_file, qa_report)
        qa_report_path = str(qa_file)
        validation_payload = {
            "validation_captures_total": len(validation_files),
            "validation_captures_used": len(validation_samples),
            "validation_captures_skipped": validation_pass["skipped"],
            "validation_samples": validation_samples_path,
            "validation_result": validation_result_payload,
            "qa_report": qa_report,
            "qa_report_path": qa_report_path,
        }

    return {
        "chart_captures_total": len(chart_files),
        "training_captures_total": len(training_files),
        "chart_captures_used": len(accepted_samples),
        "chart_captures_skipped": skipped,
        "validation_captures_total": len(validation_files),
        "validation_captures_used": validation_payload["validation_captures_used"] if validation_payload else 0,
        "development_profile_path": development_profile_path,
        "calibrated_recipe_path": calibrated_recipe_path,
        "development_profile": development_payload,
        "aggregated_samples": str(aggregated_samples_path),
        "profile": to_json_dict(profile_result),
        "profile_report_path": str(profile_report_out),
        "validation": validation_payload,
        "qa_report_path": qa_report_path,
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
    manual_detections: dict[Path, Any] | None = None,
    validation_holdout_count: int = 0,
    validation_report_out: Path | None = None,
    qa_mean_delta_e2000_max: float = 5.0,
    qa_max_delta_e2000_max: float = 10.0,
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
        manual_detections=manual_detections,
        validation_holdout_count=validation_holdout_count,
        validation_report_out=validation_report_out,
        qa_mean_delta_e2000_max=qa_mean_delta_e2000_max,
        qa_max_delta_e2000_max=qa_max_delta_e2000_max,
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
        "validation_captures_total": profile_payload.get("validation_captures_total", 0),
        "validation_captures_used": profile_payload.get("validation_captures_used", 0),
        "validation": profile_payload.get("validation"),
        "qa_report_path": profile_payload.get("qa_report_path"),
        "batch_manifest": to_json_dict(manifest),
        "batch_manifest_path": str(manifest_path),
    }


def _split_training_validation_files(chart_files: list[Path], validation_holdout_count: int) -> tuple[list[Path], list[Path]]:
    holdout = max(0, int(validation_holdout_count))
    if holdout <= 0 or len(chart_files) < 2:
        return list(chart_files), []

    holdout = min(holdout, len(chart_files) - 1)
    return list(chart_files[:-holdout]), list(chart_files[-holdout:])


def _build_session_qa_report(
    *,
    training_files: list[Path],
    validation_files: list[Path],
    training_samples: SampleSet,
    validation_samples: SampleSet | None,
    training_profile_result: Any,
    validation_result: dict[str, Any] | None,
    validation_skipped: list[dict[str, Any]],
    qa_mean_delta_e2000_max: float,
    qa_max_delta_e2000_max: float,
) -> dict[str, Any]:
    training_error = asdict(training_profile_result.error_summary)
    validation_error = validation_result.get("error_summary") if validation_result else None

    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "id": "validation_samples_available",
            "severity": "error",
            "passed": validation_result is not None,
            "message": "hay muestras independientes de validacion" if validation_result else "no hay muestras independientes validas",
        }
    )

    if validation_error:
        mean_de = float(validation_error.get("mean_delta_e2000", float("inf")))
        max_de = float(validation_error.get("max_delta_e2000", float("inf")))
        checks.extend(
            [
                {
                    "id": "validation_mean_delta_e2000",
                    "severity": "error",
                    "value": mean_de,
                    "limit": float(qa_mean_delta_e2000_max),
                    "passed": mean_de <= float(qa_mean_delta_e2000_max),
                },
                {
                    "id": "validation_max_delta_e2000",
                    "severity": "error",
                    "value": max_de,
                    "limit": float(qa_max_delta_e2000_max),
                    "passed": max_de <= float(qa_max_delta_e2000_max),
                },
            ]
        )

    training_quality = _sample_quality(training_samples)
    validation_quality = _sample_quality(validation_samples) if validation_samples else None
    training_worst_patches = _rank_patch_errors(getattr(training_profile_result, "patch_errors", []))
    validation_worst_patches = _rank_patch_errors(validation_result.get("patch_errors", [])) if validation_result else []
    training_patch_outliers = _patch_error_outliers(training_worst_patches, qa_max_delta_e2000_max)
    validation_patch_outliers = _patch_error_outliers(validation_worst_patches, qa_max_delta_e2000_max)
    for label, quality in (("training", training_quality), ("validation", validation_quality)):
        if not quality:
            continue
        max_sat = float(quality["max_saturated_pixel_ratio"])
        checks.append(
            {
                "id": f"{label}_max_saturation",
                "severity": "warning",
                "value": max_sat,
                "limit": 0.02,
                "passed": max_sat <= 0.02,
            }
        )

    for label, outliers in (("training", training_patch_outliers), ("validation", validation_patch_outliers)):
        if not outliers:
            continue
        checks.append(
            {
                "id": f"{label}_patch_delta_e2000_outliers",
                "severity": "warning",
                "value": len(outliers),
                "limit": float(qa_max_delta_e2000_max),
                "passed": False,
                "patch_ids": [str(item["patch_id"]) for item in outliers],
            }
        )

    hard_failures = [check for check in checks if check["severity"] == "error" and not check["passed"]]
    if not validation_files:
        status = "not_validated"
    elif hard_failures:
        status = "rejected"
    else:
        status = "validated"

    return {
        "status": status,
        "training_captures": [str(p) for p in training_files],
        "validation_captures": [str(p) for p in validation_files],
        "thresholds": {
            "mean_delta_e2000_max": float(qa_mean_delta_e2000_max),
            "max_delta_e2000_max": float(qa_max_delta_e2000_max),
        },
        "training_error_summary": training_error,
        "validation_error_summary": validation_error,
        "training_sample_quality": training_quality,
        "validation_sample_quality": validation_quality,
        "training_worst_patches": training_worst_patches[:8],
        "validation_worst_patches": validation_worst_patches[:8],
        "training_patch_outliers": training_patch_outliers,
        "validation_patch_outliers": validation_patch_outliers,
        "validation_skipped": validation_skipped,
        "checks": checks,
    }


def _rank_patch_errors(errors: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    raw_errors = errors if isinstance(errors, list) else []
    for error in raw_errors:
        if hasattr(error, "__dataclass_fields__"):
            data = asdict(error)
        elif isinstance(error, dict):
            data = error
        else:
            continue

        patch_id = str(data.get("patch_id") or "").strip()
        if not patch_id:
            continue
        try:
            delta_e76 = float(data.get("delta_e76", 0.0))
            delta_e2000 = float(data.get("delta_e2000", 0.0))
        except (TypeError, ValueError):
            continue
        records.append(
            {
                "patch_id": patch_id,
                "delta_e76": delta_e76,
                "delta_e2000": delta_e2000,
            }
        )
    return sorted(records, key=lambda item: item["delta_e2000"], reverse=True)


def _patch_error_outliers(records: list[dict[str, Any]], delta_e2000_limit: float) -> list[dict[str, Any]]:
    limit = float(delta_e2000_limit)
    return [record for record in records if float(record["delta_e2000"]) > limit]


def _sample_quality(samples: SampleSet) -> dict[str, Any]:
    saturated = np.asarray([s.saturated_pixel_ratio for s in samples.samples], dtype=np.float64)
    excluded = np.asarray([s.excluded_pixel_ratio for s in samples.samples], dtype=np.float64)
    return {
        "patch_count": len(samples.samples),
        "max_saturated_pixel_ratio": float(np.max(saturated)) if saturated.size else 0.0,
        "median_saturated_pixel_ratio": float(np.median(saturated)) if saturated.size else 0.0,
        "max_excluded_pixel_ratio": float(np.max(excluded)) if excluded.size else 0.0,
        "median_excluded_pixel_ratio": float(np.median(excluded)) if excluded.size else 0.0,
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
    existing_detection_note: str = "geometria de carta reutilizada desde pasada de perfil de revelado",
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
            detection_key = chart_file.expanduser().resolve()
            detection = existing_detections.get(detection_key) if existing_detections else None
            if detection is None:
                detection = detect_chart(developed_tiff, chart_type=chart_type)
            else:
                detection = _coerce_chart_detection(detection)
                detection.warnings = list(detection.warnings) + [
                    existing_detection_note
                ]
            write_json(detection_path, detection)
            draw_detection_overlay(developed_tiff, detection, overlay_path)
            detections[detection_key] = detection

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


def _validation_detection_map(
    *,
    validation_files: list[Path],
    manual_detection_map: dict[Path, Any] | None,
    recipe: Recipe,
    chart_type: str,
    min_confidence: float,
    allow_fallback_detection: bool,
    work_dir: Path,
) -> dict[Path, Any] | None:
    detection_map: dict[Path, Any] = {}
    if manual_detection_map:
        detection_map.update(manual_detection_map)

    missing = [
        p for p in validation_files
        if p.expanduser().resolve() not in detection_map
    ]
    if not missing:
        return detection_map or None

    geometry = _collect_chart_geometries(
        chart_files=missing,
        recipe=recipe,
        chart_type=chart_type,
        min_confidence=min_confidence,
        allow_fallback_detection=allow_fallback_detection,
        chart_dev_dir=work_dir / "chart_developed_validation_geometry",
        detect_dir=work_dir / "detections_validation_geometry",
        overlay_dir=work_dir / "overlays_validation_geometry",
    )
    detection_map.update(geometry["detections"])
    return detection_map or None


def _collect_chart_geometries(
    *,
    chart_files: list[Path],
    recipe: Recipe,
    chart_type: str,
    min_confidence: float,
    allow_fallback_detection: bool,
    chart_dev_dir: Path,
    detect_dir: Path,
    overlay_dir: Path,
) -> dict[str, Any]:
    for d in (chart_dev_dir, detect_dir, overlay_dir):
        d.mkdir(parents=True, exist_ok=True)

    detections: dict[Path, Any] = {}
    skipped: list[dict[str, Any]] = []

    for idx, chart_file in enumerate(chart_files, start=1):
        prefix = f"{idx:03d}_{chart_file.stem}"
        developed_tiff = chart_dev_dir / f"{prefix}.tiff"
        detection_path = detect_dir / f"{prefix}.json"
        overlay_path = overlay_dir / f"{prefix}.png"
        detection_key = chart_file.expanduser().resolve()

        try:
            develop_controlled(chart_file, recipe, developed_tiff, None)
            detection = detect_chart(developed_tiff, chart_type=chart_type)
            write_json(detection_path, detection)
            draw_detection_overlay(developed_tiff, detection, overlay_path)

            if detection.detection_mode == "fallback" and not allow_fallback_detection:
                skipped.append(
                    {
                        "pass": "validation_geometry_source",
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
                        "pass": "validation_geometry_source",
                        "capture": str(chart_file),
                        "reason": "low_confidence",
                        "confidence": float(detection.confidence_score),
                        "min_confidence": float(min_confidence),
                        "detection_json": str(detection_path),
                    }
                )
                continue

            detections[detection_key] = detection
        except Exception as exc:
            skipped.append(
                {
                    "pass": "validation_geometry_source",
                    "capture": str(chart_file),
                    "reason": "processing_error",
                    "error": str(exc),
                }
            )

    return {"detections": detections, "skipped": skipped}


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


def _normalize_detection_map(detections: dict[Path, Any] | None) -> dict[Path, Any] | None:
    if not detections:
        return None
    return {Path(path).expanduser().resolve(): detection for path, detection in detections.items()}


def _coerce_chart_detection(value: Any) -> ChartDetectionResult:
    if isinstance(value, ChartDetectionResult):
        return value
    if not isinstance(value, dict):
        raise RuntimeError("Deteccion de carta manual no compatible")

    return ChartDetectionResult(
        chart_type=str(value["chart_type"]),
        confidence_score=float(value["confidence_score"]),
        valid_patch_ratio=float(value["valid_patch_ratio"]),
        homography=[float(v) for v in value["homography"]],
        chart_polygon=[_coerce_point(p) for p in value["chart_polygon"]],
        patches=[
            PatchDetection(
                patch_id=str(patch["patch_id"]),
                polygon=[_coerce_point(p) for p in patch["polygon"]],
                sample_region=[_coerce_point(p) for p in patch["sample_region"]],
            )
            for patch in value["patches"]
        ],
        warnings=[str(w) for w in value.get("warnings", [])],
        detection_mode=str(value.get("detection_mode", "manual")),
    )


def _coerce_point(value: Any) -> Point2:
    if isinstance(value, Point2):
        return value
    if isinstance(value, dict):
        return Point2(x=float(value["x"]), y=float(value["y"]))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return Point2(x=float(value[0]), y=float(value[1]))
    raise RuntimeError("Punto de deteccion de carta no compatible")
