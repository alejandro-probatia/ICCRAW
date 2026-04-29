from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Protocol

from ..core.models import Recipe, RawMetadata
from ..core.utils import sha256_file
from ..raw.metadata import raw_info
from ..version import __version__


RAW_LINK_ASSERTION_LABEL = "org.probatia.iccraw.raw-link.v1"
RENDER_SETTINGS_SCHEMA = "org.probatia.nexoraw.render-settings.v1"
NEXORAW_RENDER_ACTION = "org.probatia.iccraw.rendered"
TIFF_MIME = "image/tiff"
DEFAULT_TIMESTAMP_URL = "http://timestamp.digicert.com"

PROPRIETARY_RAW_EXTENSIONS = {
    ".cr2",
    ".cr3",
    ".nef",
    ".arw",
    ".raf",
    ".rw2",
    ".orf",
    ".pef",
}

RAW_MIME_BY_EXTENSION = {
    ".dng": "image/x-adobe-dng",
    ".cr2": "image/x-canon-cr2",
    ".cr3": "image/x-canon-cr3",
    ".nef": "image/x-nikon-nef",
    ".arw": "image/x-sony-arw",
    ".raf": "image/x-fuji-raf",
    ".rw2": "image/x-panasonic-rw2",
    ".orf": "image/x-olympus-orf",
    ".pef": "image/x-pentax-pef",
    ".tif": TIFF_MIME,
    ".tiff": TIFF_MIME,
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class C2PAError(RuntimeError):
    """Base class for C2PA integration failures."""


class C2PANotAvailableError(C2PAError):
    """Raised when optional C2PA support is not installed."""


class C2PASigningError(C2PAError):
    """Raised when signing fails."""


class C2PAVerificationError(C2PAError):
    """Raised when C2PA verification cannot be executed."""


class C2PAClient(Protocol):
    def sign_file(
        self,
        source_path: Path,
        dest_path: Path,
        manifest: dict[str, Any],
        *,
        cert_path: Path,
        key_path: Path,
        alg: str,
        timestamp_url: str | None = None,
        source_ingredient_path: Path | None = None,
        key_passphrase: str | None = None,
    ) -> dict[str, Any]:
        ...

    def read_manifest_store(self, asset_path: Path) -> dict[str, Any]:
        ...


@dataclass
class C2PASignConfig:
    cert_path: Path
    key_path: Path
    alg: str = "ps256"
    timestamp_url: str | None = DEFAULT_TIMESTAMP_URL
    signer_name: str = "NexoRAW"
    technical_manifest_path: Path | None = None
    session_id: str | None = None
    key_passphrase: str | None = field(default=None, repr=False)
    client: C2PAClient | None = field(default=None, repr=False)
    local_identity: bool = False
    fail_on_error: bool = True


@dataclass
class C2PASignResult:
    signed_tiff: str
    c2pa_manifest: dict[str, Any]
    embedded_manifest_store: dict[str, Any] | None
    output_sha256_after_signing: str
    raw_link_assertion: dict[str, Any]


def c2pa_config_from_environment(
    *,
    technical_manifest_path: Path | None = None,
    session_id: str | None = None,
) -> C2PASignConfig:
    cert = _env_first("NEXORAW_C2PA_CERT")
    key = _env_first("NEXORAW_C2PA_KEY")
    if not cert or not key:
        raise C2PASigningError(
            "No hay credenciales C2PA configuradas. Configura NEXORAW_C2PA_CERT "
            "y NEXORAW_C2PA_KEY, o pasa --c2pa-cert y --c2pa-key en la CLI, "
            "solo si quieres incrustar la capa C2PA opcional."
        )

    env_manifest = _env_first("NEXORAW_C2PA_TECHNICAL_MANIFEST")
    env_session = _env_first("NEXORAW_SESSION_ID")
    return C2PASignConfig(
        cert_path=Path(cert).expanduser(),
        key_path=Path(key).expanduser(),
        alg=_env_first("NEXORAW_C2PA_ALG") or "ps256",
        timestamp_url=_env_first("NEXORAW_C2PA_TIMESTAMP_URL") or DEFAULT_TIMESTAMP_URL,
        signer_name=_env_first("NEXORAW_C2PA_SIGNER_NAME") or "NexoRAW",
        technical_manifest_path=technical_manifest_path
        or (Path(env_manifest).expanduser() if env_manifest else None),
        session_id=session_id or env_session,
        key_passphrase=_env_first("NEXORAW_C2PA_KEY_PASSPHRASE"),
    )


def auto_c2pa_config(
    *,
    technical_manifest_path: Path | None = None,
    session_id: str | None = None,
    signer_name: str = "NexoRAW local signer",
    timestamp_url: str | None = DEFAULT_TIMESTAMP_URL,
) -> C2PASignConfig | None:
    try:
        return c2pa_config_from_environment(
            technical_manifest_path=technical_manifest_path,
            session_id=session_id,
        )
    except C2PASigningError:
        pass

    try:
        _import_c2pa()
    except C2PANotAvailableError:
        return None

    return local_c2pa_config(
        technical_manifest_path=technical_manifest_path,
        session_id=session_id,
        signer_name=signer_name,
        timestamp_url=timestamp_url,
    )


def local_c2pa_config(
    *,
    technical_manifest_path: Path | None = None,
    session_id: str | None = None,
    signer_name: str = "NexoRAW local signer",
    timestamp_url: str | None = DEFAULT_TIMESTAMP_URL,
    base_dir: Path | None = None,
) -> C2PASignConfig:
    identity = ensure_local_c2pa_identity(signer_name=signer_name, base_dir=base_dir)
    return C2PASignConfig(
        cert_path=Path(identity["cert_chain"]),
        key_path=Path(identity["private_key"]),
        alg="ps256",
        timestamp_url=timestamp_url,
        signer_name=signer_name,
        technical_manifest_path=technical_manifest_path,
        session_id=session_id,
        local_identity=True,
        fail_on_error=False,
    )


def ensure_local_c2pa_identity(
    *,
    signer_name: str = "NexoRAW local signer",
    overwrite: bool = False,
    base_dir: Path | None = None,
) -> dict[str, str]:
    base = Path(base_dir) if base_dir is not None else _default_c2pa_identity_dir()
    private_key = base / "nexoraw-c2pa-private-key.pem"
    cert_chain = base / "nexoraw-c2pa-cert-chain.pem"
    root_cert = base / "nexoraw-c2pa-local-root.pem"
    if not overwrite and private_key.exists() and cert_chain.exists() and root_cert.exists():
        return {
            "private_key": str(private_key),
            "cert_chain": str(cert_chain),
            "root_cert": str(root_cert),
            "identity_kind": "local_self_issued_c2pa",
        }

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NexoRAW local trust"),
            x509.NameAttribute(NameOID.COMMON_NAME, "NexoRAW local C2PA root"),
        ]
    )
    leaf_name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NexoRAW local signer"),
            x509.NameAttribute(NameOID.COMMON_NAME, signer_name[:64] or "NexoRAW local signer"),
        ]
    )
    root = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), critical=False)
        .sign(root_key, hashes.SHA256())
    )
    leaf = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(root_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
        .sign(root_key, hashes.SHA256())
    )

    base.mkdir(parents=True, exist_ok=True)
    private_key.write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    cert_chain.write_bytes(leaf.public_bytes(serialization.Encoding.PEM) + root.public_bytes(serialization.Encoding.PEM))
    root_cert.write_bytes(root.public_bytes(serialization.Encoding.PEM))
    _restrict_private_key_permissions(private_key)
    return {
        "private_key": str(private_key),
        "cert_chain": str(cert_chain),
        "root_cert": str(root_cert),
        "identity_kind": "local_self_issued_c2pa",
    }


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _default_c2pa_identity_dir() -> Path:
    base = _env_first("NEXORAW_HOME")
    if base:
        return Path(base).expanduser() / "c2pa"
    return Path.home().expanduser() / ".nexoraw" / "c2pa"


