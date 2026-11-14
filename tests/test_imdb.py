import httpx

from vistoflow.imdb import ImdbClient, from_dict, to_dict

SEARCH = {
    "metas": [
        {"id": "tt1", "imdb_id": "tt1", "type": "movie", "name": "Forrest Gump 2", "releaseInfo": "2030"},
        {"id": "tt0109830", "imdb_id": "tt0109830", "type": "movie", "name": "Forrest Gump",
         "releaseInfo": "1994", "poster": "https://images.metahub.space/poster/small/tt0109830/img"},
    ]
}
META = {
    "meta": {
        "imdb_id": "tt0109830", "type": "movie", "name": "Forrest Gump", "releaseInfo": "1994",
        "imdbRating": "8.8", "runtime": "142 min", "genres": ["Drama", "Romance"],
        "director": ["Robert Zemeckis"], "cast": ["Tom Hanks", "Robin Wright"],
        "description": "Plot", "poster": "https://images.metahub.space/poster/small/tt0109830/img",
    }
}


def _client(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if "/catalog/" in request.url.path:
            return httpx.Response(200, json=SEARCH)
        return httpx.Response(200, json=META)

    return ImdbClient(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_search_puts_exact_title_first():
    results = _client([]).search("forrest gump", "movie")
    assert results[0].imdb_id == "tt0109830"
    assert results[0].poster.endswith("/poster/medium/tt0109830/img")


def test_match_library_file_returns_full_details(tmp_path):
    calls = []
    title = _client(calls).match("Forrest Gump (1994)", library_kind="film")
    assert title is not None
    assert (title.rating, title.runtime, title.cast[0]) == ("8.8", "142 min", "Tom Hanks")
    assert "★ 8.8" in title.summary()
    assert from_dict(to_dict(title)) == title


def test_cache_avoids_second_request(tmp_path):
    calls = []
    client = _client(calls)
    client._cache_path = tmp_path / "cache.json"
    client.details("tt0109830")
    client.details("tt0109830")
    assert calls.count("/meta/movie/tt0109830.json") == 1
    assert (tmp_path / "cache.json").is_file()
