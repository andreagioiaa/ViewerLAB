"""Client HTTP asincrono condiviso, con retry e timeout."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .config import Settings
from .errors import MediaCenterError

LOGGER = logging.getLogger(__name__)
RETRY_STATUS = {429, 500, 502, 503, 504}


def create_client(settings: Settings) -> httpx.AsyncClient:
    """Crea un AsyncClient con header, redirect e limiti coerenti con il progetto."""

    return httpx.AsyncClient(
        headers={
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
        },
        follow_redirects=True,
        timeout=httpx.Timeout(settings.request_timeout),
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
    )


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRY_STATUS
    return False


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 2,
    timeout: float | None = None,
    **kwargs,
) -> httpx.Response:
    """Esegue una richiesta con retry su errori di rete e status temporanei.

    I dettagli dell'URL non vengono mai inclusi nei messaggi d'errore per non
    esporre eventuali chiavi API passate come query string.
    """

    host = urlsplit(url).netloc or url
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max(1, retries + 1)),
            wait=wait_exponential(multiplier=0.25, max=2.0),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        ):
            with attempt:
                request_kwargs = dict(kwargs)
                if timeout is not None:
                    request_kwargs["timeout"] = timeout
                response = await client.request(
                    method,
                    url,
                    **request_kwargs,
                )
                if response.status_code in RETRY_STATUS:
                    raise httpx.HTTPStatusError(
                        f"Status temporaneo {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response
    except httpx.HTTPStatusError as exc:
        raise MediaCenterError(
            f"HTTP {exc.response.status_code} da {host}"
        ) from exc
    except httpx.HTTPError as exc:
        raise MediaCenterError(
            f"Errore HTTP da {host}: {type(exc).__name__}"
        ) from exc
    raise MediaCenterError(f"Richiesta HTTP non completata per {host}")
