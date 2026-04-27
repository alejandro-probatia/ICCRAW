from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from iccraw.core.recipe import load_recipe
from iccraw.raw.pipeline import develop_controlled
from iccraw.version import __version__


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "testdata" / "regression" / "MANIFEST.json"
LOG_PATH = REPO_ROOT / "tests" / "regression" / "golden" / "REGENERATION_LOG.md"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenera hashes golden canonicos de NexoRAW")
    parser.add_argument("--confirm", action="store_true", help="Requerido para modificar MANIFEST.json")
    parser.add_argument("--note", default="", help="Nota breve para el log de regeneracion")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm:
        raise SystemExit("Operacion destructiva bloqueada: vuelve a ejecutar con --confirm")

    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = list(payload.get("cases") or [])
    with tempfile.TemporaryDirectory(prefix="nexoraw-golden-") as tmp:
        tmp_path = Path(tmp)
        for case in cases:
            recipe = load_recipe(REPO_ROOT / case["recipe"])
            recipe.use_cache = False
            out = tmp_path / f"{case['id']}.tiff"
            audit = tmp_path / f"{case['id']}.linear.tiff"
            develop_controlled(REPO_ROOT / case["input"], recipe, out, audit)
            case["output_sha256"] = sha256_file(out)
            case["audit_sha256"] = sha256_file(audit)

    MANIFEST_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    note = str(args.note or "regeneracion manual").strip()
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"\n- {timestamp} - NexoRAW {__version__}: {note}\n")
    print(f"Regenerado {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
