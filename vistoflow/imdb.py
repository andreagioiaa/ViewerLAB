"""Metadati IMDb tramite Cinemeta (lo stesso servizio usato da Stream Goat).

Cinemeta espone i dati IMDb senza chiave API:
- ricerca:  /catalog/{movie|series}/top/search={query}.json
- dettagli: /meta/{movie|series}/{tt…}.json  (voto, durata, cast, regia, generi,
  trama, locandina, sfondo, episodi).

Le risposte vengono messe in cache su disco (``imdb_cache.json`` nella cartella
dati) per non ripetere le richieste a ogni avvio.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://v3-cinemeta.strem.io"
CACHE_TTL = 14 * 24 * 3600
TYPES = ("movie", "series")
_IMDB_ID = re.compile(r"\btt\d{5,10}\b")


@dataclass
class Title:
    """Scheda IMDb normalizzata."""

    imdb_id: str
    kind: str  # "movie" | "series"
    name: str
    year: str = ""
    poster: str = ""
    background: str = ""
    rating: str = ""
    runtime: str = ""
    genres: list[str] = field(default_factory=list)
    director: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    description: str = ""
    seasons: int = 0
    episodes: int = 0
    tmdb_id: int = 0  # per riconoscere lo stesso film nel motore di download

    @property
    def url(self) -> str:
        return f"https://www.imdb.com/title/{self.imdb_id}/"

    @property
    def library_kind(self) -> str:
        return "serie" if self.kind == "series" else "film"

    def summary(self) -> str:
        """Riga compatta: ★ voto · durata · generi."""
        parts = []
        if self.rating:
            parts.append(f"★ {self.rating}")
        if self.year:
            parts.append(self.year)
        if self.runtime:
            parts.append(self.runtime)
        if self.genres:
            parts.append(", ".join(self.genres[:3]))
        return "  ·  ".join(parts)


def _bigger_poster(url: str) -> str:
    # Cinemeta restituisce /poster/small/: la versione medium è più nitida
    return url.replace("/poster/small/", "/poster/medium/") if url else ""


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [value] if isinstance(value, str) and value else []


def _parse(meta: dict, kind: str) -> Title:
    videos = meta.get("videos") or []
    seasons = {video.get("season") for video in videos if video.get("season")}
    return Title(
        imdb_id=str(meta.get("imdb_id") or meta.get("id") or ""),
        kind=str(meta.get("type") or kind),
        name=str(meta.get("name") or ""),
        year=str(meta.get("releaseInfo") or meta.get("year") or ""),
        poster=_bigger_poster(str(meta.get("poster") or "")),
        background=str(meta.get("background") or ""),
        rating=str(meta.get("imdbRating") or ""),
        runtime=str(meta.get("runtime") or ""),
        genres=_as_list(meta.get("genres") or meta.get("genre")),
        director=_as_list(meta.get("director")),
        cast=_as_list(meta.get("cast")),
        description=str(meta.get("description") or ""),
        seasons=len(seasons),
        episodes=sum(1 for video in videos if video.get("season")),
        tmdb_id=int(meta.get("moviedb_id") or 0) if str(meta.get("moviedb_id") or "").isdigit() else 0,
    )


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _first_year(text: str) -> int | None:
    match = re.search(r"(19|20)\d{2}", text or "")
    return int(match.group(0)) if match else None


class ImdbClient:
    """Client Cinemeta sincrono e thread-safe con cache su disco."""

    def __init__(
        self,
        cache_path: Path | None = None,
        client: httpx.Client | None = None,
        timeout: float = 12.0,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "ViewerLAB/1.0", "Accept": "application/json"},
        )
        self._cache_path = cache_path
        self._lock = threading.Lock()
        self._cache: dict[str, dict] = {}
        if cache_path is not None:
            try:
                self._cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._cache = {}

    # ------------------------------------------------------------- HTTP/cache
    def _get(self, path: str) -> dict:
        return self._get_url(BASE_URL + path, path)

    def _get_url(self, url: str, key: str) -> dict:
        path = key
        now = time.time()
        with self._lock:
            hit = self._cache.get(path)
        if hit and now - hit.get("t", 0) < CACHE_TTL:
            return hit["data"]
        try:
            response = self._client.get(url)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            if hit:  # meglio un dato vecchio che nessun dato
                return hit["data"]
            raise ImdbError(f"IMDb non raggiungibile: {error}") from error
        with self._lock:
            self._cache[path] = {"t": now, "data": data}
        self._save()
        return data

    def _save(self) -> None:
        if self._cache_path is None:
            return
        with self._lock:
            payload = json.dumps(self._cache, ensure_ascii=False)
        try:
            tmp = self._cache_path.with_suffix(".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self._cache_path)
        except OSError:
            LOGGER.debug("Cache IMDb non salvata", exc_info=True)

    # ---------------------------------------------------------------- API
    def search(self, query: str, kind: str | None = None, limit: int = 30) -> list[Title]:
        """Cerca film e/o serie. ``query`` può anche essere un ID ``tt…``."""
        query = (query or "").strip()
        if not query:
            return []
        direct = _IMDB_ID.search(query)
        if direct:
            for item_kind in ([kind] if kind else TYPES):
                try:
                    return [self.details(direct.group(0), item_kind)]
                except ImdbError:
                    continue
            return []
        results: list[Title] = []
        for item_kind in ([kind] if kind else TYPES):
            data = self._get(f"/catalog/{item_kind}/top/search={quote(query)}.json")
            results.extend(_parse(meta, item_kind) for meta in data.get("metas") or [])
        target = normalize(query)
        # i titoli esatti prima, poi l'ordine di popolarità di Cinemeta
        results.sort(key=lambda title: normalize(title.name) != target)
        return [title for title in results if title.imdb_id][:limit]

    def details(self, imdb_id: str, kind: str = "movie") -> Title:
        data = self._get(f"/meta/{kind}/{imdb_id}.json")
        meta = data.get("meta")
        if not meta:
            raise ImdbError(f"Titolo IMDb non trovato: {imdb_id}")
        return _parse(meta, kind)

    def match(self, title: str, year: str | int | None = None, library_kind: str = "film") -> Title | None:
        """Trova la scheda IMDb più probabile per un file della libreria."""
        kind = "series" if library_kind == "serie" else "movie"
        wanted_year = _first_year(str(year or "")) or _first_year(title)
        clean = re.sub(r"\(?(19|20)\d{2}\)?", " ", title)
        target = normalize(clean)
        if not target:
            return None
        candidates = self.search(clean, kind, limit=10)

        def year_ok(candidate: Title) -> bool:
            found = _first_year(candidate.year)
            return not (wanted_year and found and abs(found - wanted_year) > 1)

        # Cinemeta ordina già per pertinenza e riconosce i titoli italiani
        # ("Salvate il soldato Ryan" → "Saving Private Ryan"): si preferisce il
        # titolo identico, poi l'anno indicato nel nome del file, poi il primo.
        exact = [c for c in candidates if normalize(c.name) == target and year_ok(c)]
        same_year = [c for c in candidates[:5] if wanted_year and _first_year(c.year) == wanted_year]
        plausible = [c for c in candidates[:5] if year_ok(c)]
        best = (exact or same_year or plausible or [None])[0]
        if best is None:
            return None
        return self.details(best.imdb_id, best.kind)

    def close(self) -> None:
        self._client.close()


class ImdbError(Exception):
    """Errore di rete o titolo inesistente."""


def to_dict(title: Title) -> dict:
    return asdict(title)


def from_dict(data: dict) -> Title | None:
    try:
        return Title(**{key: data[key] for key in Title.__dataclass_fields__ if key in data})
    except TypeError:
        return None


_shared: ImdbClient | None = None
_shared_lock = threading.Lock()


def shared_client() -> ImdbClient:
    """Client condiviso con cache in ``<cartella dati>/imdb_cache.json``."""
    global _shared
    with _shared_lock:
        if _shared is None:
            from .config import data_dir

            _shared = ImdbClient(cache_path=data_dir() / "imdb_cache.json")
        return _shared
