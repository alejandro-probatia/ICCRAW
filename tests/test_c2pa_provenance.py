from pathlib import Path
import json

import numpy as np
import pytest
import tifffile

from iccraw.core.models import RawMetadata, Recipe
from iccraw.core.utils import sha256_file
from iccraw.profile.export import batch_develop, write_signed_profiled_tiff
from iccraw.provenance.c2pa import (
    RAW_LINK_ASSERTION_LABEL,
    RENDER_SETTINGS_SCHEMA,
    C2PASigningError,
    C2PASignConfig,
    build_c2pa_manifest,
    build_raw_link_assertion,
    build_render_settings,
    c2pa_config_from_environment,
    ensure_local_c2pa_identity,
    local_c2pa_config,
    sign_tiff_with_c2pa,
    verify_c2pa_raw_link,
)
from iccraw.provenance.nexoraw_proof import NexoRawProofConfig, generate_ed25519_identity


class FakeC2PAClient:
    def __init__(self, manifest_store: dict | None = None) -> None:
        self.calls: list[dict] = []
        self.manifest_store = manifest_store

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
        self.calls.append(
            {
                "source_path": source_path,
                "dest_path": dest_path,
                "manifest": manifest,
                "cert_path": cert_path,
                "key_path": key_path,
                "alg": alg,
                "timestamp_url": timestamp_url,
                "source_ingredient_path": source_ingredient_path,
            }
        )
        dest_path.write_bytes(source_path.read_bytes() + b"\nFAKE-C2PA")
        self.manifest_store = {
            "active_manifest": "nexoraw:1",
            "manifests": {"nexoraw:1": manifest},
            "validation_status": [],
        }
        return self.manifest_store

    def read_manifest_store(self, asset_path: Path) -> dict:
        assert self.manifest_store is not None
        return self.manifest_store


class FailingC2PAClient:
    def sign_file(self, *args, **kwargs) -> dict:
        raise RuntimeError("sign failed")

    def read_manifest_store(self, asset_path: Path) -> dict:
        return {}


def _metadata(path: Path) -> RawMetadata:
    return RawMetadata(
        source_file=str(path),
        input_sha256=sha256_file(path),
        camera_model="Test Camera",
        cfa_pattern="bayer_rggb",
        available_white_balance="camera_metadata",
        wb_multipliers=[1.0, 1.0, 1.0, 1.0],
        black_level=0,
        white_level=65535,
        color_matrix_hint=None,
        iso=100,
        exposure_time_seconds=0.01,
        lens_model="Test Lens",
        capture_datetime="2026:04:25 12:00:00",
        dimensions=[12, 10],
        intermediate_working_space="scene_linear_camera_rgb",
    )


def _proof_config(tmp_path: Path) -> NexoRawProofConfig:
    private_key = tmp_path / "proof-private.pem"
    public_key = tmp_path / "proof-public.pem"
    generate_ed25519_identity(private_key_path=private_key, public_key_path=public_key)
    return NexoRawProofConfig(private_key_path=private_key, public_key_path=public_key)


def test_raw_link_assertion_uses_raw_sha_as_probative_identifier(tmp_path: Path):
    raw = tmp_path / "capture.NEF"
    profile = tmp_path / "camera.icc"
    raw.write_bytes(b"exact raw bytes")
    profile.write_bytes(b"profile bytes")

    recipe = Recipe(demosaic_algorithm="amaze", output_space="camera_rgb")
    settings = build_render_settings(
        recipe=recipe,
        profile_path=profile,
        color_management_mode="camera_rgb_with_input_icc",
        detail_adjustments={"denoise_luminance": 0.2, "sharpen_amount": 0.3},
        render_adjustments={"brightness_ev": 0.5, "tone_curve_preset": "custom"},
        context={"entrypoint": "unit-test"},
    )
    assertion = build_raw_link_assertion(
        source_raw=raw,
        recipe=recipe,
        profile_path=profile,
        color_management_mode="camera_rgb_with_input_icc",
        session_id="session-1",
        raw_metadata=_metadata(raw),
        render_settings=settings,
    )

    assert assertion["schema"] == RAW_LINK_ASSERTION_LABEL
    assert assertion["raw_identity"]["sha256"] == sha256_file(raw)
    assert assertion["raw_identity"]["path_auxiliary_role"] == "non_probative_locator"
    assert assertion["nexoraw"]["icc_profile_sha256"] == sha256_file(profile)
    assert assertion["nexoraw"]["demosaicing_algorithm"] == "amaze"
    assert assertion["nexoraw"]["render_settings_sha256"] == settings["settings_sha256"]
    summary = assertion["nexoraw"]["render_settings_summary"]
    assert summary["settings_sha256"] == settings["settings_sha256"]
    assert summary["detail_adjustments"]["sharpen_amount"] == 0.3
    assert summary["render_adjustments"]["brightness_ev"] == 0.5
    assert summary["color_management"]["mode"] == "camera_rgb_with_input_icc"
    assert summary["complete_render_settings_embedded"] is True
    assert assertion["render_settings"]["schema"] == RENDER_SETTINGS_SCHEMA
    assert assertion["render_settings"]["recipe_parameters"]["demosaic_algorithm"] == "amaze"
    assert assertion["render_settings"]["detail_adjustments"]["denoise_luminance"] == 0.2
    assert assertion["render_settings"]["render_adjustments"]["brightness_ev"] == 0.5
    assert assertion["render_settings"]["context"]["entrypoint"] == "unit-test"
    assert assertion["render_settings"]["reproducibility"]["complete_settings_embedded"] is True
    pipeline = assertion["render_settings"]["color_management"]["raw_color_pipeline"]
    assert pipeline["raw_engine"] == "LibRaw/rawpy"
    assert pipeline["camera_to_xyz"] == "deferred_to_embedded_session_input_icc"
    assert pipeline["export_transform"] == "embed_session_input_icc_without_output_conversion"
    assert "output_sha256" not in str(assertion)


