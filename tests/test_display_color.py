from pathlib import Path

import numpy as np
from PIL import ImageCms

from probraw.display_color import (
    _colord_display_device_candidates,
    _parse_colord_profile_filename,
    _parse_xprop_icc_profile_bytes,
    display_profile_label,
    profiled_float_to_display_u8,
    profiled_u8_to_display_u8,
    srgb_float_to_u8,
    srgb_to_display_u8,
    srgb_u8_to_display_u8,
)


def test_srgb_float_to_u8_clamps_and_quantizes():
    image = np.asarray([[[-0.1, 0.5, 1.2]]], dtype=np.float32)

    out = srgb_float_to_u8(image)

    assert out.dtype == np.uint8
    assert out.tolist() == [[[0, 128, 255]]]


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
