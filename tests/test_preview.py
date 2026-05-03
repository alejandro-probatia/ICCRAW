from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile
import colour

from probraw.core.models import Recipe
from probraw.profile.export import apply_profile_matrix
import probraw.raw.preview as preview_module
from probraw.raw.preview import (
    _camera_rgb_display_balance_if_needed,
    apply_adjustments,
    apply_lateral_chromatic_aberration,
    apply_profile_preview,
    apply_render_adjustments,
    apply_tone_curve,
    estimate_temperature_tint_from_neutral_sample,
    extract_embedded_thumbnail,
    linear_to_srgb_display,
    load_image_for_preview,
    normalize_tone_curve_points,
    preview_analysis_text,
    standard_profile_to_srgb_display,
    srgb_to_linear_display,
    tone_curve_lut,
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


def test_apply_render_adjustments_identity_when_disabled():
    img = np.random.default_rng(9).uniform(0.0, 1.0, size=(18, 20, 3)).astype(np.float32)

    out = apply_render_adjustments(img)

    assert out.shape == img.shape
    assert np.allclose(out, img, atol=1e-7)


def test_estimate_temperature_tint_from_neutral_sample_reduces_cast():
    sample = np.array([0.18, 0.24, 0.34], dtype=np.float32)

    temperature, tint = estimate_temperature_tint_from_neutral_sample(sample)
    corrected = apply_render_adjustments(
        sample.reshape((1, 1, 3)),
        temperature_kelvin=temperature,
        tint=tint,
    )[0, 0]

    before = float(np.std(np.log(sample / np.mean(sample))))
    after = float(np.std(np.log(corrected / np.mean(corrected))))
    assert 2000 <= temperature <= 12000
    assert -100.0 <= tint <= 100.0
    assert after < before * 0.5


def test_normalize_tone_curve_points_clamps_sorts_and_keeps_endpoints():
    points = normalize_tone_curve_points([(0.7, 0.8), (-0.5, 0.2), (1.2, 2.0), (0.2, 0.1)])

    assert points[0] == (0.0, 0.0)
    assert points[-1] == (1.0, 1.0)
    assert [x for x, _y in points] == sorted(x for x, _y in points)
    assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in points)


def test_normalize_tone_curve_points_prevents_descending_segments():
    points = normalize_tone_curve_points([(0.25, 0.75), (0.75, 0.25)])

    assert np.all(np.diff([y for _x, y in points]) >= 0.0)


def test_apply_tone_curve_identity_for_linear_points():
    img = np.linspace(0.0, 1.0, 3 * 8 * 9, dtype=np.float32).reshape((8, 9, 3))
    out = apply_tone_curve(img, [(0.0, 0.0), (1.0, 1.0)])

    assert out.shape == img.shape
    assert np.allclose(out, img, atol=1e-7)


def test_apply_render_adjustments_uses_advanced_tone_curve():
    img = np.full((6, 7, 3), 0.25, dtype=np.float32)
    out = apply_render_adjustments(
        img,
        tone_curve_points=[(0.0, 0.0), (0.25, 0.45), (1.0, 1.0)],
    )

    assert out.shape == img.shape
    assert float(np.mean(out)) > float(np.mean(img))


def test_apply_render_adjustments_uses_per_channel_tone_curves():
    img = np.full((5, 6, 3), 0.25, dtype=np.float32)
    out = apply_render_adjustments(
        img,
        tone_curve_channel_points={
            "red": [(0.0, 0.0), (0.25, 0.6), (1.0, 1.0)],
            "green": [(0.0, 0.0), (1.0, 1.0)],
            "blue": [(0.0, 0.0), (0.25, 0.1), (1.0, 1.0)],
        },
    )

    assert out.shape == img.shape
    assert float(out[..., 0].mean()) > float(img[..., 0].mean())
    assert np.allclose(out[..., 1], img[..., 1], atol=1e-6)
    assert float(out[..., 2].mean()) < float(img[..., 2].mean())


def test_apply_render_adjustments_uses_extended_tone_and_color_controls():
    img = np.zeros((8, 9, 3), dtype=np.float32)
    img[:, :3] = [0.12, 0.10, 0.08]
    img[:, 3:6] = [0.40, 0.36, 0.30]
    img[:, 6:] = [0.78, 0.74, 0.68]

    out = apply_render_adjustments(
        img,
        highlights=-0.35,
        shadows=0.45,
        whites=0.20,
        blacks=-0.15,
        vibrance=0.40,
        saturation=0.15,
    )

    assert out.shape == img.shape
    assert np.isfinite(out).all()
    assert not np.allclose(out, img)
    assert float(out[:, :3].mean()) > float(img[:, :3].mean())


