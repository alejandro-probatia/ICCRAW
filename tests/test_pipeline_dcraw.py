from pathlib import Path

import pytest
import numpy as np
import tifffile

from iccraw.core.models import Recipe
from iccraw.core.utils import read_image
from iccraw.raw.pipeline import _build_dcraw_command, _develop_image, _parse_int_mode_value, develop_controlled


def test_build_dcraw_command_with_fixed_wb_and_black_level():
    recipe = Recipe(
        raw_developer="dcraw",
        demosaic_algorithm="vng",
        white_balance_mode="fixed",
        wb_multipliers=[2.0, 1.0, 1.5],
        black_level_mode="fixed:64",
    )
    cmd = _build_dcraw_command(Path("/tmp/capture.nef"), recipe)

    assert cmd[:3] == ["dcraw", "-T", "-4"]
    assert cmd[cmd.index("-q") + 1] == "1"
    assert cmd[cmd.index("-r") + 1 : cmd.index("-r") + 5] == ["2", "1", "1.5", "1"]
    assert cmd[cmd.index("-k") + 1] == "64"
    assert cmd[-2:] == ["-c", "/tmp/capture.nef"]


def test_build_dcraw_command_with_camera_wb_and_white_level():
    recipe = Recipe(
        raw_developer="dcraw",
        demosaic_algorithm="ahd",
        white_balance_mode="camera_metadata",
        black_level_mode="white:15000",
    )
    cmd = _build_dcraw_command(Path("/tmp/capture.cr3"), recipe)

    assert "-w" in cmd
    assert "-r" not in cmd
    assert cmd[cmd.index("-S") + 1] == "15000"
    assert cmd[-2:] == ["-c", "/tmp/capture.cr3"]


def test_parse_int_mode_value_rejects_invalid():
    with pytest.raises(RuntimeError):
        _parse_int_mode_value("fixed:abc", "fixed")


def test_build_dcraw_command_rejects_unsupported_demosaic():
    recipe = Recipe(demosaic_algorithm="rcd")
    with pytest.raises(RuntimeError, match="demosaic_algorithm no soportado"):
        _build_dcraw_command(Path("/tmp/capture.nef"), recipe)


def test_develop_image_rejects_unknown_raw_developer():
    recipe = Recipe(raw_developer="rawpy")
    with pytest.raises(RuntimeError, match="raw_developer no soportado"):
        _develop_image(Path("/tmp/capture.nef"), recipe)


def test_develop_controlled_writes_audit_before_output_adjustments(tmp_path: Path):
    source = tmp_path / "input.tiff"
    out = tmp_path / "out.tiff"
    audit = tmp_path / "audit_linear.tiff"

    image = np.zeros((8, 10, 3), dtype=np.uint16)
    image[..., 0] = 9000
    image[..., 1] = 14000
    image[..., 2] = 22000
    tifffile.imwrite(str(source), image, photometric="rgb", metadata=None)

    recipe = Recipe(
        exposure_compensation=1.0,
        tone_curve="srgb",
        output_linear=False,
    )
    develop_controlled(source, recipe, out, audit)

    source_linear = read_image(source)
    audit_linear = read_image(audit)
    rendered = read_image(out)

    assert np.allclose(audit_linear, source_linear, atol=1 / 65535)
    assert not np.allclose(rendered, audit_linear, atol=1e-3)
