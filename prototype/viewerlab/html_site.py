"""Ricerca e risoluzione di flussi da siti web HTML.

L'utente configura la **home** di un sito (``url``) e, se serve, l'URL di
ricerca con ``{query}``. Se il modello di ricerca non è indicato, viene
ricavato dalla pagina (OpenSearch, form HTML) oppure provando alcuni
schemi comuni.

I risultati vengono individuati con selettori CSS opzionali
(``item``, ``title``, ``link``, ``cover``) o, in assenza, con un'euristica
sui link ripetuti. La pagina di dettaglio viene poi analizzata per trovare
un flusso riproducibile (``<video>``, ``<source>``, meta ``og:video``,
JSON-LD, link ``.mp4/.m3u8/.webm``, iframe annidati).

Nessun JavaScript viene eseguito e nessun DRM viene aggirato: se il flusso
è generato solo lato client o è protetto, la risoluzione fallisce.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, quote_plus, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from .models import Source, StreamCandidate

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
MAX_HTML_BYTES = 8 * 1024 * 1024
MAX_RESULTS = 60
MEDIA_EXTENSIONS = (".m3u8", ".mp4", ".webm", ".mkv", ".m4v", ".mov")
_MEDIA_RE = re.compile(
    r"""https?:(?:\\?/){2}[^\s"'<>\\]+?\.(?:m3u8|mp4|webm|mkv|m4v|mov)"""
    r"""(?:\?[^\s"'<>\\]*)?""",
    re.IGNORECASE,
)
_HREF_SKIP = re.compile(
    r"(?:/login|/signin|/sign-in|/register|/signup|/account|/cart|/checkout|"
    r"/privacy|/terms|/contact|/about|/faq|/dmca|/help|/search|/tag/|/category/|"
    r"/author/|/page/\d|/wp-login|/feed|/rss)",
    re.IGNORECASE,
)
_DETAIL_HINT = re.compile(
    r"(?:/movie|/film|/watch|/video|/serie|/series|/tv|/title|/anime|/episode|"
    r"/detail|/stream|/play|/media|/v/|/f/)",
    re.IGNORECASE,
)
_SEARCH_PARAMS = ("q", "s", "query", "search", "keyword", "keywords", "term", "text")

_TEMPLATE_CACHE: dict[tuple[str, str], str] = {}


class SiteError(RuntimeError):
    """Errore durante ricerca o risoluzione su un sito HTML."""


class MediaResponse(SiteError):
    """La risorsa richiesta è già un flusso audio/video, non una pagina HTML."""

    def __init__(self, message: str, url: str, content_type: str) -> None:
        super().__init__(message)
        self.url = url
        self.content_type = content_type


def _client(timeout: float) -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(timeout, connect=min(8.0, timeout)),
        headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
    )


