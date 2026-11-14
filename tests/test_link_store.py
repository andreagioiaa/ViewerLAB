from __future__ import annotations

from pathlib import Path

from vistoflow.library.link_dialog import _load_links, _save_links, _valid_http_url
from vistoflow.library.media_manager import MediaManager


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


def test_cover_found_after_app_folder_moved(tmp_path):
    manager = MediaManager(str(tmp_path / "visto_settings.json"))
    (tmp_path / "covers").mkdir()
    (tmp_path / "covers" / "film-x-1.jpg").write_bytes(b"jpg")
    manager.data["covers"] = {"film|x": r"C:\vecchia\cartella\covers\film-x-1.jpg"}
    assert manager.get_cover("film", "x") == str(tmp_path / "covers" / "film-x-1.jpg")