def test_c2pa_manifest_contains_actions_and_custom_raw_link(tmp_path: Path):
    raw = tmp_path / "capture.NEF"
    raw.write_bytes(b"raw")
    assertion = build_raw_link_assertion(
        source_raw=raw,
        recipe=Recipe(),
        profile_path=None,
        color_management_mode="no_profile",
        raw_metadata=_metadata(raw),
    )

    manifest = build_c2pa_manifest(
        output_tiff=tmp_path / "rendered.tiff",
        raw_link_assertion=assertion,
    )

    labels = [item["label"] for item in manifest["assertions"]]
    assert "c2pa.actions.v2" in labels
    assert RAW_LINK_ASSERTION_LABEL in labels
    action_names = manifest["assertions"][0]["data"]["actions"]
    assert action_names[0]["action"] == "c2pa.created"
    assert action_names[1]["action"] == "org.probatia.iccraw.rendered"


def test_sign_tiff_with_c2pa_replaces_output_and_hashes_after_signing(tmp_path: Path):
    raw = tmp_path / "capture.NEF"
    tiff = tmp_path / "rendered.tiff"
    profile = tmp_path / "camera.icc"
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    raw.write_bytes(b"raw bytes")
    tiff.write_bytes(b"tiff bytes")
    profile.write_bytes(b"profile")
    cert.write_bytes(b"cert")
    key.write_bytes(b"key")
    client = FakeC2PAClient()

    result = sign_tiff_with_c2pa(
        tiff,
        source_raw=raw,
        recipe=Recipe(output_space="camera_rgb"),
        profile_path=profile,
        color_management_mode="camera_rgb_with_input_icc",
        config=C2PASignConfig(cert_path=cert, key_path=key, client=client),
        render_settings={"settings_sha256": "render-hash", "render_adjustments": {"contrast": 0.2}},
    )

    assert tiff.read_bytes().endswith(b"FAKE-C2PA")
    assert result.output_sha256_after_signing == sha256_file(tiff)
    assert client.calls[0]["source_ingredient_path"] is None
    raw_link = json.loads(client.calls[0]["manifest"]["assertions"][1]["data"])
    assert raw_link["nexoraw"]["render_settings_sha256"] == "render-hash"
    assert raw_link["nexoraw"]["render_settings_summary"]["render_adjustments"]["contrast"] == 0.2
    assert raw_link["render_settings"]["render_adjustments"]["contrast"] == 0.2
    assert "output_sha256" not in str(client.calls[0]["manifest"])


def test_verify_c2pa_raw_link_checks_raw_and_external_manifest(tmp_path: Path):
    raw = tmp_path / "capture.NEF"
    tiff = tmp_path / "rendered.tiff"
    raw.write_bytes(b"raw bytes")
    tiff.write_bytes(b"signed tiff bytes")
    assertion = build_raw_link_assertion(
        source_raw=raw,
        recipe=Recipe(),
        profile_path=None,
        color_management_mode="no_profile",
        raw_metadata=_metadata(raw),
    )
    manifest_store = {
        "active_manifest": "nexoraw:1",
        "manifests": {
            "nexoraw:1": {
                "assertions": [
                    {"label": "org.probatia.iccraw.raw-link", "data": assertion},
                ],
            }
        },
        "validation_status": [],
    }
    external_manifest = tmp_path / "batch_manifest.json"
    external_manifest.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "source_sha256": sha256_file(raw),
                        "output_tiff": str(tiff),
                        "output_sha256": sha256_file(tiff),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = verify_c2pa_raw_link(
        signed_tiff=tiff,
        source_raw=raw,
        external_manifest_path=external_manifest,
        client=FakeC2PAClient(manifest_store),
    )

    assert result["status"] == "ok"
    assert result["raw_matches_c2pa_assertion"] is True
    assert result["render_settings_hash"]["ok"] is True
    assert result["external_manifest"]["ok"] is True


