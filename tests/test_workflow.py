from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import tifffile

from iccraw.chart.detection import detect_chart_from_corners
from iccraw.chart.sampling import ReferenceCatalog
from iccraw.core.models import ErrorSummary, PatchError, ValidationResult, read_json
from iccraw.core.recipe import load_recipe
from iccraw.workflow import auto_generate_profile_from_charts, auto_profile_batch
import iccraw.workflow as workflow
import iccraw.profile.builder as profiling


def test_auto_profile_batch_end_to_end(tmp_path: Path, monkeypatch):
    def fake_build_profile_with_argyll(
        out_icc: Path,
        measured_rgb: np.ndarray,
        reference_lab: np.ndarray,
        patch_ids: list[str],
        description: str,
        extra_args: list[str] | None,
    ) -> None:
        icc_bytes = profiling.build_matrix_shaper_icc(
            description=description,
            matrix_camera_to_xyz=np.eye(3),
            gamma=1.0,
        )
        out_icc.write_bytes(icc_bytes)

    monkeypatch.setattr(profiling, "_build_profile_with_argyll", fake_build_profile_with_argyll)

    charts_dir = tmp_path / "charts"
    targets_dir = tmp_path / "targets"
    out_dir = tmp_path / "out"
    work_dir = tmp_path / "work"
    charts_dir.mkdir()
    targets_dir.mkdir()

    img = _synthetic_colorchecker_image()
    tifffile.imwrite(str(charts_dir / "chart_01.tiff"), img, photometric="rgb", metadata=None)
    tifffile.imwrite(str(charts_dir / "chart_02.tiff"), img, photometric="rgb", metadata=None)
    tifffile.imwrite(str(targets_dir / "target_01.tiff"), img, photometric="rgb", metadata=None)
    tifffile.imwrite(str(targets_dir / "target_02.tiff"), img, photometric="rgb", metadata=None)

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    profile_out = tmp_path / "camera.icc"
    profile_report = tmp_path / "profile_report.json"

    result = auto_profile_batch(
        chart_captures_dir=charts_dir,
        target_captures_dir=targets_dir,
        recipe=recipe,
        reference=reference,
        profile_out=profile_out,
        profile_report_out=profile_report,
        batch_out_dir=out_dir,
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.0,
        allow_fallback_detection=True,
    )

    assert profile_out.exists()
    assert profile_report.exists()
    assert (out_dir / "batch_manifest.json").exists()
    assert result["chart_captures_used"] >= 1
    assert len(result["batch_manifest"]["entries"]) == 2


def test_auto_generate_profile_from_charts_only(tmp_path: Path, monkeypatch):
    def fake_build_profile_with_argyll(
        out_icc: Path,
        measured_rgb: np.ndarray,
        reference_lab: np.ndarray,
        patch_ids: list[str],
        description: str,
        extra_args: list[str] | None,
    ) -> None:
        icc_bytes = profiling.build_matrix_shaper_icc(
            description=description,
            matrix_camera_to_xyz=np.eye(3),
            gamma=1.0,
        )
        out_icc.write_bytes(icc_bytes)

    monkeypatch.setattr(profiling, "_build_profile_with_argyll", fake_build_profile_with_argyll)

    charts_dir = tmp_path / "charts"
    work_dir = tmp_path / "work_profile"
    charts_dir.mkdir()

    img = _synthetic_colorchecker_image()
    tifffile.imwrite(str(charts_dir / "chart_01.tiff"), img, photometric="rgb", metadata=None)
    tifffile.imwrite(str(charts_dir / "chart_02.tiff"), img, photometric="rgb", metadata=None)

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    profile_out = tmp_path / "profile_only.icc"
    profile_report = tmp_path / "profile_only_report.json"

    result = auto_generate_profile_from_charts(
        chart_captures_dir=charts_dir,
        recipe=recipe,
        reference=reference,
        profile_out=profile_out,
        profile_report_out=profile_report,
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.0,
        allow_fallback_detection=True,
    )

    assert profile_out.exists()
    assert profile_report.exists()
    assert result["chart_captures_total"] == 2
    assert result["chart_captures_used"] >= 1
    assert "profile" in result
    assert result["profile_status"]["status"] == "draft"
    assert read_json(profile_report)["metadata"]["profile_status"] == "draft"


