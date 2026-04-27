from pathlib import Path

import numpy as np

from iccraw.core.models import Recipe
from iccraw.core.utils import write_tiff16
from iccraw.provenance.c2pa import build_render_settings
from iccraw.provenance.nexoraw_proof import (
    NexoRawProofConfig,
    generate_ed25519_identity,
    sign_nexoraw_proof,
    verify_nexoraw_proof,
)


def test_nexoraw_proof_signs_and_verifies_raw_tiff_link(tmp_path: Path):
    raw = tmp_path / "capture.NEF"
    tiff = tmp_path / "capture.tiff"
    private_key = tmp_path / "proof-private.pem"
    public_key = tmp_path / "proof-public.pem"
    raw.write_bytes(b"raw bytes")
    write_tiff16(tiff, np.full((4, 5, 3), 0.25, dtype=np.float32))
    identity = generate_ed25519_identity(private_key_path=private_key, public_key_path=public_key)
    recipe = Recipe(demosaic_algorithm="amaze")
    render_settings = build_render_settings(
        recipe=recipe,
        profile_path=None,
        color_management_mode="no_profile",
        render_adjustments={"applied": False},
    )

    result = sign_nexoraw_proof(
        output_tiff=tiff,
        source_raw=raw,
        recipe=recipe,
        profile_path=None,
        color_management_mode="no_profile",
        render_settings=render_settings,
        config=NexoRawProofConfig(
            private_key_path=private_key,
            public_key_path=public_key,
            signer_name="Unit Test",
        ),
    )

    verified = verify_nexoraw_proof(
        Path(result.proof_path),
        output_tiff=tiff,
        source_raw=raw,
        public_key_path=public_key,
    )

    assert verified["status"] == "ok"
    assert result.signer_public_key_sha256 == identity["public_key_sha256"]
    assert verified["proof"]["subject"]["source_raw"]["sha256"] == result.raw_sha256
    assert verified["proof"]["process"]["demosaicing_algorithm"] == "amaze"
    assert verified["proof"]["process"]["render_settings"]["render_adjustments"]["applied"] is False
    assert verified["proof"]["process"]["render_settings"]["reproducibility"]["complete_settings_embedded"] is True


def test_nexoraw_proof_detects_modified_tiff(tmp_path: Path):
    raw = tmp_path / "capture.NEF"
    tiff = tmp_path / "capture.tiff"
    private_key = tmp_path / "proof-private.pem"
    public_key = tmp_path / "proof-public.pem"
    raw.write_bytes(b"raw bytes")
    write_tiff16(tiff, np.full((4, 5, 3), 0.25, dtype=np.float32))
    generate_ed25519_identity(private_key_path=private_key, public_key_path=public_key)

    result = sign_nexoraw_proof(
        output_tiff=tiff,
        source_raw=raw,
        recipe=Recipe(),
        profile_path=None,
        color_management_mode="no_profile",
        render_settings=build_render_settings(recipe=Recipe(), profile_path=None, color_management_mode="no_profile"),
        config=NexoRawProofConfig(private_key_path=private_key, public_key_path=public_key),
    )
    tiff.write_bytes(tiff.read_bytes() + b"tamper")

    verified = verify_nexoraw_proof(Path(result.proof_path), output_tiff=tiff, source_raw=raw)

    assert verified["status"] == "failed"
    assert verified["output_tiff"]["ok"] is False
