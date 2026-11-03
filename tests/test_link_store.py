from __future__ import annotations

from pathlib import Path

from link_dialog import _load_links, _save_links, _valid_http_url
from media_manager import MediaManager


def test_saved_links_roundtrip(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.json"
    manager = MediaManager(str(config_path))
    links = [
        {
            "id": "abc",
            "title": "Test",
            "url": "https://example.invalid/watch",
            "kind": "page",
            "source_url": "",
            "referer": "https://example.invalid/",
            "user_agent": "TestAgent/1.0",
        }
    ]

    _save_links(manager, links)

    reloaded = MediaManager(str(config_path))
    assert _load_links(reloaded) == links


def test_link_url_requires_a_complete_host() -> None:
    assert _valid_http_url("https://streaming-community.biz/watch")
    assert not _valid_http_url("https://streaming-community")
    assert not _valid_http_url("streaming-community.biz/watch")
