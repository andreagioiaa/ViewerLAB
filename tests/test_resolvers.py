from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from pydantic import ValidationError

from vistoflow_online.models import PlayRequest, StreamSource
from vistoflow_online.resolvers import ResolverEngine, find_resolver, get_resolvers

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@respx.mock
async def test_mixdrop_resolver_with_packed_js() -> None:
    respx.get("https://mixdrop.co/e/abc123").mock(
        return_value=httpx.Response(200, text=fixture("mixdrop.html"))
    )
    async with httpx.AsyncClient() as client:
        engine = ResolverEngine(client)
        stream = await engine.resolve(
            "https://mixdrop.co/e/abc123",
            referer="https://example.invalid/movie/inception",
        )
    assert stream.url == "https://cdn.example/video.m3u8"
    assert stream.resolver_name == "mixdrop"
    assert stream.mime_type == "application/vnd.apple.mpegurl"
    assert stream.headers["Referer"] == "https://example.invalid/movie/inception"
    assert stream.headers["User-Agent"]


@respx.mock
async def test_voe_resolver() -> None:
    respx.get("https://voe.sx/e/xyz").mock(
        return_value=httpx.Response(200, text=fixture("voe.html"))
    )
    async with httpx.AsyncClient() as client:
        stream = await ResolverEngine(client).resolve("https://voe.sx/e/xyz")
    assert stream.url == "https://cdn.example.invalid/voe/playlist.m3u8"
    assert stream.resolver_name == "voe"


@respx.mock
async def test_streamtape_resolver_keeps_query() -> None:
    respx.get("https://streamtape.com/e/abc").mock(
        return_value=httpx.Response(200, text=fixture("streamtape.html"))
    )
    async with httpx.AsyncClient() as client:
        stream = await ResolverEngine(client).resolve("https://streamtape.com/e/abc")
    assert stream.url == "https://cdn.example.invalid/streamtape/video.mp4?token=abc"
    assert stream.mime_type == "video/mp4"


@respx.mock
async def test_supervideo_resolver() -> None:
    respx.get("https://supervideo.tv/e/abc").mock(
        return_value=httpx.Response(200, text=fixture("supervideo.html"))
    )
    async with httpx.AsyncClient() as client:
        stream = await ResolverEngine(client).resolve("https://supervideo.tv/e/abc")
    assert stream.url == "https://cdn.example.invalid/supervideo/video.mp4"
    assert stream.resolver_name == "supervideo"


async def test_direct_resolver() -> None:
    async with httpx.AsyncClient() as client:
        stream = await ResolverEngine(client).resolve(
            "https://cdn.example.invalid/video.m3u8"
        )
    assert stream.resolver_name == "direct"
    assert stream.headers["Referer"] == "https://cdn.example.invalid/"


async def test_direct_resolver_uses_client_user_agent() -> None:
    async with httpx.AsyncClient(headers={"User-Agent": "CustomUA/1.0"}) as client:
        stream = await ResolverEngine(client).resolve(
            "https://cdn.example.invalid/video.mp4"
        )
    assert stream.headers["User-Agent"] == "CustomUA/1.0"


@respx.mock
async def test_resolve_many_isolates_errors() -> None:
    respx.get("https://mixdrop.co/e/empty").mock(
        return_value=httpx.Response(200, text="<html><body></body></html>")
    )
    async with httpx.AsyncClient() as client:
        report = await ResolverEngine(client).resolve_many(
            ["https://mixdrop.co/e/empty", "https://unsupported.invalid/e/1"]
        )
    assert report.streams == []
    assert len(report.errors) == 2


def test_stream_source_requires_headers() -> None:
    with pytest.raises(ValidationError):
        StreamSource(
            url="https://cdn.example/video.m3u8",
            headers={"User-Agent": "test"},
            resolver_name="test",
        )


def test_play_request_can_refresh_with_source() -> None:
    stream = StreamSource(
        url="https://cdn.example/video.m3u8",
        headers={
            "User-Agent": "test",
            "Referer": "https://example.invalid/watch",
        },
        resolver_name="direct",
    )
    assert PlayRequest(stream=stream, title="Test").can_refresh is False
    assert (
        PlayRequest(
            stream=stream,
            title="Test",
            source_url="https://example.invalid/watch",
        ).can_refresh
        is True
    )


def test_registry() -> None:
    names = {resolver.name for resolver in get_resolvers()}
    assert {"direct", "mixdrop", "voe", "supervideo", "streamtape"} <= names
    assert find_resolver("https://mixdrop.co/e/x").name == "mixdrop"
    assert find_resolver("https://cdn.example/video.m3u8").name == "direct"
    assert find_resolver("https://unknown.invalid/video") is None

