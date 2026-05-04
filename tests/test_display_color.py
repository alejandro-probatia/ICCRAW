from pathlib import Path

import numpy as np
from PIL import ImageCms

import probraw.display_color as display_color_module
from probraw.display_color import (
    _colord_display_device_candidates,
    _parse_colord_profile_filename,
    _parse_xprop_icc_profile_bytes,
    display_profile_label,
    profiled_float_to_display_u8,
    profiled_u8_to_display_u8,
    rgb_float_to_u8,
    srgb_float_to_u8,
    srgb_to_display_u8,
    srgb_u8_to_display_u8,
)


def test_srgb_float_to_u8_clamps_and_quantizes():
    image = np.asarray([[[-0.1, 0.5, 1.2]]], dtype=np.float32)

    out = srgb_float_to_u8(image)

    assert out.dtype == np.uint8
    assert out.tolist() == [[[0, 128, 255]]]


def test_rgb_float_to_u8_matches_legacy_srgb_quantization():
    image = np.asarray([[[0.0, 0.25, 1.0], [0.5, -0.2, 1.2]]], dtype=np.float32)

    assert np.array_equal(rgb_float_to_u8(image), srgb_float_to_u8(image))


def test_srgb_to_display_u8_without_monitor_profile_is_srgb():
    image = np.asarray([[[0.0, 0.5, 1.0]]], dtype=np.float32)

    out = srgb_to_display_u8(image, None)

    assert out.tolist() == [[[0, 128, 255]]]


def test_srgb_to_display_u8_with_srgb_monitor_profile_is_stable(tmp_path: Path):
    profile = tmp_path / "monitor_srgb.icc"
    srgb_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    profile.write_bytes(srgb_profile.tobytes())
    rgb = np.asarray([[[12, 128, 240], [255, 64, 0]]], dtype=np.uint8)

    out = srgb_u8_to_display_u8(rgb, profile)

    assert out.dtype == np.uint8
    assert out.shape == rgb.shape
    assert np.max(np.abs(out.astype(np.int16) - rgb.astype(np.int16))) <= 1
    assert display_profile_label(profile)


def test_srgb_to_display_u8_uses_dense_lut_when_available(tmp_path: Path, monkeypatch):
    profile = tmp_path / "monitor_srgb.icc"
    profile.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    rgb = np.asarray([[[12, 128, 240], [255, 64, 0]]], dtype=np.uint8)
    expected = np.asarray([[[13, 129, 241], [254, 63, 1]]], dtype=np.uint8)
    sentinel = object()
    calls: dict[str, object] = {}

    def fake_lut(monitor_profile, rgb_u8):
        calls["profile"] = monitor_profile
        calls["rgb"] = rgb_u8.copy()
        return sentinel

    def fake_apply(rgb_u8, lut):
        calls["lut"] = lut
        assert np.array_equal(rgb_u8, rgb)
        return expected

    monkeypatch.setattr(display_color_module, "_srgb_to_display_dense_lut_for_image", fake_lut)
    monkeypatch.setattr(display_color_module, "_apply_dense_u8_lut", fake_apply)

    out = srgb_u8_to_display_u8(rgb, profile)

    assert out is expected
    assert calls["profile"] == profile
    assert calls["lut"] is sentinel


def test_profiled_display_direct_srgb_to_srgb_is_stable(tmp_path: Path):
    source = tmp_path / "source_srgb.icc"
    monitor = tmp_path / "monitor_srgb.icc"
    srgb_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    source.write_bytes(srgb_profile.tobytes())
    monitor.write_bytes(srgb_profile.tobytes())
    image = np.asarray([[[0.0, 0.5, 1.0], [0.25, 0.75, 0.1]]], dtype=np.float32)

    out = profiled_float_to_display_u8(image, source, monitor)

    assert out.dtype == np.uint8
    assert out.shape == image.shape
    assert np.max(np.abs(out.astype(np.int16) - srgb_float_to_u8(image).astype(np.int16))) <= 1


def test_profiled_u8_without_monitor_profile_converts_to_srgb(tmp_path: Path):
    source = tmp_path / "source_srgb.icc"
    srgb_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    source.write_bytes(srgb_profile.tobytes())
    rgb = np.asarray([[[12, 128, 240], [255, 64, 0]]], dtype=np.uint8)

    out = profiled_u8_to_display_u8(rgb, source, None)

    assert out.dtype == np.uint8
    assert out.shape == rgb.shape
    assert np.max(np.abs(out.astype(np.int16) - rgb.astype(np.int16))) <= 1


def test_colord_parser_prefers_primary_enabled_display():
    output = """
Object Path:   /org/freedesktop/ColorManager/devices/display_secondary
Enabled:       Yes
Metadata:      OutputPriority=secondary
Object Path:   /org/freedesktop/ColorManager/devices/display_primary
Enabled:       Yes
Metadata:      OutputPriority=primary
"""

    candidates = _colord_display_device_candidates(output)

    assert candidates[0][1] == "/org/freedesktop/ColorManager/devices/display_primary"


def test_colord_profile_filename_parser_returns_existing_icc(tmp_path: Path):
    profile = tmp_path / "monitor.icc"
    profile.write_bytes(b"0" * 128)
    output = f"""
Object Path:   /org/freedesktop/ColorManager/profiles/display
Filename:      {profile}
"""

    assert _parse_colord_profile_filename(output) == profile


def test_xprop_icc_profile_parser_trims_to_declared_profile_size():
    data = bytearray(b"0" * 132)
    data[:4] = (128).to_bytes(4, "big")
    output = "_ICC_PROFILE(CARDINAL) = " + ", ".join(str(value) for value in data)

    parsed = _parse_xprop_icc_profile_bytes(output)

    assert parsed == bytes(data[:128])