def test_apply_render_adjustments_uses_color_grading():
    img = np.full((6, 7, 3), 0.35, dtype=np.float32)

    out = apply_render_adjustments(
        img,
        grade_midtones_hue=210,
        grade_midtones_saturation=0.45,
        grade_blending=0.5,
    )

    assert out.shape == img.shape
    assert not np.allclose(out[..., 0], out[..., 2])


def test_tone_curve_lut_is_smooth_monotonic_and_honors_black_white_points():
    lut_x, lut_y = tone_curve_lut(
        [(0.0, 0.0), (0.25, 0.12), (0.55, 0.72), (1.0, 1.0)],
        lut_size=256,
        black_point=0.2,
        white_point=0.82,
    )

    assert lut_x.shape == lut_y.shape
    assert float(np.max(lut_y[lut_x <= 0.2])) == 0.0
    assert float(np.min(lut_y[lut_x >= 0.82])) == 1.0
    assert np.all(np.diff(lut_y) >= -1e-6)


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


def test_standard_profile_to_srgb_display_keeps_srgb_encoded_values():
    encoded = np.asarray([[[0.5, 0.25, 0.75], [0.05, 0.8, 1.0]]], dtype=np.float32)

    out = standard_profile_to_srgb_display(encoded, "srgb")

    assert out.shape == encoded.shape
    assert np.allclose(out, encoded, atol=1e-7)


def test_standard_profile_to_srgb_display_converts_prophoto_neutral_without_cast():
    encoded = np.full((2, 3, 3), 0.5, dtype=np.float32)

    out = standard_profile_to_srgb_display(encoded, "prophoto_rgb")

    assert out.shape == encoded.shape
    assert np.isfinite(out).all()
    assert float(np.max(np.abs(out[..., 0] - out[..., 1]))) < 0.01
    assert float(np.max(np.abs(out[..., 1] - out[..., 2]))) < 0.01


def test_standard_profile_to_srgb_display_matches_colour_reference_for_prophoto():
    encoded = np.random.default_rng(14).uniform(0.0, 1.0, size=(8, 9, 3)).astype(np.float32)
    rgb_space = colour.RGB_COLOURSPACES["ProPhoto RGB"]
    linear = np.asarray(rgb_space.cctf_decoding(encoded), dtype=np.float64)
    flat = linear.reshape((-1, 3))
    xyz_native = flat @ np.asarray(rgb_space.matrix_RGB_to_XYZ, dtype=np.float64).T
    source_white = np.asarray(colour.xy_to_XYZ(rgb_space.whitepoint), dtype=np.float64)
    d65_xy = np.asarray(colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D65"], dtype=np.float64)
    d65_xyz = np.asarray(colour.xy_to_XYZ(d65_xy), dtype=np.float64)
    adaptation = preview_module.matrix_chromatic_adaptation_VonKries(source_white, d65_xyz, transform="Bradford")
    xyz_d65 = xyz_native @ np.asarray(adaptation, dtype=np.float64).T
    reference = colour.XYZ_to_sRGB(
        xyz_d65.reshape(encoded.shape),
        illuminant=d65_xy,
        apply_cctf_encoding=True,
    )
    reference = np.clip(np.asarray(reference, dtype=np.float32), 0.0, 1.0)

    out = standard_profile_to_srgb_display(encoded, "prophoto_rgb")

    assert np.allclose(out, reference, atol=2e-6)


def test_preview_analysis_text_includes_global_stats():
    original = np.full((8, 8, 3), 0.4, dtype=np.float32)
    adjusted = np.full((8, 8, 3), 0.5, dtype=np.float32)
    text = preview_analysis_text(original, adjusted)
    assert "Diagnóstico de imagen" in text
    assert "Resultado ajustado" in text
    assert "Clipping global" in text
    assert "Balance RGB medio" in text
    assert "Impacto de la receta" in text
    assert "Diferencia media absoluta global" in text
    assert "Diferencia máxima absoluta global" in text


def test_preview_analysis_text_samples_large_images_without_changing_format():
    original = np.linspace(0.0, 1.0, 3 * 120 * 160, dtype=np.float32).reshape((120, 160, 3))
    adjusted = np.clip(original + 0.02, 0.0, 1.0)

    text = preview_analysis_text(original, adjusted, max_pixels=2048)

    assert "Canales originales:" in text
    assert "Canales ajustados:" in text
    assert "Diferencia media absoluta global" in text


def test_apply_profile_preview_uses_cached_argyll_lut(tmp_path: Path, monkeypatch):
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"icc-placeholder")
    lut = np.zeros((3, 3, 3, 3), dtype=np.float32)
    axis = np.linspace(0.0, 1.0, 3, dtype=np.float32)
    rr, gg, bb = np.meshgrid(axis, axis, axis, indexing="ij")
    lut[..., 0] = rr
    lut[..., 1] = gg
    lut[..., 2] = bb
    monkeypatch.setattr(preview_module, "_profile_preview_lut", lambda _profile, *, grid_size: lut)

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


