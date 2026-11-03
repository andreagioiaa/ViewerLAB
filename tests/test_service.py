from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from vistoflow_online import OnlineService, StreamSource

FIXTURES = Path(__file__).parent / "fixtures"


def _channel_config(base: str = "https://one.invalid") -> dict:
    return {
        "id": "one",
        "name": "One",
        "domain": base,
        "search_url": f"{base}/search?q={{query}}",
        "selectors": {
            "item_card": "article.result",
            "title": "h2 a",
            "url": "h2 a",
            "cover": "img.poster",
        },
        "detail_selectors": {"embed_links": "iframe[src], a.embed-link[href]"},
        "enabled": True,
        "priority": 10,
    }


def _service(tmp_path: Path, tmdb_api_key: str = "") -> OnlineService:
    (tmp_path / "one.json").write_text(
        json.dumps(_channel_config()), encoding="utf-8"
    )
    return OnlineService(
        {
            "channels_dir": str(tmp_path),
            "tmdb_api_key": tmdb_api_key,
        }
    )


@respx.mock
async def test_online_service_search_and_detail(tmp_path: Path) -> None:
    search_html = (FIXTURES / "search.html").read_text(encoding="utf-8")
    detail_html = (FIXTURES / "detail.html").read_text(encoding="utf-8")
    mixdrop_html = (FIXTURES / "mixdrop.html").read_text(encoding="utf-8")
    voe_html = (FIXTURES / "voe.html").read_text(encoding="utf-8")
    respx.get("https://one.invalid/search?q=Inception").mock(
        return_value=httpx.Response(200, text=search_html)
    )
    respx.get("https://one.invalid/movie/inception").mock(
        return_value=httpx.Response(200, text=detail_html)
    )
    respx.get("https://mixdrop.co/e/abc123").mock(
        return_value=httpx.Response(200, text=mixdrop_html)
    )
    respx.get("https://voe.sx/e/xyz").mock(
        return_value=httpx.Response(200, text=voe_html)
    )

    service = _service(tmp_path)
    outcome = await service.search("Inception", "movie", enrich=False)

    assert len(outcome.results) == 2
    assert outcome.channel_count == 1
    assert outcome.enabled_channels == 1
    assert outcome.tmdb_enabled is False
    first = next(result for result in outcome.results if result.title.startswith("Inception"))

    resolved = await service.resolve_result(first)
    assert resolved.streams
    assert {stream.resolver_name for stream in resolved.streams} == {"mixdrop", "voe"}
    assert all(stream.headers.get("User-Agent") for stream in resolved.streams)
    assert all(stream.headers.get("Referer") for stream in resolved.streams)


@respx.mock
async def test_online_service_enriches_results_with_tmdb(tmp_path: Path) -> None:
    search_html = (FIXTURES / "search.html").read_text(encoding="utf-8")
    respx.get("https://one.invalid/search?q=Inception").mock(
        return_value=httpx.Response(200, text=search_html)
    )
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 27205,
                        "title": "Inception",
                        "original_title": "Inception",
                        "release_date": "2010-07-15",
                        "poster_path": "/poster.jpg",
                        "overview": "Un ladro che ruba segreti nei sogni.",
                        "vote_average": 8.4,
                        "popularity": 80.0,
                    }
                ]
            },
        )
    )

    service = _service(tmp_path, tmdb_api_key="test-key")
    outcome = await service.search("Inception", "movie")

    assert outcome.tmdb_enabled is True
    first = next(result for result in outcome.results if result.title.startswith("Inception"))
    assert first.media_item is not None
    assert first.media_item.year == 2010
    assert first.cover_url == "https://image.tmdb.org/t/p/w500/poster.jpg"


async def test_resolve_direct_url_without_network(tmp_path: Path) -> None:
    service = _service(tmp_path)
    outcome = await service.resolve_url("https://cdn.example.com/video.m3u8")
    assert len(outcome.streams) == 1
    stream = outcome.streams[0]
    assert stream.resolver_name == "direct"
    assert stream.mime_type == "application/vnd.apple.mpegurl"
    assert "vlc" in service.vlc_command(stream)


async def test_resolve_direct_url_with_custom_headers(tmp_path: Path) -> None:
    service = _service(tmp_path)
    outcome = await service.resolve_url(
        "https://cdn.example.com/video.m3u8",
        referer="https://example.invalid/watch",
        user_agent="CustomAgent/1.0",
    )
    stream = outcome.streams[0]
    assert stream.headers["User-Agent"] == "CustomAgent/1.0"
    assert stream.headers["Referer"] == "https://example.invalid/watch"


@respx.mock
async def test_resolve_generic_page_with_nested_embed(tmp_path: Path) -> None:
    respx.get("https://page.invalid/watch").mock(
        return_value=httpx.Response(
            200,
            text='<html><iframe src="/player/one"></iframe></html>',
        )
    )
    respx.get("https://page.invalid/player/one").mock(
        return_value=httpx.Response(
            200,
            text='<script>const src = "/media/video.m3u8?token=fresh";</script>',
        )
    )

    service = _service(tmp_path)
    outcome = await service.resolve_url("https://page.invalid/watch")

    assert len(outcome.streams) == 1
    stream = outcome.streams[0]
    assert stream.url == "https://page.invalid/media/video.m3u8?token=fresh"
    assert stream.resolver_name == "direct"
    assert stream.referer == "https://page.invalid/player/one"


def test_stream_source_requires_player_headers() -> None:
    try:
        StreamSource(
            url="https://cdn.example.com/video.mp4",
            headers={"Referer": "https://example.org"},
            resolver_name="direct",
        )
    except Exception as exc:
        assert "user-agent" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("StreamSource avrebbe dovuto rifiutare gli header incompleti")
