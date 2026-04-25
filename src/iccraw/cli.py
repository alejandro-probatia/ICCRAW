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

from .chart.detection import detect_chart, detect_chart_from_corners, draw_detection_overlay
from .chart.sampling import (
    ReferenceCatalog,
    chart_detection_from_json,
    sample_chart,
    sampleset_from_json,
)
from .core.models import to_json_dict, write_json
from .core.recipe import load_recipe, save_recipe
from .profile.development import build_development_profile
from .profile.builder import build_profile, validate_profile, write_samples_cgats
from .profile.export import batch_develop
from .provenance.c2pa import DEFAULT_TIMESTAMP_URL, C2PASignConfig, verify_c2pa_raw_link
from .qa_compare import compare_qa_reports
from .raw.metadata import raw_info
from .raw.pipeline import develop_controlled
from .reporting import check_amaze_backend, check_external_tools, gather_run_context
from .version import __version__
from .workflow import auto_profile_batch

APP_VERSION = __version__
DEFAULT_CLI_NAME = "nexoraw"


def _runtime_cli_name() -> str:
    stem = Path(sys.argv[0]).stem
    return stem if stem in {"nexoraw", "iccraw"} else DEFAULT_CLI_NAME


def _parse_corner_arg(value: str) -> tuple[float, float]:
    try:
        x_text, y_text = value.split(",", 1)
        return float(x_text), float(y_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("usa formato x,y para cada esquina") from exc


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog or DEFAULT_CLI_NAME,
        description="CLI de NexoRAW para perfilado ICC reproducible",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
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
    s.add_argument(
        "--manual-corners",
        nargs=4,
        type=_parse_corner_arg,
        metavar="X,Y",
        help="Cuatro esquinas de la carta para deteccion manual/asistida",
    )

    s = sub.add_parser("sample-chart")
    s.add_argument("input")
    s.add_argument("--detection", required=True)
    s.add_argument("--reference", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--recipe", default=None, help="Receta opcional para parametros de muestreo")

    s = sub.add_parser("build-profile")
    s.add_argument("samples")
    s.add_argument("--recipe", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--report", required=True)
    s.add_argument("--camera", default=None)
    s.add_argument("--lens", default=None)

    s = sub.add_parser("export-cgats")
    s.add_argument("samples")
    s.add_argument("--out", required=True)

    s = sub.add_parser("build-develop-profile")
    s.add_argument("samples")
    s.add_argument("--recipe", required=True)
    s.add_argument("--out", required=True, help="Perfil de revelado JSON")
    s.add_argument("--calibrated-recipe", required=True, help="Receta calibrada YAML/JSON")

    s = sub.add_parser("batch-develop")
    s.add_argument("input")
    s.add_argument("--recipe", required=True)
    s.add_argument("--profile", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--c2pa-sign", action="store_true", help="Firma cada TIFF final con C2PA")
    s.add_argument("--c2pa-cert", default=None, help="Cadena de certificado PEM para C2PA")
    s.add_argument("--c2pa-key", default=None, help="Clave privada PEM para C2PA")
    s.add_argument("--c2pa-alg", default="ps256", help="Algoritmo de firma C2PA: ps256, ps384, es256...")
    s.add_argument("--c2pa-timestamp-url", default=DEFAULT_TIMESTAMP_URL, help="URL TSA RFC 3161")
    s.add_argument("--c2pa-signer-name", default="NexoRAW", help="Nombre publico del agente firmante")
    s.add_argument(
        "--c2pa-technical-manifest",
        default=None,
        help="Manifiesto tecnico existente cuyo SHA-256 se incluira en la asercion C2PA",
    )
    s.add_argument("--session-id", default=None, help="Identificador de sesion opcional para trazabilidad C2PA")

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
    s.add_argument("--validation-report", default=None)
    s.add_argument("--out", required=True, help="Directorio de salida TIFF batch")
    s.add_argument("--workdir", required=True, help="Directorio de artefactos intermedios (detecciones/samples)")
    s.add_argument("--development-profile-out", default=None)
    s.add_argument("--calibrated-recipe-out", default=None)
    s.add_argument("--no-development-calibration", action="store_true")
    s.add_argument("--chart-type", choices=["colorchecker24", "it8"], default="colorchecker24")
    s.add_argument("--min-confidence", type=float, default=0.35)
    s.add_argument("--allow-fallback-detection", action="store_true")
    s.add_argument(
        "--validation-holdout-count",
        type=int,
        default=0,
        help="Reserva N capturas de carta para validacion cruzada independiente",
    )
    s.add_argument("--qa-mean-deltae2000-max", type=float, default=5.0)
    s.add_argument("--qa-max-deltae2000-max", type=float, default=10.0)
    s.add_argument(
        "--profile-validity-days",
        type=int,
        default=None,
        help="Vigencia opcional del perfil validado; al superarse se marca como expired",
    )
    s.add_argument("--camera", default=None)
    s.add_argument("--lens", default=None)

    s = sub.add_parser("compare-qa-reports")
    s.add_argument("reports", nargs="+", help="Reportes qa_session_report.json a comparar")
    s.add_argument("--out", default=None, help="JSON de salida opcional")

    s = sub.add_parser("check-tools")
    s.add_argument("--out", default=None, help="JSON de salida opcional")
    s.add_argument(
        "--strict",
        action="store_true",
        help="Devuelve codigo 2 si falta una herramienta externa requerida",
    )

    s = sub.add_parser("check-amaze")
    s.add_argument("--out", default=None, help="JSON de salida opcional")

    s = sub.add_parser("verify-c2pa")
    s.add_argument("input", help="TIFF final firmado")
    s.add_argument("--raw", required=True, help="RAW fuente para verificar SHA-256 declarado")
    s.add_argument("--manifest", default=None, help="batch_manifest.json externo de NexoRAW")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser(_runtime_cli_name()).parse_args(argv)

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
            if args.manual_corners:
                result = detect_chart_from_corners(
                    Path(args.input),
                    corners=list(args.manual_corners),
                    chart_type=args.chart_type,
                )
            else:
                result = detect_chart(Path(args.input), chart_type=args.chart_type)
            write_json(Path(args.out), result)
            if args.preview:
                draw_detection_overlay(Path(args.input), result, Path(args.preview))
            print(json.dumps(to_json_dict(result), indent=2))
            return 0

        if args.command == "sample-chart":
            detection = chart_detection_from_json(Path(args.detection))
            reference = ReferenceCatalog.from_path(Path(args.reference))
            recipe = load_recipe(Path(args.recipe)) if args.recipe else None
            samples = sample_chart(
                Path(args.input),
                detection,
                reference,
                strategy=recipe.sampling_strategy if recipe else "trimmed_mean",
                trim_percent=recipe.sampling_trim_percent if recipe else 0.1,
                reject_saturated=recipe.sampling_reject_saturated if recipe else True,
            )
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

        if args.command == "export-cgats":
            samples = sampleset_from_json(Path(args.samples))
            write_samples_cgats(samples, Path(args.out))
            print(json.dumps({"output_cgats": str(Path(args.out))}, indent=2))
            return 0

        if args.command == "build-develop-profile":
            samples = sampleset_from_json(Path(args.samples))
            recipe = load_recipe(Path(args.recipe))
            result = build_development_profile(samples=samples, base_recipe=recipe)
            write_json(Path(args.out), result)
            save_recipe(result.calibrated_recipe, Path(args.calibrated_recipe))
            print(json.dumps(to_json_dict(result), indent=2))
            return 0

        if args.command == "batch-develop":
            recipe = load_recipe(Path(args.recipe))
            c2pa_config = None
            if args.c2pa_sign:
                if not args.c2pa_cert or not args.c2pa_key:
                    raise RuntimeError("--c2pa-sign requiere --c2pa-cert y --c2pa-key")
                c2pa_config = C2PASignConfig(
                    cert_path=Path(args.c2pa_cert),
                    key_path=Path(args.c2pa_key),
                    alg=args.c2pa_alg,
                    timestamp_url=args.c2pa_timestamp_url,
                    signer_name=args.c2pa_signer_name,
                    technical_manifest_path=Path(args.c2pa_technical_manifest)
                    if args.c2pa_technical_manifest
                    else None,
                    session_id=args.session_id,
                )
            manifest = batch_develop(
                raws_dir=Path(args.input),
                recipe=recipe,
                profile_path=Path(args.profile),
                out_dir=Path(args.out),
                c2pa_config=c2pa_config,
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
                validation_report_out=Path(args.validation_report) if args.validation_report else None,
                batch_out_dir=Path(args.out),
                work_dir=Path(args.workdir),
                development_profile_out=Path(args.development_profile_out) if args.development_profile_out else None,
                calibrated_recipe_out=Path(args.calibrated_recipe_out) if args.calibrated_recipe_out else None,
                calibrate_development=not bool(args.no_development_calibration),
                chart_type=args.chart_type,
                min_confidence=float(args.min_confidence),
                allow_fallback_detection=bool(args.allow_fallback_detection),
                validation_holdout_count=int(args.validation_holdout_count),
                qa_mean_delta_e2000_max=float(args.qa_mean_deltae2000_max),
                qa_max_delta_e2000_max=float(args.qa_max_deltae2000_max),
                profile_validity_days=args.profile_validity_days,
                camera_model=args.camera,
                lens_model=args.lens,
            )
            print(json.dumps(result, indent=2))
            return 0

        if args.command == "compare-qa-reports":
            result = compare_qa_reports([Path(p) for p in args.reports])
            if args.out:
                write_json(Path(args.out), result)
            print(json.dumps(result, indent=2))
            return 0

        if args.command == "check-tools":
            result = check_external_tools()
            if args.out:
                write_json(Path(args.out), result)
            print(json.dumps(result, indent=2))
            if args.strict and result.get("status") != "ok":
                return 2
            return 0

        if args.command == "check-amaze":
            result = check_amaze_backend()
            if args.out:
                write_json(Path(args.out), result)
            print(json.dumps(result, indent=2))
            return 0 if result.get("amaze_supported") else 2

        if args.command == "verify-c2pa":
            result = verify_c2pa_raw_link(
                signed_tiff=Path(args.input),
                source_raw=Path(args.raw),
                external_manifest_path=Path(args.manifest) if args.manifest else None,
            )
            print(json.dumps(result, indent=2))
            return 0 if result.get("status") == "ok" else 2

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