def test_auto_generate_profile_from_explicit_chart_files(tmp_path: Path, monkeypatch):
    def fake_build_profile_with_argyll(
        out_icc: Path,
        measured_rgb: np.ndarray,
        reference_lab: np.ndarray,
        patch_ids: list[str],
        description: str,
        extra_args: list[str] | None,
    ) -> None:
        icc_bytes = profiling.build_matrix_shaper_icc(
            description=description,
            matrix_camera_to_xyz=np.eye(3),
            gamma=1.0,
        )
        out_icc.write_bytes(icc_bytes)

    monkeypatch.setattr(profiling, "_build_profile_with_argyll", fake_build_profile_with_argyll)

    charts_a = tmp_path / "charts_a"
    charts_b = tmp_path / "charts_b"
    work_dir = tmp_path / "work_explicit"
    charts_a.mkdir()
    charts_b.mkdir()

    img = _synthetic_colorchecker_image()
    chart_01 = charts_a / "chart_01.tiff"
    chart_02 = charts_b / "chart_02.tiff"
    tifffile.imwrite(str(chart_01), img, photometric="rgb", metadata=None)
    tifffile.imwrite(str(chart_02), img, photometric="rgb", metadata=None)

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    profile_out = tmp_path / "profile_from_files.icc"
    profile_report = tmp_path / "profile_from_files_report.json"

    result = auto_generate_profile_from_charts(
        chart_captures_dir=tmp_path / "unused_charts_dir",
        chart_capture_files=[chart_02, chart_01],
        recipe=recipe,
        reference=reference,
        profile_out=profile_out,
        profile_report_out=profile_report,
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.0,
        allow_fallback_detection=True,
    )

    assert profile_out.exists()
    assert profile_report.exists()
    assert result["chart_captures_total"] == 2
    assert result["chart_captures_used"] >= 1


def test_auto_generate_profile_uses_manual_detection(tmp_path: Path, monkeypatch):
    def fake_build_profile_with_argyll(
        out_icc: Path,
        measured_rgb: np.ndarray,
        reference_lab: np.ndarray,
        patch_ids: list[str],
        description: str,
        extra_args: list[str] | None,
    ) -> None:
        icc_bytes = profiling.build_matrix_shaper_icc(
            description=description,
            matrix_camera_to_xyz=np.eye(3),
            gamma=1.0,
        )
        out_icc.write_bytes(icc_bytes)

    monkeypatch.setattr(profiling, "_build_profile_with_argyll", fake_build_profile_with_argyll)

    charts_dir = tmp_path / "charts"
    work_dir = tmp_path / "work_manual"
    charts_dir.mkdir()

    img = _synthetic_colorchecker_image()
    chart = charts_dir / "chart_manual.tiff"
    tifffile.imwrite(str(chart), img, photometric="rgb", metadata=None)
    manual_detection = detect_chart_from_corners(
        chart,
        corners=[(0.0, 0.0), (720.0, 0.0), (720.0, 480.0), (0.0, 480.0)],
        chart_type="colorchecker24",
    )

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    result = auto_generate_profile_from_charts(
        chart_captures_dir=tmp_path / "unused",
        chart_capture_files=[chart],
        manual_detections={chart: manual_detection},
        recipe=recipe,
        reference=reference,
        profile_out=tmp_path / "manual.icc",
        profile_report_out=tmp_path / "manual_report.json",
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.95,
        allow_fallback_detection=False,
    )

    detection_payload = (work_dir / "detections" / "001_chart_manual.json").read_text(encoding="utf-8")
    assert result["chart_captures_used"] == 1
    assert '"detection_mode": "manual"' in detection_payload


