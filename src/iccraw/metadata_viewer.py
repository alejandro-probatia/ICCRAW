from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from .core.external import external_tool_path, run_external
from .provenance.c2pa import (
    C2PAClient,
    C2PAError,
    C2PANotAvailableError,
    C2PAPythonClient,
    extract_raw_link_assertion,
)
from .provenance.nexoraw_proof import PROOF_SCHEMA, NexoRawProofError, verify_nexoraw_proof


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
        "nexoraw_proof": read_nexoraw_proof_metadata(path),
    }
    if include_c2pa:
        payload["c2pa"] = read_c2pa_metadata(path, client=c2pa_client)
    else:
        payload["c2pa"] = {"status": "skipped"}
    return payload


def read_nexoraw_proof_metadata(path: Path) -> dict[str, Any]:
    path = Path(path)
    proof_path = path if path.suffix.lower() == ".json" else path.with_suffix(path.suffix + ".nexoraw.proof.json")
    if not proof_path.exists():
        return {"status": "absent", "proof_path": str(proof_path)}
    try:
        raw_payload = json.loads(proof_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "error", "proof_path": str(proof_path), "reason": f"JSON no valido: {exc}"}
    if raw_payload.get("schema") != PROOF_SCHEMA:
        return {"status": "not_nexoraw_proof", "proof_path": str(proof_path)}
    try:
        result = verify_nexoraw_proof(
            proof_path,
            output_tiff=path if path != proof_path and path.exists() else None,
        )
    except NexoRawProofError as exc:
        return {"status": "invalid", "proof_path": str(proof_path), "reason": str(exc), "proof": raw_payload}
    except Exception as exc:
        return {"status": "error", "proof_path": str(proof_path), "reason": str(exc), "proof": raw_payload}
    return result


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
        proc = run_external(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
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
    proof = payload.get("nexoraw_proof", {})
    return {
        "summary": _json_text(_summary_payload(payload)),
        "exif": _json_text(exif_gps.get("exif", {})),
        "gps": _json_text(exif_gps.get("gps", {})),
        "c2pa": _json_text({"nexoraw_proof": proof, "c2pa": c2pa}),
        "all": _json_text(payload),
    }


def metadata_display_sections(payload: dict[str, Any]) -> dict[str, Any]:
    exif_gps = payload.get("exif_gps", {})
    c2pa = payload.get("c2pa", {})
    proof = payload.get("nexoraw_proof", {})
    raw = exif_gps.get("all", {}) if isinstance(exif_gps, dict) else {}
    gps = exif_gps.get("gps", {}) if isinstance(exif_gps, dict) else {}
    return {
        "summary": _interpreted_summary(payload, raw, gps, c2pa),
        "exif": _grouped_tree(exif_gps.get("groups", {}) if isinstance(exif_gps, dict) else {}),
        "gps": _gps_display(gps),
        "c2pa": _proof_display(proof) + _c2pa_display(c2pa),
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
    proof = payload.get("nexoraw_proof", {})
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
        "nexoraw_proof_status": proof.get("status") if isinstance(proof, dict) else None,
        "nexoraw_proof_path": proof.get("proof_path") if isinstance(proof, dict) else None,
    }


def _interpreted_summary(
    payload: dict[str, Any],
    raw: dict[str, Any],
    gps: dict[str, Any],
    c2pa: dict[str, Any],
) -> list[dict[str, Any]]:
    file_payload = payload.get("file", {}) if isinstance(payload.get("file"), dict) else {}
    proof = payload.get("nexoraw_proof", {}) if isinstance(payload.get("nexoraw_proof"), dict) else {}
    return [
        {
            "title": "Archivo",
            "items": _items(
                ("Nombre", file_payload.get("basename")),
                ("Ruta", file_payload.get("path")),
                ("Tipo", _first(raw, "File:MIMEType", "File:FileType", default=file_payload.get("extension"))),
                ("Tamaño", _format_bytes(file_payload.get("size_bytes"))),
                ("Modificado UTC", file_payload.get("modified_utc")),
            ),
        },
        {
            "title": "Cámara",
            "items": _items(
                ("Marca", _first(raw, "EXIF:Make", "IFD0:Make")),
                ("Modelo", _first(raw, "EXIF:Model", "IFD0:Model")),
                ("Número de serie", _first(raw, "EXIF:SerialNumber", "MakerNotes:SerialNumber", "Composite:SerialNumber")),
                ("Firmware / software", _first(raw, "EXIF:Software", "IFD0:Software")),
                ("Autor / propietario", _first(raw, "EXIF:Artist", "IFD0:Artist", "EXIF:OwnerName")),
            ),
        },
        {
            "title": "Captura",
            "items": _items(
                ("Fecha/hora original", _first(raw, "EXIF:DateTimeOriginal", "EXIF:CreateDate", "Composite:SubSecDateTimeOriginal")),
                ("Exposición", _format_exposure(_first(raw, "EXIF:ExposureTime", "Composite:ShutterSpeed"))),
                ("Apertura", _format_aperture(_first(raw, "EXIF:FNumber", "Composite:Aperture"))),
                ("ISO", _first(raw, "EXIF:ISO", "Composite:ISO")),
                ("Compensación EV", _first(raw, "EXIF:ExposureCompensation", "Composite:ExposureCompensation")),
                ("Programa / modo", _first(raw, "EXIF:ExposureProgram", "EXIF:ExposureMode")),
                ("Medición", _first(raw, "EXIF:MeteringMode")),
                ("Flash", _first(raw, "EXIF:Flash")),
                ("Balance de blancos", _first(raw, "EXIF:WhiteBalance", "Composite:WhiteBalance")),
                ("Fuente de luz", _first(raw, "EXIF:LightSource", "Composite:LightSource")),
            ),
        },
        {
            "title": "Óptica",
            "items": _items(
                ("Lente", _first(raw, "Composite:LensID", "EXIF:LensModel", "MakerNotes:Lens")),
                ("Focal", _format_focal(_first(raw, "EXIF:FocalLength", "Composite:FocalLength"))),
                ("Focal equivalente 35 mm", _format_focal(_first(raw, "EXIF:FocalLengthIn35mmFormat", "Composite:FocalLength35efl"))),
                ("Distancia de enfoque", _first(raw, "Composite:FocusDistance", "MakerNotes:FocusDistance")),
            ),
        },
        {
            "title": "Imagen",
            "items": _items(
                ("Dimensiones", _image_size(raw)),
                ("Megapíxeles", _format_number(_first(raw, "Composite:Megapixels"))),
                ("Orientación", _first(raw, "EXIF:Orientation", "IFD0:Orientation")),
                ("Bits por muestra", _first(raw, "EXIF:BitsPerSample")),
                ("Compresión", _first(raw, "EXIF:Compression")),
                ("Espacio color", _first(raw, "EXIF:ColorSpace", "Composite:ColorSpace")),
                ("Perfil ICC", _first(raw, "ICC_Profile:ProfileDescription", "EXIF:ProfileName")),
            ),
        },
        {
            "title": "Localización",
            "items": _items(
                ("Estado GPS", "presente" if gps else "sin GPS"),
                ("Latitud", _first(gps, "GPS:GPSLatitude", "Composite:GPSLatitude")),
                ("Longitud", _first(gps, "GPS:GPSLongitude", "Composite:GPSLongitude")),
                ("Altitud", _format_altitude(_first(gps, "GPS:GPSAltitude", "Composite:GPSAltitude"))),
            ),
        },
        {
            "title": "Prueba forense",
            "items": _items(
                ("NexoRAW Proof", _proof_status_label(proof)),
                ("Proof sidecar", proof.get("proof_path")),
                ("Estado", _c2pa_status_label(c2pa)),
                ("Motivo", c2pa.get("reason") if isinstance(c2pa, dict) else None),
                ("Manifiesto activo", c2pa.get("active_manifest_id") if isinstance(c2pa, dict) else None),
                ("Firma", _c2pa_signature_summary(c2pa)),
                ("Validación", _c2pa_validation_summary(c2pa)),
                ("Vinculo RAW", _c2pa_raw_link_summary(c2pa)),
            ),
        },
    ]


def _gps_display(gps: dict[str, Any]) -> list[dict[str, Any]]:
    if not gps:
        return [{"title": "GPS", "items": [{"label": "Estado", "value": "No hay coordenadas GPS"}]}]
    return [
        {
            "title": "Coordenadas",
            "items": _items(
                ("Latitud", _first(gps, "GPS:GPSLatitude", "Composite:GPSLatitude")),
                ("Longitud", _first(gps, "GPS:GPSLongitude", "Composite:GPSLongitude")),
                ("Altitud", _format_altitude(_first(gps, "GPS:GPSAltitude", "Composite:GPSAltitude"))),
                ("Fecha GPS", _first(gps, "GPS:GPSDateStamp", "Composite:GPSDateTime")),
                ("Hora GPS", _first(gps, "GPS:GPSTimeStamp")),
                ("Mapa", _map_hint(gps)),
            ),
        },
        {
            "title": "Todos los campos GPS",
            "items": [{"label": key, "value": _format_value(value)} for key, value in sorted(gps.items())],
        },
    ]


def _proof_display(proof: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(proof, dict):
        return [{"title": "NexoRAW Proof", "items": [{"label": "Estado", "value": "No disponible"}]}]
    proof_payload = proof.get("proof") if isinstance(proof.get("proof"), dict) else {}
    subject = proof_payload.get("subject", {}) if isinstance(proof_payload, dict) else {}
    source_raw = subject.get("source_raw", {}) if isinstance(subject, dict) else {}
    output_tiff = subject.get("output_tiff", {}) if isinstance(subject, dict) else {}
    process = proof_payload.get("process", {}) if isinstance(proof_payload, dict) else {}
    signer = proof_payload.get("signer", {}) if isinstance(proof_payload, dict) else {}
    return [
        {
            "title": "NexoRAW Proof",
            "items": _items(
                ("Estado", _proof_status_label(proof)),
                ("Sidecar", proof.get("proof_path")),
                ("Firma", "valida" if proof.get("signature_valid") is True else proof.get("signature_error")),
                ("Clave publica SHA-256", proof.get("public_key_sha256_actual")),
                ("Firmante", signer.get("name") if isinstance(signer, dict) else None),
            ),
        },
        {
            "title": "Vinculo RAW-TIFF Proof",
            "items": _items(
                ("RAW SHA-256", source_raw.get("sha256") if isinstance(source_raw, dict) else None),
                ("RAW", source_raw.get("basename") if isinstance(source_raw, dict) else None),
                ("TIFF SHA-256", output_tiff.get("sha256") if isinstance(output_tiff, dict) else None),
                ("TIFF", output_tiff.get("basename") if isinstance(output_tiff, dict) else None),
                ("Hash receta", process.get("recipe_sha256") if isinstance(process, dict) else None),
                ("Hash ajustes", process.get("render_settings_sha256") if isinstance(process, dict) else None),
                ("Demosaicing", process.get("demosaicing_algorithm") if isinstance(process, dict) else None),
                ("Modo color", process.get("color_management_mode") if isinstance(process, dict) else None),
            ),
        },
    ]


def _c2pa_display(c2pa: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(c2pa, dict):
        return [{"title": "C2PA", "items": [{"label": "Estado", "value": "No disponible"}]}]
    if c2pa.get("status") != "ok":
        return [
            {
                "title": "Estado C2PA",
                "items": _items(
                    ("Estado", _c2pa_status_label(c2pa)),
                    ("Codigo interno", c2pa.get("status")),
                    ("Motivo", c2pa.get("reason")),
                    ("Validacion", _c2pa_validation_summary(c2pa)),
                ),
            },
            {
                "title": "Interpretacion forense",
                "items": _items(
                    ("Resultado", _c2pa_non_ok_result(c2pa)),
                    ("Vinculo RAW-TIFF C2PA", "No disponible"),
                    ("Siguiente paso", _c2pa_next_step(c2pa)),
                ),
            },
        ]
    manifest_store = c2pa.get("manifest_store")
    raw_link = None
    if isinstance(manifest_store, dict):
        try:
            raw_link = extract_raw_link_assertion(manifest_store)
        except Exception:
            raw_link = None
    raw_identity = raw_link.get("raw_identity", {}) if isinstance(raw_link, dict) else {}
    nexoraw = raw_link.get("nexoraw", {}) if isinstance(raw_link, dict) else {}
    render_settings = raw_link.get("render_settings", {}) if isinstance(raw_link, dict) else {}
    recipe_parameters = render_settings.get("recipe_parameters", {}) if isinstance(render_settings, dict) else {}
    return [
        {
            "title": "Estado C2PA",
            "items": _items(
                ("Estado", c2pa.get("status")),
                ("Manifiesto activo", c2pa.get("active_manifest_id")),
                ("Firma", _c2pa_signature_summary(c2pa)),
                ("Validación", _c2pa_validation_summary(c2pa)),
            ),
        },
        {
            "title": "Firma",
            "items": _dict_items(c2pa.get("signature_info")),
        },
        {
            "title": "Aserciones",
            "items": [{"label": f"{idx + 1}", "value": label} for idx, label in enumerate(c2pa.get("assertion_labels") or [])],
        },
        {
            "title": "Vínculo RAW NexoRAW",
            "items": _items(
                ("RAW SHA-256", raw_identity.get("sha256")),
                ("RAW", raw_identity.get("basename")),
                ("Tamaño RAW", _format_bytes(raw_identity.get("size_bytes"))),
                ("MIME RAW", raw_identity.get("mime_type")),
                ("Hash receta", nexoraw.get("recipe_sha256")),
                ("Hash ICC", nexoraw.get("icc_profile_sha256")),
                ("Hash ajustes render", nexoraw.get("render_settings_sha256")),
                ("Backend RAW", nexoraw.get("raw_backend")),
                ("Demosaicing", nexoraw.get("demosaicing_algorithm")),
                ("Espacio salida", nexoraw.get("output_space")),
                ("Modo color", nexoraw.get("color_management_mode")),
                ("Generado UTC", nexoraw.get("generated_at_utc")),
            ),
        },
        {
            "title": "Ajustes TIFF NexoRAW",
            "items": _items(
                ("Hash ajustes", render_settings.get("settings_sha256") if isinstance(render_settings, dict) else None),
                ("RAW developer", recipe_parameters.get("raw_developer") if isinstance(recipe_parameters, dict) else None),
                ("Demosaicing", recipe_parameters.get("demosaic_algorithm") if isinstance(recipe_parameters, dict) else None),
                ("WB modo", recipe_parameters.get("white_balance_mode") if isinstance(recipe_parameters, dict) else None),
                ("WB multiplicadores", recipe_parameters.get("wb_multipliers") if isinstance(recipe_parameters, dict) else None),
                ("Exposicion receta EV", recipe_parameters.get("exposure_compensation") if isinstance(recipe_parameters, dict) else None),
                ("Curva receta", recipe_parameters.get("tone_curve") if isinstance(recipe_parameters, dict) else None),
                ("Espacio trabajo", recipe_parameters.get("working_space") if isinstance(recipe_parameters, dict) else None),
                ("Espacio salida", recipe_parameters.get("output_space") if isinstance(recipe_parameters, dict) else None),
                ("Salida lineal", recipe_parameters.get("output_linear") if isinstance(recipe_parameters, dict) else None),
                ("Correccion basica/curvas", render_settings.get("render_adjustments") if isinstance(render_settings, dict) else None),
                ("Nitidez", render_settings.get("detail_adjustments") if isinstance(render_settings, dict) else None),
                ("Gestion color", render_settings.get("color_management") if isinstance(render_settings, dict) else None),
                ("Contexto", render_settings.get("context") if isinstance(render_settings, dict) else None),
            ),
        },
        {
            "title": "Validacion",
            "items": _validation_items(c2pa.get("validation_status")),
        },
    ]


def _grouped_tree(groups: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for group, values in sorted(groups.items()):
        if isinstance(values, dict):
            items = [{"label": key, "value": _format_value(value)} for key, value in sorted(values.items())]
        else:
            items = [{"label": group, "value": _format_value(values)}]
        out.append({"title": str(group), "items": items})
    return out


def _items(*pairs: tuple[str, Any]) -> list[dict[str, str]]:
    return [{"label": label, "value": _format_value(value)} for label, value in pairs if _present(value)]


def _dict_items(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, dict) or not value:
        return [{"label": "Estado", "value": "No disponible"}]
    return [{"label": str(key), "value": _format_value(val)} for key, val in sorted(value.items())]


def _validation_items(value: Any) -> list[dict[str, str]]:
    if not value:
        return [{"label": "Estado", "value": "Sin errores declarados"}]
    if not isinstance(value, list):
        return [{"label": "Estado", "value": _format_value(value)}]
    out = []
    for idx, item in enumerate(value, start=1):
        if isinstance(item, dict):
            label = str(item.get("code") or f"Validación {idx}")
            detail = item.get("explanation") or item.get("url") or item
            out.append({"label": label, "value": _format_value(detail)})
        else:
            out.append({"label": f"Validación {idx}", "value": _format_value(item)})
    return out


def _first(source: dict[str, Any], *keys: str, default: Any = None) -> Any:
    if not isinstance(source, dict):
        return default
    lower_map = {str(key).lower(): value for key, value in source.items()}
    for key in keys:
        if key in source and _present(source[key]):
            return source[key]
        low = key.lower()
        if low in lower_map and _present(lower_map[low]):
            return lower_map[low]
    return default


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return _format_number(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _format_number(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return _format_value(value)
    if number == 0:
        return "0"
    if abs(number) >= 1000 or abs(number) < 0.001:
        return f"{number:.6g}"
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _format_bytes(value: Any) -> str | None:
    if value is None:
        return None
    try:
        size = float(value)
    except Exception:
        return _format_value(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.2f} {units[idx]}"


def _format_exposure(value: Any) -> str | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except Exception:
        return _format_value(value)
    if seconds <= 0:
        return _format_value(value)
    if seconds < 1:
        denominator = round(1.0 / seconds)
        return f"1/{denominator} s ({seconds:.6g} s)"
    return f"{seconds:.3f}".rstrip("0").rstrip(".") + " s"


def _format_aperture(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return f"f/{float(value):.1f}".rstrip("0").rstrip(".")
    except Exception:
        return _format_value(value)


def _format_focal(value: Any) -> str | None:
    if value is None:
        return None
    text = _format_value(value)
    return text if "mm" in text.lower() else f"{text} mm"


def _format_altitude(value: Any) -> str | None:
    if value is None:
        return None
    text = _format_value(value)
    return text if "m" in text.lower() else f"{text} m"


def _image_size(raw: dict[str, Any]) -> str | None:
    width = _first(raw, "EXIF:ImageWidth", "File:ImageWidth", "Composite:ImageWidth")
    height = _first(raw, "EXIF:ImageHeight", "File:ImageHeight", "Composite:ImageHeight")
    composite = _first(raw, "Composite:ImageSize")
    if width and height:
        return f"{width} x {height} px"
    return _format_value(composite) if composite else None


def _map_hint(gps: dict[str, Any]) -> str | None:
    lat = _first(gps, "GPS:GPSLatitude", "Composite:GPSLatitude")
    lon = _first(gps, "GPS:GPSLongitude", "Composite:GPSLongitude")
    if lat is None or lon is None:
        return None
    return f"https://maps.google.com/?q={lat},{lon}"


def _c2pa_status_label(c2pa: dict[str, Any]) -> str | None:
    if not isinstance(c2pa, dict):
        return None
    status = c2pa.get("status")
    if status == "ok":
        return "Manifiesto C2PA legible"
    labels = {
        "absent_or_invalid": "Ausente o no valido",
        "unavailable": "Soporte C2PA no instalado",
        "error": "Error de lectura C2PA",
        "skipped": "Lectura C2PA omitida",
    }
    return labels.get(status, _format_value(status) if status else None)


def _proof_status_label(proof: dict[str, Any]) -> str | None:
    if not isinstance(proof, dict):
        return None
    status = proof.get("status")
    if status == "ok":
        return "NexoRAW Proof valido"
    labels = {
        "absent": "Sin sidecar NexoRAW Proof",
        "invalid": "NexoRAW Proof no valido",
        "error": "Error de lectura/verificacion Proof",
        "not_nexoraw_proof": "JSON no es NexoRAW Proof",
        "failed": "NexoRAW Proof fallido",
    }
    return labels.get(status, _format_value(status) if status else None)


def _c2pa_non_ok_result(c2pa: dict[str, Any]) -> str:
    status = c2pa.get("status")
    if status == "unavailable":
        return "No se puede evaluar C2PA porque falta el extra c2pa."
    if status == "absent_or_invalid":
        return "Este archivo no contiene un manifiesto C2PA legible o el lector lo considera invalido."
    if status == "skipped":
        return "La lectura C2PA fue omitida para esta consulta."
    return "No se ha podido obtener una credencial C2PA verificable."


def _c2pa_next_step(c2pa: dict[str, Any]) -> str:
    status = c2pa.get("status")
    if status == "unavailable":
        return "Instalar el extra opcional c2pa y volver a leer el archivo."
    if status == "absent_or_invalid":
        return "Los TIFF finales de NexoRAW deben exportarse con C2PA; vuelve a renderizar con firma configurada."
    if status == "skipped":
        return "Activar la lectura C2PA para inspeccionar credenciales embebidas."
    return "Revisar el motivo mostrado y conservar el manifiesto externo de NexoRAW."


def _c2pa_raw_link_summary(c2pa: dict[str, Any]) -> str | None:
    if not isinstance(c2pa, dict) or c2pa.get("status") != "ok":
        return None
    store = c2pa.get("manifest_store")
    if not isinstance(store, dict):
        return "No evaluable"
    try:
        raw_link = extract_raw_link_assertion(store)
    except Exception:
        return "No encontrado"
    raw_identity = raw_link.get("raw_identity") if isinstance(raw_link, dict) else None
    if isinstance(raw_identity, dict) and raw_identity.get("sha256"):
        basename = raw_identity.get("basename") or "RAW"
        return f"{basename} / SHA-256 {str(raw_identity.get('sha256'))[:16]}..."
    return "Asercion presente"


def _c2pa_signature_summary(c2pa: dict[str, Any]) -> str | None:
    if not isinstance(c2pa, dict):
        return None
    sig = c2pa.get("signature_info")
    if not isinstance(sig, dict):
        return None
    signer = sig.get("common_name") or sig.get("issuer") or "firmante no declarado"
    alg = sig.get("alg")
    time = sig.get("time")
    parts = [str(signer)]
    if alg:
        parts.append(str(alg))
    if time:
        parts.append(str(time))
    return " / ".join(parts)


def _c2pa_validation_summary(c2pa: dict[str, Any]) -> str | None:
    if not isinstance(c2pa, dict):
        return None
    if c2pa.get("status") != "ok":
        return c2pa.get("reason") or "No hay manifiesto C2PA validable"
    status = c2pa.get("validation_status")
    if not status:
        return "Sin errores declarados"
    if isinstance(status, list):
        codes = [str(item.get("code") if isinstance(item, dict) else item) for item in status]
        return "; ".join(codes)
    return _format_value(status)


def _json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
