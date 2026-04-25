from pathlib import Path
import shutil

import numpy as np
import pytest
import tifffile
from PIL import ImageCms

from iccraw.core.models import Recipe
from iccraw.core.utils import read_image
from iccraw.profile.export import batch_develop, color_management_mode, write_profiled_tiff


def test_color_management_mode_assigns_camera_profile_by_default():
    recipe = Recipe(output_space="scene_linear_camera_rgb", output_linear=True)
    assert color_management_mode(recipe) == "camera_rgb_with_input_icc"


def test_color_management_mode_requires_non_linear_srgb_output():
    recipe = Recipe(output_space="srgb", output_linear=True)
    with pytest.raises(RuntimeError, match="output_space=srgb requiere output_linear=false"):
        color_management_mode(recipe)


def test_write_profiled_tiff_assigns_input_profile_without_conversion(tmp_path: Path):
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")
    out = tmp_path / "camera_rgb.tiff"
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)

    mode = write_profiled_tiff(
        out,
        image,
        recipe=Recipe(output_space="camera_rgb", output_linear=True),
        profile_path=profile,
    )

    assert mode == "camera_rgb_with_input_icc"
    with tifffile.TiffFile(out) as tif:
        tags = tif.pages[0].tags
        assert 34675 in tags
        assert bytes(tags[34675].value) == b"camera-profile-placeholder"


def test_batch_develop_keeps_linear_audit_separate_from_final_outputs(tmp_path: Path):
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    raws.mkdir()
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)
    tifffile.imwrite(str(raws / "capture_01.tiff"), (image * 65535).astype(np.uint16), photometric="rgb", metadata=None)

    manifest = batch_develop(
        raws_dir=raws,
        recipe=Recipe(output_space="camera_rgb", output_linear=True),
        profile_path=profile,
        out_dir=out_dir,
    )

    assert (out_dir / "capture_01.tiff").exists()
    assert not (out_dir / "capture_01.linear.tiff").exists()
    assert (out_dir / "_linear_audit" / "capture_01.scene_linear.tiff").exists()
    assert manifest.entries[0].linear_audit_tiff == str(out_dir / "_linear_audit" / "capture_01.scene_linear.tiff")


def test_batch_develop_writes_true_linear_audit_before_output_adjustments(tmp_path: Path):
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    raws.mkdir()
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")

    image = np.zeros((6, 8, 3), dtype=np.uint16)
    image[..., 0] = 7000
    image[..., 1] = 14000
    image[..., 2] = 21000
    source = raws / "capture_01.tiff"
    tifffile.imwrite(str(source), image, photometric="rgb", metadata=None)

    recipe = Recipe(
        output_space="camera_rgb",
        output_linear=False,
        exposure_compensation=1.0,
        tone_curve="srgb",
    )
    manifest = batch_develop(
        raws_dir=raws,
        recipe=recipe,
        profile_path=profile,
        out_dir=out_dir,
    )

    source_linear = read_image(source)
    audit_linear = read_image(Path(manifest.entries[0].linear_audit_tiff or ""))
    rendered = read_image(out_dir / "capture_01.tiff")

    assert np.allclose(audit_linear, source_linear, atol=1 / 65535)
    assert not np.allclose(rendered, audit_linear, atol=1e-3)


@pytest.mark.skipif(shutil.which("tificc") is None, reason="requiere tificc/LittleCMS")
def test_write_profiled_tiff_converts_to_srgb_with_cmm(tmp_path: Path):
    profile = tmp_path / "source_srgb.icc"
    profile.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    out = tmp_path / "converted_srgb.tiff"
    image = np.zeros((10, 12, 3), dtype=np.float32)
    image[..., 0] = 0.2
    image[..., 1] = 0.3
    image[..., 2] = 0.4

    mode = write_profiled_tiff(
        out,
        image,
        recipe=Recipe(output_space="srgb", output_linear=False),
        profile_path=profile,
    )

    assert mode == "converted_srgb"
    arr = tifffile.imread(out)
    assert arr.dtype == np.uint16
    assert arr.shape == image.shape
    with tifffile.TiffFile(out) as tif:
        assert 34675 in tif.pages[0].tags
