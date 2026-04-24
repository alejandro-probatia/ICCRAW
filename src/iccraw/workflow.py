from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .chart.detection import detect_chart, draw_detection_overlay
from .chart.sampling import ReferenceCatalog, sample_chart
from .core.models import PatchSample, Recipe, SampleSet, to_json_dict, write_json
from .core.utils import RAW_EXTENSIONS
from .profile.builder import build_profile
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
    chart_type: str = "colorchecker24",
    min_confidence: float = 0.35,
    camera_model: str | None = None,
    lens_model: str | None = None,
) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    chart_dev_dir = work_dir / "chart_developed"
    detect_dir = work_dir / "detections"
    sample_dir = work_dir / "samples"
    overlay_dir = work_dir / "overlays"

    for d in (chart_dev_dir, detect_dir, sample_dir, overlay_dir):
        d.mkdir(parents=True, exist_ok=True)

    chart_files = _list_chart_capture_files(chart_captures_dir)
    if not chart_files:
        raise RuntimeError(f"No se encontraron capturas de carta en: {chart_captures_dir}")

    accepted_samples: list[SampleSet] = []
    skipped: list[dict[str, Any]] = []

    for idx, chart_file in enumerate(chart_files, start=1):
        prefix = f"{idx:03d}_{chart_file.stem}"
        developed_tiff = chart_dev_dir / f"{prefix}.tiff"
        detection_path = detect_dir / f"{prefix}.json"
        overlay_path = overlay_dir / f"{prefix}.png"
        sample_path = sample_dir / f"{prefix}.json"

        try:
            develop_controlled(chart_file, recipe, developed_tiff, None)
            detection = detect_chart(developed_tiff, chart_type=chart_type)
            write_json(detection_path, detection)
            draw_detection_overlay(developed_tiff, detection, overlay_path)

            if detection.confidence_score < float(min_confidence):
                skipped.append(
                    {
                        "capture": str(chart_file),
                        "reason": "low_confidence",
                        "confidence": float(detection.confidence_score),
                        "min_confidence": float(min_confidence),
                        "detection_json": str(detection_path),
                    }
                )
                continue

            samples = sample_chart(developed_tiff, detection, reference, strategy=recipe.sampling_strategy)
            write_json(sample_path, samples)
            accepted_samples.append(samples)

        except Exception as exc:
            skipped.append(
                {
                    "capture": str(chart_file),
                    "reason": "processing_error",
                    "error": str(exc),
                }
            )

    if not accepted_samples:
        raise RuntimeError(
            "No hubo capturas de carta válidas para construir perfil. "
            "Revisa exposición, encuadre de carta y min_confidence."
        )

    aggregated_samples = _aggregate_samples(accepted_samples, strategy=recipe.sampling_strategy)
    aggregated_samples_path = work_dir / "samples_aggregated.json"
    write_json(aggregated_samples_path, aggregated_samples)

    profile_result = build_profile(
        samples=aggregated_samples,
        recipe=recipe,
        out_icc=profile_out,
        camera_model=camera_model,
        lens_model=lens_model,
    )
    write_json(profile_report_out, profile_result)

    return {
        "chart_captures_total": len(chart_files),
        "chart_captures_used": len(accepted_samples),
        "chart_captures_skipped": skipped,
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
    chart_type: str = "colorchecker24",
    min_confidence: float = 0.35,
    camera_model: str | None = None,
    lens_model: str | None = None,
) -> dict[str, Any]:
    profile_payload = auto_generate_profile_from_charts(
        chart_captures_dir=chart_captures_dir,
        recipe=recipe,
        reference=reference,
        profile_out=profile_out,
        profile_report_out=profile_report_out,
        work_dir=work_dir,
        chart_type=chart_type,
        min_confidence=min_confidence,
        camera_model=camera_model,
        lens_model=lens_model,
    )

    manifest = batch_develop(
        raws_dir=target_captures_dir,
        recipe=recipe,
        profile_path=profile_out,
        out_dir=batch_out_dir,
    )
    manifest_path = batch_out_dir / "batch_manifest.json"
    write_json(manifest_path, manifest)

    return {
        "chart_captures_total": profile_payload["chart_captures_total"],
        "chart_captures_used": profile_payload["chart_captures_used"],
        "chart_captures_skipped": profile_payload["chart_captures_skipped"],
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
        strategy=f"aggregate_median({strategy})",
        samples=aggregated_samples,
        missing_reference_patches=missing,
    )


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