def _restrict_private_key_permissions(path: Path) -> None:
    try:
        path.chmod(0o600)
    except Exception:
        pass


def recipe_sha256(recipe: Recipe) -> str:
    payload = json.dumps(asdict(recipe), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_sha256(payload: Any) -> str:
    data = json.dumps(_normalize_json(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


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


def build_render_settings(
    *,
    recipe: Recipe,
    profile_path: Path | None,
    color_management_mode: str,
    detail_adjustments: dict[str, Any] | None = None,
    render_adjustments: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_role = _icc_profile_role(color_management_mode, profile_path)
    payload: dict[str, Any] = {
        "schema": RENDER_SETTINGS_SCHEMA,
        "schema_version": 1,
        "recipe_parameters": _normalize_json(asdict(recipe)),
        "detail_adjustments": _normalize_json(detail_adjustments or {}),
        "render_adjustments": _normalize_json(render_adjustments or {}),
        "color_management": {
            "mode": color_management_mode,
            "icc_profile_role": profile_role,
            "icc_profile_path_auxiliary": str(profile_path) if profile_path is not None else None,
            "icc_profile_sha256": sha256_file(profile_path) if profile_path is not None and profile_path.exists() else None,
            "output_space": recipe.output_space,
            "working_space": recipe.working_space,
            "output_linear": recipe.output_linear,
            "raw_color_pipeline": _raw_color_pipeline_trace(recipe, color_management_mode),
        },
        "reproducibility": {
            "complete_settings_embedded": True,
            "settings_sha256_role": "integrity_check_over_recipe_detail_render_and_color_management",
            "experimental_replay_inputs": [
                "recipe_parameters",
                "detail_adjustments",
                "render_adjustments",
                "color_management",
            ],
        },
        "context": _normalize_json(context or {}),
    }
    payload["settings_sha256"] = _json_sha256(payload)
    return payload


def _icc_profile_role(color_management_mode: str, profile_path: Path | None) -> str | None:
    if profile_path is None:
        return None
    mode = str(color_management_mode or "")
    if mode == "camera_rgb_with_input_icc":
        return "session_input_icc"
    if mode.startswith("standard_") or mode.startswith("assigned_") or mode.startswith("converted_"):
        return "generic_output_icc"
    return "icc_profile"


def _raw_color_pipeline_trace(recipe: Recipe, color_management_mode: str) -> dict[str, Any]:
    mode = str(color_management_mode or "")
    output_space = str(recipe.output_space or "").strip()
    trace: dict[str, Any] = {
        "raw_engine": "LibRaw/rawpy",
        "metadata_read": [
            "camera_model",
            "cfa_pattern",
            "black_level",
            "white_level",
            "as_shot_white_balance",
            "camera_matrix_if_available",
            "embedded_profile_if_available",
        ],
        "libraw_linear_steps": [
            "raw_unpack",
            "black_subtraction",
            "white_normalization",
            "white_balance_in_camera_space",
            "demosaicing",
        ],
        "nexoraw_linear_editing": {
            "working_space": recipe.working_space,
            "domain": "float32_linear",
        },
        "display_transform": "preview_sRGB_to_monitor_ICC_with_LittleCMS_ImageCms",
        "export_transform": None,
    }
    if mode == "camera_rgb_with_input_icc":
        trace["camera_to_xyz"] = "deferred_to_embedded_session_input_icc"
        trace["export_transform"] = "embed_session_input_icc_without_output_conversion"
    elif mode.startswith("standard_"):
        trace["camera_to_xyz"] = "LibRaw_camera_profile_to_standard_rgb"
        trace["export_transform"] = f"LibRaw_to_{output_space}_then_embed_standard_output_icc"
    elif mode.startswith("converted_"):
        trace["camera_to_xyz"] = "session_input_icc_used_by_ArgyllCMS_cctiff"
        trace["export_transform"] = f"ArgyllCMS_cctiff_to_{output_space}_and_embed_output_icc"
    elif mode == "no_profile":
        trace["camera_to_xyz"] = "not_applied"
        trace["export_transform"] = "write_pixels_without_icc"
    else:
        trace["camera_to_xyz"] = "mode_specific"
        trace["export_transform"] = mode
    return trace


def estimate_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in RAW_MIME_BY_EXTENSION:
        return RAW_MIME_BY_EXTENSION[suffix]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def build_raw_link_assertion(
    *,
    source_raw: Path,
    recipe: Recipe,
    profile_path: Path | None,
    color_management_mode: str,
    technical_manifest_path: Path | None = None,
    session_id: str | None = None,
    generated_at_utc: datetime | None = None,
    raw_metadata: RawMetadata | None = None,
    render_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_raw = Path(source_raw)
    generated = generated_at_utc or datetime.now(timezone.utc)
    generated_iso = generated.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    metadata = raw_metadata if raw_metadata is not None else raw_info(source_raw)
    technical_manifest_sha = (
        sha256_file(technical_manifest_path)
        if technical_manifest_path is not None and technical_manifest_path.exists()
        else None
    )
    settings = render_settings or build_render_settings(
        recipe=recipe,
        profile_path=profile_path,
        color_management_mode=color_management_mode,
    )

    return {
        "schema": RAW_LINK_ASSERTION_LABEL,
        "schema_version": 1,
        "raw_identity": {
            "sha256": sha256_file(source_raw),
            "size_bytes": source_raw.stat().st_size,
            "basename": source_raw.name,
            "extension": source_raw.suffix.lower(),
            "mime_type": estimate_mime_type(source_raw),
            "path_auxiliary": str(source_raw),
            "path_auxiliary_role": "non_probative_locator",
        },
        "camera_metadata": _camera_metadata_payload(metadata),
        "nexoraw": {
            "software_name": "NexoRAW",
            "software_version": __version__,
            "recipe_sha256": recipe_sha256(recipe),
            "icc_profile_sha256": sha256_file(profile_path) if profile_path is not None and profile_path.exists() else None,
            "icc_profile_role": _icc_profile_role(color_management_mode, profile_path),
            "raw_backend": recipe.raw_developer,
            "demosaicing_algorithm": recipe.demosaic_algorithm,
            "output_space": recipe.output_space,
            "color_management_mode": color_management_mode,
            "render_settings_sha256": settings.get("settings_sha256") if isinstance(settings, dict) else None,
            "render_settings_summary": _render_settings_summary(settings),
            "technical_manifest_sha256": technical_manifest_sha,
            "technical_manifest_path_auxiliary": str(technical_manifest_path) if technical_manifest_sha else None,
            "session_id": session_id,
            "generated_at_utc": generated_iso,
        },
        "render_settings": settings,
        "forensic_notes": {
            "raw_sha256_is_probative_identifier": True,
            "raw_path_is_probative_identifier": False,
            "signed_output_hash_is_external_only": True,
            "raw_original_modified": False,
        },
    }


def _render_settings_summary(settings: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(settings, dict):
        return {}
    recipe = settings.get("recipe_parameters") if isinstance(settings.get("recipe_parameters"), dict) else {}
    return {
        "settings_sha256": settings.get("settings_sha256"),
        "recipe_parameters": {
            "raw_developer": recipe.get("raw_developer"),
            "demosaic_algorithm": recipe.get("demosaic_algorithm"),
            "black_level_mode": recipe.get("black_level_mode"),
            "white_balance_mode": recipe.get("white_balance_mode"),
            "wb_multipliers": recipe.get("wb_multipliers"),
            "exposure_compensation": recipe.get("exposure_compensation"),
            "tone_curve": recipe.get("tone_curve"),
            "working_space": recipe.get("working_space"),
            "output_space": recipe.get("output_space"),
            "output_linear": recipe.get("output_linear"),
            "profile_engine": recipe.get("profile_engine"),
            "argyll_colprof_args": recipe.get("argyll_colprof_args"),
        },
        "detail_adjustments": _normalize_json(settings.get("detail_adjustments") or {}),
        "render_adjustments": _normalize_json(settings.get("render_adjustments") or {}),
        "color_management": _normalize_json(settings.get("color_management") or {}),
        "context": _normalize_json(settings.get("context") or {}),
        "complete_render_settings_embedded": True,
    }


def build_c2pa_manifest(
    *,
    output_tiff: Path,
    raw_link_assertion: dict[str, Any],
    signer_name: str = "NexoRAW",
) -> dict[str, Any]:
    raw_sha = raw_link_assertion["raw_identity"]["sha256"]
    software_agent = {"name": signer_name, "version": __version__}
    return {
        "claim_generator": f"NexoRAW/{__version__}",
        "title": Path(output_tiff).name,
        "format": TIFF_MIME,
        "assertions": [
            {
                "label": "c2pa.actions.v2",
                "created": True,
                "data": {
                    "actions": [
                        {
                            "action": "c2pa.created",
                            "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/digitalCapture",
                            "softwareAgent": software_agent,
                            "parameters": {
                                "description": "Rendered TIFF generated by NexoRAW from a camera RAW source.",
                                "raw_sha256": raw_sha,
                                "raw_link_assertion": RAW_LINK_ASSERTION_LABEL,
                            },
                        },
                        {
                            "action": NEXORAW_RENDER_ACTION,
                            "softwareAgent": software_agent,
                            "parameters": {
                                "raw_sha256": raw_sha,
                                "recipe_sha256": raw_link_assertion["nexoraw"]["recipe_sha256"],
                                "icc_profile_sha256": raw_link_assertion["nexoraw"]["icc_profile_sha256"],
                                "demosaicing_algorithm": raw_link_assertion["nexoraw"]["demosaicing_algorithm"],
                                "output_space": raw_link_assertion["nexoraw"]["output_space"],
                                "color_management_mode": raw_link_assertion["nexoraw"]["color_management_mode"],
                                "render_settings_sha256": raw_link_assertion["nexoraw"].get("render_settings_sha256"),
                            },
                        },
                    ]
                },
            },
            {
                "label": RAW_LINK_ASSERTION_LABEL,
                "created": True,
                "kind": "Json",
                "data": json.dumps(_normalize_json(raw_link_assertion), sort_keys=True, separators=(",", ":")),
            },
        ],
    }


def sign_tiff_with_c2pa(
    output_tiff: Path,
    *,
    source_raw: Path,
    recipe: Recipe,
    profile_path: Path | None,
    color_management_mode: str,
    config: C2PASignConfig,
    render_settings: dict[str, Any] | None = None,
) -> C2PASignResult:
    output_tiff = Path(output_tiff)
    source_raw = Path(source_raw)
    if not output_tiff.exists():
        raise FileNotFoundError(f"No existe TIFF final para firmar: {output_tiff}")
    if not source_raw.exists():
        raise FileNotFoundError(f"No existe RAW fuente para vincular C2PA: {source_raw}")
    if not config.cert_path.exists():
        raise FileNotFoundError(f"No existe certificado C2PA")
    if not config.key_path.exists():
        raise FileNotFoundError("No existe clave privada C2PA")

    raw_link = build_raw_link_assertion(
        source_raw=source_raw,
        recipe=recipe,
        profile_path=profile_path,
        color_management_mode=color_management_mode,
        technical_manifest_path=config.technical_manifest_path,
        session_id=config.session_id,
        render_settings=render_settings,
    )
    manifest = build_c2pa_manifest(
        output_tiff=output_tiff,
        raw_link_assertion=raw_link,
        signer_name=config.signer_name,
    )
    client = config.client or C2PAPythonClient()

    signed_store: dict[str, Any] | None = None
    with tempfile.TemporaryDirectory(prefix="nexoraw_c2pa_") as tmp:
        signed_tmp = Path(tmp) / output_tiff.name
        ingredient_path = _c2pa_source_ingredient_path(source_raw)
        sign_kwargs: dict[str, Any] = {
            "cert_path": config.cert_path,
            "key_path": config.key_path,
            "alg": config.alg,
            "timestamp_url": config.timestamp_url,
            "source_ingredient_path": ingredient_path,
        }
        if config.key_passphrase:
            sign_kwargs["key_passphrase"] = config.key_passphrase
        signed_store = client.sign_file(output_tiff, signed_tmp, manifest, **sign_kwargs)
        if not signed_tmp.exists():
            raise C2PASigningError("La firma C2PA no genero TIFF firmado")
        shutil.move(str(signed_tmp), str(output_tiff))

    return C2PASignResult(
        signed_tiff=str(output_tiff),
        c2pa_manifest=manifest,
        embedded_manifest_store=signed_store,
        output_sha256_after_signing=sha256_file(output_tiff),
        raw_link_assertion=raw_link,
    )


def verify_c2pa_raw_link(
    *,
    signed_tiff: Path,
    source_raw: Path,
    external_manifest_path: Path | None = None,
    client: C2PAClient | None = None,
) -> dict[str, Any]:
    signed_tiff = Path(signed_tiff)
    source_raw = Path(source_raw)
    if not signed_tiff.exists():
        raise FileNotFoundError(f"No existe TIFF firmado: {signed_tiff}")
    if not source_raw.exists():
        raise FileNotFoundError(f"No existe RAW fuente: {source_raw}")

    c2pa_client = client or C2PAPythonClient()
    try:
        manifest_store = c2pa_client.read_manifest_store(signed_tiff)
    except Exception as exc:
        raise C2PAVerificationError(f"No se pudo leer/validar manifiesto C2PA: {exc}") from exc

    raw_link = extract_raw_link_assertion(manifest_store)
    declared_raw_sha = _nested_get(raw_link, ("raw_identity", "sha256"))
    actual_raw_sha = sha256_file(source_raw)
    raw_matches = declared_raw_sha == actual_raw_sha
    render_settings_check = _verify_render_settings_hash(raw_link)

    external = _verify_external_manifest(
        signed_tiff=signed_tiff,
        source_raw_sha=actual_raw_sha,
        external_manifest_path=external_manifest_path,
    )
    validation_status = manifest_store.get("validation_status") or []
    active_manifest = _active_manifest(manifest_store)
    if not validation_status and isinstance(active_manifest, dict):
        validation_status = active_manifest.get("validation_status") or []
    validation_eval = _evaluate_c2pa_validation_status(validation_status)
    c2pa_valid = bool(validation_eval["technical_signature_ok"])

    status = "ok" if raw_matches and external["ok"] and c2pa_valid and render_settings_check["ok"] else "failed"
    return {
        "status": status,
        "c2pa_manifest_present": True,
        "c2pa_validation_status": validation_status,
        "c2pa_signature_valid": c2pa_valid,
        "c2pa_trust_status": validation_eval,
        "raw_sha256_declared": declared_raw_sha,
        "raw_sha256_actual": actual_raw_sha,
        "raw_matches_c2pa_assertion": raw_matches,
        "render_settings_hash": render_settings_check,
        "external_manifest": external,
        "raw_link_assertion": raw_link,
    }


def extract_raw_link_assertion(manifest_store: dict[str, Any]) -> dict[str, Any]:
    active = _active_manifest(manifest_store)
    assertions = active.get("assertions") if isinstance(active, dict) else None
    if not isinstance(assertions, list):
        raise C2PAVerificationError("El manifiesto C2PA no contiene aserciones legibles")
    for assertion in assertions:
        if not isinstance(assertion, dict):
            continue
        data = assertion.get("data")
        label = str(assertion.get("label") or "")
        parsed_data: Any = data
        if isinstance(data, str):
            try:
                parsed_data = json.loads(data)
            except json.JSONDecodeError:
                parsed_data = data
        if label in {RAW_LINK_ASSERTION_LABEL, "org.probatia.iccraw.raw-link"} or (
            isinstance(parsed_data, dict) and parsed_data.get("schema") == RAW_LINK_ASSERTION_LABEL
        ):
            if isinstance(data, dict):
                return data
            if isinstance(parsed_data, dict):
                return parsed_data
            raise C2PAVerificationError(f"Asercion {RAW_LINK_ASSERTION_LABEL} sin datos JSON")
    raise C2PAVerificationError(f"No se encontro asercion {RAW_LINK_ASSERTION_LABEL}")


class C2PAPythonClient:
    def __init__(self, *, verify_settings: dict[str, Any] | None = None) -> None:
        self.verify_settings = verify_settings or {}

    def sign_file(
        self,
        source_path: Path,
        dest_path: Path,
        manifest: dict[str, Any],
        *,
        cert_path: Path,
        key_path: Path,
        alg: str,
        timestamp_url: str | None = None,
        source_ingredient_path: Path | None = None,
        key_passphrase: str | None = None,
    ) -> dict[str, Any]:
        c2pa = _import_c2pa()
        manifest_json = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
        key_data = b""
        try:
            with open(cert_path, "rb") as cert_file:
                cert_data = cert_file.read()
            key_data = _read_private_key_for_c2pa(key_path, key_passphrase=key_passphrase)
            if not timestamp_url:
                raise C2PASigningError("c2pa-python requiere una URL TSA RFC 3161 para firmar")
            signer_info = c2pa.C2paSignerInfo(
                alg=_signing_alg(c2pa, alg),
                sign_cert=cert_data,
                private_key=key_data,
                ta_url=timestamp_url.encode("utf-8"),
            )
            with c2pa.Context() as ctx:
                with c2pa.Signer.from_info(signer_info) as signer:
                    with c2pa.Builder(manifest_json, ctx) as builder:
                        if source_ingredient_path is not None:
                            ingredient_json = json.dumps(
                                {
                                    "title": source_ingredient_path.name,
                                    "format": estimate_mime_type(source_ingredient_path),
                                    "relationship": "parentOf",
                                },
                                ensure_ascii=False,
                            )
                            with open(source_ingredient_path, "rb") as ingredient_file:
                                builder.add_ingredient(
                                    ingredient_json,
                                    estimate_mime_type(source_ingredient_path),
                                    ingredient_file,
                                )
                        builder.sign_file(str(source_path), str(dest_path), signer)
            return self.read_manifest_store(dest_path)
        except C2PAError:
            raise
        except Exception as exc:
            raise C2PASigningError(f"Firma C2PA fallida para TIFF final {Path(source_path).name}: {exc}") from exc
        finally:
            # Avoid keeping private-key material alive longer than needed.
            key_data = b""

    def read_manifest_store(self, asset_path: Path) -> dict[str, Any]:
        c2pa = _import_c2pa()
        try:
            if self.verify_settings:
                settings = c2pa.Settings.from_dict(self.verify_settings)
                with c2pa.Context(settings) as ctx:
                    with c2pa.Reader(str(asset_path), context=ctx) as reader:
                        return json.loads(reader.json())
            with c2pa.Reader(str(asset_path)) as reader:
                return json.loads(reader.json())
        except C2PAError:
            raise
        except Exception as exc:
            raise C2PAVerificationError(f"Lectura C2PA fallida para {Path(asset_path).name}: {exc}") from exc


def _import_c2pa():
    try:
        import c2pa  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - exercised without optional extra.
        raise C2PANotAvailableError(
            "Soporte C2PA no instalado. Instala el extra requerido para exportar TIFF final: pip install -e .[c2pa]"
        ) from exc
    return c2pa


def _signing_alg(c2pa, alg: str):
    normalized = alg.strip().upper().replace("-", "")
    try:
        return getattr(c2pa.C2paSigningAlg, normalized)
    except AttributeError as exc:
        raise C2PASigningError(f"Algoritmo C2PA no soportado: {alg}") from exc


def _read_private_key_for_c2pa(key_path: Path, *, key_passphrase: str | None = None) -> bytes:
    key_data = key_path.read_bytes()
    if b"-----BEGIN ENCRYPTED PRIVATE KEY-----" in key_data and key_passphrase:
        from cryptography.hazmat.primitives import serialization

        key = serialization.load_pem_private_key(key_data, password=key_passphrase.encode("utf-8"))
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    if b"-----BEGIN PRIVATE KEY-----" in key_data or b"-----BEGIN ENCRYPTED PRIVATE KEY-----" in key_data:
        return key_data
    try:
        from cryptography.hazmat.primitives import serialization

        password = key_passphrase.encode("utf-8") if key_passphrase else None
        key = serialization.load_pem_private_key(key_data, password=password)
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    except Exception:
        return key_data


def _c2pa_source_ingredient_path(source_raw: Path) -> Path | None:
    suffix = source_raw.suffix.lower()
    if suffix == ".dng":
        return source_raw
    if suffix in PROPRIETARY_RAW_EXTENSIONS:
        return None
    if estimate_mime_type(source_raw) in {TIFF_MIME, "image/png", "image/jpeg"}:
        return source_raw
    return None


def _camera_metadata_payload(metadata: RawMetadata) -> dict[str, Any]:
    return {
        "camera_model": metadata.camera_model,
        "lens_model": metadata.lens_model,
        "iso": metadata.iso,
        "exposure_time_seconds": metadata.exposure_time_seconds,
        "capture_datetime": metadata.capture_datetime,
        "dimensions": metadata.dimensions,
        "cfa_pattern": metadata.cfa_pattern,
        "available_white_balance": metadata.available_white_balance,
        "white_balance_multipliers": metadata.wb_multipliers,
        "black_level": metadata.black_level,
        "black_level_per_channel": metadata.black_level_per_channel,
        "white_level": metadata.white_level,
        "intermediate_working_space": metadata.intermediate_working_space,
        "embedded_profile_description": metadata.embedded_profile_description,
        "embedded_profile_source": metadata.embedded_profile_source,
    }


def _active_manifest(manifest_store: dict[str, Any]) -> dict[str, Any]:
    active_id = manifest_store.get("active_manifest")
    manifests = manifest_store.get("manifests")
    if isinstance(manifests, dict) and isinstance(active_id, str) and active_id in manifests:
        active = manifests[active_id]
        if isinstance(active, dict):
            return active
    if isinstance(manifests, dict):
        for value in manifests.values():
            if isinstance(value, dict):
                return value
    if "assertions" in manifest_store:
        return manifest_store
    raise C2PAVerificationError("No se encontro manifiesto activo C2PA")


def _nested_get(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _verify_render_settings_hash(raw_link: dict[str, Any]) -> dict[str, Any]:
    render_settings = raw_link.get("render_settings") if isinstance(raw_link, dict) else None
    if not isinstance(render_settings, dict):
        return {"ok": False, "reason": "render_settings_missing"}
    declared = render_settings.get("settings_sha256") or _nested_get(raw_link, ("nexoraw", "render_settings_sha256"))
    if not declared:
        return {"ok": False, "reason": "render_settings_sha256_missing"}
    payload = dict(render_settings)
    payload.pop("settings_sha256", None)
    actual = _json_sha256(payload)
    return {
        "ok": declared == actual,
        "declared_sha256": declared,
        "actual_sha256": actual,
    }


def _verify_external_manifest(
    *,
    signed_tiff: Path,
    source_raw_sha: str,
    external_manifest_path: Path | None,
) -> dict[str, Any]:
    if external_manifest_path is None:
        return {"checked": False, "ok": False, "reason": "external_manifest_not_provided"}
    if not external_manifest_path.exists():
        return {"checked": True, "ok": False, "reason": "external_manifest_missing"}
    try:
        payload = json.loads(external_manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"checked": True, "ok": False, "reason": f"external_manifest_unreadable: {exc}"}
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return {"checked": True, "ok": False, "reason": "external_manifest_without_entries"}

    signed_resolved = signed_tiff.resolve()
    selected: dict[str, Any] | None = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        out = entry.get("output_tiff")
        if isinstance(out, str):
            try:
                if Path(out).resolve() == signed_resolved:
                    selected = entry
                    break
            except Exception:
                pass
        if entry.get("source_sha256") == source_raw_sha:
            selected = entry
    if selected is None:
        return {"checked": True, "ok": False, "reason": "external_manifest_entry_not_found"}

    actual_output_sha = sha256_file(signed_tiff)
    declared_output_sha = selected.get("output_sha256")
    return {
        "checked": True,
        "ok": declared_output_sha == actual_output_sha,
        "declared_output_sha256": declared_output_sha,
        "actual_output_sha256": actual_output_sha,
        "source_sha256": selected.get("source_sha256"),
    }


def _evaluate_c2pa_validation_status(status: Any) -> dict[str, Any]:
    if not status:
        return {
            "technical_signature_ok": True,
            "trust_model": "c2pa_trusted_or_no_warnings",
            "untrusted_signing_credential_only": False,
            "fatal_codes": [],
        }
    items = status if isinstance(status, list) else [status]
    codes = [str(item.get("code") if isinstance(item, dict) else item) for item in items]
    fatal = [code for code in codes if code != "signingCredential.untrusted"]
    local_only = bool(codes) and not fatal
    return {
        "technical_signature_ok": local_only,
        "trust_model": "local_self_issued_or_untrusted_c2pa_signer" if local_only else "c2pa_validation_failed",
        "untrusted_signing_credential_only": local_only,
        "fatal_codes": fatal,
    }
