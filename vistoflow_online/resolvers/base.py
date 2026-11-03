"""Interfaccia base dei resolver video."""

from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlparse

import httpx

from ..models import StreamSource


def host_matches(url: str, domains: tuple[str, ...]) -> bool:
    """True se l'host dell'URL appartiene a uno dei domini indicati."""

    host = (urlparse(url).hostname or "").lower()
    for domain in domains:
        domain = domain.lower()
        if host == domain or host.endswith("." + domain):
            return True
    return False


class BaseResolver(ABC):
    """Contratto comune a tutti i resolver."""

    name: str = "base"
    priority: int = 100
    domains: tuple[str, ...] = ()

    def can_handle(self, url: str) -> bool:
        """Indica se il resolver riconosce l'URL."""

        return bool(self.domains) and host_matches(url, self.domains)

    @abstractmethod
    async def resolve(
        self,
        url: str,
        client: httpx.AsyncClient,
        *,
        referer: str | None = None,
    ) -> StreamSource:
        """Risolve l'URL e restituisce un flusso con header obbligatori."""