def test_auto_generate_profile_writes_holdout_qa_report(tmp_path: Path, monkeypatch):
    def fake_build_profile_with_argyll(
        out_icc: Path,
        measured_rgb: np.ndarray,
        reference_lab: np.ndarray,
        patch_ids: list[str],
        description: str,
        extra_args: list[str] | None,
    ) -> None:
        icc_bytes = profiling.build_matrix_shaper_icc(
            description=description,
            matrix_camera_to_xyz=np.eye(3),
            gamma=1.0,
        )
        out_icc.write_bytes(icc_bytes)

    def fake_validate_profile(samples, profile_path):
        return ValidationResult(
            profile_path=str(profile_path),
            error_summary=ErrorSummary(
                mean_delta_e76=2.0,
                median_delta_e76=2.0,
                p95_delta_e76=3.0,
                max_delta_e76=4.0,
                mean_delta_e2000=1.5,
                median_delta_e2000=1.4,
                p95_delta_e2000=2.1,
                max_delta_e2000=2.8,
            ),
            patch_errors=[
                PatchError(patch_id="P01", delta_e76=1.1, delta_e2000=0.8),
                PatchError(patch_id="P02", delta_e76=3.5, delta_e2000=2.8),
            ],
        )

    monkeypatch.setattr(profiling, "_build_profile_with_argyll", fake_build_profile_with_argyll)
    monkeypatch.setattr(workflow, "validate_profile", fake_validate_profile)

    charts_dir = tmp_path / "charts"
    work_dir = tmp_path / "work_holdout"
    qa_report = tmp_path / "qa_session_report.json"
    charts_dir.mkdir()

    img = _synthetic_colorchecker_image()
    tifffile.imwrite(str(charts_dir / "chart_01.tiff"), img, photometric="rgb", metadata=None)
    tifffile.imwrite(str(charts_dir / "chart_02.tiff"), img, photometric="rgb", metadata=None)

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    profile_out = tmp_path / "holdout.icc"
    profile_report = tmp_path / "holdout_report.json"
    result = auto_generate_profile_from_charts(
        chart_captures_dir=charts_dir,
        recipe=recipe,
        reference=reference,
        profile_out=profile_out,
        profile_report_out=profile_report,
        validation_report_out=qa_report,
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.0,
        allow_fallback_detection=True,
        validation_holdout_count=1,
    )

    assert qa_report.exists()
    assert result["training_captures_total"] == 1
    assert result["chart_captures_used"] == 1
    assert result["validation_captures_total"] == 1
    assert result["validation_captures_used"] == 1
    assert result["profile_status"]["status"] == "validated"
    assert result["validation"]["qa_report"]["status"] == "validated"
    assert result["validation"]["qa_report"]["validation_worst_patches"][0]["patch_id"] == "P02"
    assert read_json(profile_report)["metadata"]["profile_status"] == "validated"
    assert read_json(profile_out.with_suffix(".profile.json"))["profile_status"] == "validated"
    qa = result["validation"]["qa_report"]
    check_ids = {check["id"] for check in qa["checks"]}
    assert "training_low_signal" in check_ids
    assert "validation_low_signal" in check_ids
    assert qa["training_capture_quality"]["capture_count"] == 1
    assert qa["training_capture_quality"]["captures"][0]["brightest_neutral_luma"] > 0.0
    assert qa["training_sample_quality"]["median_patch_luma"] > 0.0
    assert (work_dir / "samples_aggregated_validation.json").exists()


