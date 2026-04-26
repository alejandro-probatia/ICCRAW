from pathlib import Path

from iccraw.core.utils import versioned_output_path


def test_versioned_output_path_keeps_first_free_name(tmp_path: Path):
    target = tmp_path / "capture.tiff"

    assert versioned_output_path(target) == target

    target.write_bytes(b"first")
    assert versioned_output_path(target) == tmp_path / "capture_v002.tiff"

    (tmp_path / "capture_v002.tiff").write_bytes(b"second")
    assert versioned_output_path(target) == tmp_path / "capture_v003.tiff"
