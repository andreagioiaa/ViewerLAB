"""Verifica che un flusso sia realmente raggiungibile e riproducibile.

Il controllo non si limita all'URL: per gli HLS scarica il manifest, segue le
varianti, verifica la presenza di segmenti e (quando presente) della chiave
AES-128. Per gli altri flussi usa HEAD e, se necessario, una GET con Range.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

from .models import ProbeResult, StreamCandidate
from .sources import DEFAULT_USER_AGENT, detect_kind

MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_RANGE_BYTES = 2048
_DRM_MARKERS = (
    "sample-aes",
    "streamingkeydelivery",
    "playready",
    "widevine",
)


class StreamProbe:
    def __init__(self, timeout: float = 12.0) -> None:
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout, connect=min(8.0, timeout)),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "StreamProbe":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ API

    def probe(self, candidate: StreamCandidate) -> ProbeResult:
        headers = self._headers_for(candidate)
        url = candidate.url.strip()
        if not url.startswith(("http://", "https://")):
            return ProbeResult(
                ok=False,
                url=url,
                error="Sono supportati solo flussi http:// o https://",
            )

        try:
            if self._looks_like_hls(url):
                return self._probe_hls(url, headers, depth=0)
            return self._probe_direct(url, headers, candidate)
        except httpx.TimeoutException:
            return ProbeResult(ok=False, url=url, error="Timeout durante la verifica")
        except httpx.HTTPError as error:
            return ProbeResult(ok=False, url=url, error=f"Errore HTTP: {error}")
        except (OSError, ValueError) as error:
            return ProbeResult(ok=False, url=url, error=f"Errore: {error}")

    # ------------------------------------------------------------- internals

    @staticmethod
    def _headers_for(candidate: StreamCandidate) -> dict[str, str]:
        headers = {
            "User-Agent": candidate.user_agent or DEFAULT_USER_AGENT,
            "Accept": "*/*",
        }
        if candidate.referer:
            headers["Referer"] = candidate.referer
        for name, value in candidate.headers.items():
            if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
                continue
            headers[name] = value
        return headers

    @staticmethod
    def _looks_like_hls(url: str) -> bool:
        return urlparse(url).path.lower().endswith((".m3u8", ".m3u"))

    def _probe_direct(
        self, url: str, headers: dict[str, str], candidate: StreamCandidate
    ) -> ProbeResult:
        response = self._probe_resource(url, headers)
        if not response.ok:
            return ProbeResult(ok=False, url=url, final_url=response.final_url, error=response.error)

        content_type = response.content_type.lower()
        if content_type.startswith("text/html") or content_type.startswith("application/xhtml"):
            return ProbeResult(
                ok=False,
                url=url,
                final_url=response.final_url,
                status=response.status,
                content_type=response.content_type,
                error="La risposta è una pagina HTML, non un flusso video",
            )

        kind = candidate.kind if candidate.kind not in ("", "auto") else detect_kind(url)
        return ProbeResult(
            ok=True,
            url=url,
            final_url=response.final_url,
            status=response.status,
            kind=kind,
            content_type=response.content_type,
            size=response.size,
            details="HEAD/Range raggiungibile",
        )

    def _probe_hls(self, url: str, headers: dict[str, str], depth: int) -> ProbeResult:
        if depth > 2:
            return ProbeResult(ok=False, url=url, error="Troppi livelli di playlist HLS")

        text, response = self._fetch_manifest(url, headers)
        if text is None:
            return ProbeResult(
                ok=False,
                url=url,
                final_url=str(response.url) if response is not None else "",
                status=response.status_code if response is not None else 0,
                error="Manifest HLS non raggiungibile",
            )

        lowered = text.lower()
        if any(marker in lowered for marker in _DRM_MARKERS):
            return ProbeResult(
                ok=False,
                url=url,
                final_url=str(response.url),
                status=response.status_code,
                kind="hls",
                error="Il manifest usa DRM non supportato",
            )

        if "#extm3u" not in lowered:
            return ProbeResult(
                ok=False,
                url=url,
                final_url=str(response.url),
                status=response.status_code,
                kind="hls",
                error="Il contenuto non è un manifest HLS valido",
            )

        base_url = str(response.url)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        is_master = any(line.startswith("#EXT-X-STREAM-INF") for line in lines)

        if is_master:
            variants = self._playlist_uris(lines, base_url, master=True)
            if not variants:
                return ProbeResult(
                    ok=False,
                    url=url,
                    final_url=base_url,
                    status=response.status_code,
                    kind="hls",
                    error="Playlist master senza varianti",
                )
            child = self._probe_hls(variants[0], headers, depth + 1)
            if not child.ok:
                return ProbeResult(
                    ok=False,
                    url=url,
                    final_url=base_url,
                    status=response.status_code,
                    kind="hls",
                    variants=len(variants),
                    error=f"Variante non raggiungibile: {child.error}",
                )
            child.url = url
            child.variants = len(variants)
            child.details = f"Master con {len(variants)} varianti"
            return child

        segments = self._playlist_uris(lines, base_url, master=False)
        init_segment = self._init_segment(lines, base_url)
        key_uri = self._key_uri(lines, base_url)

        if init_segment:
            init_result = self._probe_resource(init_segment, headers)
            if not init_result.ok:
                return ProbeResult(
                    ok=False,
                    url=url,
                    final_url=base_url,
                    status=response.status_code,
                    kind="hls",
                    segments=len(segments),
                    error=f"Init segment non raggiungibile: {init_result.error}",
                )

        if key_uri:
            key_result = self._probe_resource(key_uri, headers)
            if not key_result.ok:
                return ProbeResult(
                    ok=False,
                    url=url,
                    final_url=base_url,
                    status=response.status_code,
                    kind="hls",
                    segments=len(segments),
                    error=f"Chiave AES-128 non raggiungibile: {key_result.error}",
                )

        if not segments:
            return ProbeResult(
                ok=True,
                url=url,
                final_url=base_url,
                status=response.status_code,
                kind="hls",
                content_type=response.headers.get("content-type", ""),
                details="Manifest valido senza segmenti (playlist live vuota?)",
            )

        first_segment = self._probe_resource(segments[0], headers)
        if not first_segment.ok:
            return ProbeResult(
                ok=False,
                url=url,
                final_url=base_url,
                status=response.status_code,
                kind="hls",
                segments=len(segments),
                error=f"Primo segmento non raggiungibile: {first_segment.error}",
            )

        return ProbeResult(
            ok=True,
            url=url,
            final_url=base_url,
            status=response.status_code,
            kind="hls",
            content_type=response.headers.get("content-type", ""),
            size=first_segment.size,
            segments=len(segments),
            details=f"{len(segments)} segmenti, primo leggibile",
        )

    def _fetch_manifest(
        self, url: str, headers: dict[str, str]
    ) -> tuple[str | None, httpx.Response | None]:
        with self._client.stream("GET", url, headers=headers) as response:
            if response.status_code >= 400:
                response.read()
                return None, response
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_MANIFEST_BYTES:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8", errors="replace"), response

    @staticmethod
    def _playlist_uris(lines: list[str], base_url: str, master: bool) -> list[str]:
        uris: list[str] = []
        if master:
            for index, line in enumerate(lines):
                if line.startswith("#EXT-X-STREAM-INF"):
                    for candidate in lines[index + 1 :]:
                        if not candidate.startswith("#"):
                            uris.append(urljoin(base_url, candidate))
                            break
        else:
            for line in lines:
                if not line.startswith("#"):
                    uris.append(urljoin(base_url, line))
        return uris

    @staticmethod
    def _init_segment(lines: list[str], base_url: str) -> str | None:
        for line in lines:
            if line.startswith("#EXT-X-MAP"):
                match = re.search(r'URI="([^"]+)"', line)
                if match:
                    return urljoin(base_url, match.group(1))
        return None

    @staticmethod
    def _key_uri(lines: list[str], base_url: str) -> str | None:
        for line in lines:
            if line.startswith("#EXT-X-KEY") and "METHOD=AES-128" in line.upper():
                match = re.search(r'URI="([^"]+)"', line)
                if match:
                    return urljoin(base_url, match.group(1))
        return None

    def _probe_resource(self, url: str, headers: dict[str, str]) -> ProbeResult:
        try:
            head = self._client.head(url, headers=headers)
            content_type = head.headers.get("content-type", "")
            if head.status_code in (200, 206) and not content_type.lower().startswith(
                "text/html"
            ):
                size = _content_length(head)
                if size > 0 or content_type.lower().startswith(("video/", "audio/")):
                    return ProbeResult(
                        ok=True,
                        url=url,
                        final_url=str(head.url),
                        status=head.status_code,
                        content_type=content_type,
                        size=size,
                    )
        except httpx.HTTPError:
            pass

        ranged = dict(headers)
        ranged["Range"] = f"bytes=0-{_RANGE_BYTES - 1}"
        with self._client.stream("GET", url, headers=ranged) as response:
            content_type = response.headers.get("content-type", "")
            size = _content_range_total(response) or _content_length(response)
            first = b""
            for chunk in response.iter_bytes():
                first = chunk[:_RANGE_BYTES]
                break
            ok = response.status_code in (200, 206) and bool(first)
            if not ok:
                return ProbeResult(
                    ok=False,
                    url=url,
                    final_url=str(response.url),
                    status=response.status_code,
                    content_type=content_type,
                    error=f"HTTP {response.status_code} o risposta vuota",
                )
            if content_type.lower().startswith("text/html") and first.lstrip().startswith(b"<"):
                return ProbeResult(
                    ok=False,
                    url=url,
                    final_url=str(response.url),
                    status=response.status_code,
                    content_type=content_type,
                    error="La risposta è HTML",
                )
            return ProbeResult(
                ok=True,
                url=url,
                final_url=str(response.url),
                status=response.status_code,
                content_type=content_type,
                size=size or len(first),
            )


def _content_length(response: httpx.Response) -> int:
    try:
        return int(response.headers.get("content-length", "0"))
    except (TypeError, ValueError):
        return 0


def _content_range_total(response: httpx.Response) -> int:
    value = response.headers.get("content-range", "")
    match = re.search(r"/(\d+)$", value)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0
