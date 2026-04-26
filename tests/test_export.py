from pathlib import Path
import shutil

import numpy as np
import pytest
import tifffile

from iccraw.core.models import Recipe
from iccraw.core.external import external_tool_path
from iccraw.core.utils import read_image
from iccraw.profile.export import _argyll_reference_profile, batch_develop, color_management_mode, write_profiled_tiff
from iccraw.provenance.c2pa import C2PASignConfig
from iccraw.provenance.nexoraw_proof import NexoRawProofConfig, generate_ed25519_identity, verify_nexoraw_proof


class FakeC2PAClient:
    def sign_file(
        self,
        source_path: Path,
        dest_path: Path,
        manifest: dict,
        *,
        cert_path: Path,
        key_path: Path,
        alg: str,
        timestamp_url: str | None = None,
        source_ingredient_path: Path | None = None,
    ) -> dict:
        dest_path.write_bytes(source_path.read_bytes() + b"\nFAKE-C2PA")
        return {
            "active_manifest": "nexoraw:test",
            "manifests": {"nexoraw:test": manifest},
            "validation_status": [],
        }

    def read_manifest_store(self, asset_path: Path) -> dict:
        return {"validation_status": []}


def _fake_c2pa_config(tmp_path: Path) -> C2PASignConfig:
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_bytes(b"cert")
    key.write_bytes(b"key")
    return C2PASignConfig(cert_path=cert, key_path=key, client=FakeC2PAClient())


def _proof_config(tmp_path: Path) -> NexoRawProofConfig:
    private_key = tmp_path / "proof-private.pem"
    public_key = tmp_path / "proof-public.pem"
    generate_ed25519_identity(private_key_path=private_key, public_key_path=public_key)
    return NexoRawProofConfig(
        private_key_path=private_key,
        public_key_path=public_key,
        signer_name="Unit Test",
    )


def test_color_management_mode_assigns_camera_profile_by_default():
    recipe = Recipe(output_space="scene_linear_camera_rgb", output_linear=True)
    assert color_management_mode(recipe) == "camera_rgb_with_input_icc"


def test_color_management_mode_requires_non_linear_srgb_output():
    recipe = Recipe(output_space="srgb", output_linear=True)
    with pytest.raises(RuntimeError, match="output_space=srgb requiere output_linear=false"):
        color_management_mode(recipe)


def test_write_profiled_tiff_assigns_input_profile_without_conversion(tmp_path: Path):
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")
    out = tmp_path / "camera_rgb.tiff"
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)

    mode = write_profiled_tiff(
        out,
        image,
        recipe=Recipe(output_space="camera_rgb", output_linear=True),
        profile_path=profile,
    )

    assert mode == "camera_rgb_with_input_icc"
    with tifffile.TiffFile(out) as tif:
        tags = tif.pages[0].tags
        assert 34675 in tags
        assert bytes(tags[34675].value) == b"camera-profile-placeholder"


def test_batch_develop_keeps_linear_audit_separate_from_final_outputs(tmp_path: Path):
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    raws.mkdir()
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)
    tifffile.imwrite(str(raws / "capture_01.tiff"), (image * 65535).astype(np.uint16), photometric="rgb", metadata=None)

    manifest = batch_develop(
        raws_dir=raws,
        recipe=Recipe(output_space="camera_rgb", output_linear=True),
        profile_path=profile,
        out_dir=out_dir,
        c2pa_config=_fake_c2pa_config(tmp_path),
        proof_config=_proof_config(tmp_path),
    )

    assert (out_dir / "capture_01.tiff").exists()
    assert (out_dir / "capture_01.tiff.nexoraw.proof.json").exists()
    assert not (out_dir / "capture_01.linear.tiff").exists()
    assert (out_dir / "_linear_audit" / "capture_01.scene_linear.tiff").exists()
    assert manifest.entries[0].linear_audit_tiff == str(out_dir / "_linear_audit" / "capture_01.scene_linear.tiff")


