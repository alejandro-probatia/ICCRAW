from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

from ..core.models import Recipe
from ..core.utils import RAW_EXTENSIONS, read_image
from ..raw.pipeline import develop_image_array, develop_standard_output_array, is_standard_output_space


def normalize_full_resolution_image(image: np.ndarray) -> np.ndarray:
    normalized = np.asarray(image, dtype=np.float32)
    if normalized.ndim == 2:
        normalized = np.repeat(normalized[..., None], 3, axis=2)
    if normalized.ndim != 3 or normalized.shape[2] < 3:
        raise ValueError(f"Imagen inesperada para MTF: shape={normalized.shape}")
    return np.ascontiguousarray(np.clip(normalized[..., :3], 0.0, 1.0).astype(np.float32, copy=False))


def roi_for_analysis_dimensions(
    roi: tuple[int, int, int, int],
    display_dimensions: tuple[int, int] | None,
    analysis_dimensions: tuple[int, int],
) -> tuple[int, int, int, int]:
    if display_dimensions is None or display_dimensions == analysis_dimensions:
        return roi
    display_w, display_h = display_dimensions
    analysis_w, analysis_h = analysis_dimensions
    if display_w <= 0 or display_h <= 0 or analysis_w <= 0 or analysis_h <= 0:
        return roi
    scale_x = float(analysis_w) / float(display_w)
    scale_y = float(analysis_h) / float(display_h)
    x, y, width, height = roi
    return (
        int(round(float(x) * scale_x)),
        int(round(float(y) * scale_y)),
        max(1, int(round(float(width) * scale_x))),
        max(1, int(round(float(height) * scale_y))),
    )


def clip_roi_to_dimensions(
    roi: tuple[int, int, int, int],
    dimensions: tuple[int, int],
) -> tuple[int, int, int, int]:
    width, height = int(dimensions[0]), int(dimensions[1])
    x, y, roi_w, roi_h = [int(round(float(v))) for v in roi]
    x0 = int(np.clip(x, 0, max(0, width - 1)))
    y0 = int(np.clip(y, 0, max(0, height - 1)))
    x1 = int(np.clip(x + max(1, roi_w), x0 + 1, width))
    y1 = int(np.clip(y + max(1, roi_h), y0 + 1, height))
    return x0, y0, x1 - x0, y1 - y0


def padded_roi(
    roi: tuple[int, int, int, int],
    dimensions: tuple[int, int],
    *,
    padding: int,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    width, height = int(dimensions[0]), int(dimensions[1])
    x, y, roi_w, roi_h = clip_roi_to_dimensions(roi, dimensions)
    pad = max(0, int(padding))
    px0 = max(0, x - pad)
    py0 = max(0, y - pad)
    px1 = min(width, x + roi_w + pad)
    py1 = min(height, y + roi_h + pad)
    padded = (px0, py0, max(1, px1 - px0), max(1, py1 - py0))
    relative = (x - px0, y - py0, roi_w, roi_h)
    return padded, relative


def build_full_resolution_base_roi(request: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(request["path"])).expanduser()
    recipe_payload = request.get("recipe")
    recipe = Recipe(**recipe_payload) if isinstance(recipe_payload, dict) else None
    display_dimensions = _optional_dimensions(request.get("display_dimensions"))
    display_roi = _roi_tuple(request["display_roi"])
    padding = int(request.get("padding", 0))
    source_key = str(request.get("source_key") or "")

    if path.suffix.lower() in RAW_EXTENSIONS:
        recipe = recipe or Recipe()
        if is_standard_output_space(recipe.output_space):
            image = develop_standard_output_array(path, recipe, half_size=False)
        else:
            image = develop_image_array(path, recipe, half_size=False)
    else:
        image = read_image(path)

    base = normalize_full_resolution_image(image)
    analysis_dimensions = (int(base.shape[1]), int(base.shape[0]))
    analysis_roi = roi_for_analysis_dimensions(display_roi, display_dimensions, analysis_dimensions)
    analysis_roi = clip_roi_to_dimensions(analysis_roi, analysis_dimensions)
    padded, relative = padded_roi(analysis_roi, analysis_dimensions, padding=padding)
    px, py, pw, ph = padded
    block = np.ascontiguousarray(base[py : py + ph, px : px + pw, :3]).copy()
    return {
        "image": block,
        "source_key": source_key,
        "analysis_dimensions": analysis_dimensions,
        "display_dimensions": display_dimensions,
        "display_roi": display_roi,
        "analysis_roi": analysis_roi,
        "padded_roi": padded,
        "relative_roi": relative,
        "padding": padding,
    }


def write_base_roi_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.ascontiguousarray(np.asarray(payload["image"], dtype=np.float32)[..., :3])
    meta = {key: value for key, value in payload.items() if key != "image"}
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("wb") as handle:
        np.savez(handle, image=image, meta=json.dumps(meta, sort_keys=True, ensure_ascii=False))
    tmp_path.replace(path)


def read_base_roi_cache(path: Path) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as data:
        image = np.asarray(data["image"], dtype=np.float32)
        meta_raw = data["meta"]
        meta_text = str(meta_raw.item() if hasattr(meta_raw, "item") else meta_raw)
    payload = json.loads(meta_text)
    payload["image"] = np.ascontiguousarray(image[..., :3])
    for key in ("analysis_dimensions", "display_dimensions", "display_roi", "analysis_roi", "padded_roi", "relative_roi"):
        value = payload.get(key)
        if isinstance(value, list):
            payload[key] = tuple(int(v) for v in value)
    return payload


def _roi_tuple(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        raise ValueError(f"ROI MTF inválida: {value!r}")
    return tuple(int(round(float(v))) for v in value[:4])  # type: ignore[return-value]


def _optional_dimensions(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    width = int(round(float(value[0])))
    height = int(round(float(value[1])))
    if width <= 0 or height <= 0:
        return None
    return width, height


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: python -m probraw.analysis.mtf_roi request.json output.npz", file=sys.stderr)
        return 2
    request_path = Path(args[0])
    output_path = Path(args[1])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    payload = build_full_resolution_base_roi(request)
    write_base_roi_cache(output_path, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
