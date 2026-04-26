from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ..core.models import Recipe
from ..core.utils import sha256_file
from ..raw.metadata import raw_info
from ..version import __version__
from .c2pa import estimate_mime_type, recipe_sha256


PROOF_SCHEMA = "org.probatia.nexoraw.proof.v1"
PROOF_ALGORITHM = "Ed25519"
PROOF_CANONICALIZATION = "json-rfc8785-like-sort-keys-v1"


class NexoRawProofError(RuntimeError):
    """Raised when NexoRAW Proof cannot be created or verified."""


@dataclass
class NexoRawProofConfig:
    private_key_path: Path
    public_key_path: Path | None = None
    key_passphrase: str | None = field(default=None, repr=False)
    signer_name: str = "NexoRAW local signer"
    signer_id: str | None = None


@dataclass
class NexoRawProofResult:
    proof_path: str
    proof_sha256: str
    output_tiff_sha256: str
    raw_sha256: str
    signer_public_key_sha256: str


def proof_config_from_environment() -> NexoRawProofConfig:
    key = _env_first("NEXORAW_PROOF_KEY", "ICCRAW_PROOF_KEY")
    if not key:
        raise NexoRawProofError(
            "NexoRAW Proof es obligatorio para exportar TIFF final. Configura NEXORAW_PROOF_KEY "
            "o genera una identidad local con 'nexoraw proof-keygen'."
        )
    public = _env_first("NEXORAW_PROOF_PUBLIC_KEY", "ICCRAW_PROOF_PUBLIC_KEY")
    return NexoRawProofConfig(
        private_key_path=Path(key).expanduser(),
        public_key_path=Path(public).expanduser() if public else None,
        key_passphrase=_env_first("NEXORAW_PROOF_KEY_PASSPHRASE", "ICCRAW_PROOF_KEY_PASSPHRASE"),
        signer_name=_env_first("NEXORAW_PROOF_SIGNER_NAME", "ICCRAW_PROOF_SIGNER_NAME") or "NexoRAW local signer",
        signer_id=_env_first("NEXORAW_PROOF_SIGNER_ID", "ICCRAW_PROOF_SIGNER_ID"),
    )


def default_proof_sidecar_path(output_tiff: Path) -> Path:
    return Path(output_tiff).with_suffix(Path(output_tiff).suffix + ".nexoraw.proof.json")


def generate_ed25519_identity(
    *,
    private_key_path: Path,
    public_key_path: Path | None = None,
    passphrase: str | None = None,
    overwrite: bool = False,
) -> dict[str, str]:
    private_key_path = Path(private_key_path)
    public_key_path = Path(public_key_path) if public_key_path is not None else private_key_path.with_suffix(".pub.pem")
    if not overwrite:
        for path in (private_key_path, public_key_path):
            if path.exists():
                raise FileExistsError(f"Ya existe la clave: {path}")

    key = Ed25519PrivateKey.generate()
    encryption = (
        serialization.BestAvailableEncryption(passphrase.encode("utf-8"))
        if passphrase
        else serialization.NoEncryption()
    )
    private_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        encryption,
    )
    public_bytes = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.parent.mkdir(parents=True, exist_ok=True)
    private_key_path.write_bytes(private_bytes)
    public_key_path.write_bytes(public_bytes)
    _restrict_private_key_permissions(private_key_path)

    public_der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "private_key": str(private_key_path),
        "public_key": str(public_key_path),
        "public_key_sha256": hashlib.sha256(public_der).hexdigest(),
        "algorithm": PROOF_ALGORITHM,
    }


def sign_nexoraw_proof(
    *,
    output_tiff: Path,
    source_raw: Path,
    recipe: Recipe,
    profile_path: Path | None,
    color_management_mode: str,
    render_settings: dict[str, Any],
    config: NexoRawProofConfig,
    proof_path: Path | None = None,
    c2pa_embedded: bool = False,
    c2pa_status: dict[str, Any] | None = None,
) -> NexoRawProofResult:
    output_tiff = Path(output_tiff)
    source_raw = Path(source_raw)
    proof_path = proof_path or default_proof_sidecar_path(output_tiff)
    if not output_tiff.exists():
        raise FileNotFoundError(f"No existe TIFF final para firmar con NexoRAW Proof: {output_tiff}")
    if not source_raw.exists():
        raise FileNotFoundError(f"No existe RAW fuente para NexoRAW Proof: {source_raw}")

    private_key = _load_private_key(config.private_key_path, config.key_passphrase)
    public_key = _load_public_key(config.public_key_path) if config.public_key_path else private_key.public_key()
    public_pem = public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    public_der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_fingerprint = hashlib.sha256(public_der).hexdigest()

    payload = build_nexoraw_proof_payload(
        output_tiff=output_tiff,
        source_raw=source_raw,
        recipe=recipe,
        profile_path=profile_path,
        color_management_mode=color_management_mode,
        render_settings=render_settings,
        signer_name=config.signer_name,
        signer_id=config.signer_id,
        public_key_pem=public_pem,
        public_key_sha256=public_fingerprint,
        c2pa_embedded=c2pa_embedded,
        c2pa_status=c2pa_status,
    )
    signed_bytes = _canonical_json(payload)
    signature = private_key.sign(signed_bytes)
    payload["signature"] = {
        "algorithm": PROOF_ALGORITHM,
        "canonicalization": PROOF_CANONICALIZATION,
        "signed_payload_sha256": hashlib.sha256(signed_bytes).hexdigest(),
        "value": base64.b64encode(signature).decode("ascii"),
    }

    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return NexoRawProofResult(
        proof_path=str(proof_path),
        proof_sha256=sha256_file(proof_path),
        output_tiff_sha256=payload["subject"]["output_tiff"]["sha256"],
        raw_sha256=payload["subject"]["source_raw"]["sha256"],
        signer_public_key_sha256=public_fingerprint,
    )


