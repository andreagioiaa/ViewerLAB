"""Percorsi applicativi e persistenza delle fonti."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from .models import Source

APP_NAME = "ViewerLAB"
CONFIG_FILENAME = "sources.json"

_DEMO_SOURCE_ID = "demo-public"


def resource_dir() -> Path:
    """Cartella delle risorse incluse (sorgenti, catalogo demo)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Cartella scrivibile per configurazione e log."""
    override = os.environ.get("VIEWERLAB_DATA")
    if override:
        path = Path(override).expanduser()
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        path = Path(base) / APP_NAME if base else Path.home() / ".viewerlab"
    else:
        path = Path.home() / ".local" / "share" / "viewerlab"
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundled_path(relative: str) -> Path:
    return (resource_dir() / relative).resolve()


def config_path() -> Path:
    return data_dir() / CONFIG_FILENAME


def default_sources() -> list[Source]:
    return [
        Source(
            id=_DEMO_SOURCE_ID,
            name="Demo — contenuti pubblici",
            kind="catalog",
            url="@bundled/sources/demo_catalog.json",
            enabled=True,
        )
    ]


def load_sources() -> list[Source]:
    path = config_path()
    if not path.exists():
        sources = default_sources()
        save_sources(sources)
        return sources

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        logging.getLogger(__name__).warning("Configurazione fonti non leggibile: %s", error)
        return default_sources()

    entries = payload.get("sources") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return default_sources()

    sources: list[Source] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            source = Source.from_dict(entry)
            source.validate()
        except ValueError as error:
            logging.getLogger(__name__).warning("Fonte ignorata: %s", error)
            continue
        if source.id in seen:
            continue
        seen.add(source.id)
        sources.append(source)

    return sources or default_sources()


def save_sources(sources: list[Source]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "sources": [source.to_dict() for source in sources]}

    handle, temp_name = tempfile.mkstemp(prefix="sources-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp_name, path)
    except OSError:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def resolve_location(location: str, base: Path | None = None) -> tuple[str, Path | None]:
    """Risolve ``@bundled/...`` e i percorsi locali.

    Ritorna ``(kind, path)`` con ``kind`` in ``http``, ``file`` o ``bundled``.
    """
    from urllib.parse import urlparse

    text = location.strip()
    if text.startswith("@bundled/"):
        return "bundled", bundled_path(text[len("@bundled/") :])

    parsed = urlparse(text)
    if parsed.scheme in ("http", "https"):
        return "http", None
    if parsed.scheme == "file":
        from urllib.parse import unquote
        from urllib.request import url2pathname

        return "file", Path(url2pathname(unquote(parsed.path)))

    path = Path(text).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    return "file", path
