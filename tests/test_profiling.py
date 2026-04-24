from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from iccraw.core.models import PatchSample, Recipe, SampleSet, write_json
from iccraw.profile.builder import build_profile, validate_profile
import iccraw.profile.builder as profiling


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


@pytest.mark.skipif(shutil.which("xicclu") is None, reason="requiere xicclu/ArgyllCMS")
def test_validate_profile_uses_real_icc_not_sidecar_matrix(tmp_path: Path):
    profile = tmp_path / "srgb.icc"
    profile.write_bytes(
        profiling.build_matrix_shaper_icc(
            description="synthetic validation profile",
            matrix_camera_to_xyz=np.eye(3),
            gamma=1.0,
        )
    )
    write_json(
        profile.with_suffix(".profile.json"),
        {
            "matrix_camera_to_xyz": [
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
            ],
        },
    )

    rgb = [0.25, 0.4, 0.6]
    reference_lab = _lookup_lab_with_xicclu(profile, rgb)
    samples = SampleSet(
        chart_name="synthetic",
        chart_version="1",
        illuminant="D50",
        strategy="direct",
        samples=[
            PatchSample(
                patch_id="P01",
                measured_rgb=rgb,
                reference_rgb=None,
                reference_lab=reference_lab,
                excluded_pixel_ratio=0.0,
                saturated_pixel_ratio=0.0,
            )
        ],
        missing_reference_patches=[],
    )

    result = validate_profile(samples, profile)

    assert result.error_summary.max_delta_e76 < 1e-5
    assert result.error_summary.max_delta_e2000 < 1e-5


def test_validate_profile_requires_real_icc_even_if_sidecar_exists(tmp_path: Path):
    profile = tmp_path / "missing.icc"
    write_json(profile.with_suffix(".profile.json"), {"matrix_camera_to_xyz": np.eye(3).tolist()})
    samples = SampleSet(
        chart_name="synthetic",
        chart_version="1",
        illuminant="D50",
        strategy="direct",
        samples=[
            PatchSample(
                patch_id="P01",
                measured_rgb=[0.2, 0.3, 0.4],
                reference_rgb=None,
                reference_lab=[50.0, 0.0, 0.0],
                excluded_pixel_ratio=0.0,
                saturated_pixel_ratio=0.0,
            )
        ],
        missing_reference_patches=[],
    )

    with pytest.raises(FileNotFoundError, match="No existe perfil ICC"):
        validate_profile(samples, profile)


def _lookup_lab_with_xicclu(profile: Path, rgb: list[float]) -> list[float]:
    proc = subprocess.run(
        ["xicclu", "-v0", "-ff", "-ir", "-pl", str(profile)],
        input=" ".join(str(v) for v in rgb) + "\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return [float(v) for v in proc.stdout.split()[:3]]