def test_extract_embedded_thumbnail_applies_raw_orientation(tmp_path: Path, monkeypatch):
    raw_path = tmp_path / "rotated.nef"
    raw_path.write_bytes(b"raw")
    source = np.zeros((2, 4, 3), dtype=np.uint8)
    source[:, :2] = [255, 0, 0]
    source[:, 2:] = [0, 255, 0]

    from PIL import Image
    import io

    encoded = io.BytesIO()
    Image.fromarray(source, mode="RGB").save(encoded, format="JPEG")

    class FakeSizes:
        flip = 6

    class FakeThumb:
        format = preview_module.rawpy.ThumbFormat.JPEG
        data = encoded.getvalue()

    class FakeRaw:
        sizes = FakeSizes()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def extract_thumb(self):
            return FakeThumb()

    monkeypatch.setattr(preview_module, "open_rawpy", lambda _path: FakeRaw())

    thumb = extract_embedded_thumbnail(raw_path, max_side=100)

    assert thumb is not None
    assert thumb.shape[:2] == (4, 2)


def test_load_image_for_preview_hq_uses_half_size_when_preview_is_smaller(tmp_path: Path, monkeypatch):
    raw_path = tmp_path / "sample.nef"
    raw_path.write_bytes(b"raw")
    recipe = Recipe()
    called: dict[str, bool] = {}

    monkeypatch.setattr(preview_module, "_raw_preview_source_max_side", lambda _path: 6200)
    monkeypatch.delenv("PROBRAW_PREVIEW_HQ_HALF_SIZE", raising=False)

    def fake_develop(_path, _recipe, *, half_size=False):
        called["half_size"] = bool(half_size)
        shape = (3000, 2000, 3) if half_size else (6000, 4000, 3)
        return np.full(shape, 0.25, dtype=np.float32)

    monkeypatch.setattr(preview_module, "develop_image_array", fake_develop)

    loaded, msg = load_image_for_preview(raw_path, recipe=recipe, fast_raw=False, max_preview_side=2400)

    assert called["half_size"] is True
    assert "HQ optimizado" in msg
    assert max(loaded.shape[0], loaded.shape[1]) <= 2400


def test_load_image_for_preview_hq_uses_standard_space_renderer(tmp_path: Path, monkeypatch):
    raw_path = tmp_path / "sample.nef"
    raw_path.write_bytes(b"raw")
    recipe = Recipe(output_space="prophoto_rgb", output_linear=False, tone_curve="gamma:1.8")
    called: dict[str, bool] = {}

    monkeypatch.setattr(preview_module, "_raw_preview_source_max_side", lambda _path: 6200)

    def fake_standard_develop(_path, _recipe, *, half_size=False):
        called["standard"] = True
        called["half_size"] = bool(half_size)
        return np.full((3000, 2000, 3), 0.25, dtype=np.float32)

    monkeypatch.setattr(preview_module, "develop_standard_output_array", fake_standard_develop)

    loaded, msg = load_image_for_preview(raw_path, recipe=recipe, fast_raw=False, max_preview_side=2400)

    assert called == {"standard": True, "half_size": True}
    assert "HQ optimizado" in msg
    assert max(loaded.shape[0], loaded.shape[1]) <= 2400


def test_load_image_for_preview_hq_can_disable_half_size_by_env(tmp_path: Path, monkeypatch):
    raw_path = tmp_path / "sample.nef"
    raw_path.write_bytes(b"raw")
    recipe = Recipe()
    called: dict[str, bool] = {}

    monkeypatch.setattr(preview_module, "_raw_preview_source_max_side", lambda _path: 6200)
    monkeypatch.setenv("PROBRAW_PREVIEW_HQ_HALF_SIZE", "0")

    def fake_develop(_path, _recipe, *, half_size=False):
        called["half_size"] = bool(half_size)
        return np.full((3000, 2000, 3), 0.25, dtype=np.float32)

    monkeypatch.setattr(preview_module, "develop_image_array", fake_develop)

    _loaded, _msg = load_image_for_preview(raw_path, recipe=recipe, fast_raw=False, max_preview_side=2400)

    assert called["half_size"] is False


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