def _request_headers(source: Source, referer: str = "") -> dict[str, str]:
    headers = {
        "User-Agent": source.user_agent or DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    if source.referer:
        headers["Referer"] = source.referer
    if referer:
        headers["Referer"] = referer
    for name, value in source.headers.items():
        if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
            continue
        headers[name] = value
    return headers


def _fetch_html(
    client: httpx.Client, url: str, headers: dict[str, str]
) -> tuple[str, str]:
    try:
        with client.stream("GET", url, headers=headers) as response:
            if response.status_code >= 400:
                response.read()
                raise SiteError(f"HTTP {response.status_code} per {url}")
            content_type = response.headers.get("content-type", "").lower()
            if content_type.startswith(("video/", "audio/")) or "mpegurl" in content_type:
                raise MediaResponse(
                    "La pagina richiesta è già un flusso, non HTML",
                    str(response.url),
                    content_type,
                )
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_HTML_BYTES:
                    raise SiteError("Pagina troppo grande")
                chunks.append(chunk)
            content = b"".join(chunks)
            encoding = response.charset_encoding or response.encoding or "utf-8"
            try:
                text = content.decode(encoding, errors="replace")
            except LookupError:
                text = content.decode("utf-8", errors="replace")
            return text, str(response.url)
    except httpx.HTTPError as error:
        raise SiteError(f"Richiesta fallita: {error}") from error


def _soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # pragma: no cover - lxml opzionale
        return BeautifulSoup(html, "html.parser")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _absolute(base: str, href: str) -> str:
    href = href.strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return ""
    return urljoin(base, href)


_MEDIA_QUERY_RE = re.compile(
    r"\.(?:m3u8|m3u|mp4|webm|mkv|m4v|mov)(?:$|[&#;])", re.IGNORECASE
)


def _is_media_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.path.lower().endswith(MEDIA_EXTENSIONS):
        return True
    return bool(_MEDIA_QUERY_RE.search(parsed.query))


def _search_parameter_template(url: str) -> str | None:
    """Se l'URL contiene già un parametro di ricerca, lo rende un modello."""
    parsed = urlparse(url)
    if not parsed.query:
        return None
    params = parse_qs(parsed.query, keep_blank_values=True)
    for key in _SEARCH_PARAMS:
        if key in params:
            params[key] = ["{query}"]
            query = urlencode(params, doseq=True).replace("%7Bquery%7D", "{query}")
            return urlunparse(parsed._replace(query=query))
    return None


def _template_from_discovery(client: httpx.Client, source: Source) -> list[str]:
    """Prova OpenSearch, form GET e schemi comuni sulla home del sito."""
    templates: list[str] = []
    base = source.url.strip()
    headers = _request_headers(source, referer=base)

    try:
        html, final_url = _fetch_html(client, base, headers)
    except SiteError:
        html, final_url = "", base

    if html:
        soup = _soup(html)
        link = soup.find(
            "link",
            attrs={"rel": lambda value: value and "search" in str(value).lower()},
        )
        if link is not None and "opensearch" in str(link.get("type", "")).lower():
            href = _absolute(final_url, str(link.get("href", "")))
            if href:
                try:
                    xml, _ = _fetch_html(client, href, headers)
                    match = re.search(r'<Url[^>]*template="([^"]+)"', xml, re.IGNORECASE)
                    if match:
                        template = (
                            match.group(1)
                            .replace("%7BsearchTerms%7D", "{query}")
                            .replace("{searchTerms}", "{query}")
                        )
                        templates.append(template)
                except SiteError:
                    pass

        for form in soup.find_all("form"):
            method = str(form.get("method", "get")).lower()
            if method != "get":
                continue
            text_input = None
            for field in form.find_all("input"):
                field_type = str(field.get("type", "text")).lower()
                name = str(field.get("name", "")).strip()
                if name and field_type in ("", "text", "search", "query"):
                    text_input = name
                    break
            if not text_input:
                continue
            action = _absolute(final_url, str(form.get("action") or final_url)) or final_url
            parsed = urlparse(action)
            params = parse_qs(parsed.query, keep_blank_values=True)
            params[text_input] = ["{query}"]
            query = urlencode(params, doseq=True).replace("%7Bquery%7D", "{query}")
            templates.append(urlunparse(parsed._replace(query=query)))
            if form.get("action"):
                break

    root = "{uri.scheme}://{uri.netloc}/".format(uri=urlparse(final_url))
    templates.extend(
        [
            urljoin(root, "?s={query}"),
            urljoin(root, "?q={query}"),
            urljoin(root, "search?q={query}"),
            urljoin(root, "search/{query}"),
            urljoin(root, "cerca?q={query}"),
        ]
    )

    seen: set[str] = set()
    unique: list[str] = []
    for template in templates:
        template = template.strip()
        if "{query}" in template and template not in seen:
            seen.add(template)
            unique.append(template)
    return unique


def _extract_items(
    soup: BeautifulSoup, base_url: str, source: Source
) -> list[StreamCandidate]:
    selectors = source.selectors
    if selectors.get("item"):
        return _extract_with_selectors(soup, base_url, source, selectors)
    return _extract_auto(soup, base_url, source)


def _kind_for(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith((".m3u8", ".m3u")) or ".m3u8" in parsed.query.lower():
        return "hls"
    if path.endswith((".mp4", ".webm", ".mkv", ".m4v", ".mov")):
        return "mp4"
    if _MEDIA_QUERY_RE.search(parsed.query):
        return "mp4"
    return "auto"


def _candidate(
    source: Source, title: str, url: str, page_url: str, base_url: str, card=None
) -> StreamCandidate | None:
    if not title or not url:
        return None
    poster = ""
    if card is not None:
        image = card.find("img")
        if image is not None:
            raw = image.get("data-src") or image.get("src") or ""
            if raw:
                poster = _absolute(base_url, str(raw))
    direct = _is_media_url(url)
    return StreamCandidate(
        source_id=source.id,
        source_name=source.name,
        title=_clean_text(title),
        url=url,
        kind=_kind_for(url) if direct else "page",
        headers=dict(source.headers),
        referer=base_url if direct else source.referer,
        user_agent=source.user_agent,
        page_url=page_url,
        poster=poster,
        needs_resolution=not direct,
    )


def _extract_with_selectors(
    soup: BeautifulSoup, base_url: str, source: Source, selectors: dict[str, str]
) -> list[StreamCandidate]:
    results: list[StreamCandidate] = []
    seen: set[str] = set()
    try:
        cards = soup.select(selectors["item"])[:MAX_RESULTS]
    except Exception as error:
        raise SiteError(f"Selettore 'item' non valido: {error}") from error
    for card in cards:
        link_selector = selectors.get("link") or "a[href]"
        title_selector = selectors.get("title") or link_selector
        try:
            link = card.select_one(link_selector)
        except Exception as error:
            raise SiteError(f"Selettore 'link' non valido: {error}") from error
        if link is None:
            continue
        href = _absolute(base_url, str(link.get("href") or link.get("src") or ""))
        if not href:
            continue
        try:
            title_node = card.select_one(title_selector)
        except Exception as error:
            raise SiteError(f"Selettore 'title' non valido: {error}") from error
        title_node = title_node or link
        title = _clean_text(
            title_node.get("title")
            or title_node.get_text(" ", strip=True)
            or link.get("title", "")
        )
        if not title:
            image = card.find("img")
            if image is not None:
                title = _clean_text(str(image.get("alt") or ""))
        candidate = _candidate(source, title, href, href, base_url, card)
        if candidate is not None and candidate.url not in seen:
            seen.add(candidate.url)
            results.append(candidate)
    return results


def _card_for(anchor) -> object:
    node = anchor
    for _ in range(4):
        node = node.parent
        if node is None:
            break
        classes = node.get("class") or []
        if classes or node.name in ("li", "article", "div", "tr"):
            return node
    return anchor.parent


def _extract_auto(
    soup: BeautifulSoup, base_url: str, source: Source
) -> list[StreamCandidate]:
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    anchors: list[tuple[object, str, str, str]] = []
    for anchor in soup.find_all("a", href=True):
        if anchor.find_parent(["nav", "header", "footer", "aside"]):
            continue
        href = _absolute(base_url, str(anchor.get("href", "")))
        if not href or _HREF_SKIP.search(href):
            continue
        title = _clean_text(anchor.get_text(" ", strip=True) or anchor.get("title") or "")
        if not title or len(title) > 180:
            image = anchor.find("img")
            if image is not None:
                title = _clean_text(str(image.get("alt") or ""))
        if not title:
            continue
        card = _card_for(anchor)
        anchor_id = id(card)
        anchors.append((card, href, title, anchor_id))

    if not anchors:
        return []

    groups: dict[tuple[str, tuple[str, ...]], list[tuple[object, str, str]]] = {}
    for card, href, title, _anchor_id in anchors:
        classes = card.get("class") or [] if hasattr(card, "get") else []
        signature = (getattr(card, "name", ""), tuple(classes))
        groups.setdefault(signature, []).append((card, href, title))

    def score(group: list[tuple[object, str, str]]) -> float:
        size = len(group)
        detail_hits = sum(1 for _, href, _ in group if _DETAIL_HINT.search(href))
        return size * 2.0 + detail_hits * 1.5

    best_signature = max(groups, key=lambda key: score(groups[key]))
    best = groups[best_signature]
    if len(best) < 2 and len(groups) > 1:
        # Preferisci un gruppo con link "di dettaglio" se quello più grande è
        # solo navigazione.
        candidates = [
            group for group in groups.values()
            if any(_DETAIL_HINT.search(href) for _, href, _ in group)
        ]
        if candidates:
            best = max(candidates, key=score)

    results: list[StreamCandidate] = []
    seen: set[str] = set()
    for card, href, title in best[:MAX_RESULTS]:
        candidate = _candidate(source, title, href, href, base_url, card)
        if candidate is not None and candidate.url not in seen:
            seen.add(candidate.url)
            results.append(candidate)
    return results


# --------------------------------------------------------------------- API


def search_site(
    source: Source,
    query: str,
    timeout: float = 15.0,
    client: httpx.Client | None = None,
) -> list[StreamCandidate]:
    """Cerca ``query`` sul sito e restituisce le pagine dei contenuti."""
    owns_client = client is None
    client = client or _client(timeout)
    headers = _request_headers(source, referer=source.url)
    try:
        if not query.strip():
            html, final_url = _fetch_html(client, source.url, headers)
            items = _extract_items(_soup(html), final_url, source)
            if items:
                return items

        templates: list[str] = []
        cache_key = (source.id, source.url)
        cached = _TEMPLATE_CACHE.get(cache_key)
        if source.search_url:
            templates.append(source.search_url)
        if cached:
            templates.append(cached)
        if not source.search_url:
            derived = _search_parameter_template(source.url)
            if derived:
                templates.append(derived)
            if not cached:
                templates.extend(_template_from_discovery(client, source))

        seen: set[str] = set()
        unique_templates: list[str] = []
        for template in templates:
            if "{query}" in template and template not in seen:
                seen.add(template)
                unique_templates.append(template)

        for template in unique_templates[:5]:
            url = template.replace("{query}", quote_plus(query))
            try:
                html, final_url = _fetch_html(
                    client, url, _request_headers(source, referer=source.url)
                )
            except SiteError:
                continue
            items = _extract_items(_soup(html), final_url, source)
            if items:
                _TEMPLATE_CACHE[cache_key] = template
                return items
        return []
    finally:
        if owns_client:
            client.close()


def _extract_stream_urls(html: str, base_url: str) -> list[tuple[int, str]]:
    """Estrae URL di flusso con una priorità (più basso = più affidabile)."""
    soup = _soup(html)
    found: list[tuple[int, str]] = []
    seen: set[str] = set()

    def add(raw: str | None, priority: int) -> None:
        if not raw:
            return
        url = _absolute(base_url, str(raw))
        if not url or not url.startswith(("http://", "https://")):
            return
        if not _is_media_url(url) or url in seen:
            return
        seen.add(url)
        found.append((priority, url))

    for tag in ("video", "source"):
        for element in soup.find_all(tag):
            add(element.get("src"), 0)
            add(element.get("data-src"), 0)
            add(element.get("data-url"), 0)

    for meta in soup.find_all("meta"):
        prop = str(meta.get("property") or meta.get("name") or "").lower()
        if prop in (
            "og:video",
            "og:video:url",
            "og:video:secure_url",
            "twitter:player:stream",
        ):
            add(meta.get("content"), 1)

    for element in soup.find_all(attrs={"data-src": True}):
        add(element.get("data-src"), 2)
    for element in soup.find_all(attrs={"data-video": True}):
        add(element.get("data-video"), 2)
    for element in soup.find_all(attrs={"data-file": True}):
        add(element.get("data-file"), 2)

    for anchor in soup.find_all("a", href=True):
        add(anchor.get("href"), 3)

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key, value in node.items():
                    if key.lower() in ("contenturl", "contenturl_", "url") and isinstance(
                        value, str
                    ):
                        add(value, 4)
                    elif isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)

    for match in _MEDIA_RE.finditer(html):
        add(match.group(0).replace("\\/", "/").replace("\\u0026", "&"), 5)

    found.sort(key=lambda item: item[0])
    return found


def _iframe_urls(html: str, base_url: str) -> list[str]:
    soup = _soup(html)
    urls: list[str] = []
    for iframe in soup.find_all("iframe", src=True):
        url = _absolute(base_url, str(iframe.get("src")))
        if url and url.startswith(("http://", "https://")) and url not in urls:
            urls.append(url)
    return urls


def resolve_site(
    source: Source,
    candidate: StreamCandidate,
    timeout: float = 15.0,
    client: httpx.Client | None = None,
) -> list[StreamCandidate]:
    """Apre la pagina del contenuto e restituisce i flussi riproducibili."""
    owns_client = client is None
    client = client or _client(timeout)
    page_url = candidate.page_url or candidate.url
    final_url = page_url
    collected: list[tuple[int, str]] = []
    media_kind = ""
    try:
        try:
            html, final_url = _fetch_html(
                client, page_url, _request_headers(source, referer=source.url)
            )
        except MediaResponse as error:
            # L'URL del contenuto è già un flusso (anche senza estensione).
            final_url = error.url
            collected = [(0, error.url)]
            media_kind = "hls" if "mpegurl" in error.content_type else "mp4"
        else:
            collected = _extract_stream_urls(html, final_url)
            if not collected:
                iframes = _iframe_urls(html, final_url)[:4]
                same_host = [
                    url for url in iframes
                    if urlparse(url).netloc == urlparse(final_url).netloc
                ]
                others = [url for url in iframes if url not in same_host]
                for iframe_url in (same_host + others)[:3]:
                    if _is_media_url(iframe_url):
                        collected = [(0, iframe_url)]
                        break
                    try:
                        frame_html, frame_url = _fetch_html(
                            client, iframe_url, _request_headers(source, referer=final_url)
                        )
                    except SiteError:
                        continue
                    collected = _extract_stream_urls(frame_html, frame_url)
                    if collected:
                        break
    finally:
        if owns_client:
            client.close()

    results: list[StreamCandidate] = []
    seen: set[str] = set()
    for _priority, url in collected:
        if url in seen:
            continue
        seen.add(url)
        kind = media_kind or _kind_for(url)
        results.append(
            StreamCandidate(
                source_id=candidate.source_id,
                source_name=candidate.source_name,
                title=candidate.title,
                url=url,
                kind=kind,
                year=candidate.year,
                headers=dict(source.headers),
                referer=final_url,
                user_agent=source.user_agent,
                page_url=final_url,
                poster=candidate.poster,
                description=candidate.description,
                score=candidate.score,
            )
        )
    return results
