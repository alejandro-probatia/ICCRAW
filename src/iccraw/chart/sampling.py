from __future__ import annotations

from pathlib import Path
import numpy as np
import cv2

from ..core.models import ChartDetectionResult, PatchDetection, PatchSample, Point2, SampleSet, read_json
from ..core.utils import read_image, robust_trimmed_mean


class ReferenceCatalog:
    def __init__(self, payload: dict):
        self.chart_name: str = payload.get("chart_name", "unknown")
        self.chart_version: str = payload.get("chart_version", "unknown")
        self.illuminant: str = payload.get("illuminant", "unknown")
        self.observer: str = payload.get("observer", "2")
        patches = payload.get("patches", [])
        self.patch_map = {p["patch_id"]: p for p in patches if "patch_id" in p}

    @classmethod
    def from_path(cls, path: Path) -> "ReferenceCatalog":
        return cls(read_json(path))


def sample_chart(
    image_path: Path,
    detection: ChartDetectionResult,
    reference: ReferenceCatalog,
    strategy: str = "trimmed_mean",
) -> SampleSet:
    image = read_image(image_path)
    h, w = image.shape[:2]

    samples: list[PatchSample] = []
    missing: list[str] = []

    for patch in detection.patches:
        ref = reference.patch_map.get(patch.patch_id)
        if ref is None:
            missing.append(patch.patch_id)
            continue

        poly = np.array([[p.x, p.y] for p in patch.sample_region], dtype=np.float32)
        rgb, excluded_ratio, sat_ratio = _sample_patch(image, poly, strategy)

        samples.append(
            PatchSample(
                patch_id=patch.patch_id,
                measured_rgb=[float(v) for v in rgb],
                reference_rgb=[float(v) for v in ref.get("reference_rgb", [])] if ref.get("reference_rgb") is not None else None,
                reference_lab=[float(v) for v in ref.get("reference_lab", [])] if ref.get("reference_lab") is not None else None,
                excluded_pixel_ratio=float(excluded_ratio),
                saturated_pixel_ratio=float(sat_ratio),
            )
        )

    if not samples:
        raise RuntimeError("no se pudo muestrear ningun parche")

    return SampleSet(
        chart_name=reference.chart_name,
        chart_version=reference.chart_version,
        illuminant=reference.illuminant,
        strategy=strategy,
        samples=samples,
        missing_reference_patches=missing,
    )


def _sample_patch(image: np.ndarray, polygon: np.ndarray, strategy: str) -> tuple[np.ndarray, float, float]:
    h, w = image.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    poly_int = np.round(polygon).astype(np.int32)
    cv2.fillPoly(mask, [poly_int], 255)

    pixels = image[mask == 255]
    if pixels.size == 0:
        return np.array([0.0, 0.0, 0.0], dtype=np.float32), 1.0, 0.0

    saturated = np.any(pixels >= 0.999, axis=1)
    sat_ratio = float(np.mean(saturated))

    valid = pixels[~saturated]
    if valid.size == 0:
        valid = pixels

    if strategy == "median":
        measured = np.median(valid, axis=0)
        excluded_ratio = 0.0
    else:
        measured = np.array(
            [robust_trimmed_mean(valid[:, c], 0.1) for c in range(3)],
            dtype=np.float32,
        )
        excluded_ratio = 0.1

    return measured, excluded_ratio, sat_ratio


def chart_detection_from_json(path: Path) -> ChartDetectionResult:
    payload = read_json(path)

    chart_polygon = [Point2(**p) for p in payload["chart_polygon"]]
    patches = []
    for p in payload["patches"]:
        patches.append(
            PatchDetection(
                patch_id=p["patch_id"],
                polygon=[Point2(**q) for q in p["polygon"]],
                sample_region=[Point2(**q) for q in p["sample_region"]],
            )
        )

    return ChartDetectionResult(
        chart_type=payload["chart_type"],
        confidence_score=float(payload["confidence_score"]),
        valid_patch_ratio=float(payload["valid_patch_ratio"]),
        homography=[float(v) for v in payload["homography"]],
        chart_polygon=chart_polygon,
        patches=patches,
        warnings=[str(v) for v in payload.get("warnings", [])],
    )


def sampleset_from_json(path: Path) -> SampleSet:
    payload = read_json(path)
    samples = [PatchSample(**s) for s in payload["samples"]]
    return SampleSet(
        chart_name=payload["chart_name"],
        chart_version=payload["chart_version"],
        illuminant=payload["illuminant"],
        strategy=payload.get("strategy", "trimmed_mean"),
        samples=samples,
        missing_reference_patches=payload.get("missing_reference_patches", []),
    )
