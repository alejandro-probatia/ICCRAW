"""Benchmark real del pipeline RAW de NexoRAW.

El script no depende de psutil y funciona en Windows, macOS y Linux. Mide el
tiempo de pared, tiempo CPU, shape/dtype del array y pico de memoria residente
del proceso cuando el sistema operativo lo expone.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import gc
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import sys
import tempfile
import time
from typing import Any, Callable

import numpy as np

from nexoraw.core.models import Recipe
from nexoraw.raw.pipeline import develop_scene_linear_array
from nexoraw.version import __version__


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark de demosaico RAW y cache numerica")
    parser.add_argument("raw", type=Path, help="Archivo RAW real a medir")
    parser.add_argument("--out", type=Path, default=Path("tmp/raw_benchmark/results.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("tmp/raw_benchmark/cache"))
    parser.add_argument("--algorithms", default="linear,dcb,amaze", help="Lista separada por comas")
    parser.add_argument("--cache-algorithm", default="dcb")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--process-jobs", type=int, default=4)
    parser.add_argument("--process-workers", default="1,2,4", help="Lista separada por comas")
    parser.add_argument("--skip-process-pool", action="store_true")
    parser.add_argument("--keep-cache", action="store_true")
    return parser.parse_args()


def peak_rss_mb() -> float | None:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            psapi = ctypes.WinDLL("psapi.dll")
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                wintypes.DWORD,
            ]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
            if ok:
                return float(counters.PeakWorkingSetSize) / (1024.0 * 1024.0)
        except Exception:
            return None
        return None

    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return float(usage) / (1024.0 * 1024.0)
        return float(usage) / 1024.0
    except Exception:
        return None


def measure(label: str, func: Callable[[], np.ndarray]) -> dict[str, Any]:
    gc.collect()
    start_wall = time.perf_counter()
    start_cpu = time.process_time()
    image = func()
    wall = time.perf_counter() - start_wall
    cpu = time.process_time() - start_cpu
    result = {
        "label": label,
        "wall_seconds": round(wall, 4),
        "cpu_seconds": round(cpu, 4),
        "peak_rss_mb": round(peak_rss_mb(), 1) if peak_rss_mb() is not None else None,
        "shape": list(image.shape),
        "dtype": str(image.dtype),
        "array_mb": round(float(image.nbytes) / (1024.0 * 1024.0), 1),
        "min": round(float(np.min(image)), 6),
        "max": round(float(np.max(image)), 6),
    }
    del image
    gc.collect()
    return result


def median_wall(rows: list[dict[str, Any]]) -> float:
    values = [float(row["wall_seconds"]) for row in rows]
    return round(float(statistics.median(values)), 4)


def decode_once(raw: Path, recipe: Recipe, *, half_size: bool = False, cache_dir: Path | None = None) -> np.ndarray:
    return develop_scene_linear_array(raw, recipe, half_size=half_size, cache_dir=cache_dir)


def process_decode_worker(job: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    raw_text, recipe_payload = job
    raw = Path(raw_text)
    recipe = Recipe(**recipe_payload)
    started = time.perf_counter()
    image = develop_scene_linear_array(raw, recipe)
    wall = time.perf_counter() - started
    payload = {
        "wall_seconds": round(wall, 4),
        "peak_rss_mb": round(peak_rss_mb(), 1) if peak_rss_mb() is not None else None,
        "shape": list(image.shape),
        "dtype": str(image.dtype),
    }
    del image
    return payload


def run_process_pool(raw: Path, recipe: Recipe, *, jobs: int, workers: int) -> dict[str, Any]:
    started = time.perf_counter()
    worker_results: list[dict[str, Any]] = []
    job_payload = [(str(raw), asdict(recipe)) for _ in range(max(1, jobs))]
    with ProcessPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(process_decode_worker, job) for job in job_payload]
        for future in as_completed(futures):
            worker_results.append(future.result())
    wall = time.perf_counter() - started
    worker_walls = [float(row["wall_seconds"]) for row in worker_results]
    peaks = [float(row["peak_rss_mb"]) for row in worker_results if row.get("peak_rss_mb") is not None]
    return {
        "label": f"process_pool_jobs{jobs}_workers{workers}",
        "jobs": int(jobs),
        "workers": int(workers),
        "wall_seconds": round(wall, 4),
        "median_worker_wall_seconds": round(float(statistics.median(worker_walls)), 4),
        "max_worker_wall_seconds": round(float(max(worker_walls)), 4),
        "sum_worker_peak_rss_mb": round(float(sum(peaks)), 1) if peaks else None,
        "worker_results": worker_results,
    }


def main() -> int:
    args = parse_args()
    raw = args.raw.expanduser().resolve()
    if not raw.is_file():
        raise SystemExit(f"No existe RAW: {raw}")

    out = args.out.expanduser().resolve()
    cache_dir = args.cache_dir.expanduser().resolve()
    algorithms = [part.strip() for part in str(args.algorithms).split(",") if part.strip()]
    worker_counts = [int(part.strip()) for part in str(args.process_workers).split(",") if part.strip()]

    if cache_dir.exists() and not args.keep_cache:
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {
        "schema": 1,
        "nexoraw_version": __version__,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "raw": {
            "path": str(raw),
            "size_mb": round(raw.stat().st_size / (1024.0 * 1024.0), 1),
        },
        "runs": [],
        "process_pool": [],
    }

    for algorithm in algorithms:
        recipe = Recipe(demosaic_algorithm=algorithm, output_space="scene_linear_camera_rgb", output_linear=True)
        per_algorithm: list[dict[str, Any]] = []
        for repeat in range(max(1, int(args.repeats))):
            per_algorithm.append(
                measure(
                    f"full_no_cache_{algorithm}_r{repeat + 1}",
                    lambda raw=raw, recipe=recipe: decode_once(raw, recipe),
                )
            )
        results["runs"].append(
            {
                "label": f"full_no_cache_{algorithm}",
                "median_wall_seconds": median_wall(per_algorithm),
                "samples": per_algorithm,
            }
        )

    cache_recipe = Recipe(
        demosaic_algorithm=str(args.cache_algorithm),
        output_space="scene_linear_camera_rgb",
        output_linear=True,
        use_cache=True,
    )
    results["runs"].append(
        {
            "label": f"cache_populate_{args.cache_algorithm}",
            "samples": [
                measure(
                    f"cache_populate_{args.cache_algorithm}",
                    lambda: decode_once(raw, cache_recipe, cache_dir=cache_dir),
                )
            ],
        }
    )
    cache_hits: list[dict[str, Any]] = []
    for repeat in range(max(1, int(args.repeats))):
        cache_hits.append(
            measure(
                f"cache_hit_{args.cache_algorithm}_r{repeat + 1}",
                lambda: decode_once(raw, cache_recipe, cache_dir=cache_dir),
            )
        )
    results["runs"].append(
        {
            "label": f"cache_hit_{args.cache_algorithm}",
            "median_wall_seconds": median_wall(cache_hits),
            "samples": cache_hits,
        }
    )

    half_recipe = Recipe(
        demosaic_algorithm=str(args.cache_algorithm),
        output_space="scene_linear_camera_rgb",
        output_linear=True,
    )
    half_samples: list[dict[str, Any]] = []
    for repeat in range(max(1, int(args.repeats))):
        half_samples.append(
            measure(
                f"half_size_{args.cache_algorithm}_r{repeat + 1}",
                lambda: decode_once(raw, half_recipe, half_size=True),
            )
        )
    results["runs"].append(
        {
            "label": f"half_size_{args.cache_algorithm}",
            "median_wall_seconds": median_wall(half_samples),
            "samples": half_samples,
        }
    )

    if not args.skip_process_pool:
        multiprocessing_recipe = Recipe(
            demosaic_algorithm=str(args.cache_algorithm),
            output_space="scene_linear_camera_rgb",
            output_linear=True,
        )
        for workers in worker_counts:
            results["process_pool"].append(
                run_process_pool(
                    raw,
                    multiprocessing_recipe,
                    jobs=max(1, int(args.process_jobs)),
                    workers=max(1, int(workers)),
                )
            )

    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
