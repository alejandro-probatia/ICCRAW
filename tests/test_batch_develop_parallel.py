from __future__ import annotations

from pathlib import Path
import shutil

from iccraw.core.models import Recipe
from iccraw.core.utils import sha256_file
from iccraw.profile.export import batch_develop
from iccraw.provenance.nexoraw_proof import NexoRawProofConfig, generate_ed25519_identity


def _proof_config(tmp_path: Path) -> NexoRawProofConfig:
    private_key = tmp_path / "proof-private.pem"
    public_key = tmp_path / "proof-public.pem"
    generate_ed25519_identity(private_key_path=private_key, public_key_path=public_key)
    return NexoRawProofConfig(
        private_key_path=private_key,
        public_key_path=public_key,
        signer_name="Parallel Unit Test",
    )


def test_parallel_process_outputs_match_serial(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    source_dir = repo_root / "testdata" / "batch_images"
    raws = tmp_path / "inputs"
    serial = tmp_path / "serial"
    parallel = tmp_path / "parallel"
    raws.mkdir()
    for source in sorted(source_dir.glob("session_*.tiff")):
        shutil.copy2(source, raws / source.name)

    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")
    recipe = Recipe(output_space="camera_rgb", output_linear=True)
    proof = _proof_config(tmp_path)

    serial_manifest = batch_develop(
        raws_dir=raws,
        recipe=recipe,
        profile_path=profile,
        out_dir=serial,
        workers=1,
        proof_config=proof,
    )
    parallel_manifest = batch_develop(
        raws_dir=raws,
        recipe=recipe,
        profile_path=profile,
        out_dir=parallel,
        workers=2,
        proof_config=proof,
    )

    assert [Path(e.source_raw).name for e in serial_manifest.entries] == [
        Path(e.source_raw).name for e in parallel_manifest.entries
    ]
    for serial_entry, parallel_entry in zip(serial_manifest.entries, parallel_manifest.entries, strict=True):
        assert sha256_file(Path(serial_entry.output_tiff)) == sha256_file(Path(parallel_entry.output_tiff))
        assert sha256_file(Path(serial_entry.linear_audit_tiff or "")) == sha256_file(
            Path(parallel_entry.linear_audit_tiff or "")
        )
