#!/usr/bin/env python
"""Crea l'eseguibile di ViewerLAB con PyInstaller.

Esempi:
    python build_exe.py            # cartella dist/ViewerLAB
    python build_exe.py --onefile  # singolo file dist/ViewerLAB.exe
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build dell'eseguibile ViewerLAB")
    parser.add_argument("--onefile", action="store_true", help="Crea un singolo .exe")
    parser.add_argument("--clean", action="store_true", help="Pulisce build/ e dist/")
    args = parser.parse_args(argv)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller non installato: esegui 'pip install pyinstaller'.", file=sys.stderr)
        return 1

    if args.clean:
        import shutil

        for name in ("build", "dist"):
            target = ROOT / name
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--name",
        "ViewerLAB",
        "--add-data",
        f"{ROOT / 'sources'}{os.pathsep}sources",
        "--collect-submodules",
        "viewerlab",
    ]
    if args.onefile:
        command.append("--onefile")
    command.append(str(ROOT / "main.py"))

    print(" ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    target = ROOT / "dist" / ("ViewerLAB.exe" if os.name == "nt" else "ViewerLAB")
    if not target.exists():
        target = ROOT / "dist" / "ViewerLAB"
    print(f"\nBuild completata: {target}")
    print(
        "Ricorda: mpv non è incluso. Imposta MPV_PATH oppure copia mpv(.exe) "
        "nella cartella bin/ accanto all'eseguibile."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
