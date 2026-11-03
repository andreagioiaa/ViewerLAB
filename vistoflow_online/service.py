"""Pipeline online di VistoFlow: canali, metadati TMDB e flussi VLC.

Il modulo è volutamente indipendente da Qt: la GUI lo esegue in un thread
separato tramite ``online_dialog``. Ogni operazione crea il proprio client
HTTP, così può essere eseguita in un event loop dedicato senza condividere
oggetti asincroni tra thread.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .channels import ChannelEngine, load_channels_with_errors, parse_generic_embeds
from .config import Settings, load_settings
from .errors import ChannelError, MediaCenterError, MetadataError
from .http import create_client, request_with_retry
from .metadata import clean_title
from .metadata.tmdb import TMDBClient
from .models import MediaType, ResolveReport, SearchReport, SearchResult, StreamSource
from .resolvers import ResolverEngine

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchOutcome:
    """Risultato completo di una ricerca, pronto per la GUI."""

    query: str
    media_type: MediaType
    results: list[SearchResult] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    channel_count: int = 0
    enabled_channels: int = 0
    tmdb_enabled: bool = False


@dataclass(slots=True)
class ResolveOutcome:
    """Flussi trovati per un risultato e relativi errori isolati."""

    streams: list[StreamSource] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    candidates: list[str] = field(default_factory=list)
    title: str = ""


def _media_type(value: str | MediaType) -> MediaType:
    if isinstance(value, MediaType):
        return value
    try:
        return MediaType(str(value).lower())
    except ValueError:
        return MediaType.unknown


class OnlineService:
    """Facciata unica usata dall'interfaccia VistoFlow."""

    def __init__(
        self,
        app_config: dict[str, Any] | None = None,
        channels_dir: Path | str | None = None,
    ) -> None:
        self.settings: Settings = load_settings(channels_dir, app_config)

    # --------------------------------------------------------------- canali
    @property
    def channels_dir(self) -> Path:
        return self.settings.channels_dir

    def channel_summary(self) -> tuple[int, int, dict[str, str]]:
        """Restituisce (canali totali, attivi, errori di caricamento)."""

        channels, errors = load_channels_with_errors(self.settings.channels_dir)
        return len(channels), sum(1 for channel in channels if channel.enabled), errors

    # -------------------------------------------------------------- ricerca
    async def search(
        self,
        query: str,
        media_type: str | MediaType = "auto",
        *,
        year: int | None = None,
        limit: int = 40,
        enrich: bool = True,
    ) -> SearchOutcome:
        """Cerca sui canali configurati e arricchisce i risultati con TMDB."""

        query = (query or "").strip()
        if not query:
            raise ChannelError("Inserisci un titolo da cercare")
        requested = _media_type(media_type)
        errors: dict[str, str] = {}
        warnings: list[str] = []

        async with create_client(self.settings) as client:
            async with ChannelEngine(self.settings, client=client) as engine:
                errors.update(engine.load_errors)
                total_channels = len(engine.channels)
                enabled = sum(1 for channel in engine.channels if channel.enabled)
                if not total_channels:
                    detail = ""
                    if errors:
                        detail = "\n\nErrori di configurazione:\n" + "\n".join(
                            f"• {name}: {message}"
                            for name, message in list(errors.items())[:8]
                        )
                    raise ChannelError(
                        "Nessun canale configurato. Apri la cartella dei canali "
                        f"e aggiungi un file JSON/YAML.\n\n"
                        f"{self.settings.channels_dir}{detail}"
                    )
                if not enabled:
                    raise ChannelError(
                        "Nessun canale attivo. Imposta \"enabled\": true in almeno "
                        f"un file dentro:\n{self.settings.channels_dir}"
                    )

                report: SearchReport = await engine.search_all(query, requested)
                errors.update(report.errors)
                results = report.results[: max(1, limit)]

                if enrich and results:
                    if self.settings.tmdb_api_key:
                        tmdb = TMDBClient(
                            self.settings.tmdb_api_key,
                            client,
                            language=self.settings.tmdb_language,
                            timeout=self.settings.request_timeout,
                        )
                        await self._enrich_results(
                            tmdb, results, requested, year=year, errors=errors
                        )
                    else:
                        warnings.append(
                            "TMDB non configurato: poster, trama e voto non sono "
                            "disponibili. Puoi aggiungere la chiave dal menu "
                            "«⋯» della ricerca online."
                        )

        return SearchOutcome(
            query=query,
            media_type=requested,
            results=results,
            errors=errors,
            warnings=warnings,
            channel_count=total_channels,
            enabled_channels=enabled,
            tmdb_enabled=bool(self.settings.tmdb_api_key),
        )

    async def _enrich_results(
        self,
        tmdb: TMDBClient,
        results: list[SearchResult],
        media_type: MediaType,
        *,
        year: int | None,
        errors: dict[str, str],
    ) -> None:
        semaphore = asyncio.Semaphore(4)
        requested = media_type.value if media_type != MediaType.unknown else "auto"

        async def enrich_one(result: SearchResult) -> None:
            async with semaphore:
                try:
                    item = await tmdb.search(
                        clean_title(result.title) or result.title,
                        requested,
                        year=year,
                    )
                except MetadataError as exc:
                    errors[f"tmdb:{result.channel_name}:{result.title}"] = str(exc)
                    return
                except Exception as exc:  # pragma: no cover - difensivo
                    errors[f"tmdb:{result.channel_name}:{result.title}"] = (
                        str(exc) or type(exc).__name__
                    )
                    return
                if item is not None:
                    result.media_item = item
                    if item.poster_url:
                        result.cover_url = item.poster_url

        # Arricchisce i primi risultati: gli altri restano comunque selezionabili.
        await asyncio.gather(
            *(enrich_one(result) for result in results[:20]),
            return_exceptions=True,
        )

    # ----------------------------------------------------------- risoluzione
    async def resolve_result(self, result: SearchResult) -> ResolveOutcome:
        """Da un risultato di canale ai flussi pronti per VLC."""

        errors: dict[str, str] = {}
        candidates: list[str] = []
        title = self._display_title(result)

        async with create_client(self.settings) as client:
            async with ChannelEngine(self.settings, client=client) as channel_engine:
                errors.update(channel_engine.load_errors)
                resolver = ResolverEngine(
                    client,
                    timeout=self.settings.resolver_timeout,
                    concurrency=self.settings.concurrency,
                )

                if resolver.can_handle(result.page_url):
                    candidates = [result.page_url]
                else:
                    try:
                        candidates = await channel_engine.find_embed_urls(result)
                    except MediaCenterError as exc:
                        errors[f"detail:{result.page_url}"] = str(exc)
                    except Exception as exc:  # pragma: no cover - difensivo
                        errors[f"detail:{result.page_url}"] = (
                            str(exc) or type(exc).__name__
                        )

                if not candidates and resolver.can_handle(result.page_url):
                    candidates = [result.page_url]
                if not candidates:
                    errors.setdefault(
                        "detail",
                        "Nessun embed o flusso video trovato nella pagina dettaglio.",
                    )
                    return ResolveOutcome(
                        errors=errors, candidates=[], title=title
                    )

                report: ResolveReport = await resolver.resolve_many(
                    candidates,
                    referer=result.page_url,
                )
                errors.update(report.errors)
                return ResolveOutcome(
                    streams=report.streams,
                    errors=errors,
                    candidates=candidates,
                    title=title,
                )

    async def resolve_url(
        self,
        url: str,
        *,
        referer: str | None = None,
        headers: dict[str, str] | None = None,
        user_agent: str | None = None,
    ) -> ResolveOutcome:
        """Risolve un URL diretto, un host supportato o una pagina generica.

        Se il link non è un media diretto e non appartiene a un resolver noto,
        la pagina viene scaricata e vengono cercati iframe, tag video e URL
        HLS/MP4 anche dentro gli script. I link di embed sconosciuti vengono
        aperti una volta per estrarre il media finale.
        """

        url = (url or "").strip()
        if not url:
            raise MediaCenterError("Inserisci un URL da risolvere")
        if urlparse(url).scheme not in ("http", "https"):
            raise MediaCenterError("L'URL deve iniziare con http:// o https://")

        request_headers = {
            str(key): str(value)
            for key, value in (headers or {}).items()
            if value
        }
        if referer and not any(key.lower() == "referer" for key in request_headers):
            request_headers["Referer"] = referer

        async with create_client(self.settings) as client:
            if user_agent:
                client.headers["User-Agent"] = user_agent
            resolver = ResolverEngine(
                client,
                timeout=self.settings.resolver_timeout,
                concurrency=self.settings.concurrency,
            )
            candidates: list[str] = []
            referers: dict[str, str] = {}
            embed_errors: dict[str, str] = {}
            page_title = self._url_title(url)

            if resolver.can_handle(url):
                candidates = [url]
            else:
                try:
                    response = await request_with_retry(
                        client,
                        "GET",
                        url,
                        headers=request_headers or None,
                    )
                except MediaCenterError as exc:
                    return ResolveOutcome(
                        errors={"page": str(exc)},
                        candidates=[url],
                        title=page_title,
                    )

                page_url = str(response.url)
                found = parse_generic_embeds(response.content, page_url)
                if not found:
                    return ResolveOutcome(
                        errors={
                            "page": (
                                "Nessun iframe, player o flusso HLS/MP4 trovato "
                                "nella pagina. Verifica il link o indica una "
                                "pagina sorgente diversa."
                            )
                        },
                        candidates=[url],
                        title=page_title,
                    )

                for candidate in found:
                    if resolver.can_handle(candidate):
                        candidates.append(candidate)
                        continue
                    # Un iframe può contenere il player vero e proprio.
                    try:
                        nested = await request_with_retry(
                            client,
                            "GET",
                            candidate,
                            headers=request_headers or None,
                        )
                    except MediaCenterError as exc:
                        message = str(exc)
                        if "403" in message:
                            message += (
                                " · il player potrebbe richiedere una sessione "
                                "browser o cookie"
                            )
                        embed_errors[candidate] = message
                        candidates.append(candidate)
                        continue
                    nested_url = str(nested.url)
                    nested_candidates = parse_generic_embeds(
                        nested.content, nested_url
                    )
                    if nested_candidates:
                        for nested_candidate in nested_candidates:
                            candidates.append(nested_candidate)
                            referers[nested_candidate] = nested_url
                    else:
                        embed_errors[candidate] = (
                            "Il player di embed non espone un flusso HLS/MP4 "
                            "nella pagina HTML."
                        )
                        candidates.append(candidate)
                candidates = list(dict.fromkeys(candidates))
                if not referers and page_url:
                    referers = {candidate: page_url for candidate in candidates}
                referer = referer or page_url

            report = await resolver.resolve_many(
                candidates,
                referer=referer,
                referers=referers,
            )
            errors = dict(report.errors)
            errors.update(embed_errors)
            if not report.streams and not errors:
                errors["page"] = "Nessun flusso video riproducibile trovato."
            return ResolveOutcome(
                streams=report.streams,
                errors=errors,
                candidates=candidates,
                title=page_title,
            )

    # ------------------------------------------------------------- VLC
    @staticmethod
    def header(stream: StreamSource, name: str) -> str | None:
        for key, value in stream.headers.items():
            if key.lower() == name.lower() and value:
                return value
        return None

    @classmethod
    def vlc_args(cls, stream: StreamSource) -> list[str]:
        """Argomenti per un VLC esterno, con UA e Referer del flusso."""

        args = ["vlc"]
        user_agent = cls.header(stream, "user-agent")
        referer = cls.header(stream, "referer")
        if user_agent:
            args.extend(["--http-user-agent", user_agent])
        if referer:
            args.extend(["--http-referrer", referer])
        args.append(stream.url)
        return args

    @classmethod
    def vlc_command(cls, stream: StreamSource) -> str:
        args = cls.vlc_args(stream)
        if os.name == "nt":
            return subprocess.list2cmdline(args)
        return shlex.join(args)

    @staticmethod
    def _url_title(url: str) -> str:
        parsed = urlparse(url)
        name = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        return name or parsed.netloc or url

    @staticmethod
    def _display_title(result: SearchResult) -> str:
        if result.media_item is not None:
            return result.media_item.title
        return result.title


__all__ = ["OnlineService", "ResolveOutcome", "SearchOutcome"]
