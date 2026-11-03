"""Configurazione del motore online, caricata da ambiente e file .env."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dipendenza opzionale a runtime
    load_dotenv = None


def _app_root() -> Path:
    """Cartella dati: accanto all'exe quando l'app è compilata."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _app_root()
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "VistoFlowPro/1.0 (libreria locale film e serie TV)"
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
    """Impostazioni condivise da canali, resolver e TMDB."""

    channels_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "channels")
    tmdb_api_key: str | None = None
    tmdb_language: str = "it-IT"
    request_timeout: float = 15.0
    channel_timeout: float = 20.0
    resolver_timeout: float = 25.0
    concurrency: int = 8
    user_agent: str = DEFAULT_USER_AGENT
    log_level: str = "INFO"


def _as_path(value: str | os.PathLike[str] | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def load_settings(
    channels_dir: Path | str | None = None,
    app_config: dict[str, Any] | None = None,
) -> Settings:
    """Carica ``.env``, variabili d'ambiente e la sezione ``online`` dell'app.

    ``app_config`` è il dizionario letto da ``visto_settings.json``. I valori
    espliciti hanno precedenza sulle variabili d'ambiente, così l'utente può
    configurare TMDB e la cartella dei canali direttamente dalla GUI.
    """

    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)

    config = app_config or {}
    configured_dir = (
        _as_path(channels_dir)
        or _as_path(config.get("channels_dir"))
        or _as_path(os.getenv("CHANNELS_DIR"))
        or PROJECT_ROOT / "channels"
    )

    key = str(config.get("tmdb_api_key") or "").strip()
    if not key:
        key = (os.getenv("TMDB_API_KEY") or "").strip()
    language = str(
        config.get("tmdb_language")
        or os.getenv("TMDB_LANGUAGE")
        or "it-IT"
    ).strip() or "it-IT"

    return Settings(
        channels_dir=configured_dir,
        tmdb_api_key=key or None,
        tmdb_language=language,
        request_timeout=float(
            config.get("request_timeout") or _float_env("HTTP_TIMEOUT", 15.0)
        ),
        channel_timeout=float(
            config.get("channel_timeout") or _float_env("CHANNEL_TIMEOUT", 20.0)
        ),
        resolver_timeout=float(
            config.get("resolver_timeout") or _float_env("RESOLVER_TIMEOUT", 25.0)
        ),
        concurrency=max(
            1, int(config.get("concurrency") or _int_env("MAX_CONCURRENCY", 8))
        ),
        user_agent=str(
            config.get("user_agent") or os.getenv("USER_AGENT") or DEFAULT_USER_AGENT
        )
        or DEFAULT_USER_AGENT,
        log_level=str(config.get("log_level") or os.getenv("LOG_LEVEL") or "INFO"),
    )
