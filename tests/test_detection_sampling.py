from pathlib import Path

import numpy as np
import tifffile

from iccraw.chart.detection import detect_chart
from iccraw.chart.sampling import ReferenceCatalog, sample_chart
from iccraw.core.models import ChartDetectionResult, PatchDetection, Point2


def test_detect_chart_marks_fallback_as_low_confidence(tmp_path: Path):
    path = tmp_path / "blank.tiff"
    image = np.full((120, 180, 3), 20000, dtype=np.uint16)
    tifffile.imwrite(str(path), image, photometric="rgb", metadata=None)

    detection = detect_chart(path, chart_type="colorchecker24")

    assert detection.detection_mode == "fallback"
    assert detection.confidence_score <= 0.05
    assert detection.valid_patch_ratio == 0.0
    assert any("fallback" in warning for warning in detection.warnings)


def test_sample_chart_honors_trim_percent_and_saturation_rejection(tmp_path: Path):
    path = tmp_path / "patch.tiff"
    image = np.zeros((10, 10, 3), dtype=np.uint16)
    image[:] = [10000, 10000, 10000]
    image[0, 1] = [50000, 50000, 50000]
    image[0, 0] = [65535, 65535, 65535]
    tifffile.imwrite(str(path), image, photometric="rgb", metadata=None)

    detection = ChartDetectionResult(
        chart_type="unit",
        confidence_score=1.0,
        valid_patch_ratio=1.0,
        homography=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        chart_polygon=[],
        patches=[
            PatchDetection(
                patch_id="P01",
                polygon=[],
                sample_region=[
                    Point2(0, 0),
                    Point2(9, 0),
                    Point2(9, 9),
                    Point2(0, 9),
                ],
            )
        ],
        warnings=[],
    )
    reference = ReferenceCatalog(
        {
            "chart_name": "unit",
            "chart_version": "1",
            "illuminant": "D50",
            "patches": [{"patch_id": "P01", "reference_lab": [50, 0, 0]}],
        }
    )

    untrimmed = sample_chart(
        path,
        detection,
        reference,
        strategy="trimmed_mean",
        trim_percent=0.0,
        reject_saturated=True,
    )
    trimmed = sample_chart(
        path,
        detection,
        reference,
        strategy="trimmed_mean",
        trim_percent=0.25,
        reject_saturated=True,
    )
    saturated_kept = sample_chart(
        path,
        detection,
        reference,
        strategy="trimmed_mean",
        trim_percent=0.0,
        reject_saturated=False,
    )

    assert trimmed.samples[0].measured_rgb[0] < untrimmed.samples[0].measured_rgb[0]
    assert saturated_kept.samples[0].measured_rgb[0] > untrimmed.samples[0].measured_rgb[0]
    assert "trim_percent=0.25" in trimmed.strategy
    assert "reject_saturated=true" in trimmed.strategy