def test_auto_profile_batch_refuses_rejected_session_profile(tmp_path: Path, monkeypatch):
    def fake_build_profile_with_argyll(
        out_icc: Path,
        measured_rgb: np.ndarray,
        reference_lab: np.ndarray,
        patch_ids: list[str],
        description: str,
        extra_args: list[str] | None,
    ) -> None:
        out_icc.write_bytes(
            profiling.build_matrix_shaper_icc(
                description=description,
                matrix_camera_to_xyz=np.eye(3),
                gamma=1.0,
            )
        )

    def fake_validate_profile(samples, profile_path):
        return ValidationResult(
            profile_path=str(profile_path),
            error_summary=ErrorSummary(
                mean_delta_e76=30.0,
                median_delta_e76=30.0,
                p95_delta_e76=30.0,
                max_delta_e76=30.0,
                mean_delta_e2000=25.0,
                median_delta_e2000=25.0,
                p95_delta_e2000=25.0,
                max_delta_e2000=25.0,
            ),
            patch_errors=[PatchError(patch_id="P01", delta_e76=30.0, delta_e2000=25.0)],
        )

    monkeypatch.setattr(profiling, "_build_profile_with_argyll", fake_build_profile_with_argyll)
    monkeypatch.setattr(workflow, "validate_profile", fake_validate_profile)

    charts_dir = tmp_path / "charts"
    targets_dir = tmp_path / "targets"
    out_dir = tmp_path / "out"
    work_dir = tmp_path / "work_rejected"
    charts_dir.mkdir()
    targets_dir.mkdir()

    img = _synthetic_colorchecker_image()
    tifffile.imwrite(str(charts_dir / "chart_01.tiff"), img, photometric="rgb", metadata=None)
    tifffile.imwrite(str(charts_dir / "chart_02.tiff"), img, photometric="rgb", metadata=None)
    tifffile.imwrite(str(targets_dir / "target_01.tiff"), img, photometric="rgb", metadata=None)

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    with pytest.raises(RuntimeError, match="estado rejected"):
        auto_profile_batch(
            chart_captures_dir=charts_dir,
            target_captures_dir=targets_dir,
            recipe=recipe,
            reference=reference,
            profile_out=tmp_path / "rejected.icc",
            profile_report_out=tmp_path / "rejected_report.json",
            batch_out_dir=out_dir,
            work_dir=work_dir,
            chart_type="colorchecker24",
            min_confidence=0.0,
            allow_fallback_detection=True,
            validation_holdout_count=1,
        )

    assert not (out_dir / "batch_manifest.json").exists()


def test_profile_status_resolves_draft_rejected_and_expired():
    generated_at = "2026-04-20T10:00:00+00:00"

    draft = workflow._build_profile_status(
        validation_payload=None,
        qa_report_path=None,
        generated_at=generated_at,
        valid_until=None,
    )
    rejected = workflow._build_profile_status(
        validation_payload={"qa_report": {"status": "rejected"}},
        qa_report_path="/tmp/qa.json",
        generated_at=generated_at,
        valid_until=None,
    )
    expired = workflow._build_profile_status(
        validation_payload={"qa_report": {"status": "validated"}},
        qa_report_path="/tmp/qa.json",
        generated_at=generated_at,
        valid_until="2026-04-21T10:00:00+00:00",
        now="2026-04-22T10:00:00+00:00",
    )

    assert draft["status"] == "draft"
    assert rejected["status"] == "rejected"
    assert expired["status"] == "expired"


def _synthetic_colorchecker_image() -> np.ndarray:
    rows, cols = 4, 6
    cell_h, cell_w = 120, 120
    h, w = rows * cell_h, cols * cell_w
    img = np.zeros((h, w, 3), dtype=np.uint16)

    # Deterministic patch palette with luminance progression.
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            rgb = np.array([
                3000 + idx * 1500,
                5000 + idx * 1200,
                7000 + idx * 900,
            ], dtype=np.uint16)
            y0, y1 = r * cell_h, (r + 1) * cell_h
            x0, x1 = c * cell_w, (c + 1) * cell_w
            img[y0:y1, x0:x1] = rgb

    return img
