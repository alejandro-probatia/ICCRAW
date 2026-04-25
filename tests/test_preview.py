from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile
import colour

from iccraw.core.models import Recipe, write_json
from iccraw.profile.export import apply_profile_matrix
from iccraw.raw.preview import (
    _camera_rgb_display_balance_if_needed,
    apply_adjustments,
    apply_lateral_chromatic_aberration,
    apply_profile_preview,
    apply_render_adjustments,
    linear_to_srgb_display,
    load_image_for_preview,
    preview_analysis_text,
    srgb_to_linear_display,
)


def test_apply_adjustments_identity_when_disabled():
    img = np.full((10, 12, 3), 0.25, dtype=np.float32)
    out = apply_adjustments(
        img,
        denoise_luminance=0.0,
        denoise_color=0.0,
        sharpen_amount=0.0,
        sharpen_radius=1.0,
    )
    assert out.shape == img.shape
    assert np.allclose(out, img, atol=1e-7)


def test_apply_adjustments_changes_image_with_luma_and_chroma():
    rng = np.random.default_rng(42)
    img = rng.uniform(0.0, 1.0, size=(20, 24, 3)).astype(np.float32)
    out = apply_adjustments(
        img,
        denoise_luminance=0.4,
        denoise_color=0.6,
        sharpen_amount=0.0,
        sharpen_radius=1.0,
    )
    assert out.shape == img.shape
    assert not np.allclose(out, img)


def test_apply_render_adjustments_changes_tone_and_white_balance():
    img = np.full((10, 12, 3), 0.25, dtype=np.float32)
    out = apply_render_adjustments(
        img,
        temperature_kelvin=6504,
        tint=25,
        brightness_ev=0.5,
        black_point=0.02,
        white_point=0.95,
        contrast=0.2,
        midtone=1.1,
    )
    assert out.shape == img.shape
    assert np.isfinite(out).all()
    assert not np.allclose(out, img)


def test_lateral_chromatic_aberration_identity_at_neutral_scales():
    img = np.random.default_rng(7).uniform(0.0, 1.0, size=(16, 18, 3)).astype(np.float32)
    out = apply_lateral_chromatic_aberration(img, red_scale=1.0, blue_scale=1.0)
    assert out.shape == img.shape
    assert np.allclose(out, img)


def test_linear_to_srgb_display_range():
    img = np.linspace(0.0, 1.0, 3 * 5 * 7, dtype=np.float32).reshape((5, 7, 3))
    out = linear_to_srgb_display(img)
    assert out.shape == img.shape
    assert float(np.min(out)) >= 0.0
    assert float(np.max(out)) <= 1.0


def test_srgb_linear_roundtrip_stability():
    linear = np.linspace(0.0, 1.0, 3 * 4 * 5, dtype=np.float32).reshape((4, 5, 3))
    srgb = linear_to_srgb_display(linear)
    restored = srgb_to_linear_display(srgb)
    assert restored.shape == linear.shape
    assert np.allclose(restored, linear, atol=2e-3)


def test_preview_analysis_text_includes_global_stats():
    original = np.full((8, 8, 3), 0.4, dtype=np.float32)
    adjusted = np.full((8, 8, 3), 0.5, dtype=np.float32)
    text = preview_analysis_text(original, adjusted)
    assert "Resumen de análisis" in text
    assert "Diferencia media absoluta global" in text
    assert "Diferencia máxima absoluta global" in text


def test_apply_profile_preview_uses_profile_sidecar(tmp_path: Path):
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"icc-placeholder")
    sidecar = profile.with_suffix(".profile.json")
    write_json(
        sidecar,
        {
            "matrix_camera_to_xyz": [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            "trc_gamma": 1.0,
        },
    )

    image = np.full((6, 9, 3), 0.2, dtype=np.float32)
    out = apply_profile_preview(image, profile)
    assert out.shape == image.shape
    assert np.isfinite(out).all()
    assert float(np.min(out)) >= 0.0
    assert float(np.max(out)) <= 1.0


def test_apply_profile_matrix_adapts_d50_neutral_to_srgb_neutral():
    d50_xy = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D50"]
    neutral_xyz = colour.Lab_to_XYZ(np.asarray([50.0, 0.0, 0.0]), illuminant=d50_xy)
    matrix = np.tile(neutral_xyz / 3.0, (3, 1))
    image = np.ones((1, 1, 3), dtype=np.float32)

    out = apply_profile_matrix(image, matrix, output_space="srgb", output_linear=False)[0, 0]

    assert float(np.max(out) - np.min(out)) < 0.02


def test_load_image_for_preview_downscales_non_raw(tmp_path: Path):
    image = np.zeros((3200, 4800, 3), dtype=np.uint16)
    image[..., 0] = 10000
    image[..., 1] = 20000
    image[..., 2] = 30000
    path = tmp_path / "big_input.tiff"
    tifffile.imwrite(str(path), image, photometric="rgb", metadata=None)

    loaded, msg = load_image_for_preview(path, max_preview_side=1000)
    assert "Imagen cargada" in msg
    assert loaded.ndim == 3
    assert loaded.shape[2] == 3
    assert max(loaded.shape[0], loaded.shape[1]) <= 1000


def test_camera_rgb_preview_balance_is_display_only_for_strong_cast():
    image = np.zeros((12, 16, 3), dtype=np.float32)
    image[..., 0] = 0.15
    image[..., 1] = 0.30
    image[..., 2] = 0.22
    recipe = Recipe(profiling_mode=True, output_space="scene_linear_camera_rgb")

    balanced = _camera_rgb_display_balance_if_needed(image, recipe)

    means = np.mean(balanced, axis=(0, 1))
    assert float(np.max(means) / np.min(means)) < 1.05
    assert not np.shares_memory(balanced, image)
