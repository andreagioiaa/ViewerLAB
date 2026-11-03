"""Modelli Pydantic condivisi da canali, resolver e metadati online."""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MediaType(StrEnum):
    """Tipo di contenuto gestito dal Media Center."""

    movie = "movie"
    tv = "tv"
    unknown = "unknown"


class MediaItem(BaseModel):
    """Metadati arricchiti, principalmente provenienti da TMDB."""

    model_config = ConfigDict(extra="allow")

    tmdb_id: int | None = None
    title: str
    original_title: str | None = None
    year: int | None = None
    media_type: MediaType = MediaType.unknown
    poster_url: str | None = None
    overview: str | None = None
    rating: float | None = None
    raw_title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """Risultato di ricerca proveniente da un canale."""

    model_config = ConfigDict(extra="allow")

    channel_id: str
    channel_name: str
    title: str
    page_url: str
    cover_url: str | None = None
    media_item: MediaItem | None = None
    score: float = 0.0
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("page_url")
    @classmethod
    def _absolute_page_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("page_url deve essere un URL assoluto http/https")
        return value


class StreamSource(BaseModel):
    """Flusso video risolto, completo degli header necessari al player."""

    model_config = ConfigDict(extra="allow")

    url: str
    headers: dict[str, str]
    quality: str | None = None
    mime_type: str | None = None
    resolver_name: str
    referer: str | None = None
    expires_at: str | None = None
    subtitles: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def _absolute_stream_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("url del flusso non valido")
        return value

    @model_validator(mode="after")
    def _require_player_headers(self) -> StreamSource:
        lowered = {
            key.lower(): value
            for key, value in self.headers.items()
            if value is not None
        }
        missing = [
            name for name in ("user-agent", "referer") if not lowered.get(name)
        ]
        if missing:
            raise ValueError(
                "headers obbligatori mancanti: " + ", ".join(missing)
            )
        if not self.referer:
            self.referer = lowered["referer"]
        return self


class ChannelSelectors(BaseModel):
    """Selettori CSS per interpretare la pagina di ricerca di un canale."""

    model_config = ConfigDict(extra="allow")

    item_card: str
    title: str
    url: str
    cover: str | None = None


class ChannelConfig(BaseModel):
    """Schema di configurazione di un canale JSON/YAML."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    domain: str | None = None
    search_url: str
    selectors: ChannelSelectors
    detail_selectors: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    priority: int = 100
    parser_options: dict[str, Any] = Field(default_factory=dict)
    source_path: str | None = None

    @field_validator("id", "name")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("campo obbligatorio vuoto")
        return value

    @field_validator("domain")
    @classmethod
    def _absolute_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("domain deve iniziare con http:// o https://")
        return value or None

    @model_validator(mode="after")
    def _check_query_placeholder(self) -> ChannelConfig:
        if "{query}" not in self.search_url:
            raise ValueError("search_url deve contenere il segnaposto {query}")
        if not self.search_url.startswith(("http://", "https://")) and not self.domain:
            raise ValueError(
                "search_url deve essere assoluto oppure domain deve essere presente"
            )
        return self


class SearchReport(BaseModel):
    """Risultato aggregato della ricerca su più canali."""

    query: str
    media_type: MediaType = MediaType.unknown
    results: list[SearchResult] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)
    timings: dict[str, float] = Field(default_factory=dict)


class ResolveReport(BaseModel):
    """Risultato aggregato della risoluzione di più URL."""

    streams: list[StreamSource] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)


@dataclass(slots=True)
class PlayRequest:
    """Flusso da riprodurre e informazioni per rigenerarlo se scade.

    ``source_result`` indica una pagina di dettaglio di un canale: in caso di
    errore VLC il sistema può risolverla di nuovo con i selettori del canale.
    ``source_url`` indica invece una pagina o un link diretto generico.
    """

    stream: StreamSource
    title: str
    source_url: str | None = None
    source_result: SearchResult | None = None
    referer: str | None = None
    headers: dict[str, str] = dataclass_field(default_factory=dict)
    user_agent: str | None = None
    is_refresh: bool = False

    @property
    def can_refresh(self) -> bool:
        return bool(self.source_result or self.source_url)
