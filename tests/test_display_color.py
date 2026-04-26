from pathlib import Path

import numpy as np
from PIL import ImageCms

from iccraw.display_color import (
    display_profile_label,
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
