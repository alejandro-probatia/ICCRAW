from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys
import warnings

warnings.filterwarnings(
    "ignore",
    message='.*"Matplotlib" related API features are not available.*',
)

try:
    from colour.utilities import ColourUsageWarning

    warnings.filterwarnings("ignore", category=ColourUsageWarning)
except Exception:
    pass

from .chart_detection import detect_chart, draw_detection_overlay
from .export import batch_develop
from .models import to_json_dict, write_json
from .pipeline import develop_controlled
from .profiling import build_profile, validate_profile
from .raw import raw_info
from .recipe import load_recipe
from .reporting import gather_run_context
from .sampling import ReferenceCatalog, chart_detection_from_json, sample_chart, sampleset_from_json
from .workflow import auto_profile_batch

APP_VERSION = "0.1.0-python"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="app", description="CLI para perfilado ICC reproducible")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("raw-info")
    s.add_argument("input")

    s = sub.add_parser("develop")
    s.add_argument("input")
    s.add_argument("--recipe", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--audit-linear", default=None)

    s = sub.add_parser("detect-chart")
    s.add_argument("input")
    s.add_argument("--out", required=True)
    s.add_argument("--preview", default=None)
    s.add_argument("--chart-type", choices=["colorchecker24", "it8"], default="colorchecker24")

    s = sub.add_parser("sample-chart")
    s.add_argument("input")
    s.add_argument("--detection", required=True)
    s.add_argument("--reference", required=True)
    s.add_argument("--out", required=True)

    s = sub.add_parser("build-profile")
    s.add_argument("samples")
    s.add_argument("--recipe", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--report", required=True)
    s.add_argument("--camera", default=None)
    s.add_argument("--lens", default=None)

    s = sub.add_parser("batch-develop")
    s.add_argument("input")
    s.add_argument("--recipe", required=True)
    s.add_argument("--profile", required=True)
    s.add_argument("--out", required=True)

    s = sub.add_parser("validate-profile")
    s.add_argument("samples")
    s.add_argument("--profile", required=True)
    s.add_argument("--out", required=True)

    s = sub.add_parser("auto-profile-batch")
    s.add_argument("--charts", required=True, help="Directorio de capturas RAW/imagen con carta ColorChecker")
    s.add_argument("--targets", required=True, help="Directorio de RAW/imagenes objetivo para batch")
    s.add_argument("--recipe", required=True)
    s.add_argument("--reference", required=True)
    s.add_argument("--profile-out", required=True)
    s.add_argument("--profile-report", required=True)
    s.add_argument("--out", required=True, help="Directorio de salida TIFF batch")
    s.add_argument("--workdir", required=True, help="Directorio de artefactos intermedios (detecciones/samples)")
    s.add_argument("--chart-type", choices=["colorchecker24", "it8"], default="colorchecker24")
    s.add_argument("--min-confidence", type=float, default=0.35)
    s.add_argument("--camera", default=None)
    s.add_argument("--lens", default=None)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "raw-info":
            result = raw_info(Path(args.input))
            print(json.dumps(to_json_dict(result), indent=2))
            return 0

        if args.command == "develop":
            recipe = load_recipe(Path(args.recipe))
            result = develop_controlled(
                Path(args.input),
                recipe,
                Path(args.out),
                Path(args.audit_linear) if args.audit_linear else None,
            )
            payload = {
                "run_context": gather_run_context(APP_VERSION),
                "develop": to_json_dict(result),
            }
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "detect-chart":
            result = detect_chart(Path(args.input), chart_type=args.chart_type)
            write_json(Path(args.out), result)
            if args.preview:
                draw_detection_overlay(Path(args.input), result, Path(args.preview))
            print(json.dumps(to_json_dict(result), indent=2))
            return 0

        if args.command == "sample-chart":
            detection = chart_detection_from_json(Path(args.detection))
            reference = ReferenceCatalog.from_path(Path(args.reference))
            samples = sample_chart(Path(args.input), detection, reference)
            write_json(Path(args.out), samples)
            print(json.dumps(to_json_dict(samples), indent=2))
            return 0

        if args.command == "build-profile":
            samples = sampleset_from_json(Path(args.samples))
            recipe = load_recipe(Path(args.recipe))
            result = build_profile(
                samples=samples,
                recipe=recipe,
                out_icc=Path(args.out),
                camera_model=args.camera,
                lens_model=args.lens,
            )
            write_json(Path(args.report), result)
            print(json.dumps(to_json_dict(result), indent=2))
            return 0

        if args.command == "batch-develop":
            recipe = load_recipe(Path(args.recipe))
            manifest = batch_develop(
                raws_dir=Path(args.input),
                recipe=recipe,
                profile_path=Path(args.profile),
                out_dir=Path(args.out),
            )
            manifest_path = Path(args.out) / "batch_manifest.json"
            write_json(manifest_path, manifest)
            print(json.dumps(to_json_dict(manifest), indent=2))
            return 0

        if args.command == "validate-profile":
            samples = sampleset_from_json(Path(args.samples))
            result = validate_profile(samples=samples, profile_path=Path(args.profile))
            write_json(Path(args.out), result)
            print(json.dumps(to_json_dict(result), indent=2))
            return 0

        if args.command == "auto-profile-batch":
            recipe = load_recipe(Path(args.recipe))
            reference = ReferenceCatalog.from_path(Path(args.reference))
            result = auto_profile_batch(
                chart_captures_dir=Path(args.charts),
                target_captures_dir=Path(args.targets),
                recipe=recipe,
                reference=reference,
                profile_out=Path(args.profile_out),
                profile_report_out=Path(args.profile_report),
                batch_out_dir=Path(args.out),
                work_dir=Path(args.workdir),
                chart_type=args.chart_type,
                min_confidence=float(args.min_confidence),
                camera_model=args.camera,
                lens_model=args.lens,
            )
            print(json.dumps(result, indent=2))
            return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
