"""Client asincrono per TMDB v3 con cache, rate limit e fallback lingua."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from ..errors import MediaCenterError, MetadataError
from ..http import request_with_retry
from ..models import MediaItem, MediaType
from .title_cleaner import clean_title, score_title

LOGGER = logging.getLogger(__name__)
TMDB_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
IMAGE_ORIGINAL = "https://image.tmdb.org/t/p/original"


class TMDBClient:
    """Arricchisce i titoli con poster, trama, anno e voto TMDB."""

    def __init__(
        self,
        api_key: str | None,
        client: httpx.AsyncClient,
        *,
        language: str = "it-IT",
        cache_ttl: float = 3600.0,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = (api_key or "").strip() or None
        self.client = client
        self.language = language or "it-IT"
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self._cache: dict[tuple[str, str, int | None, str], tuple[float, MediaItem]] = {}
        self._rate_lock = asyncio.Lock()
        self._last_request = 0.0

    @property
    def enabled(self) -> bool:
        return self.api_key is not None

    def _cache_get(self, key: tuple[str, str, int | None, str]) -> MediaItem | None:
        cached = self._cache.get(key)
        if not cached:
            return None
        created_at, item = cached
        if time.monotonic() - created_at > self.cache_ttl:
            self._cache.pop(key, None)
            return None
        return item.model_copy(deep=True)

    async def _throttle(self) -> None:
        async with self._rate_lock:
            elapsed = time.monotonic() - self._last_request
            if elapsed < 0.06:
                await asyncio.sleep(0.06 - elapsed)
            self._last_request = time.monotonic()

    async def _request(
        self,
        endpoint: str,
        query: str,
        language: str,
        year: int | None,
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            raise MetadataError("TMDB_API_KEY non configurata")
        params: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "language": language,
            "include_adult": "false",
            "page": 1,
        }
        if year is not None:
            if endpoint == "movie":
                params["year"] = year
            elif endpoint == "tv":
                params["first_air_date_year"] = year

        await self._throttle()
        try:
            response = await request_with_retry(
                self.client,
                "GET",
                f"{TMDB_BASE}/search/{endpoint}",
                params=params,
                timeout=self.timeout,
            )
        except MediaCenterError as exc:
            # MediaCenterError non contiene la query string con la chiave API.
            raise MetadataError(f"Ricerca TMDB non riuscita: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise MetadataError("Risposta TMDB non valida (JSON)") from exc
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []
        return [item for item in results if isinstance(item, dict)]

    def _to_media_item(
        self,
        result: dict[str, Any],
        *,
        fallback_type: MediaType,
        raw_title: str,
        language: str,
    ) -> MediaItem | None:
        title = result.get("title") or result.get("name")
        if not title:
            return None
        result_type = result.get("media_type")
        if result_type in ("movie", "tv"):
            media_type = MediaType(result_type)
        else:
            media_type = fallback_type
        if media_type == MediaType.unknown:
            media_type = MediaType.movie

        date = result.get("release_date") or result.get("first_air_date") or ""
        year = None
        if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
            year = int(date[:4])
        poster_path = result.get("poster_path")
        poster_url = f"{IMAGE_BASE}{poster_path}" if poster_path else None
        original_poster = f"{IMAGE_ORIGINAL}{poster_path}" if poster_path else None
        rating = result.get("vote_average")
        return MediaItem(
            tmdb_id=result.get("id"),
            title=str(title),
            original_title=(
                result.get("original_title") or result.get("original_name") or str(title)
            ),
            year=year,
            media_type=media_type,
            poster_url=poster_url,
            overview=result.get("overview") or None,
            rating=float(rating) if isinstance(rating, (int, float)) else None,
            raw_title=raw_title,
            metadata={
                "poster_original": original_poster,
                "popularity": result.get("popularity"),
                "vote_count": result.get("vote_count"),
                "tmdb_language": language,
            },
        )

    def _pick_best(
        self,
        results: list[dict[str, Any]],
        *,
        query: str,
        fallback_type: MediaType,
        raw_title: str,
        language: str,
        year: int | None,
    ) -> MediaItem | None:
        best: tuple[float, float, float] | None = None
        best_item: MediaItem | None = None
        for result in results:
            candidate_title = result.get("title") or result.get("name") or ""
            if not candidate_title:
                continue
            if result.get("media_type") == "person":
                continue
            item = self._to_media_item(
                result,
                fallback_type=fallback_type,
                raw_title=raw_title,
                language=language,
            )
            if item is None:
                continue
            title_score = score_title(query, candidate_title)
            year_match = 1.0 if year is not None and item.year == year else 0.0
            popularity = float(result.get("popularity") or 0.0)
            rank = (title_score, year_match, popularity)
            if best is None or rank > best:
                best = rank
                best_item = item
        return best_item

    async def search(
        self,
        raw_title: str,
        media_type: str | MediaType = MediaType.unknown,
        *,
        year: int | None = None,
    ) -> MediaItem | None:
        """Cerca un titolo su TMDB e restituisce il risultato migliore.

        Prova prima la lingua configurata e poi en-US. La chiave API non viene
        mai inclusa in log o eccezioni.
        """

        if not self.enabled:
            raise MetadataError("TMDB_API_KEY non configurata")
        query = clean_title(raw_title)
        if not query:
            return None

        if isinstance(media_type, MediaType):
            requested = media_type.value
        else:
            requested = str(media_type).lower()
        if requested not in ("movie", "tv", "auto", "multi"):
            requested = "auto"

        cache_key = (query.casefold(), requested, year, self.language)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        languages: list[str] = [self.language]
        if self.language.lower() != "en-us":
            languages.append("en-US")

        if requested == "movie":
            endpoints = [("movie", MediaType.movie)]
        elif requested == "tv":
            endpoints = [("tv", MediaType.tv)]
        else:
            endpoints = [
                ("multi", MediaType.unknown),
                ("movie", MediaType.movie),
                ("tv", MediaType.tv),
            ]

        for language in languages:
            for endpoint, fallback_type in endpoints:
                results = await self._request(endpoint, query, language, year)
                item = self._pick_best(
                    results,
                    query=query,
                    fallback_type=fallback_type,
                    raw_title=raw_title,
                    language=language,
                    year=year,
                )
                if item is not None:
                    self._cache[cache_key] = (time.monotonic(), item)
                    return item.model_copy(deep=True)
        return None


__all__ = ["TMDBClient", "TMDB_BASE", "IMAGE_BASE"]
