from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from cli.main import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def write_channel(directory: Path) -> None:
    payload = {
        "id": "demo",
        "name": "Demo Channel",
        "domain": "https://example.invalid",
        "search_url": "https://example.invalid/search?q={query}",
        "selectors": {
            "item_card": "article.result",
            "title": "h2 a",
            "url": "h2 a",
            "cover": "img.poster",
        },
    }
    (directory / "demo.json").write_text(json.dumps(payload), encoding="utf-8")


def test_channels_list(tmp_path: Path) -> None:
    write_channel(tmp_path)
    result = runner.invoke(
        app,
        ["channels", "list", "--channels-dir", str(tmp_path), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["channels"][0]["id"] == "demo"
    assert payload["errors"] == {}


def test_doctor_json(tmp_path: Path) -> None:
    write_channel(tmp_path)
    result = runner.invoke(
        app,
        ["doctor", "--channels-dir", str(tmp_path), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["channels_found"] == 1
    assert payload["enabled_channels"] == 1
    assert "mixdrop" in payload["resolvers"]


def test_clean_command() -> None:
    result = runner.invoke(app, ["clean", "Inception.2010.1080p.BluRay"])
    assert result.exit_code == 0
    assert "Pulito: Inception" in result.output


@respx.mock
def test_search_json_pipeline(tmp_path: Path) -> None:
    write_channel(tmp_path)
    search_html = (FIXTURES / "search.html").read_text(encoding="utf-8")
    respx.get("https://example.invalid/search?q=Inception").mock(
        return_value=httpx.Response(200, text=search_html)
    )
    result = runner.invoke(
        app,
        [
            "search",
            "Inception",
            "--channels-dir",
            str(tmp_path),
            "--json",
            "--no-metadata",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["channels"] == 1
    assert len(payload["results"]) == 2
    assert payload["results"][0]["channel_id"] == "demo"
    assert payload["errors"] == {}


def test_resolve_command_json() -> None:
    result = runner.invoke(
        app,
        ["resolve", "https://cdn.example/video.m3u8", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["resolver_name"] == "direct"
    assert payload["headers"]["User-Agent"]
    assert payload["headers"]["Referer"] == "https://cdn.example/"


@respx.mock
def test_search_resolve_pipeline(tmp_path: Path) -> None:
    write_channel(tmp_path)
    search_html = (FIXTURES / "search.html").read_text(encoding="utf-8")
    detail_html = (FIXTURES / "detail_mixdrop.html").read_text(encoding="utf-8")
    mixdrop_html = (FIXTURES / "mixdrop.html").read_text(encoding="utf-8")
    respx.get("https://example.invalid/search?q=Inception").mock(
        return_value=httpx.Response(200, text=search_html)
    )
    respx.get("https://example.invalid/movie/inception").mock(
        return_value=httpx.Response(200, text=detail_html)
    )
    respx.get("https://mixdrop.co/e/abc123").mock(
        return_value=httpx.Response(200, text=mixdrop_html)
    )
    result = runner.invoke(
        app,
        [
            "search",
            "Inception",
            "--channels-dir",
            str(tmp_path),
            "--json",
            "--no-metadata",
            "--resolve",
            "--limit",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert len(payload["streams"]) == 1
    stream = payload["streams"][0]
    assert stream["resolver_name"] == "mixdrop"
    assert stream["url"] == "https://cdn.example/video.m3u8"
    assert stream["headers"]["Referer"] == "https://example.invalid/movie/inception"
    assert stream["vlc_args"][0] == "vlc"