def test_verify_c2pa_accepts_local_untrusted_signer_as_technical_warning(tmp_path: Path):
    raw = tmp_path / "capture.NEF"
    tiff = tmp_path / "rendered.tiff"
    raw.write_bytes(b"raw bytes")
    tiff.write_bytes(b"signed tiff bytes")
    assertion = build_raw_link_assertion(
        source_raw=raw,
        recipe=Recipe(),
        profile_path=None,
        color_management_mode="no_profile",
        raw_metadata=_metadata(raw),
    )
    manifest_store = {
        "active_manifest": "nexoraw:1",
        "manifests": {
            "nexoraw:1": {
                "assertions": [{"label": RAW_LINK_ASSERTION_LABEL, "data": assertion}],
            }
        },
        "validation_status": [{"code": "signingCredential.untrusted"}],
    }
    external_manifest = tmp_path / "batch_manifest.json"
    external_manifest.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "source_sha256": sha256_file(raw),
                        "output_tiff": str(tiff),
                        "output_sha256": sha256_file(tiff),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = verify_c2pa_raw_link(
        signed_tiff=tiff,
        source_raw=raw,
        external_manifest_path=external_manifest,
        client=FakeC2PAClient(manifest_store),
    )

    assert result["status"] == "ok"
    assert result["c2pa_signature_valid"] is True
    assert result["c2pa_trust_status"]["untrusted_signing_credential_only"] is True


def test_local_c2pa_config_generates_self_issued_identity(tmp_path: Path):
    identity = ensure_local_c2pa_identity(base_dir=tmp_path / "c2pa", signer_name="Lab")
    config = local_c2pa_config(base_dir=tmp_path / "c2pa", signer_name="Lab")

    assert Path(identity["private_key"]).exists()
    assert Path(identity["cert_chain"]).exists()
    assert Path(identity["root_cert"]).exists()
    assert config.local_identity is True
    assert config.fail_on_error is False
    assert config.cert_path == Path(identity["cert_chain"])


def test_batch_develop_hashes_signed_tiff_when_c2pa_enabled(tmp_path: Path):
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    raws.mkdir()
    profile = tmp_path / "camera.icc"
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    profile.write_bytes(b"camera-profile-placeholder")
    cert.write_bytes(b"cert")
    key.write_bytes(b"key")
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)
    tifffile.imwrite(str(raws / "capture_01.tiff"), (image * 65535).astype(np.uint16), photometric="rgb", metadata=None)

    manifest = batch_develop(
        raws_dir=raws,
        recipe=Recipe(output_space="camera_rgb", output_linear=True),
        profile_path=profile,
        out_dir=out_dir,
        c2pa_config=C2PASignConfig(cert_path=cert, key_path=key, client=FakeC2PAClient()),
        proof_config=_proof_config(tmp_path),
    )

    signed = out_dir / "capture_01.tiff"
    assert signed.read_bytes().endswith(b"FAKE-C2PA")
    assert manifest.entries[0].output_sha256 == sha256_file(signed)
    assert Path(manifest.entries[0].proof_path or "").exists()


def test_c2pa_environment_config_still_reports_missing_credentials(tmp_path: Path, monkeypatch):
    for name in (
        "NEXORAW_C2PA_CERT",
        "NEXORAW_C2PA_KEY",
        "ICCRAW_C2PA_CERT",
        "ICCRAW_C2PA_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(C2PASigningError, match="credenciales C2PA"):
        c2pa_config_from_environment()


def test_signed_tiff_write_does_not_leave_unsigned_final_on_c2pa_failure(tmp_path: Path):
    raw = tmp_path / "capture.NEF"
    out = tmp_path / "rendered.tiff"
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    raw.write_bytes(b"raw bytes")
    cert.write_bytes(b"cert")
    key.write_bytes(b"key")
    image = np.full((4, 5, 3), 0.25, dtype=np.float32)

    with pytest.raises(Exception, match="sign failed"):
        write_signed_profiled_tiff(
            out,
            image,
            source_raw=raw,
            recipe=Recipe(output_space="camera_rgb", output_linear=True),
            profile_path=None,
            c2pa_config=C2PASignConfig(cert_path=cert, key_path=key, client=FailingC2PAClient()),
            proof_config=_proof_config(tmp_path),
        )

    assert not out.exists()
