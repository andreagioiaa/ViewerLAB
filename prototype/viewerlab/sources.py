"""Caricamento di cataloghi JSON e API di ricerca dichiarative.

Nessuno scraping HTML: una fonte deve esporre un catalogo JSON (statico o
dinamico) con una struttura documentata. Questo tiene il prototipo generico e
limitato a fonti che l'utente è autorizzato a usare.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

import httpx

from .config import data_dir, resolve_location
from .models import Source, StreamCandidate, _clean_headers

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
MAX_CATALOG_BYTES = 8 * 1024 * 1024


class CatalogError(RuntimeError):
    """Errore durante il caricamento di una fonte."""


def detect_kind(url: str, declared: str = "") -> str:
    declared = (declared or "").lower()
    path = urlparse(url).path.lower()
    if "mpegurl" in declared or path.endswith((".m3u8", ".m3u")):
        return "hls"
    if path.endswith((".mp4", ".m4v", ".webm", ".mkv", ".mov", ".ts")):
        return "mp4"
    return "auto"


def merge_headers(*groups: dict[str, str] | None) -> dict[str, str]:
    merged: dict[str, str] = {}
    for group in groups:
        for name, value in _clean_headers(group).items():
            for existing in [key for key in merged if key.lower() == name.lower()]:
                del merged[existing]
            merged[name] = value
    return merged


class SourceLoader:
    """Scarica e normalizza i risultati di una fonte."""

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout, connect=min(8.0, timeout)),
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json,*/*"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SourceLoader":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ API

    def fetch(self, source: Source, query: str = "") -> list[StreamCandidate]:
        if source.kind == "direct":
            return self._from_direct(source)
        if source.kind == "site":
            from .html_site import search_site

            return search_site(
                source, query, timeout=self._timeout, client=self._client
            )

        location = source.url
        if source.kind == "json_api":
            location = source.search_url.replace("{query}", quote_plus(query))

        payload, resolved_base = self._load_json(location, source)
        return self._parse_catalog(source, payload, resolved_base)

    # ------------------------------------------------------------- internals

    def _from_direct(self, source: Source) -> list[StreamCandidate]:
        if not source.url.startswith(("http://", "https://")):
            raise CatalogError("Il link diretto deve essere http:// o https://")
        title = source.title or source.name
        return [
            StreamCandidate(
                source_id=source.id,
                source_name=source.name,
                title=title,
                url=source.url,
                kind=detect_kind(source.url),
                year=source.year,
                headers=dict(source.headers),
                referer=source.referer,
                user_agent=source.user_agent,
            )
        ]

    def _load_json(self, location: str, source: Source) -> tuple[Any, str | None]:
        kind, path = resolve_location(location, base=data_dir())
        headers = merge_headers(source.headers)

        if kind == "http":
            try:
                response = self._client.get(location, headers=headers)
                response.raise_for_status()
            except httpx.HTTPError as error:
                raise CatalogError(f"Richiesta fallita: {error}") from error
            if len(response.content) > MAX_CATALOG_BYTES:
                raise CatalogError("Catalogo troppo grande")
            try:
                payload = response.json()
            except (ValueError, json.JSONDecodeError) as error:
                raise CatalogError("Il catalogo non è JSON valido") from error
            return payload, str(response.url)

        if path is None:
            raise CatalogError("Percorso del catalogo non valido")
        if not path.exists():
            raise CatalogError(f"Catalogo non trovato: {path}")
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise CatalogError(f"Lettura fallita: {error}") from error
        if len(raw) > MAX_CATALOG_BYTES:
            raise CatalogError("Catalogo troppo grande")
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CatalogError("Il catalogo non è JSON valido") from error
        return payload, path.parent.as_uri() + "/"

    def _parse_catalog(
        self, source: Source, payload: Any, resolved_base: str | None
    ) -> list[StreamCandidate]:
        if isinstance(payload, dict):
            items = payload.get("items")
            catalog_base = payload.get("base_url") or resolved_base
        else:
            items = payload
            catalog_base = resolved_base

        if not isinstance(items, list):
            raise CatalogError("Il catalogo deve contenere una lista 'items'")

        results: list[StreamCandidate] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            results.extend(self._parse_item(source, item, catalog_base))

        logging.getLogger(__name__).debug(
            "Fonte %s: %d elementi", source.name, len(results)
        )
        return results

    def _parse_item(
        self, source: Source, item: dict[str, Any], base: str | None
    ) -> list[StreamCandidate]:
        title = str(item.get("title") or item.get("name") or "").strip()
        if not title:
            return []

        item_year = item.get("year")
        try:
            year = int(item_year) if item_year not in (None, "") else None
        except (TypeError, ValueError):
            year = None

        declared_kind = str(item.get("kind") or "").strip()
        headers = merge_headers(source.headers, item.get("headers") if isinstance(item.get("headers"), dict) else None)
        referer = str(item.get("referer") or source.referer or "").strip()
        user_agent = str(item.get("user_agent") or source.user_agent or "").strip()
        page_url = str(item.get("page") or item.get("page_url") or "").strip()
        poster = str(item.get("poster") or item.get("cover") or "").strip()
        description = str(item.get("description") or item.get("plot") or "").strip()

        streams: list[str] = []
        for field in ("stream", "url", "stream_url", "link"):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                streams.append(value.strip())
                break
        extra_streams = item.get("streams")
        if isinstance(extra_streams, list):
            for entry in extra_streams:
                if isinstance(entry, str) and entry.strip():
                    streams.append(entry.strip())
                elif isinstance(entry, dict):
                    nested = entry.get("url") or entry.get("stream")
                    if isinstance(nested, str) and nested.strip():
                        streams.append(nested.strip())

        candidates: list[StreamCandidate] = []
        seen: set[str] = set()
        for raw_url in streams:
            url = self._absolute_stream_url(raw_url, base)
            if url is None or url in seen:
                continue
            seen.add(url)
            candidates.append(
                StreamCandidate(
                    source_id=source.id,
                    source_name=source.name,
                    title=title,
                    url=url,
                    kind=detect_kind(url, declared_kind),
                    year=year,
                    headers=dict(headers),
                    referer=referer,
                    user_agent=user_agent,
                    page_url=self._absolute_optional(page_url, base),
                    poster=self._absolute_optional(poster, base),
                    description=description,
                )
            )
        return candidates

    @staticmethod
    def _absolute_optional(value: str, base: str | None) -> str:
        if not value:
            return ""
        if value.startswith(("http://", "https://")):
            return value
        if base:
            return urljoin(base, value)
        return ""

    @staticmethod
    def _absolute_stream_url(value: str, base: str | None) -> str | None:
        if value.startswith(("http://", "https://")):
            return value
        if base and base.startswith(("http://", "https://")):
            return urljoin(base, value)
        return None


def load_local_catalog(path: Path) -> list[StreamCandidate]:
    """Utile per test e per il catalogo demo incluso."""
    source = Source(
        id="local",
        name="Catalogo locale",
        kind="catalog",
        url=path.as_uri(),
        enabled=True,
    )
    with SourceLoader() as loader:
        return loader.fetch(source)
