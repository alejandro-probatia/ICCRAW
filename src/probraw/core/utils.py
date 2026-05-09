from __future__ import annotations

from pathlib import Path
import hashlib
import itertools
import os
from typing import Any, Iterable

import numpy as np
import tifffile
from PIL import Image


RAW_EXTENSIONS = {".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf", ".pef"}
TIFF_COMPRESSION_OPTIONS = {
    "none": None,
    "uncompressed": None,
    "sin_compresion": None,
    "zip": "adobe_deflate",
    "deflate": "adobe_deflate",
    "adobe_deflate": "adobe_deflate",
    "zlib": "adobe_deflate",
    "lzw": "lzw",
    "jpeg": "jpeg",
    "jpg": "jpeg",
    "zstd": "zstd",
    "zfs": "zstd",
}
TIFF_MAXWORKERS_ENV = "PROBRAW_TIFF_MAXWORKERS"
TIFF_QUANTIZE_TILE_PIXELS = 4_000_000


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def versioned_output_path(path: Path, *, separator: str = "_v", width: int = 3) -> Path:
    """Return a non-existing sibling path by appending a version suffix.

    The first render keeps the requested name. If it already exists, subsequent
    renders use ``stem_v002.ext``, ``stem_v003.ext`` and so on, preserving
    previous TIFFs and their audit value.
    """
    candidate = Path(path)
    if not candidate.exists():
        return candidate

    parent = candidate.parent
    stem = candidate.stem
    suffix = candidate.suffix
    for index in itertools.count(2):
        versioned = parent / f"{stem}{separator}{index:0{int(width)}d}{suffix}"
        if not versioned.exists():
            return versioned
    raise RuntimeError("No se pudo generar una ruta versionada de salida")


def list_raw_files(folder: Path) -> list[Path]:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in RAW_EXTENSIONS]
    files.sort()
    return files


def read_image(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        arr = tifffile.imread(str(path))
        return _to_float_rgb(arr)
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img)
    return _to_float_rgb(arr)


def _to_float_rgb(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr)
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=2)
    if arr.shape[-1] > 3:
        arr = arr[..., :3]

    if np.issubdtype(arr.dtype, np.integer):
        maxv = np.iinfo(arr.dtype).max
        return arr.astype(np.float32) / float(maxv)
    return np.clip(arr.astype(np.float32), 0.0, 1.0)


def normalize_tiff_compression(compression: str | None) -> str | None:
    key = str(compression or "none").strip().lower().replace(" ", "_").replace("-", "_")
    if key not in TIFF_COMPRESSION_OPTIONS:
        supported = ", ".join(["none", "zip", "lzw", "jpeg", "zstd"])
        raise ValueError(f"Compresion TIFF no soportada: {compression!r}. Valores: {supported}")
    return TIFF_COMPRESSION_OPTIONS[key]


def tiff_compression_for_metadata(compression: str | None) -> str:
    return normalize_tiff_compression(compression) or "none"


def resolve_tiff_maxworkers(maxworkers: int | None = None, *, compression: str | None = None) -> int | None:
    if normalize_tiff_compression(compression) is None:
        return None
    if maxworkers is not None:
        value = int(maxworkers)
        return value if value > 0 else None
    raw = os.environ.get(TIFF_MAXWORKERS_ENV, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _tiff_write_kwargs(compression: str | None, maxworkers: int | None = None) -> dict[str, Any]:
    normalized = normalize_tiff_compression(compression)
    if normalized is None:
        return {}
    kwargs: dict[str, Any] = {"compression": normalized}
    resolved_maxworkers = resolve_tiff_maxworkers(maxworkers, compression=normalized)
    if resolved_maxworkers is not None:
        kwargs["maxworkers"] = resolved_maxworkers
    return kwargs


def _write_tiff_array(
    path: Path,
    data: np.ndarray,
    *,
    icc_profile: bytes | None = None,
    compression: str | None = None,
    maxworkers: int | None = None,
) -> None:
    extratags = None
    if icc_profile:
        extratags = [(34675, "B", len(icc_profile), icc_profile, False)]
    try:
        tifffile.imwrite(
            str(path),
            data,
            photometric="rgb",
            metadata=None,
            extratags=extratags,
            **_tiff_write_kwargs(compression, maxworkers=maxworkers),
        )
    except Exception as exc:
        normalized = tiff_compression_for_metadata(compression)
        if normalized == "none":
            raise
        raise RuntimeError(
            f"No se pudo escribir TIFF con compresion {normalized!r}. "
            "Instala los codecs necesarios para tifffile/imagecodecs o elige 'Sin compresion'/'ZIP'."
        ) from exc


def write_tiff16(
    path: Path,
    image_linear_rgb: np.ndarray,
    icc_profile: bytes | None = None,
    *,
    compression: str | None = None,
    maxworkers: int | None = None,
) -> None:
    ensure_parent(path)
    source = np.asarray(image_linear_rgb, dtype=np.float32)
    data = _quantize_float_to_uint16_tiled(source)
    _write_tiff_array(path, data, icc_profile=icc_profile, compression=compression, maxworkers=maxworkers)


def _quantize_float_to_uint16_tiled(source: np.ndarray) -> np.ndarray:
    source = np.asarray(source, dtype=np.float32)
    data = np.empty(source.shape, dtype=np.uint16)
    if source.ndim < 2 or source.size <= TIFF_QUANTIZE_TILE_PIXELS:
        work = np.empty(source.shape, dtype=np.float32)
        np.clip(source, 0.0, 1.0, out=work)
        np.multiply(work, 65535.0, out=work)
        np.rint(work, out=work)
        data[...] = work.astype(np.uint16, copy=False)
        return data

    height = int(source.shape[0])
    width = int(source.shape[1])
    rows = max(1, min(height, int(TIFF_QUANTIZE_TILE_PIXELS) // max(1, width)))
    for y0 in range(0, height, rows):
        y1 = min(height, y0 + rows)
        block = source[y0:y1]
        work = np.empty(block.shape, dtype=np.float32)
        np.clip(block, 0.0, 1.0, out=work)
        np.multiply(work, 65535.0, out=work)
        np.rint(work, out=work)
        data[y0:y1] = work.astype(np.uint16, copy=False)
    return data


def rewrite_tiff_compression(path: Path, compression: str | None, *, maxworkers: int | None = None) -> None:
    if normalize_tiff_compression(compression) is None:
        return
    with tifffile.TiffFile(str(path)) as tiff:
        page = tiff.pages[0]
        data = page.asarray()
        tag = page.tags.get(34675)
        icc_profile = bytes(tag.value) if tag is not None else None
    temp_path = path.with_name(f".{path.stem}.compressed{path.suffix}")
    _write_tiff_array(temp_path, data, icc_profile=icc_profile, compression=compression, maxworkers=maxworkers)
    temp_path.replace(path)


def robust_trimmed_mean(values: np.ndarray, trim_percent: float) -> float:
    if values.size == 0:
        return float("nan")
    values = np.sort(values)
    n = values.size
    k = int(n * trim_percent)
    if 2 * k >= n:
        return float(np.mean(values))
    return float(np.mean(values[k : n - k]))


def as_float_list(values: Iterable[float]) -> list[float]:
    return [float(v) for v in values]
