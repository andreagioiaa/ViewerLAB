"""Resolver HTML generico, con supporto al classico JS packer."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx

from ..config import DEFAULT_USER_AGENT
from ..errors import ResolverError
from ..http import request_with_retry
from ..models import StreamSource
from .base import BaseResolver
from .js_unpacker import extract_stream_urls, mime_for_url, unpack_all

_QUALITY_RE = re.compile(r"(2160p|1080p|720p|480p|360p|4k|uhd)", re.IGNORECASE)
_RELATIVE_STREAM_RE = re.compile(
    r"""['"](/[^"'<>\\\s]+?\.(?:m3u8|mp4)(?:\?[^"'<>\\\s]*)?)['"]""",
    re.IGNORECASE,
)


class HTMLStreamResolver(BaseResolver):
    """Legge una pagina host, decodifica i packer e cerca un URL media."""

    async def resolve(
        self,
        url: str,
        client: httpx.AsyncClient,
        *,
        referer: str | None = None,
    ) -> StreamSource:
        request_referer = referer or url
        response = await request_with_retry(
            client,
            "GET",
            url,
            headers={"Referer": request_referer},
        )
        page_url = str(response.url)
        html = response.text

        unpacked_parts: list[str] = []
        try:
            unpacked_parts = unpack_all(html)
        except Exception:
            # Un packer malformato non deve impedire il parsing del resto.
            unpacked_parts = []

        candidates = extract_stream_urls("\n".join(unpacked_parts))
        if not candidates:
            candidates = extract_stream_urls(html)
        if not candidates:
            for match in _RELATIVE_STREAM_RE.finditer(html):
                candidate = urljoin(page_url, match.group(1))
                if candidate not in candidates:
                    candidates.append(candidate)
        if not candidates:
            raise ResolverError(f"Nessun flusso video trovato su {self.name}")

        stream_url = candidates[0]
        parsed_page = urlparse(page_url)
        origin = f"{parsed_page.scheme}://{parsed_page.netloc}/"
        quality_match = _QUALITY_RE.search(stream_url)
        user_agent = client.headers.get("User-Agent") or DEFAULT_USER_AGENT
        return StreamSource(
            url=stream_url,
            headers={
                "User-Agent": user_agent,
                "Referer": referer or page_url,
                "Origin": origin.rstrip("/"),
            },
            quality=quality_match.group(1) if quality_match else None,
            mime_type=mime_for_url(stream_url),
            resolver_name=self.name,
            referer=referer or page_url,
            metadata={"page_url": page_url},
        )
