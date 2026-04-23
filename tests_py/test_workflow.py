from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile

from icc_entrada.recipe import load_recipe
from icc_entrada.sampling import ReferenceCatalog
from icc_entrada.workflow import auto_profile_batch
import icc_entrada.profiling as profiling


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
    )

    assert profile_out.exists()
    assert profile_report.exists()
    assert (out_dir / "batch_manifest.json").exists()
    assert result["chart_captures_used"] >= 1
    assert len(result["batch_manifest"]["entries"]) == 2


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
