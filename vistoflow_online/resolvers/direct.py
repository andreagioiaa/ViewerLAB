"""Resolver per URL media diretti (HLS/MP4)."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from ..config import DEFAULT_USER_AGENT
from ..models import StreamSource
from .base import BaseResolver
from .js_unpacker import mime_for_url
from .registry import register_resolver


@register_resolver
class DirectStreamResolver(BaseResolver):
    """Gestisce URL che puntano già a un file .m3u8 o .mp4."""

    name = "direct"
    priority = 1

    def can_handle(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        return path.endswith((".m3u8", ".mp4"))

    async def resolve(
        self,
        url: str,
        client: httpx.AsyncClient,
        *,
        referer: str | None = None,
    ) -> StreamSource:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}/"
        stream_referer = referer or origin
        user_agent = client.headers.get("User-Agent") or DEFAULT_USER_AGENT
        return StreamSource(
            url=url,
            headers={
                "User-Agent": user_agent,
                "Referer": stream_referer,
                "Origin": origin.rstrip("/"),
            },
            mime_type=mime_for_url(url),
            resolver_name=self.name,
            referer=stream_referer,
            metadata={"direct": True},
        )
