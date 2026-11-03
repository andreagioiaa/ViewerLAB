"""Configurazione applicativa caricata da ambiente e file .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dipendenza opzionale a runtime
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "MediaCenterCLI/0.1 (libreria locale film e serie TV)"
)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class Settings:
    """Impostazioni condivise da CLI, canali, resolver e TMDB."""

    channels_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "channels")
    tmdb_api_key: str | None = None
    tmdb_language: str = "it-IT"
    request_timeout: float = 15.0
    channel_timeout: float = 20.0
    resolver_timeout: float = 25.0
    concurrency: int = 8
    user_agent: str = DEFAULT_USER_AGENT
    log_level: str = "INFO"


def load_settings(channels_dir: Path | None = None) -> Settings:
    """Carica .env e variabili d'ambiente, con override esplicito della cartella canali."""

    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)

    configured_dir = channels_dir or (
        Path(os.getenv("CHANNELS_DIR", "channels")) if os.getenv("CHANNELS_DIR") else PROJECT_ROOT / "channels"
    )
    if not configured_dir.is_absolute():
        configured_dir = (PROJECT_ROOT / configured_dir).resolve()

    return Settings(
        channels_dir=configured_dir,
        tmdb_api_key=(os.getenv("TMDB_API_KEY") or "").strip() or None,
        tmdb_language=(os.getenv("TMDB_LANGUAGE", "it-IT") or "it-IT").strip() or "it-IT",
        request_timeout=_float_env("HTTP_TIMEOUT", 15.0),
        channel_timeout=_float_env("CHANNEL_TIMEOUT", 20.0),
        resolver_timeout=_float_env("RESOLVER_TIMEOUT", 25.0),
        concurrency=max(1, _int_env("MAX_CONCURRENCY", 8)),
        user_agent=os.getenv("USER_AGENT", DEFAULT_USER_AGENT) or DEFAULT_USER_AGENT,
        log_level=os.getenv("LOG_LEVEL", "INFO") or "INFO",
    )