def build_nexoraw_proof_payload(
    *,
    output_tiff: Path,
    source_raw: Path,
    recipe: Recipe,
    profile_path: Path | None,
    color_management_mode: str,
    render_settings: dict[str, Any],
    signer_name: str,
    signer_id: str | None,
    public_key_pem: str,
    public_key_sha256: str,
    c2pa_embedded: bool,
    c2pa_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    raw_metadata = raw_info(source_raw)
    return {
        "schema": PROOF_SCHEMA,
        "schema_version": 1,
        "proof_type": "nexoraw-ed25519-sidecar-v1",
        "generated_at_utc": generated,
        "subject": {
            "source_raw": {
                "sha256": sha256_file(source_raw),
                "size_bytes": source_raw.stat().st_size,
                "basename": source_raw.name,
                "extension": source_raw.suffix.lower(),
                "mime_type": estimate_mime_type(source_raw),
                "path_auxiliary": str(source_raw),
                "path_auxiliary_role": "non_probative_locator",
            },
            "output_tiff": {
                "sha256": sha256_file(output_tiff),
                "size_bytes": output_tiff.stat().st_size,
                "basename": output_tiff.name,
                "extension": output_tiff.suffix.lower(),
                "mime_type": "image/tiff",
                "path_auxiliary": str(output_tiff),
                "path_auxiliary_role": "non_probative_locator",
            },
        },
        "camera_metadata": {
            "camera_model": raw_metadata.camera_model,
            "lens_model": raw_metadata.lens_model,
            "iso": raw_metadata.iso,
            "exposure_time_seconds": raw_metadata.exposure_time_seconds,
            "capture_datetime": raw_metadata.capture_datetime,
            "dimensions": raw_metadata.dimensions,
            "cfa_pattern": raw_metadata.cfa_pattern,
        },
        "process": {
            "software_name": "NexoRAW",
            "software_version": __version__,
            "raw_backend": recipe.raw_developer,
            "demosaicing_algorithm": recipe.demosaic_algorithm,
            "recipe_sha256": recipe_sha256(recipe),
            "recipe_parameters": _normalize_json(asdict(recipe)),
            "icc_profile_path_auxiliary": str(profile_path) if profile_path else None,
            "icc_profile_sha256": sha256_file(profile_path) if profile_path is not None and profile_path.exists() else None,
            "color_management_mode": color_management_mode,
            "render_settings": _normalize_json(render_settings),
            "render_settings_sha256": render_settings.get("settings_sha256") if isinstance(render_settings, dict) else None,
        },
        "c2pa": {
            "embedded": bool(c2pa_embedded),
            "status": _normalize_json(c2pa_status or {}),
            "is_required_for_nexoraw_proof": False,
        },
        "forensic_notes": {
            "raw_original_modified": False,
            "raw_sha256_is_probative_identifier": True,
            "raw_path_is_probative_identifier": False,
            "output_tiff_sha256_signed_in_sidecar": True,
            "trust_model": "La confianza depende de la custodia/publicacion de la clave publica del firmante.",
        },
        "signer": {
            "name": signer_name,
            "signer_id": signer_id,
            "public_key_algorithm": PROOF_ALGORITHM,
            "public_key_sha256": public_key_sha256,
            "public_key_pem": public_key_pem,
        },
    }


def verify_nexoraw_proof(
    proof_path: Path,
    *,
    output_tiff: Path | None = None,
    source_raw: Path | None = None,
    public_key_path: Path | None = None,
) -> dict[str, Any]:
    proof_path = Path(proof_path)
    payload = json.loads(proof_path.read_text(encoding="utf-8"))
    signature_block = payload.get("signature")
    if not isinstance(signature_block, dict):
        raise NexoRawProofError("El proof no contiene bloque de firma")
    signature = base64.b64decode(str(signature_block.get("value") or ""))
    unsigned = dict(payload)
    unsigned.pop("signature", None)
    signed_bytes = _canonical_json(unsigned)
    signed_hash = hashlib.sha256(signed_bytes).hexdigest()
    declared_signed_hash = signature_block.get("signed_payload_sha256")

    public_key = _load_public_key(public_key_path) if public_key_path else _public_key_from_payload(payload)
    try:
        public_key.verify(signature, signed_bytes)
        signature_valid = True
        signature_error = None
    except InvalidSignature:
        signature_valid = False
        signature_error = "invalid_signature"

    public_der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key_sha = hashlib.sha256(public_der).hexdigest()
    declared_public_key_sha = _nested_get(payload, ("signer", "public_key_sha256"))

    output_check = _file_hash_check(
        output_tiff,
        _nested_get(payload, ("subject", "output_tiff", "sha256")),
        "output_tiff",
    )
    raw_check = _file_hash_check(
        source_raw,
        _nested_get(payload, ("subject", "source_raw", "sha256")),
        "source_raw",
    )
    render_settings_check = _render_settings_hash_check(payload)
    ok = (
        signature_valid
        and declared_signed_hash == signed_hash
        and declared_public_key_sha == public_key_sha
        and output_check["ok"]
        and raw_check["ok"]
        and render_settings_check["ok"]
    )
    return {
        "status": "ok" if ok else "failed",
        "proof_path": str(proof_path),
        "signature_valid": signature_valid,
        "signature_error": signature_error,
        "signed_payload_sha256_declared": declared_signed_hash,
        "signed_payload_sha256_actual": signed_hash,
        "public_key_sha256_declared": declared_public_key_sha,
        "public_key_sha256_actual": public_key_sha,
        "output_tiff": output_check,
        "source_raw": raw_check,
        "render_settings_hash": render_settings_check,
        "proof": payload,
    }


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        _normalize_json(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _normalize_json(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize_json(val) for key, val in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return value.item()
    except Exception:
        return str(value)


def _load_private_key(path: Path, passphrase: str | None) -> Ed25519PrivateKey:
    if not Path(path).exists():
        raise FileNotFoundError(f"No existe clave privada NexoRAW Proof: {path}")
    password = passphrase.encode("utf-8") if passphrase else None
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=password)
    if not isinstance(key, Ed25519PrivateKey):
        raise NexoRawProofError("NexoRAW Proof requiere clave privada Ed25519")
    return key


def _load_public_key(path: Path | None) -> Ed25519PublicKey:
    if path is None:
        raise NexoRawProofError("No se ha indicado clave publica NexoRAW Proof")
    key = serialization.load_pem_public_key(Path(path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise NexoRawProofError("NexoRAW Proof requiere clave publica Ed25519")
    return key


def _public_key_from_payload(payload: dict[str, Any]) -> Ed25519PublicKey:
    public_key_pem = _nested_get(payload, ("signer", "public_key_pem"))
    if not public_key_pem:
        raise NexoRawProofError("El proof no contiene clave publica embebida")
    key = serialization.load_pem_public_key(str(public_key_pem).encode("ascii"))
    if not isinstance(key, Ed25519PublicKey):
        raise NexoRawProofError("La clave publica embebida no es Ed25519")
    return key


def _file_hash_check(path: Path | None, declared_sha: str | None, label: str) -> dict[str, Any]:
    if path is None:
        return {"ok": True, "checked": False, "declared_sha256": declared_sha}
    path = Path(path)
    if not path.exists():
        return {"ok": False, "checked": True, "reason": f"{label}_missing", "path": str(path)}
    actual = sha256_file(path)
    return {
        "ok": declared_sha == actual,
        "checked": True,
        "path": str(path),
        "declared_sha256": declared_sha,
        "actual_sha256": actual,
    }


def _render_settings_hash_check(payload: dict[str, Any]) -> dict[str, Any]:
    render_settings = _nested_get(payload, ("process", "render_settings"))
    declared = _nested_get(payload, ("process", "render_settings_sha256"))
    if not isinstance(render_settings, dict):
        return {"ok": False, "reason": "render_settings_missing"}
    if not declared:
        return {"ok": False, "reason": "render_settings_sha256_missing"}
    candidate = dict(render_settings)
    candidate.pop("settings_sha256", None)
    actual = hashlib.sha256(_canonical_json(candidate)).hexdigest()
    return {"ok": declared == actual, "declared_sha256": declared, "actual_sha256": actual}


def _nested_get(payload: Any, keys: tuple[str, ...]) -> Any:
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _restrict_private_key_permissions(path: Path) -> None:
    try:
        path.chmod(0o600)
    except Exception:
        pass
