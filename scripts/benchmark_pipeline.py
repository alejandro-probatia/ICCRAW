from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from statistics import mean, median
from time import perf_counter

warnings.filterwarnings(
    "ignore",
    message='.*"Matplotlib" related API features are not available.*',
)

try:
    from colour.utilities import ColourUsageWarning

    warnings.filterwarnings("ignore", category=ColourUsageWarning)
except Exception:
    pass

from iccraw.core.recipe import load_recipe
from iccraw.core.utils import sha256_file
from iccraw.raw.pipeline import develop_controlled, develop_image_array
from iccraw.raw.preview import apply_adjustments, apply_render_adjustments, linear_to_srgb_display, load_image_for_preview


def _time_call(fn, repeat: int) -> tuple[object, list[float]]:
    timings: list[float] = []
    result = None
    for _ in range(max(1, int(repeat))):
        start = perf_counter()
        result = fn()
        timings.append(perf_counter() - start)
    return result, timings


def _summary(timings: list[float]) -> dict[str, float | int]:
    return {
        "runs": len(timings),
        "mean_seconds": float(mean(timings)),
        "median_seconds": float(median(timings)),
        "min_seconds": float(min(timings)),
        "max_seconds": float(max(timings)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark basico de preview/render NexoRAW")
    parser.add_argument("input", type=Path)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--max-preview-side", type=int, default=2600)
    parser.add_argument("--include-file-render", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    recipe = load_recipe(args.recipe)
    benchmarks: dict[str, object] = {}
    payload: dict[str, object] = {
        "input": str(args.input),
        "input_sha256": sha256_file(args.input),
        "recipe": str(args.recipe),
        "repeat": int(args.repeat),
        "benchmarks": benchmarks,
    }

    preview_fast, fast_timings = _time_call(
        lambda: load_image_for_preview(
            args.input,
            recipe=recipe,
            fast_raw=True,
            max_preview_side=args.max_preview_side,
        ),
        args.repeat,
    )
    fast_image, fast_message = preview_fast
    benchmarks["preview_fast"] = {
        **_summary(fast_timings),
        "shape": list(fast_image.shape),
        "message": fast_message,
    }

    preview_hq, hq_timings = _time_call(
        lambda: load_image_for_preview(
            args.input,
            recipe=recipe,
            fast_raw=False,
            max_preview_side=args.max_preview_side,
        ),
        args.repeat,
    )
    hq_image, hq_message = preview_hq
    benchmarks["preview_high_quality"] = {
        **_summary(hq_timings),
        "shape": list(hq_image.shape),
        "message": hq_message,
    }

    detail_image, detail_timings = _time_call(
        lambda: apply_adjustments(
            hq_image,
            denoise_luminance=0.25,
            denoise_color=0.25,
            sharpen_amount=0.45,
            sharpen_radius=1.0,
        ),
        args.repeat,
    )
    benchmarks["preview_detail_adjustments"] = {
        **_summary(detail_timings),
        "shape": list(detail_image.shape),
    }

    tonal_image, tonal_timings = _time_call(
        lambda: apply_render_adjustments(
            detail_image,
            brightness_ev=0.15,
            black_point=0.01,
            white_point=0.98,
            contrast=0.12,
            midtone=1.05,
        ),
        args.repeat,
    )
    benchmarks["preview_tonal_adjustments"] = {
        **_summary(tonal_timings),
        "shape": list(tonal_image.shape),
    }

    display_image, display_timings = _time_call(lambda: linear_to_srgb_display(tonal_image), args.repeat)
    benchmarks["preview_display_srgb"] = {
        **_summary(display_timings),
        "shape": list(display_image.shape),
    }

    array_image, array_timings = _time_call(lambda: develop_image_array(args.input, recipe), args.repeat)
    benchmarks["develop_image_array"] = {
        **_summary(array_timings),
        "shape": list(array_image.shape),
    }

    if args.include_file_render:
        tmp_out = (args.out or Path.cwd() / "benchmark_pipeline.json").with_suffix(".benchmark_render.tiff")
        _, file_timings = _time_call(lambda: develop_controlled(args.input, recipe, tmp_out, None), args.repeat)
        benchmarks["develop_controlled_file"] = {
            **_summary(file_timings),
            "output_tiff": str(tmp_out),
            "output_sha256": sha256_file(tmp_out),
        }

    text = json.dumps(payload, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
