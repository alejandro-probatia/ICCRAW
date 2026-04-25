from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from .core.external import external_tool_path
from .provenance.c2pa import C2PAClient, C2PAError, C2PANotAvailableError, C2PAPythonClient


GPS_TAG_HINTS = {
    "gps",
    "latitude",
    "longitude",
    "altitude",
    "geotag",
    "position",
}

EXIF_GROUPS = {
    "exif",
    "exififd",
    "ifd0",
    "ifd1",
    "subifd",
    "composite",
    "makernotes",
}


def inspect_file_metadata(
    path: Path,
    *,
    include_c2pa: bool = True,
    c2pa_client: C2PAClient | None = None,
) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {path}")
    payload = {
        "file": _file_payload(path),
        "exif_gps": read_exif_gps_metadata(path),
    }
    if include_c2pa:
        payload["c2pa"] = read_c2pa_metadata(path, client=c2pa_client)
    else:
        payload["c2pa"] = {"status": "skipped"}
    return payload


def read_exif_gps_metadata(path: Path) -> dict[str, Any]:
    exiftool = external_tool_path("exiftool")
    if exiftool is None:
        return {
            "status": "unavailable",
            "reason": "exiftool no esta disponible",
            "groups": {},
            "exif": {},
            "gps": {},
            "all": {},
        }

    cmd = [exiftool, "-json", "-G", "-a", "-n", str(path)]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "reason": "exiftool agoto el tiempo de lectura",
            "groups": {},
            "exif": {},
            "gps": {},
            "all": {},
        }
    except Exception as exc:
        return {
            "status": "error",
            "reason": str(exc),
            "groups": {},
            "exif": {},
            "gps": {},
            "all": {},
        }

    if proc.returncode != 0:
        return {
            "status": "error",
            "reason": proc.stdout.strip()[-1000:],
            "groups": {},
            "exif": {},
            "gps": {},
            "all": {},
        }

    try:
        data = json.loads(proc.stdout)
        raw = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
    except Exception as exc:
        return {
            "status": "error",
            "reason": f"JSON exiftool no valido: {exc}",
            "groups": {},
            "exif": {},
            "gps": {},
            "all": {},
        }

    groups = _group_exiftool_tags(raw)
    gps = _gps_tags(raw)
    exif = _exif_tags(raw, gps)
    return {
        "status": "ok",
        "tool": "exiftool",
        "groups": groups,
        "exif": exif,
        "gps": gps,
        "all": raw,
    }


def read_c2pa_metadata(path: Path, *, client: C2PAClient | None = None) -> dict[str, Any]:
    c2pa_client = client or C2PAPythonClient()
    try:
        store = c2pa_client.read_manifest_store(Path(path))
    except C2PANotAvailableError as exc:
        return {"status": "unavailable", "reason": str(exc), "manifest_store": None}
    except C2PAError as exc:
        return {"status": "absent_or_invalid", "reason": str(exc), "manifest_store": None}
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "manifest_store": None}

    active = _active_manifest(store)
    return {
        "status": "ok",
        "active_manifest_id": store.get("active_manifest"),
        "validation_status": store.get("validation_status") or active.get("validation_status") or [],
        "signature_info": active.get("signature_info"),
        "assertion_labels": [
            a.get("label") for a in active.get("assertions", []) if isinstance(a, dict) and a.get("label")
        ],
        "manifest_store": store,
    }


def metadata_sections_text(payload: dict[str, Any]) -> dict[str, str]:
    exif_gps = payload.get("exif_gps", {})
    c2pa = payload.get("c2pa", {})
    return {
        "summary": _json_text(_summary_payload(payload)),
        "exif": _json_text(exif_gps.get("exif", {})),
        "gps": _json_text(exif_gps.get("gps", {})),
        "c2pa": _json_text(c2pa),
        "all": _json_text(payload),
    }


def _file_payload(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "basename": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def _group_exiftool_tags(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        group, name = _split_grouped_key(str(key))
        groups.setdefault(group, {})[name] = value
    return groups


def _gps_tags(raw: dict[str, Any]) -> dict[str, Any]:
    gps: dict[str, Any] = {}
    for key, value in raw.items():
        group, name = _split_grouped_key(str(key))
        searchable = f"{group}:{name}".lower()
        if any(hint in searchable for hint in GPS_TAG_HINTS):
            gps[f"{group}:{name}"] = value
    return gps


def _exif_tags(raw: dict[str, Any], gps: dict[str, Any]) -> dict[str, Any]:
    gps_keys = set(gps)
    exif: dict[str, Any] = {}
    for key, value in raw.items():
        group, name = _split_grouped_key(str(key))
        canonical = f"{group}:{name}"
        if canonical in gps_keys:
            continue
        if group.lower() in EXIF_GROUPS:
            exif[canonical] = value
    return exif


def _split_grouped_key(key: str) -> tuple[str, str]:
    text = key.strip()
    if text.startswith("[") and "]" in text:
        group, name = text[1:].split("]", 1)
        return group.strip() or "Ungrouped", name.strip() or text
    if ":" in text:
        group, name = text.split(":", 1)
        return group.strip() or "Ungrouped", name.strip() or text
    return "Ungrouped", text


def _active_manifest(store: dict[str, Any]) -> dict[str, Any]:
    active_id = store.get("active_manifest")
    manifests = store.get("manifests")
    if isinstance(manifests, dict) and isinstance(active_id, str) and active_id in manifests:
        active = manifests[active_id]
        return active if isinstance(active, dict) else {}
    if isinstance(manifests, dict):
        for active in manifests.values():
            if isinstance(active, dict):
                return active
    return store if isinstance(store, dict) else {}


def _summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    exif_gps = payload.get("exif_gps", {})
    c2pa = payload.get("c2pa", {})
    gps = exif_gps.get("gps", {})
    return {
        "file": payload.get("file", {}),
        "exif_status": exif_gps.get("status"),
        "exif_tag_count": len(exif_gps.get("exif", {}) or {}),
        "gps_status": "present" if gps else "absent",
        "gps_tag_count": len(gps or {}),
        "c2pa_status": c2pa.get("status"),
        "c2pa_active_manifest_id": c2pa.get("active_manifest_id"),
        "c2pa_validation_status": c2pa.get("validation_status"),
        "c2pa_assertion_labels": c2pa.get("assertion_labels"),
    }


def _json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)

