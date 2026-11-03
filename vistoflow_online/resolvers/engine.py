"""Motore di risoluzione parallela dei flussi."""

from __future__ import annotations

import asyncio
import logging

import httpx

from ..errors import ResolverError, UnsupportedResolver
from ..models import ResolveReport, StreamSource
from .registry import find_resolver

LOGGER = logging.getLogger(__name__)


class ResolverEngine:
    """Seleziona il resolver adatto e gestisce più URL in parallelo."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        timeout: float = 25.0,
        concurrency: int = 4,
    ) -> None:
        self.client = client
        self.timeout = max(1.0, timeout)
        self.concurrency = max(1, concurrency)

    def can_handle(self, url: str) -> bool:
        return find_resolver(url) is not None

    async def resolve(
        self,
        url: str,
        *,
        referer: str | None = None,
    ) -> StreamSource:
        resolver = find_resolver(url)
        if resolver is None:
            raise UnsupportedResolver(f"Nessun resolver per {url}")
        return await resolver.resolve(url, self.client, referer=referer)

    async def resolve_many(
        self,
        urls: list[str],
        *,
        concurrency: int | None = None,
        referer: str | None = None,
        referers: dict[str, str] | None = None,
    ) -> ResolveReport:
        """Risolve una lista di URL, isolando gli errori per singolo host."""

        unique: list[str] = []
        seen: set[str] = set()
        for url in urls:
            if not url or url in seen:
                continue
            seen.add(url)
            unique.append(url)

        errors: dict[str, str] = {}
        streams: list[StreamSource] = []
        semaphore = asyncio.Semaphore(max(1, concurrency or self.concurrency))

        async def worker(candidate: str) -> StreamSource | None:
            try:
                async with semaphore:
                    async with asyncio.timeout(self.timeout):
                        return await self.resolve(
                            candidate,
                            referer=(referers or {}).get(candidate, referer),
                        )
            except Exception as exc:
                message = str(exc) or type(exc).__name__
                errors[candidate] = message
                LOGGER.warning("Risoluzione fallita per %s: %s", candidate, message)
                return None

        if unique:
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(worker(url)) for url in unique]
            for task in tasks:
                stream = task.result()
                if stream is not None:
                    streams.append(stream)

        streams.sort(key=lambda stream: (stream.resolver_name, stream.url))
        return ResolveReport(streams=streams, errors=errors)


__all__ = ["ResolverEngine", "ResolverError", "UnsupportedResolver"]
