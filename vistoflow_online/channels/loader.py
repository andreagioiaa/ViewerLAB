"""Caricamento e validazione dei canali JSON/YAML."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from ..models import ChannelConfig

LOGGER = logging.getLogger(__name__)


def load_channels_with_errors(
    directory: Path,
) -> tuple[list[ChannelConfig], dict[str, str]]:
    """Carica tutti i canali da una directory e restituisce anche gli errori."""

    channels: list[ChannelConfig] = []
    errors: dict[str, str] = {}
    if not directory.exists():
        return channels, {str(directory): "Cartella dei canali non trovata"}

    files = sorted(
        list(directory.glob("*.json"))
        + list(directory.glob("*.yaml"))
        + list(directory.glob("*.yml"))
    )
    seen_ids: set[str] = set()
    for path in files:
        try:
            if path.suffix.lower() == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
            else:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("la radice del file deve essere un oggetto")
            channel = ChannelConfig.model_validate(data)
            if channel.id in seen_ids:
                raise ValueError(f"id duplicato: {channel.id}")
            channel.source_path = str(path)
            seen_ids.add(channel.id)
            channels.append(channel)
        except (OSError, ValueError, json.JSONDecodeError, ValidationError, yaml.YAMLError) as exc:
            errors[path.name] = str(exc)
            LOGGER.warning("Canale ignorato %s: %s", path.name, exc)

    channels.sort(key=lambda item: (item.priority, item.name.casefold()))
    return channels, errors


def load_channels(directory: Path) -> list[ChannelConfig]:
    """Comodità per i test e per i chiamanti che non gestiscono gli errori."""

    channels, _errors = load_channels_with_errors(directory)
    return channels
