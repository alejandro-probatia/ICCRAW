"""Profile granular para comandos reales de ProbRAW.

Ejemplos:
  python scripts/profile_pipeline.py batch-develop ./raws --recipe recipe.yml --profile camera.icc --out ./out
  python scripts/profile_pipeline.py auto-profile-batch --charts ./charts --targets ./raws --recipe recipe.yml --reference ref.json --profile-out camera.icc --profile-report report.json --out ./out --workdir ./work
"""

from __future__ import annotations

import argparse
import cProfile
from pathlib import Path
import pstats
import shutil
import subprocess
import sys
import time


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile granular de comandos ProbRAW")
    parser.add_argument("--out-dir", default=".", help="Directorio donde escribir profile.txt/profile.svg")
    parser.add_argument("--top", type=int, default=60, help="Numero de funciones en profile.txt")
    parser.add_argument("--no-py-spy", action="store_true", help="No intenta generar flamegraph con py-spy")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Comando y argumentos para probraw.cli")
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("Indica el comando ProbRAW a perfilar")
    return args


def run_with_cprofile(argv: list[str], *, out_dir: Path, top: int) -> Path:
    from probraw.cli import main

    out_dir.mkdir(parents=True, exist_ok=True)
    profile_path = out_dir / "profile.txt"
    profiler = cProfile.Profile()
    start = time.perf_counter()
    exit_code = 0
    profiler.enable()
    try:
        try:
            exit_code = int(main(argv) or 0)
        except SystemExit as exc:
            exit_code = int(exc.code or 0) if isinstance(exc.code, int) else 1
    finally:
        profiler.disable()
        elapsed = time.perf_counter() - start
        with profile_path.open("w", encoding="utf-8") as handle:
            handle.write(f"Command: {' '.join(argv)}\n")
            handle.write(f"Exit code: {exit_code}\n")
            handle.write(f"Wall time seconds: {elapsed:.3f}\n\n")
            stats = pstats.Stats(profiler, stream=handle).sort_stats("cumulative")
            stats.print_stats(max(1, int(top)))
    print(f"Escrito {profile_path}")
    if exit_code:
        raise SystemExit(exit_code)
    return profile_path


def run_with_pyspy(argv: list[str], *, out_dir: Path) -> Path | None:
    py_spy = shutil.which("py-spy")
    if not py_spy:
        print("py-spy no instalado; se omite flamegraph.")
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = out_dir / "profile.svg"
    cmd = [
        py_spy,
        "record",
        "-o",
        str(svg_path),
        "-r",
        "200",
        "--",
        sys.executable,
        "-m",
        "probraw",
        *argv,
    ]
    subprocess.run(cmd, check=False)
    if svg_path.exists():
        print(f"Escrito {svg_path}")
        return svg_path
    return None


def main() -> int:
    args = _parse_args()
    out_dir = Path(args.out_dir).expanduser().resolve()
    run_with_cprofile(list(args.command), out_dir=out_dir, top=int(args.top))
    if not args.no_py_spy:
        run_with_pyspy(list(args.command), out_dir=out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
