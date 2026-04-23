from pathlib import Path
import numpy as np

from icc_entrada.models import PatchSample, Recipe, SampleSet
from icc_entrada.profiling import build_profile
import icc_entrada.profiling as profiling


def test_build_profile_generates_icc_and_sidecar(tmp_path: Path, monkeypatch):
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

    samples = []
    for i in range(1, 25):
        samples.append(
            PatchSample(
                patch_id=f"P{i:02d}",
                measured_rgb=[0.1 + i * 0.01, 0.2 + i * 0.005, 0.3 + i * 0.004],
                reference_rgb=None,
                reference_lab=[30 + i, -5 + i * 0.1, -10 + i * 0.1],
                excluded_pixel_ratio=0.1,
                saturated_pixel_ratio=0.0,
            )
        )

    sample_set = SampleSet(
        chart_name="ColorChecker 24",
        chart_version="2005",
        illuminant="D50",
        strategy="trimmed_mean",
        samples=samples,
        missing_reference_patches=[],
    )

    out_icc = tmp_path / "camera.icc"
    result = build_profile(sample_set, Recipe(), out_icc, camera_model="Cam", lens_model="Lens")

    assert out_icc.exists()
    assert out_icc.stat().st_size > 256
    assert Path(result.output_profile_json).exists()
    assert result.metadata["profile_engine_used"] == "argyll"
