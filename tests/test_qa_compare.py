from __future__ import annotations

from pathlib import Path

from iccraw.cli import main as cli_main
from iccraw.core.models import read_json, write_json
from iccraw.qa_compare import compare_qa_reports


def test_compare_qa_reports_ranks_and_deltas(tmp_path: Path):
    first = tmp_path / "session_a" / "qa_session_report.json"
    second = tmp_path / "session_b" / "qa_session_report.json"
    write_json(first, _qa_report(status="validated", mean=2.0, max_de=4.0, failed_warning="training_low_signal"))
    write_json(second, _qa_report(status="rejected", mean=5.5, max_de=12.0, failed_error="validation_max_delta_e2000"))

    comparison = compare_qa_reports([first, second])

    assert comparison["report_count"] == 2
    assert comparison["status_counts"] == {"validated": 1, "rejected": 1}
    assert comparison["best_validation_mean_delta_e2000"]["label"] == "session_a/qa_session_report"
    assert comparison["worst_validation_mean_delta_e2000"]["label"] == "session_b/qa_session_report"
    assert comparison["deltas_vs_baseline"][0]["status_changed"] is True
    assert comparison["deltas_vs_baseline"][0]["validation_mean_delta_e2000_delta"] == 3.5
    assert comparison["deltas_vs_baseline"][0]["new_failed_checks"] == ["validation_max_delta_e2000"]
    assert comparison["deltas_vs_baseline"][0]["resolved_failed_checks"] == ["training_low_signal"]


def test_compare_qa_reports_cli_writes_output(tmp_path: Path):
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    out = tmp_path / "comparison.json"
    write_json(first, _qa_report(status="validated", mean=1.0, max_de=2.0))
    write_json(second, _qa_report(status="validated", mean=1.5, max_de=2.5))

    rc = cli_main(["compare-qa-reports", str(first), str(second), "--out", str(out)])

    assert rc == 0
    payload = read_json(out)
    assert payload["report_count"] == 2
    assert payload["deltas_vs_baseline"][0]["validation_max_delta_e2000_delta"] == 0.5


def _qa_report(
    *,
    status: str,
    mean: float,
    max_de: float,
    failed_warning: str | None = None,
    failed_error: str | None = None,
) -> dict:
    checks = [
        {
            "id": "validation_mean_delta_e2000",
            "severity": "error",
            "passed": True,
        }
    ]
    if failed_warning:
        checks.append({"id": failed_warning, "severity": "warning", "passed": False})
    if failed_error:
        checks.append({"id": failed_error, "severity": "error", "passed": False})

    return {
        "status": status,
        "training_captures": ["train.dng"],
        "validation_captures": ["validation.dng"],
        "training_error_summary": {
            "mean_delta_e2000": mean * 0.75,
            "max_delta_e2000": max_de * 0.75,
        },
        "validation_error_summary": {
            "mean_delta_e2000": mean,
            "p95_delta_e2000": max_de * 0.9,
            "max_delta_e2000": max_de,
        },
        "validation_worst_patches": [
            {"patch_id": "P01", "delta_e2000": max_de},
        ],
        "training_patch_outliers": [],
        "validation_patch_outliers": [
            {"patch_id": "P01", "delta_e2000": max_de},
        ],
        "validation_capture_quality": {
            "capture_count": 1,
            "min_brightest_neutral_luma": 0.45,
            "min_median_luma": 0.12,
            "max_neutral_density_spread_ev": 0.1,
            "max_neutral_illumination_gradient_ev": 0.05,
        },
        "checks": checks,
    }
