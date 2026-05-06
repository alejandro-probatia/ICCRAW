from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _find_raw_run(payload: dict[str, Any], label: str) -> float | None:
    for row in payload.get("runs", []):
        if row.get("label") == label:
            value = row.get("median_wall_seconds")
            if value is not None:
                return float(value)
            samples = row.get("samples") or []
            if samples:
                return float(samples[0].get("wall_seconds", 0.0))
    return None


def _find_gui_phase(payload: dict[str, Any], name: str, metric: str) -> float | None:
    for row in payload.get("phases", []):
        if row.get("name") != name:
            continue
        current: Any = row
        for part in metric.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return float(current)
    return None


def _compare(name: str, current: float | None, baseline: float | None, tolerance: float, failures: list[str]) -> None:
    if current is None or baseline is None:
        failures.append(f"{name}: metrica ausente")
        return
    limit = baseline * (1.0 + tolerance)
    if current > limit:
        failures.append(f"{name}: {current:.4f}s > limite {limit:.4f}s (baseline {baseline:.4f}s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comprueba regresiones de rendimiento en JSON de benchmarks ProbRAW")
    parser.add_argument("--current-raw", type=Path, default=None)
    parser.add_argument("--baseline-raw", type=Path, default=None)
    parser.add_argument("--current-gui", type=Path, default=None)
    parser.add_argument("--baseline-gui", type=Path, default=None)
    parser.add_argument("--tolerance", type=float, default=0.20, help="Regresion relativa permitida, por defecto 0.20")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    failures: list[str] = []
    checks: list[dict[str, Any]] = []

    if args.current_raw and args.baseline_raw:
        current = _load(args.current_raw)
        baseline = _load(args.baseline_raw)
        for label in (
            "cache_hit_dcb",
            "half_size_dcb",
            "full_no_cache_dcb",
            "full_no_cache_amaze",
        ):
            current_value = _find_raw_run(current, label)
            baseline_value = _find_raw_run(baseline, label)
            _compare(label, current_value, baseline_value, float(args.tolerance), failures)
            checks.append({"name": label, "current": current_value, "baseline": baseline_value})

    if args.current_gui and args.baseline_gui:
        current = _load(args.current_gui)
        baseline = _load(args.baseline_gui)
        for phase, metric in (
            ("brightness_single_change", "last_preview_ms"),
            ("brightness_slider_drag", "event_loop.p95_ms"),
            ("tone_curve_drag", "event_loop.p95_ms"),
        ):
            name = f"{phase}.{metric}"
            current_value = _find_gui_phase(current, phase, metric)
            baseline_value = _find_gui_phase(baseline, phase, metric)
            _compare(name, current_value, baseline_value, float(args.tolerance), failures)
            checks.append({"name": name, "current": current_value, "baseline": baseline_value})

    result = {"status": "fail" if failures else "ok", "tolerance": float(args.tolerance), "checks": checks, "failures": failures}
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
