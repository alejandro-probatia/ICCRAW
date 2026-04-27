from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from iccraw.core.recipe import load_recipe
from iccraw.raw.pipeline import develop_controlled


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "testdata" / "regression" / "MANIFEST.json"


def sha256_bytes(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_cases() -> list[dict[str, str]]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return list(payload.get("cases") or [])


@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: str(case.get("id")))
def test_canonical_byte_stability(case: dict[str, str], tmp_path: Path):
    source = REPO_ROOT / case["input"]
    recipe = load_recipe(REPO_ROOT / case["recipe"])
    assert recipe.use_cache is False

    out = tmp_path / f"{case['id']}.tiff"
    audit = tmp_path / f"{case['id']}.linear.tiff"
    develop_controlled(source, recipe, out, audit)

    output_sha = sha256_bytes(out)
    audit_sha = sha256_bytes(audit)
    assert output_sha == case["output_sha256"], (
        f"REGRESION DE REPRODUCIBILIDAD en {case['id']} output.\n"
        f"Esperado: {case['output_sha256']}\n"
        f"Obtenido: {output_sha}\n"
        "Si el cambio es intencional, regenera los goldens y documenta la incompatibilidad."
    )
    assert audit_sha == case["audit_sha256"], (
        f"REGRESION DE REPRODUCIBILIDAD en {case['id']} audit.\n"
        f"Esperado: {case['audit_sha256']}\n"
        f"Obtenido: {audit_sha}\n"
        "Si el cambio es intencional, regenera los goldens y documenta la incompatibilidad."
    )