def test_batch_develop_versions_existing_final_and_audit_outputs(tmp_path: Path):
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    audit_dir = out_dir / "_linear_audit"
    raws.mkdir()
    out_dir.mkdir()
    audit_dir.mkdir()
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)
    tifffile.imwrite(str(raws / "capture_01.tiff"), (image * 65535).astype(np.uint16), photometric="rgb", metadata=None)

    previous_final = out_dir / "capture_01.tiff"
    previous_audit = audit_dir / "capture_01.scene_linear.tiff"
    previous_final.write_bytes(b"previous-final")
    previous_audit.write_bytes(b"previous-audit")

    manifest = batch_develop(
        raws_dir=raws,
        recipe=Recipe(output_space="camera_rgb", output_linear=True),
        profile_path=profile,
        out_dir=out_dir,
        c2pa_config=_fake_c2pa_config(tmp_path),
        proof_config=_proof_config(tmp_path),
    )

    entry = manifest.entries[0]
    assert previous_final.read_bytes() == b"previous-final"
    assert previous_audit.read_bytes() == b"previous-audit"
    assert entry.output_tiff == str(out_dir / "capture_01_v002.tiff")
    assert entry.linear_audit_tiff == str(audit_dir / "capture_01_v002.scene_linear.tiff")
    assert Path(entry.output_tiff).exists()
    assert Path(entry.linear_audit_tiff or "").exists()


def test_batch_develop_writes_true_linear_audit_before_output_adjustments(tmp_path: Path):
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    raws.mkdir()
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")

    image = np.zeros((6, 8, 3), dtype=np.uint16)
    image[..., 0] = 7000
    image[..., 1] = 14000
    image[..., 2] = 21000
    source = raws / "capture_01.tiff"
    tifffile.imwrite(str(source), image, photometric="rgb", metadata=None)

    recipe = Recipe(
        output_space="camera_rgb",
        output_linear=False,
        exposure_compensation=1.0,
        tone_curve="srgb",
    )
    manifest = batch_develop(
        raws_dir=raws,
        recipe=recipe,
        profile_path=profile,
        out_dir=out_dir,
        c2pa_config=_fake_c2pa_config(tmp_path),
        proof_config=_proof_config(tmp_path),
    )

    source_linear = read_image(source)
    audit_linear = read_image(Path(manifest.entries[0].linear_audit_tiff or ""))
    rendered = read_image(out_dir / "capture_01.tiff")

    assert np.allclose(audit_linear, source_linear, atol=1 / 65535)
    assert not np.allclose(rendered, audit_linear, atol=1e-3)


def test_batch_develop_can_sign_with_nexoraw_proof_without_c2pa(tmp_path: Path):
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    raws.mkdir()
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)
    tifffile.imwrite(str(raws / "capture_01.tiff"), (image * 65535).astype(np.uint16), photometric="rgb", metadata=None)
    proof_config = _proof_config(tmp_path)

    manifest = batch_develop(
        raws_dir=raws,
        recipe=Recipe(output_space="camera_rgb", output_linear=True),
        profile_path=profile,
        out_dir=out_dir,
        proof_config=proof_config,
    )

    entry = manifest.entries[0]
    proof_path = Path(entry.proof_path or "")
    assert proof_path.exists()
    assert entry.c2pa_embedded is False
    verified = verify_nexoraw_proof(
        proof_path,
        output_tiff=Path(entry.output_tiff),
        source_raw=Path(entry.source_raw),
        public_key_path=proof_config.public_key_path,
    )
    assert verified["status"] == "ok"


@pytest.mark.skipif(external_tool_path("cctiff") is None, reason="requiere cctiff/ArgyllCMS")
def test_write_profiled_tiff_converts_to_srgb_with_cmm(tmp_path: Path):
    profile = tmp_path / "source_srgb.icc"
    shutil.copy2(_argyll_reference_profile("sRGB.icm"), profile)
    out = tmp_path / "converted_srgb.tiff"
    image = np.zeros((10, 12, 3), dtype=np.float32)
    image[..., 0] = 0.2
    image[..., 1] = 0.3
    image[..., 2] = 0.4

    mode = write_profiled_tiff(
        out,
        image,
        recipe=Recipe(output_space="srgb", output_linear=False),
        profile_path=profile,
    )

    assert mode == "converted_srgb"
    arr = tifffile.imread(out)
    assert arr.dtype == np.uint16
    assert arr.shape == image.shape
    with tifffile.TiffFile(out) as tif:
        assert 34675 in tif.pages[0].tags


def test_argyll_reference_profile_searches_debian_share_path(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "usr" / "bin"
    ref_dir = tmp_path / "usr" / "share" / "color" / "argyll" / "ref"
    bin_dir.mkdir(parents=True)
    ref_dir.mkdir(parents=True)
    tool = bin_dir / "cctiff"
    profile = ref_dir / "sRGB.icm"
    tool.write_text("", encoding="utf-8")
    profile.write_bytes(b"profile")

    import iccraw.profile.export as export_module

    monkeypatch.setattr(export_module, "external_tool_path", lambda command: str(tool) if command == "cctiff" else None)

    assert export_module._argyll_reference_profile("sRGB.icm") == profile
