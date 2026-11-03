from __future__ import annotations

import json
from pathlib import Path

import yaml

from vistoflow_online.channels.loader import load_channels, load_channels_with_errors


def channel_payload(channel_id: str) -> dict:
    return {
        "id": channel_id,
        "name": f"Channel {channel_id}",
        "domain": "https://example.invalid",
        "search_url": "https://example.invalid/search?q={query}",
        "selectors": {
            "item_card": "article.result",
            "title": "h2 a",
            "url": "h2 a",
        },
    }


def test_load_json_and_yaml_with_errors(tmp_path: Path) -> None:
    (tmp_path / "json.json").write_text(
        json.dumps(channel_payload("json")),
        encoding="utf-8",
    )
    (tmp_path / "yaml.yaml").write_text(
        yaml.safe_dump(channel_payload("yaml")),
        encoding="utf-8",
    )
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")
    invalid = channel_payload("invalid")
    invalid["search_url"] = "https://example.invalid/search"
    (tmp_path / "invalid.json").write_text(json.dumps(invalid), encoding="utf-8")

    channels, errors = load_channels_with_errors(tmp_path)
    assert {channel.id for channel in channels} == {"json", "yaml"}
    assert all(channel.source_path for channel in channels)
    assert "broken.json" in errors
    assert "invalid.json" in errors

    assert len(load_channels(tmp_path)) == 2


def test_load_missing_directory(tmp_path: Path) -> None:
    channels, errors = load_channels_with_errors(tmp_path / "missing")
    assert channels == []
    assert errors

