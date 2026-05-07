from pathlib import Path

import numpy as np
import pytest
import tifffile

from probraw.core.utils import normalize_tiff_compression, resolve_tiff_maxworkers, versioned_output_path, write_tiff16


def test_versioned_output_path_keeps_first_free_name(tmp_path: Path):
    target = tmp_path / "capture.tiff"

    assert versioned_output_path(target) == target

    target.write_bytes(b"first")
    assert versioned_output_path(target) == tmp_path / "capture_v002.tiff"

    (tmp_path / "capture_v002.tiff").write_bytes(b"second")
    assert versioned_output_path(target) == tmp_path / "capture_v003.tiff"


@pytest.mark.parametrize(
    ("requested", "stored"),
    [
        ("zip", "ADOBE_DEFLATE"),
        ("lzw", "LZW"),
        ("jpeg", "JPEG"),
        ("zstd", "ZSTD"),
    ],
)
def test_write_tiff16_accepts_compression_codecs(tmp_path: Path, requested: str, stored: str):
    target = tmp_path / f"compressed_{requested}.tiff"
    image = np.full((8, 8, 3), 0.5, dtype=np.float32)

    write_tiff16(target, image, compression=requested)

    with tifffile.TiffFile(target) as tiff:
        assert tiff.pages[0].compression.name == stored
        assert tiff.pages[0].dtype == np.dtype("uint16")


def test_normalize_tiff_compression_accepts_zfs_alias():
    assert normalize_tiff_compression("zfs") == "zstd"


def test_write_tiff16_passes_maxworkers_to_compressed_writer(tmp_path: Path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_imwrite(path, data, **kwargs):
        captured["path"] = path
        captured["dtype"] = data.dtype
        captured["compression"] = kwargs.get("compression")
        captured["maxworkers"] = kwargs.get("maxworkers")

    monkeypatch.setattr("probraw.core.utils.tifffile.imwrite", fake_imwrite)

    write_tiff16(tmp_path / "out.tiff", np.full((4, 4, 3), 0.5, dtype=np.float32), compression="zip", maxworkers=3)

    assert captured["compression"] == "adobe_deflate"
    assert captured["maxworkers"] == 3
    assert captured["dtype"] == np.dtype("uint16")


def test_resolve_tiff_maxworkers_uses_environment_for_compressed_tiff(monkeypatch):
    monkeypatch.setenv("PROBRAW_TIFF_MAXWORKERS", "5")

    assert resolve_tiff_maxworkers(compression="zstd") == 5
    assert resolve_tiff_maxworkers(compression="none") is None
