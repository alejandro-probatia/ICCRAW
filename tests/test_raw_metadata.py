from __future__ import annotations

import pytest

from probraw.raw.metadata import estimate_pixel_pitch_um_from_exif


def test_pixel_pitch_from_sensor_width_and_dimensions():
    result = estimate_pixel_pitch_um_from_exif(
        {"SensorWidth": "35.9 mm", "SensorHeight": "23.9 mm"},
        image_dimensions=(8256, 5504),
    )

    assert result is not None
    pitch, source = result
    assert source == "sensor_width_height"
    assert pitch == pytest.approx(4.34, rel=0.01)


def test_pixel_pitch_from_focal_plane_resolution_inches():
    result = estimate_pixel_pitch_um_from_exif(
        {
            "FocalPlaneXResolution": "5080",
            "FocalPlaneYResolution": "5080",
            "FocalPlaneResolutionUnit": "inches",
        }
    )

    assert result is not None
    pitch, source = result
    assert source == "focal_plane_resolution"
    assert pitch == pytest.approx(5.0, rel=0.01)


def test_pixel_pitch_ignores_unphysical_values():
    result = estimate_pixel_pitch_um_from_exif(
        {"SensorWidth": "4000 mm"},
        image_dimensions=(100, 100),
    )

    assert result is None


def test_pixel_pitch_from_35mm_equivalent_scale_factor():
    result = estimate_pixel_pitch_um_from_exif(
        {
            "ImageWidth": 6080,
            "ImageHeight": 4044,
            "FocalLength": "60.0 mm",
            "FocalLengthIn35mmFormat": "60 mm",
            "ScaleFactor35efl": 1.0,
        },
        image_dimensions=(1200, 800),
    )

    assert result is not None
    pitch, source = result
    assert source == "35mm_equivalent"
    assert pitch == pytest.approx(5.92, rel=0.01)
