#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


DEFAULT_PACKAGE = "rawpy-demosaic"
DEFAULT_SOURCE = "git+https://github.com/exfab/rawpy-demosaic.git@8b17075"


def build_commands(
    *,
    python: Path,
    source: str,
    check_script: Path,
    verify: bool = True,
) -> list[list[str]]:
    install_command = [str(python), "-m", "pip", "install", "--force-reinstall"]
    if source.startswith("git+") or "github.com/" in source:
        install_command.append("--no-build-isolation")
    install_command.append(source)
    commands = [
        [str(python), "-m", "pip", "uninstall", "-y", "rawpy", "rawpy-demosaic"],
        install_command,
    ]
    if verify:
        commands.append([str(python), str(check_script)])
    return commands


def install_amaze_backend(
    *,
    python: Path,
    source: str,
    check_script: Path,
    verify: bool = True,
    dry_run: bool = False,
) -> dict[str, object]:
    commands = build_commands(python=python, source=source, check_script=check_script, verify=verify)
    payload: dict[str, object] = {
        "python": str(python),
        "source": source,
        "verify": verify,
        "commands": commands,
    }
    if dry_run:
        payload["status"] = "dry_run"
        return payload

    env = os.environ.copy()
    if "github.com/" in source or source.startswith("git+"):
        env.setdefault("GIT_CONFIG_COUNT", "1")
        env.setdefault("GIT_CONFIG_KEY_0", "url.https://github.com/.insteadOf")
        env.setdefault("GIT_CONFIG_VALUE_0", "git://github.com/")

    for command in commands:
        print("==> " + " ".join(command), flush=True)
        subprocess.run(command, check=True, env=env)
    payload["status"] = "ok"
    return payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Instala el backend RAW GPL3 rawpy-demosaic y verifica soporte AMaZE.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Interprete Python/venv donde instalar el backend. Por defecto: este interprete.",
    )
    parser.add_argument("--wheel", default=None, help="Wheel rawpy_demosaic compatible para instalar.")
    parser.add_argument(
        "--source",
        default=None,
        help=(
            "Especificacion pip de fuente Git/wheelhouse. Para releases reproducibles se recomienda "
            f"fijar commit; por defecto documentado: {DEFAULT_SOURCE}."
        ),
    )
    parser.add_argument(
        "--pypi",
        action="store_true",
        help="Instala rawpy-demosaic desde el indice configurado de pip si existe una distribucion compatible.",
    )
    parser.add_argument(
        "--package",
        default=DEFAULT_PACKAGE,
        help="Nombre/especificacion pip usada con --pypi. Por defecto: rawpy-demosaic.",
    )
    parser.add_argument("--no-verify", action="store_true", help="No ejecuta scripts/check_amaze_support.py.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra los comandos sin ejecutarlos.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    python = Path(args.python).expanduser()
    check_script = Path(__file__).resolve().with_name("check_amaze_support.py")

    if args.wheel:
        wheel = Path(args.wheel).expanduser()
        if not args.dry_run and not wheel.exists():
            print(f"ERROR: no existe la wheel indicada: {wheel}", file=sys.stderr)
            return 2
        source = str(wheel.resolve() if wheel.exists() else wheel)
    elif args.source:
        source = str(args.source)
    elif args.pypi:
        source = str(args.package)
    else:
        print("ERROR: indica --wheel PATH o --pypi.", file=sys.stderr)
        return 2

    try:
        payload = install_amaze_backend(
            python=python,
            source=source,
            check_script=check_script,
            verify=not bool(args.no_verify),
            dry_run=bool(args.dry_run),
        )
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: comando fallo con codigo {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
        return int(exc.returncode or 2)

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
