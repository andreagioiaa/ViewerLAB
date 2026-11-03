from __future__ import annotations

import httpx
import pytest
import respx

from vistoflow_online.errors import MetadataError
from vistoflow_online.metadata.tmdb import TMDBClient
from vistoflow_online.models import MediaType

MOVIE_PAYLOAD = {
    "results": [
        {
            "id": 27205,
            "title": "Inception",
            "original_title": "Inception",
            "release_date": "2010-07-15",
            "poster_path": "/poster.jpg",
            "overview": "Un ladro che ruba segreti nei sogni.",
            "vote_average": 8.4,
            "vote_count": 30000,
            "popularity": 80.0,
        }
    ]
}


@respx.mock
async def test_tmdb_movie_enrichment_and_cache() -> None:
    route = respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(200, json=MOVIE_PAYLOAD)
    )
    async with httpx.AsyncClient() as client:
        tmdb = TMDBClient("test-key", client)
        item = await tmdb.search("Inception.2010.1080p", "movie")
        assert item is not None
        assert item.title == "Inception"
        assert item.year == 2010
        assert item.media_type == MediaType.movie
        assert item.poster_url == "https://image.tmdb.org/t/p/w500/poster.jpg"
        assert item.rating == 8.4
        assert "sogni" in (item.overview or "")

        cached = await tmdb.search("Inception.2010.1080p", "movie")
        assert cached is not None
        assert cached.tmdb_id == item.tmdb_id
    assert route.call_count == 1


@respx.mock
async def test_tmdb_language_fallback() -> None:
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        side_effect=[
            httpx.Response(200, json={"results": []}),
            httpx.Response(200, json=MOVIE_PAYLOAD),
        ]
    )
    async with httpx.AsyncClient() as client:
        item = await TMDBClient("test-key", client, language="it-IT").search(
            "Inception",
            "movie",
        )
    assert item is not None
    assert item.metadata["tmdb_language"] == "en-US"


async def test_tmdb_requires_api_key() -> None:
    async with httpx.AsyncClient() as client:
        tmdb = TMDBClient(None, client)
        assert tmdb.enabled is False
        with pytest.raises(MetadataError):
            await tmdb.search("Inception", "movie")

