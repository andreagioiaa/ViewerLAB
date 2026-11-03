"""Motore asincrono di ricerca sui canali configurati."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import quote_plus, urljoin

import httpx

from ..config import Settings
from ..errors import ChannelError
from ..http import create_client, request_with_retry
from ..models import ChannelConfig, MediaType, SearchReport, SearchResult
from .loader import load_channels_with_errors
from .parser import parse_detail_embeds, parse_search_results

LOGGER = logging.getLogger(__name__)
_ARTICLES = {"il", "lo", "la", "i", "gli", "le", "the", "a", "an", "of", "di"}


def _normalize(value: str) -> set[str]:
    tokens = re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    return {token for token in tokens if token not in _ARTICLES}


def score_match(query: str, title: str) -> float:
    """Punteggio semplice per ordinare i risultati dei canali."""

    left = _normalize(query)
    right = _normalize(title)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left.issubset(right) or right.issubset(left):
        return 0.85
    return len(left & right) / len(left)


class ChannelEngine:
    """Carica i canali e ne esegue le ricerche in parallelo."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        channels: list[ChannelConfig] | None = None,
    ) -> None:
        self.settings = settings
        self._client = client
        self._owns_client = client is None
        if channels is None:
            self._channels, self.load_errors = load_channels_with_errors(settings.channels_dir)
        else:
            self._channels = channels
            self.load_errors = {}
        self._channels_by_id = {channel.id: channel for channel in self._channels}

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ChannelError("Client HTTP non inizializzato: usa 'async with ChannelEngine(...)'")
        return self._client

    @property
    def channels(self) -> list[ChannelConfig]:
        return list(self._channels)

    async def __aenter__(self) -> ChannelEngine:
        if self._client is None:
            self._client = create_client(self.settings)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _search_channel(self, channel: ChannelConfig, query: str) -> list[SearchResult]:
        url = urljoin(channel.domain or "", channel.search_url)
        url = url.replace("{query}", quote_plus(query))
        response = await request_with_retry(
            self.client,
            "GET",
            url,
            headers=channel.headers or None,
        )
        results = parse_search_results(response.content, channel, str(response.url))
        for result in results:
            result.score = score_match(query, result.title)
        return results

    async def _safe_search(
        self,
        channel: ChannelConfig,
        query: str,
        semaphore: asyncio.Semaphore,
        errors: dict[str, str],
        timings: dict[str, float],
    ) -> list[SearchResult]:
        started = time.perf_counter()
        try:
            async with semaphore:
                async with asyncio.timeout(self.settings.channel_timeout):
                    results = await self._search_channel(channel, query)
            return results
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            errors[channel.id] = message
            LOGGER.warning("Canale %s non disponibile: %s", channel.id, message)
            return []
        finally:
            timings[channel.id] = round(time.perf_counter() - started, 3)

    async def search_all(
        self,
        query: str,
        media_type: str | MediaType = MediaType.unknown,
        concurrency: int | None = None,
    ) -> SearchReport:
        """Esegue la ricerca su tutti i canali abilitati in parallelo."""

        if not query.strip():
            raise ChannelError("La query di ricerca è vuota")
        if not self._channels:
            raise ChannelError("Nessun canale configurato")

        try:
            content_type = media_type if isinstance(media_type, MediaType) else MediaType(media_type)
        except ValueError:
            content_type = MediaType.unknown

        errors: dict[str, str] = {}
        timings: dict[str, float] = {}
        semaphore = asyncio.Semaphore(max(1, concurrency or self.settings.concurrency))
        active = [channel for channel in self._channels if channel.enabled]
        if not active:
            raise ChannelError("Nessun canale abilitato")

        collected: list[SearchResult] = []
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(
                    self._safe_search(channel, query, semaphore, errors, timings)
                )
                for channel in active
            ]
        for task in tasks:
            collected.extend(task.result())

        collected.sort(
            key=lambda item: (-item.score, item.channel_name.casefold(), item.title.casefold())
        )
        return SearchReport(
            query=query,
            media_type=content_type,
            results=collected,
            errors=errors,
            timings=timings,
        )

    async def find_embed_urls(self, result: SearchResult) -> list[str]:
        """Apre la pagina dettaglio del risultato e restituisce gli embed trovati."""

        channel = self._channels_by_id.get(result.channel_id)
        if channel is None:
            raise ChannelError(f"Canale sconosciuto: {result.channel_id}")
        response = await request_with_retry(
            self.client,
            "GET",
            result.page_url,
            headers=channel.headers or None,
        )
        return parse_detail_embeds(response.content, channel, str(response.url))
