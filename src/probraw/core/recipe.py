from __future__ import annotations

from dataclasses import asdict, fields
from pathlib import Path
import json
import yaml

from .models import Recipe, ScientificGuard


def load_recipe(path: Path) -> Recipe:
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        payload = yaml.safe_load(raw)
    elif suffix == ".json":
        payload = json.loads(raw)
    else:
        try:
            payload = yaml.safe_load(raw)
        except Exception:
            payload = json.loads(raw)

    payload = payload or {}
    payload = _normalize_recipe_payload(payload)
    allowed = {f.name for f in fields(Recipe)}
    filtered = {k: v for k, v in payload.items() if k in allowed}
    recipe = Recipe(**filtered)
    return recipe


def save_recipe(recipe: Recipe, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(recipe)
    suffix = path.suffix.lower()
    if suffix == ".json":
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def scientific_guard(recipe: Recipe) -> ScientificGuard:
    warnings: list[str] = []
    if recipe.profiling_mode:
        if recipe.denoise.lower() != "off":
            warnings.append("denoise habilitado en profiling_mode")
        if recipe.sharpen.lower() != "off":
            warnings.append("sharpen habilitado en profiling_mode")
        if recipe.tone_curve.lower() != "linear":
            warnings.append("tone_curve no lineal en profiling_mode")
        if not recipe.output_linear:
            warnings.append("output_linear=false en profiling_mode")
    return ScientificGuard(is_scientific_safe=(len(warnings) == 0), warnings=warnings)


def _normalize_recipe_payload(payload: dict) -> dict:
    out = dict(payload)

    bl = out.get("black_level_mode")
    if isinstance(bl, dict):
        out["black_level_mode"] = str(bl.get("mode", "metadata"))

    tc = out.get("tone_curve")
    if isinstance(tc, dict):
        mode = str(tc.get("mode", "linear"))
        if mode == "gamma":
            gamma = tc.get("gamma", "2.2")
            out["tone_curve"] = f"gamma:{gamma}"
        else:
            out["tone_curve"] = mode

    ss = out.get("sampling_strategy")
    if isinstance(ss, dict):
        if "trim_percent" in ss and "sampling_trim_percent" not in out:
            out["sampling_trim_percent"] = ss.get("trim_percent")
        if "reject_saturated" in ss and "sampling_reject_saturated" not in out:
            out["sampling_reject_saturated"] = ss.get("reject_saturated")
        out["sampling_strategy"] = str(ss.get("mode", "trimmed_mean"))

    for field_name, default in {
        "raw_developer": "libraw",
        "demosaic_algorithm": "dcb",
        "black_level_mode": "metadata",
        "white_balance_mode": "fixed",
        "tone_curve": "linear",
        "denoise": "off",
        "sharpen": "off",
        "input_color_assumption": "camera_native",
        "working_space": "scene_linear_camera_rgb",
        "output_space": "scene_linear_camera_rgb",
        "sampling_strategy": "trimmed_mean",
        "profile_engine": "argyll",
    }.items():
        out[field_name] = _as_mode_string(out.get(field_name, default), default)

    for field_name in ("demosaic_edge_quality", "false_color_suppression_steps"):
        try:
            out[field_name] = max(0, int(out.get(field_name, 0) or 0))
        except Exception:
            out[field_name] = 0

    out["four_color_rgb"] = _as_bool(out.get("four_color_rgb", False))

    return out


def _as_mode_string(value, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "si", "sí"}
