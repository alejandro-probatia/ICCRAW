from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import Path
import shutil
import tempfile
from typing import Any, Protocol

from ..core.models import Recipe, RawMetadata
from ..core.utils import sha256_file
from ..raw.metadata import raw_info
from ..version import __version__


RAW_LINK_ASSERTION_LABEL = "org.probatia.iccraw.raw-link.v1"
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
    client: C2PAClient | None = field(default=None, repr=False)


@dataclass
class C2PASignResult:
    signed_tiff: str
    c2pa_manifest: dict[str, Any]
    embedded_manifest_store: dict[str, Any] | None
    output_sha256_after_signing: str
    raw_link_assertion: dict[str, Any]


def recipe_sha256(recipe: Recipe) -> str:
    payload = json.dumps(asdict(recipe), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
            "raw_backend": recipe.raw_developer,
            "demosaicing_algorithm": recipe.demosaic_algorithm,
            "output_space": recipe.output_space,
            "color_management_mode": color_management_mode,
            "technical_manifest_sha256": technical_manifest_sha,
            "technical_manifest_path_auxiliary": str(technical_manifest_path) if technical_manifest_sha else None,
            "session_id": session_id,
            "generated_at_utc": generated_iso,
        },
        "forensic_notes": {
            "raw_sha256_is_probative_identifier": True,
            "raw_path_is_probative_identifier": False,
            "signed_output_hash_is_external_only": True,
            "raw_original_modified": False,
        },
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
                            },
                        },
                    ]
                },
            },
            {
                "label": RAW_LINK_ASSERTION_LABEL,
                "created": True,
                "kind": "Json",
                "data": raw_link_assertion,
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
        signed_store = client.sign_file(
            output_tiff,
            signed_tmp,
            manifest,
            cert_path=config.cert_path,
            key_path=config.key_path,
            alg=config.alg,
            timestamp_url=config.timestamp_url,
            source_ingredient_path=ingredient_path,
        )
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

    external = _verify_external_manifest(
        signed_tiff=signed_tiff,
        source_raw_sha=actual_raw_sha,
        external_manifest_path=external_manifest_path,
    )
    validation_status = manifest_store.get("validation_status") or []
    active_manifest = _active_manifest(manifest_store)
    if not validation_status and isinstance(active_manifest, dict):
        validation_status = active_manifest.get("validation_status") or []
    c2pa_valid = not bool(validation_status)

    status = "ok" if raw_matches and external["ok"] and c2pa_valid else "failed"
    return {
        "status": status,
        "c2pa_manifest_present": True,
        "c2pa_validation_status": validation_status,
        "c2pa_signature_valid": c2pa_valid,
        "raw_sha256_declared": declared_raw_sha,
        "raw_sha256_actual": actual_raw_sha,
        "raw_matches_c2pa_assertion": raw_matches,
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
        if assertion.get("label") == RAW_LINK_ASSERTION_LABEL or (
            isinstance(data, dict) and data.get("schema") == RAW_LINK_ASSERTION_LABEL
        ):
            if isinstance(data, dict):
                return data
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
    ) -> dict[str, Any]:
        c2pa = _import_c2pa()
        manifest_json = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
        key_data = b""
        try:
            with open(cert_path, "rb") as cert_file:
                cert_data = cert_file.read()
            key_data = _read_private_key_for_c2pa(key_path)
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
            "Soporte C2PA no instalado. Instala la dependencia opcional con: pip install -e .[c2pa]"
        ) from exc
    return c2pa


def _signing_alg(c2pa, alg: str):
    normalized = alg.strip().upper().replace("-", "")
    try:
        return getattr(c2pa.C2paSigningAlg, normalized)
    except AttributeError as exc:
        raise C2PASigningError(f"Algoritmo C2PA no soportado: {alg}") from exc


def _read_private_key_for_c2pa(key_path: Path) -> bytes:
    key_data = key_path.read_bytes()
    if b"-----BEGIN PRIVATE KEY-----" in key_data or b"-----BEGIN ENCRYPTED PRIVATE KEY-----" in key_data:
        return key_data
    try:
        from cryptography.hazmat.primitives import serialization

        key = serialization.load_pem_private_key(key_data, password=None)
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
        "white_level": metadata.white_level,
        "intermediate_working_space": metadata.intermediate_working_space,
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
