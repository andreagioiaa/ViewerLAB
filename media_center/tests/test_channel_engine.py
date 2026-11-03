from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import respx

from core.channels.engine import ChannelEngine
from core.config import Settings
from core.errors import ChannelError
from core.models import ChannelConfig, MediaType

FIXTURES = Path(__file__).parent / "fixtures"


def make_channel(channel_id: str, base: str, priority: int = 100) -> ChannelConfig:
    return ChannelConfig.model_validate(
        {
            "id": channel_id,
            "name": channel_id.title(),
            "domain": base,
            "search_url": f"{base}/search?q={{query}}",
            "selectors": {
                "item_card": "article.result",
                "title": "h2 a",
                "url": "h2 a",
                "cover": "img.poster",
            },
            "detail_selectors": {"embed_links": "iframe[src], a.embed-link[href]"},
            "priority": priority,
        }
    )


@respx.mock
async def test_search_all_and_embed_detail(tmp_path: Path) -> None:
    search_html = (FIXTURES / "search.html").read_text(encoding="utf-8")
    detail_html = (FIXTURES / "detail.html").read_text(encoding="utf-8")
    respx.get("https://one.invalid/search?q=Inception").mock(
        return_value=httpx.Response(200, text=search_html)
    )
    respx.get("https://two.invalid/search?q=Inception").mock(
        return_value=httpx.Response(404, text="not found")
    )
    respx.get("https://one.invalid/movie/inception").mock(
        return_value=httpx.Response(200, text=detail_html)
    )

    settings = Settings(channels_dir=tmp_path)
    channels = [
        make_channel("one", "https://one.invalid"),
        make_channel("two", "https://two.invalid", priority=10),
    ]
    async with httpx.AsyncClient() as client:
        async with ChannelEngine(settings, client=client, channels=channels) as engine:
            report = await engine.search_all("Inception", media_type="movie")
            assert report.media_type == MediaType.movie
            assert len(report.results) == 2
            assert report.errors
            assert "two" in report.errors
            assert report.timings["one"] >= 0

            first = next(
                result for result in report.results if result.page_url.endswith("/inception")
            )
            embeds = await engine.find_embed_urls(first)
            assert "https://mixdrop.co/e/abc123" in embeds
            assert "https://voe.sx/e/xyz" in embeds


async def test_search_without_channels(tmp_path: Path) -> None:
    settings = Settings(channels_dir=tmp_path)
    async with httpx.AsyncClient() as client:
        async with ChannelEngine(settings, client=client, channels=[]) as engine:
            with pytest.raises(ChannelError):
                await engine.search_all("Inception")


async def test_search_runs_channels_in_parallel(tmp_path: Path) -> None:
    search_html = (FIXTURES / "search.html").read_text(encoding="utf-8")
    seen = 0
    barrier = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen
        seen += 1
        if seen >= 2:
            barrier.set()
        await asyncio.wait_for(barrier.wait(), timeout=1.0)
        return httpx.Response(200, text=search_html)

    transport = httpx.MockTransport(handler)
    settings = Settings(channels_dir=tmp_path)
    channels = [
        make_channel("one", "https://one.invalid"),
        make_channel("two", "https://two.invalid"),
    ]
    async with httpx.AsyncClient(transport=transport) as client:
        async with ChannelEngine(settings, client=client, channels=channels) as engine:
            report = await engine.search_all("Inception")
    assert seen == 2
    assert report.errors == {}

