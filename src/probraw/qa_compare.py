from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .core.models import read_json


def compare_qa_reports(report_paths: list[Path]) -> dict[str, Any]:
    if len(report_paths) < 2:
        raise RuntimeError("Se necesitan al menos dos reportes QA para comparar sesiones.")

    sessions = [_session_summary(path, read_json(path)) for path in report_paths]
    baseline = sessions[0]
    deltas = [_delta_vs_baseline(baseline, session) for session in sessions[1:]]
    ranked = sorted(
        [s for s in sessions if s["validation_mean_delta_e2000"] is not None],
        key=lambda item: float(item["validation_mean_delta_e2000"]),
    )

    return {
        "report_count": len(sessions),
        "baseline_report": baseline["report_path"],
        "status_counts": dict(Counter(str(s["status"]) for s in sessions)),
        "best_validation_mean_delta_e2000": ranked[0] if ranked else None,
        "worst_validation_mean_delta_e2000": ranked[-1] if ranked else None,
        "sessions": sessions,
        "deltas_vs_baseline": deltas,
    }


def _session_summary(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    validation_error = payload.get("validation_error_summary")
    if not isinstance(validation_error, dict):
        validation_error = {}
    training_error = payload.get("training_error_summary")
    if not isinstance(training_error, dict):
        training_error = {}

    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    failed_checks = [
        {
            "id": str(check.get("id") or ""),
            "severity": str(check.get("severity") or "warning"),
        }
        for check in checks
        if isinstance(check, dict) and check.get("passed") is False
    ]

    return {
        "report_path": str(path),
        "label": _session_label(path),
        "status": str(payload.get("status") or "unknown"),
        "training_capture_count": len(payload.get("training_captures", []) or []),
        "validation_capture_count": len(payload.get("validation_captures", []) or []),
        "training_mean_delta_e2000": _float_or_none(training_error.get("mean_delta_e2000")),
        "training_max_delta_e2000": _float_or_none(training_error.get("max_delta_e2000")),
        "validation_mean_delta_e2000": _float_or_none(validation_error.get("mean_delta_e2000")),
        "validation_max_delta_e2000": _float_or_none(validation_error.get("max_delta_e2000")),
        "validation_p95_delta_e2000": _float_or_none(validation_error.get("p95_delta_e2000")),
        "failed_checks": failed_checks,
        "failed_error_count": sum(1 for check in failed_checks if check["severity"] == "error"),
        "failed_warning_count": sum(1 for check in failed_checks if check["severity"] == "warning"),
        "training_patch_outliers": _patch_ids(payload.get("training_patch_outliers")),
        "validation_patch_outliers": _patch_ids(payload.get("validation_patch_outliers")),
        "worst_validation_patches": _worst_patch_summary(payload.get("validation_worst_patches")),
        "capture_quality": _capture_quality_summary(payload),
    }


def _delta_vs_baseline(baseline: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_path": session["report_path"],
        "label": session["label"],
        "status_changed": session["status"] != baseline["status"],
        "status_delta": {
            "from": baseline["status"],
            "to": session["status"],
        },
        "validation_mean_delta_e2000_delta": _numeric_delta(
            baseline.get("validation_mean_delta_e2000"),
            session.get("validation_mean_delta_e2000"),
        ),
        "validation_max_delta_e2000_delta": _numeric_delta(
            baseline.get("validation_max_delta_e2000"),
            session.get("validation_max_delta_e2000"),
        ),
        "failed_warning_count_delta": int(session["failed_warning_count"]) - int(baseline["failed_warning_count"]),
        "failed_error_count_delta": int(session["failed_error_count"]) - int(baseline["failed_error_count"]),
        "new_failed_checks": sorted(
            set(_failed_check_ids(session["failed_checks"])) - set(_failed_check_ids(baseline["failed_checks"]))
        ),
        "resolved_failed_checks": sorted(
            set(_failed_check_ids(baseline["failed_checks"])) - set(_failed_check_ids(session["failed_checks"]))
        ),
    }


def _capture_quality_summary(payload: dict[str, Any]) -> dict[str, Any]:
    validation_quality = payload.get("validation_capture_quality")
    training_quality = payload.get("training_capture_quality")
    quality = validation_quality if isinstance(validation_quality, dict) else training_quality
    if not isinstance(quality, dict):
        return {}
    return {
        "capture_count": quality.get("capture_count"),
        "min_brightest_neutral_luma": _float_or_none(quality.get("min_brightest_neutral_luma")),
        "min_median_luma": _float_or_none(quality.get("min_median_luma")),
        "max_neutral_density_spread_ev": _float_or_none(quality.get("max_neutral_density_spread_ev")),
        "max_neutral_illumination_gradient_ev": _float_or_none(
            quality.get("max_neutral_illumination_gradient_ev")
        ),
    }


def _session_label(path: Path) -> str:
    parent = path.parent.name
    stem = path.stem
    return f"{parent}/{stem}" if parent else stem


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _numeric_delta(baseline: Any, current: Any) -> float | None:
    baseline_value = _float_or_none(baseline)
    current_value = _float_or_none(current)
    if baseline_value is None or current_value is None:
        return None
    return current_value - baseline_value


def _patch_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item.get("patch_id")) for item in value if isinstance(item, dict) and item.get("patch_id")]


def _worst_patch_summary(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    patches: list[dict[str, Any]] = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        patches.append(
            {
                "patch_id": str(item.get("patch_id") or ""),
                "delta_e2000": _float_or_none(item.get("delta_e2000")),
            }
        )
    return patches


def _failed_check_ids(checks: list[dict[str, Any]]) -> list[str]:
    return [str(check.get("id") or "") for check in checks if check.get("id")]
