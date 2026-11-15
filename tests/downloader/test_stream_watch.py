"""«Guarda»: il pannello risolve il flusso e lo consegna al player di ViewerLAB."""

import pytest

from tests.downloader.conftest import enable_open_mode
from vistoflow_dl.core import stream


@pytest.fixture
def played(monkeypatch):
    calls = []
    monkeypatch.setattr(stream, "_player", lambda *args: calls.append(args))
    return calls


def test_a_film_is_resolved_and_handed_to_the_player(client, played, monkeypatch):
    enable_open_mode()
    monkeypatch.setattr(stream, "film_stream",
                        lambda film_id, domain: {"url": f"https://vix/{film_id}", "referer": domain})

    response = client.post("/api/stream/film/42", json={"title": "Film"})

    assert response.status_code == 200
    assert played == [("https://vix/42", "example.test", "Film", "sc:film:42")]


def test_episodes_and_anime_have_their_own_roads(client, played, monkeypatch):
    enable_open_mode()
    monkeypatch.setattr(stream, "episode_stream",
                        lambda tv, ep, domain: {"url": f"tv/{tv}/{ep}", "referer": "r"})
    monkeypatch.setattr(stream, "anime_stream", lambda ep: {"url": f"anime/{ep}", "referer": "r"})

    assert client.post("/api/stream/tv/7/episode/9", json={}).status_code == 200
    assert client.post("/api/stream/anime/episode/5", json={"title": "A"}).status_code == 200
    assert [(c[0], c[3]) for c in played] == [("tv/7/9", "sc:tv:7:9"), ("anime/5", "au:5")]


def test_a_failed_resolution_plays_nothing(client, played, monkeypatch):
    enable_open_mode()

    def boom(*_):
        raise RuntimeError("Cloudflare")

    monkeypatch.setattr(stream, "film_stream", boom)
    response = client.post("/api/stream/film/1", json={})
    assert response.status_code == 502
    assert "Cloudflare" in response.json()["detail"]
    assert played == []


def test_without_vistoflow_there_is_no_player(client, monkeypatch):
    enable_open_mode()
    monkeypatch.setattr(stream, "_player", None)
    assert client.post("/api/stream/film/1", json={}).status_code == 503


class _Response:
    def __init__(self, status):
        self.status_code = status
        self.ok = status == 200


def test_a_playlist_that_refuses_is_retried_with_b1(monkeypatch):
    seen = []

    def fake_get(url, headers, timeout):
        seen.append(url)
        return _Response(200 if "b=1" in url else 403)

    monkeypatch.setattr(stream.requests, "get", fake_get)
    video = {"id": "1", "host": "vixcloud.test"}
    param = {"token": "t", "expires": "9"}

    url = stream._playable(video, param, "https://vixcloud.test/embed/1")

    assert "b=1" in url and len(seen) == 2


def test_a_dead_playlist_is_an_error(monkeypatch):
    monkeypatch.setattr(stream.requests, "get", lambda *a, **k: _Response(404))
    with pytest.raises(RuntimeError, match="404"):
        stream._playable({"id": "1", "host": "h"}, {"token": "t", "expires": "9"}, "r")
