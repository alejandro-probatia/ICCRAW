from __future__ import annotations

import cv2
import numpy as np
import pytest

import probraw.analysis.mtf as mtf_module
from probraw.analysis.mtf import analyze_slanted_edge_mtf


def _slanted_edge_image(*, blur_sigma: float = 1.0, size: int = 180, angle_degrees: float = 5.0) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    angle = np.deg2rad(float(angle_degrees))
    normal = np.asarray([np.cos(angle), np.sin(angle)], dtype=np.float32)
    dist = (xx - size / 2.0) * normal[0] + (yy - size / 2.0) * normal[1]
    edge = (dist > 0.0).astype(np.float32)
    if blur_sigma > 0.0:
        edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=blur_sigma, sigmaY=blur_sigma)
    return np.repeat(edge[..., None], 3, axis=2)


def test_slanted_edge_mtf_reports_curve_and_metrics():
    image = _slanted_edge_image(blur_sigma=1.2)

    result = analyze_slanted_edge_mtf(image, roi=(25, 25, 130, 130))

    assert result.roi == (25, 25, 130, 130)
    assert len(result.esf) > 40
    assert len(result.lsf) == len(result.lsf_distance)
    assert len(result.frequency) == len(result.mtf)
    assert result.frequency[0] == pytest.approx(0.0)
    assert result.frequency[-1] <= 0.5
    assert len(result.frequency_extended) == len(result.mtf_extended)
    assert result.frequency_extended[0] == pytest.approx(0.0)
    assert result.frequency_extended[-1] > 0.5
    assert result.mtf[0] == pytest.approx(1.0)
    assert result.mtf50 is not None
    assert result.mtf50p is not None
    assert 0.05 < result.mtf50 < 0.5
    assert 0.05 < result.mtf50p < 0.5
    assert result.edge_contrast > 0.6
    assert abs(result.esf[-1] - result.esf[-5]) < 0.05


def test_slanted_edge_mtf_converts_luminance_after_roi_crop(monkeypatch):
    image = _slanted_edge_image(blur_sigma=1.2, size=220)
    seen_shapes: list[tuple[int, int]] = []
    original_luminance = mtf_module._luminance_image

    def wrapped_luminance(image_rgb):
        seen_shapes.append(tuple(image_rgb.shape[:2]))
        return original_luminance(image_rgb)

    monkeypatch.setattr(mtf_module, "_luminance_image", wrapped_luminance)

    result = analyze_slanted_edge_mtf(image, roi=(40, 45, 120, 110))

    assert result.roi == (40, 45, 120, 110)
    assert seen_shapes == [(110, 120)]


def test_slanted_edge_mtf_detects_blur_difference():
    sharp = analyze_slanted_edge_mtf(_slanted_edge_image(blur_sigma=0.6), roi=(25, 25, 130, 130))
    soft = analyze_slanted_edge_mtf(_slanted_edge_image(blur_sigma=2.4), roi=(25, 25, 130, 130))

    assert sharp.mtf50 is not None
    assert soft.mtf50 is not None
    assert sharp.mtf50 > soft.mtf50
    assert sharp.acutance > soft.acutance


def test_slanted_edge_mtf_uses_gradient_ridge_when_dark_side_is_textured():
    size = 220
    rng = np.random.default_rng(3)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    dist = (xx - size * 0.55) - (yy - size / 2.0) * 0.10
    edge = (dist > 0.0).astype(np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    texture = cv2.GaussianBlur(rng.normal(0.0, 0.08, (size, size)).astype(np.float32), (0, 0), sigmaX=1.0)
    dark_ramp = 0.04 * xx / float(size)
    image = np.clip(0.08 + 0.72 * edge + (1.0 - edge) * (texture + dark_ramp), 0.0, 1.0)
    image_rgb = np.repeat(image[..., None], 3, axis=2)

    result = analyze_slanted_edge_mtf(image_rgb, roi=(20, 20, 180, 180))

    assert result.mtf50 is not None
    assert result.mtf50 > 0.10
    assert 83.0 < result.edge_angle_degrees < 86.0


def test_slanted_edge_mtf_rejects_low_contrast_roi():
    image = np.full((80, 80, 3), 0.5, dtype=np.float32)

    with pytest.raises(ValueError, match="contraste"):
        analyze_slanted_edge_mtf(image, roi=(10, 10, 50, 50))
