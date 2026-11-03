from __future__ import annotations

from pathlib import Path

from core.channels.parser import ensure_absolute, parse_detail_embeds, parse_search_results
from core.models import ChannelConfig

FIXTURES = Path(__file__).parent / "fixtures"


def make_channel(**overrides) -> ChannelConfig:
    payload = {
        "id": "example",
        "name": "Example",
        "domain": "https://example.invalid",
        "search_url": "https://example.invalid/search?q={query}",
        "selectors": {
            "item_card": "article.result",
            "title": "h2 a",
            "url": "h2 a",
            "cover": "img.poster",
        },
        "detail_selectors": {"embed_links": "iframe[src], a.embed-link[href]"},
    }
    payload.update(overrides)
    return ChannelConfig.model_validate(payload)


def test_parse_search_results() -> None:
    channel = make_channel()
    html = (FIXTURES / "search.html").read_text(encoding="utf-8")
    results = parse_search_results(
        html,
        channel,
        "https://example.invalid/search?q=Inception",
    )
    assert len(results) == 2
    assert results[0].title == "Inception (2010) 1080p"
    assert results[0].page_url == "https://example.invalid/movie/inception"
    assert results[0].cover_url == "https://example.invalid/img/inception.jpg"
    assert results[1].title == "Dune: Parte Due 2024"
    assert results[1].page_url == "https://example.invalid/movie/dune"


def test_parse_detail_embeds() -> None:
    channel = make_channel()
    html = (FIXTURES / "detail.html").read_text(encoding="utf-8")
    urls = parse_detail_embeds(html, channel, "https://example.invalid/movie/inception")
    assert urls == [
        "https://mixdrop.co/e/abc123",
        "https://voe.sx/e/xyz",
    ]


def test_parse_detail_direct_media_in_script() -> None:
    channel = make_channel(detail_selectors={})
    html = (FIXTURES / "detail_direct.html").read_text(encoding="utf-8")
    urls = parse_detail_embeds(html, channel, "https://example.invalid/movie/inception")
    assert "https://mixdrop.co/e/abc123" in urls
    assert "https://cdn.example.invalid/trailer/inception.mp4" in urls


def test_ensure_absolute() -> None:
    assert ensure_absolute("/movie/1", "https://example.invalid") == (
        "https://example.invalid/movie/1"
    )
