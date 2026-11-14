#!/usr/bin/env python
"""Crea l'eseguibile di VistoFlow con PyInstaller.

Esempi:
    python build_exe.py            # cartella dist/VistoFlow
    python build_exe.py --onefile  # singolo file dist/VistoFlow.exe
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build dell'eseguibile VistoFlow")
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
        "VistoFlow",
        "--add-data",
        f"{ROOT / 'sources'}{os.pathsep}sources",
        "--add-data",
        f"{ROOT / 'channels'}{os.pathsep}channels",
        "--collect-submodules",
        "vistoflow",
        "--collect-submodules",
        "vistoflow",
        "--collect-submodules",
        "vistoflow_online",
        "--hidden-import",
        "vlc",
        # pannello di download: template/static del pacchetto e moduli caricati a runtime
        "--collect-all",
        "vistoflow_dl",
        "--collect-submodules",
        "uvicorn",
        "--collect-all",
        "apprise",
        "--collect-all",
        "imageio_ffmpeg",
        "--collect-all",
        "random_user_agent",
        "--collect-all",
        "cloudscraper",
        "--collect-submodules",
        "mcp",
        # browser integrato: l'exe riavvia sé stesso con --browser-engine
        "--collect-all",
        "PySide6",
    ]
    if args.onefile:
        command.append("--onefile")
    command.append(str(ROOT / "main.py"))

    print(" ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    target = ROOT / "dist" / ("VistoFlow.exe" if os.name == "nt" else "VistoFlow")
    if not target.exists():
        target = ROOT / "dist" / "VistoFlow"
    print(f"\nBuild completata: {target}")
    print(
        "Ricorda: mpv (Online) e VLC (Locale) non sono inclusi. Imposta MPV_PATH oppure copia mpv(.exe) "
        "nella cartella bin/ accanto all'eseguibile."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
