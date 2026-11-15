#!/usr/bin/env python
"""Crea l'eseguibile di ViewerLAB con PyInstaller.

Esempi:
    python build_exe.py            # cartella dist/ViewerLAB
    python build_exe.py --onefile  # singolo file dist/ViewerLAB.exe
    python build_exe.py --msi      # cartella + installer dist/ViewerLAB-<versione>.msi (serve WiX 5)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build dell'eseguibile ViewerLAB")
    parser.add_argument("--onefile", action="store_true", help="Crea un singolo .exe")
    parser.add_argument("--clean", action="store_true", help="Pulisce build/ e dist/")
    parser.add_argument("--msi", action="store_true", help="Crea anche l'installer .msi (WiX 5)")
    args = parser.parse_args(argv)
    if args.msi and args.onefile:
        parser.error("--msi impacchetta la cartella dist/ViewerLAB: non usarlo con --onefile")
    if args.msi and not shutil.which("wix"):
        print(
            "WiX non trovato. Installa .NET SDK e poi WiX 5:\n"
            "  winget install Microsoft.DotNet.SDK.8\n"
            "  dotnet tool install --global wix --version 5.0.2",
            file=sys.stderr,
        )
        return 1

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller non installato: esegui 'pip install pyinstaller'.", file=sys.stderr)
        return 1

    # L'exe tiene i dati della libreria accanto a sé: la build cancella dist/ViewerLAB,
    # quindi cronologia e copertine di chi lo usa da lì vengono messe da parte e rimesse.
    kept = ROOT / "build_keep"
    app_dir = ROOT / "dist" / "ViewerLAB"
    for name in USER_DATA:
        if (app_dir / name).exists():
            kept.mkdir(exist_ok=True)
            shutil.move(str(app_dir / name), str(kept / name))
    try:
        return _build(args)
    finally:
        for name in USER_DATA:
            if (kept / name).exists():
                app_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(kept / name), str(app_dir / name))
        if kept.exists() and not any(kept.iterdir()):
            kept.rmdir()


USER_DATA = ("visto_settings.json", "covers")


def _build(args) -> int:
    if args.clean:
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
        # niente --collect-submodules mcp: importerebbe mcp.cli, che esce senza typer
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

    target = ROOT / "dist" / ("ViewerLAB.exe" if os.name == "nt" else "ViewerLAB")
    if not target.exists():
        target = ROOT / "dist" / "ViewerLAB"
    print(f"\nBuild completata: {target}")
    print(
        "Ricorda: mpv (Online) e VLC (Locale) non sono inclusi. Imposta MPV_PATH oppure copia mpv(.exe) "
        "nella cartella bin/ accanto all'eseguibile."
    )
    return build_msi() if args.msi else 0


def build_msi() -> int:
    """Impacchetta dist/ViewerLAB in dist/ViewerLAB-<versione>.msi."""
    from vistoflow import __version__

    msi = ROOT / "dist" / f"ViewerLAB-{__version__}.msi"
    command = [
        "wix", "build", str(ROOT / "installer" / "ViewerLAB.wxs"),
        "-arch", "x64",
        "-d", f"Version={__version__}",
        "-bindpath", f"app={ROOT / 'dist' / 'ViewerLAB'}",
        "-o", str(msi),
    ]
    print(" ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode == 0:
        print(f"Installer creato: {msi}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
