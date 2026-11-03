"""Parsing HTML generico per i canali configurati."""

from __future__ import annotations

import logging
import re
from html import unescape
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..errors import ChannelError
from ..models import ChannelConfig, SearchResult

LOGGER = logging.getLogger(__name__)

_MEDIA_URL_RE = re.compile(
    r"https?://[^\s\"'<>\\]+?\.(?:m3u8|mp4)(?:\?[^\s\"'<>\\]*)?",
    re.IGNORECASE,
)
_MEDIA_PATH_RE = re.compile(
    r"""["']([^"'\\]+?\.(?:m3u8|mp4)(?:\?[^"'\\]*)?)["']""",
    re.IGNORECASE,
)
_GENERIC_EMBED_SELECTOR = (
    "iframe[src], iframe[data-src], video[src], video source[src], "
    "a[data-embed], a[href*='/e/'], a[href*='embed'], a[href*='player']"
)
_IMAGE_ATTRS = ("src", "data-src", "data-lazy-src", "data-original", "data-url")


def _make_soup(content: str | bytes) -> BeautifulSoup:
    try:
        return BeautifulSoup(content, "lxml")
    except Exception:  # pragma: no cover - fallback se lxml non è disponibile
        return BeautifulSoup(content, "html.parser")


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def _first_attr(element, attrs: tuple[str, ...]) -> str | None:
    if element is None:
        return None
    for attr in attrs:
        value = element.get(attr)
        if value and not value.strip().startswith(
            ("data:", "javascript:", "#", "about:", "blob:")
        ):
            return value
    srcset = element.get("srcset")
    if srcset:
        first = srcset.split(",")[0].strip().split(" ")[0]
        if first:
            return first
    return None


def _absolute_url(value: str | None, base_url: str) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value.startswith(("data:", "javascript:", "#", "about:", "blob:")):
        return None
    resolved = urljoin(base_url, value)
    if not resolved.startswith(("http://", "https://")):
        return None
    return resolved


def parse_search_results(
    content: str | bytes,
    channel: ChannelConfig,
    base_url: str | None = None,
) -> list[SearchResult]:
    """Applica i selettori del canale alla pagina di ricerca.

    Il parser è volutamente generico: nessun selettore o host è hardcodato.
    """

    soup = _make_soup(content)
    base = base_url or channel.domain or ""
    selectors = channel.selectors
    cards = soup.select(selectors.item_card)
    if not cards:
        LOGGER.debug("Nessuna card trovata per il canale %s", channel.id)
        return []

    results: list[SearchResult] = []
    seen: set[str] = set()
    for card in cards:
        title_element = card.select_one(selectors.title)
        if title_element is None:
            title_element = card.find(["h1", "h2", "h3"])
        title = _clean_text(
            title_element.get_text(" ", strip=True) if title_element else ""
        )

        url_element = card.select_one(selectors.url)
        if url_element is None:
            url_element = card.find("a", href=True)
        href = None
        if url_element is not None:
            href = url_element.get("href") or url_element.get("data-href")
        page_url = _absolute_url(href, base)

        if not title or not page_url:
            continue
        if page_url in seen:
            continue
        seen.add(page_url)

        cover_element = (
            card.select_one(selectors.cover) if selectors.cover else card.find("img")
        )
        cover_url = _absolute_url(_first_attr(cover_element, _IMAGE_ATTRS), base)

        results.append(
            SearchResult(
                channel_id=channel.id,
                channel_name=channel.name,
                title=title,
                page_url=page_url,
                cover_url=cover_url,
                raw={"href": href or ""},
            )
        )
    return results


def _collect_embeds(
    soup: BeautifulSoup,
    base_url: str,
    selector: str | None = None,
) -> list[str]:
    elements = soup.select(selector or _GENERIC_EMBED_SELECTOR)
    urls: list[str] = []
    seen: set[str] = set()

    for element in elements:
        raw = _first_attr(element, ("src", "data-src", "data-embed", "href"))
        url = _absolute_url(raw, base_url)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)

    # Alcune pagine espongono già un link HLS/MP4 dentro script o attributi.
    source = str(soup)
    for match in _MEDIA_URL_RE.finditer(source):
        url = unescape(match.group(0))
        if url not in seen:
            seen.add(url)
            urls.append(url)
    for match in _MEDIA_PATH_RE.finditer(source):
        url = _absolute_url(unescape(match.group(1)), base_url)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def parse_generic_embeds(
    content: str | bytes,
    base_url: str,
) -> list[str]:
    """Estrae iframe, player e URL HLS/MP4 da una pagina generica.

    È usata per i link inseriti manualmente, quando non esiste un file di
    configurazione con selettori specifici.
    """

    soup = _make_soup(content)
    return _collect_embeds(soup, base_url)


def parse_detail_embeds(
    content: str | bytes,
    channel: ChannelConfig,
    base_url: str | None = None,
) -> list[str]:
    """Estrae URL di embed o flussi diretti da una pagina dettaglio."""

    soup = _make_soup(content)
    base = base_url or channel.domain or ""
    return _collect_embeds(
        soup,
        base,
        channel.detail_selectors.get("embed_links"),
    )


def ensure_absolute(url: str, base_url: str) -> str:
    """Utility pubblica per normalizzare un URL, con errore esplicito."""

    resolved = _absolute_url(url, base_url)
    if not resolved:
        raise ChannelError(f"URL non valido: {url!r}")
    return resolved
