from __future__ import annotations

from pathlib import Path

import pytest

from vistoflow_online.resolvers.js_unpacker import extract_stream_urls, mime_for_url, unpack, unpack_all

FIXTURES = Path(__file__).parent / "fixtures"


def packed_fixture() -> str:
    html = (FIXTURES / "mixdrop.html").read_text(encoding="utf-8")
    start = html.index("eval(")
    end = html.index("</script>", start)
    return html[start:end].strip()


def test_unpack_classic_packer() -> None:
    result = unpack(packed_fixture())
    assert 'wurl="https://cdn.example/video.m3u8";' in result


def test_unpack_all() -> None:
    outputs = unpack_all(packed_fixture())
    assert len(outputs) == 1
    assert "https://cdn.example/video.m3u8" in outputs[0]


def test_extract_stream_urls_escaped() -> None:
    text = (
        'sources: [{file: "https:\\/\\/cdn.example\\/video.m3u8"}], '
        'fallback: "https:\\/\\/cdn.example\\/video.mp4"'
    )
    urls = extract_stream_urls(text)
    assert urls == [
        "https://cdn.example/video.m3u8",
        "https://cdn.example/video.mp4",
    ]
    assert mime_for_url(urls[0]) == "application/vnd.apple.mpegurl"


def test_unpack_invalid() -> None:
    with pytest.raises(ValueError):
        unpack("console.log('not packed')")

