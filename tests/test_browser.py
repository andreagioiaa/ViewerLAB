from __future__ import annotations

from browser_dialog import BROWSER_ENGINE, normalize_browser_url
from browser_engine import _is_stream_url


def test_browser_url_normalization() -> None:
    assert normalize_browser_url("example.com").toString() == "https://example.com"
    assert (
        normalize_browser_url("https://example.com/watch").toString()
        == "https://example.com/watch"
    )
    assert normalize_browser_url("about:blank").toString() == "about:blank"
    assert normalize_browser_url("ftp://example.com") is None
    assert normalize_browser_url("https://") is None
    assert normalize_browser_url("") is None


def test_browser_helper_exists() -> None:
    assert BROWSER_ENGINE.is_file()


def test_stream_url_detection() -> None:
    assert _is_stream_url("https://example.com/live/master.m3u8")
    assert _is_stream_url("https://example.com/video.m3u8?token=123&exp=456")
    assert _is_stream_url("http://cdn.net/hls/index.m3u8")

    # Scarta file non-video o librerie
    assert not _is_stream_url("https://example.com/assets/hls.min.js")
    assert not _is_stream_url("https://example.com/m3u8_preview.png")
    assert not _is_stream_url("https://example.com/page.html?ref=m3u8")
    assert not _is_stream_url("")
    assert not _is_stream_url("ftp://example.com/stream.m3u8")

