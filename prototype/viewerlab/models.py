"""Modelli condivisi tra ricerca, verifica e player."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SourceKind = Literal["catalog", "json_api", "direct", "site"]

_SELECTOR_KEYS = ("item", "title", "link", "cover")


def _clean_selectors(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key).strip().lower()
        text = str(value).strip()
        if name in _SELECTOR_KEYS and text and "\n" not in text and "\r" not in text:
            cleaned[name] = text
    return cleaned


def _clean_headers(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key).strip()
        text = str(value)
        if not name or "\r" in text or "\n" in text or ":" in name:
            continue
        cleaned[name] = text
    return cleaned


def _clean_text(value: Any, default: str = "") -> str:
    return str(value).strip() if value is not None else default


@dataclass(slots=True)
class Source:
    """Una fonte configurata dall'utente.

    - ``catalog``: URL (http/https) o percorso locale di un JSON con ``items``.
    - ``json_api``: endpoint di ricerca JSON con ``{query}`` nell'URL.
    - ``direct``: un singolo titolo con URL di flusso diretto.
    - ``site``: sito web HTML; ``url`` è la base e ``search_url`` (opzionale)
      è il modello di ricerca con ``{query}``. I flussi vengono ricavati
      dalle pagine dei risultati.
    """

    id: str
    name: str
    kind: SourceKind = "catalog"
    url: str = ""
    search_url: str = ""
    title: str = ""
    year: int | None = None
    enabled: bool = True
    headers: dict[str, str] = field(default_factory=dict)
    referer: str = ""
    user_agent: str = ""
    selectors: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("L'identificativo della fonte è obbligatorio.")
        if not self.name.strip():
            raise ValueError("Il nome della fonte è obbligatorio.")

        if self.kind in ("catalog", "direct", "site"):
            if not self.url.strip():
                raise ValueError("L'URL è obbligatorio.")
        if self.kind == "json_api":
            if not self.search_url.strip():
                raise ValueError("L'URL di ricerca è obbligatorio.")
            if "{query}" not in self.search_url:
                raise ValueError("L'URL di ricerca deve contenere {query}.")
        if self.kind == "site" and self.search_url and "{query}" not in self.search_url:
            raise ValueError(
                "Per un sito, l'URL di ricerca opzionale deve contenere {query}."
            )

        for label, value in (("URL", self.url), ("URL di ricerca", self.search_url)):
            if value and not value.startswith(("http://", "https://", "@bundled/", "file://")):
                # I cataloghi locali sono ammessi; siti e flussi diretti no.
                if self.kind in ("direct", "site") or label == "URL di ricerca":
                    raise ValueError(f"{label}: sono supportati solo http:// e https://.")
        if self.kind == "site":
            if not self.url.startswith(("http://", "https://")):
                raise ValueError("URL: per un sito sono supportati solo http:// e https://.")
            if self.search_url and not self.search_url.startswith(
                ("http://", "https://")
            ):
                raise ValueError(
                    "URL di ricerca: per un sito sono supportati solo http:// e https://."
                )

        if self.year is not None and not (1800 <= int(self.year) <= 2200):
            raise ValueError("Anno non valido.")
        self.headers = _clean_headers(self.headers)
        self.selectors = _clean_selectors(self.selectors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "url": self.url,
            "search_url": self.search_url,
            "title": self.title,
            "year": self.year,
            "enabled": bool(self.enabled),
            "headers": dict(self.headers),
            "referer": self.referer,
            "user_agent": self.user_agent,
            "selectors": dict(self.selectors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Source":
        kind = str(data.get("kind", "catalog"))
        if kind not in ("catalog", "json_api", "direct", "site"):
            kind = "catalog"
        year = data.get("year")
        try:
            year_value = int(year) if year not in (None, "") else None
        except (TypeError, ValueError):
            year_value = None
        return cls(
            id=_clean_text(data.get("id")),
            name=_clean_text(data.get("name")),
            kind=kind,  # type: ignore[arg-type]
            url=_clean_text(data.get("url")),
            search_url=_clean_text(data.get("search_url")),
            title=_clean_text(data.get("title")),
            year=year_value,
            enabled=bool(data.get("enabled", True)),
            headers=_clean_headers(data.get("headers")),
            referer=_clean_text(data.get("referer")),
            user_agent=_clean_text(data.get("user_agent")),
            selectors=_clean_selectors(data.get("selectors")),
        )


@dataclass(slots=True)
class StreamCandidate:
    """Un risultato di ricerca che punta a un possibile flusso."""

    source_id: str
    source_name: str
    title: str
    url: str
    kind: str = "auto"
    year: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    referer: str = ""
    user_agent: str = ""
    page_url: str = ""
    poster: str = ""
    description: str = ""
    score: float = 0.0
    needs_resolution: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return (self.source_id, self.url)

    def display_year(self) -> str:
        return str(self.year) if self.year else "—"


@dataclass(slots=True)
class ProbeResult:
    """Esito della verifica di raggiungibilità di un flusso."""

    ok: bool
    url: str
    final_url: str = ""
    status: int = 0
    kind: str = ""
    content_type: str = ""
    size: int = 0
    variants: int = 0
    segments: int = 0
    error: str = ""
    details: str = ""

    def label(self) -> str:
        if not self.ok:
            return f"Non disponibile — {self.error or 'errore sconosciuto'}"
        kind = (self.kind or "stream").upper()
        extra = []
        if self.variants:
            extra.append(f"{self.variants} varianti")
        if self.segments:
            extra.append(f"{self.segments} segmenti")
        suffix = f" ({', '.join(extra)})" if extra else ""
        return f"Disponibile — {kind}{suffix}"


@dataclass(slots=True)
class SourceError:
    source_id: str
    source_name: str
    message: str


@dataclass(slots=True)
class SearchOutcome:
    candidates: list[StreamCandidate] = field(default_factory=list)
    errors: list[SourceError] = field(default_factory=list)
    elapsed: float = 0.0
