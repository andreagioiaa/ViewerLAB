"""Ricerca copertine online per VistoFlow Pro.

Usa servizi pubblici senza bisogno di chiavi API:
    IMDb   -> suggerimenti con poster (film e serie TV)
    TVmaze -> copertine delle serie TV
    iTunes -> copertine delle stagioni TV

Le richieste vengono eseguite in un thread separato tramite i task in fondo
al modulo, così l'interfaccia non si blocca.
"""

import json
import os
import re
import ssl
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from PyQt6.QtCore import QObject, pyqtSignal

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover - fallback senza certifi
    SSL_CONTEXT = ssl.create_default_context()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "VistoFlowPro/1.0 (libreria locale film e serie TV)"
)
MAX_IMAGE_BYTES = 20 * 1024 * 1024
AUTO_IMPORT_SCORE = 60

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_ARTICLES = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
    "the", "a", "an", "of", "di", "del", "della", "dei", "degli", "delle",
}


class CoverSearchError(Exception):
    """Errore di rete o risposta non valida durante la ricerca."""


def normalize_text(text):
    """Normalizza titoli per confronti e punteggi."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.casefold()
    text = re.sub(r"\(\s*(?:19|20)\d{2}\s*\)", " ", text)
    text = re.sub(r"\b(?:19|20)\d{2}\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _tokens(text):
    return {token for token in normalize_text(text).split() if token not in _ARTICLES}


def match_score(query, candidate):
    """Punteggio 0-100 di somiglianza tra query e titolo trovato."""
    query_norm = normalize_text(query)
    candidate_norm = normalize_text(candidate)
    if not query_norm or not candidate_norm:
        return 0

    if query_norm == candidate_norm:
        score = 100
    elif candidate_norm.startswith(query_norm) or query_norm.startswith(candidate_norm):
        score = 85
    elif query_norm in candidate_norm or candidate_norm in query_norm:
        score = 70
    else:
        query_tokens = _tokens(query)
        candidate_tokens = _tokens(candidate)
        if not query_tokens or not candidate_tokens:
            return 0
        ratio = len(query_tokens & candidate_tokens) / len(query_tokens)
        if ratio >= 0.75:
            score = 65
        elif ratio >= 0.5:
            score = 55
        else:
            score = int(ratio * 40)

    query_year = _YEAR_RE.search(str(query or ""))
    candidate_year = _YEAR_RE.search(str(candidate or ""))
    # L'anno nel titolo del file non fa parte del titolo: va rimosso dal
    # confronto, ma se entrambi gli anni sono noti e diversi penalizziamo.
    if query_year and candidate_year and query_year.group(0) != candidate_year.group(0):
        score -= 20
    return max(0, min(100, score))


def _ssl_context():
    return SSL_CONTEXT


def _open(url, timeout):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, image/*, */*",
        },
    )
    try:
        return urllib.request.urlopen(request, timeout=timeout, context=_ssl_context())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CoverSearchError(str(exc)) from exc


def _get_json(url, timeout):
    last_error = None
    for attempt in range(2):
        try:
            with _open(url, timeout) as response:
                payload = response.read(3 * 1024 * 1024)
        except CoverSearchError as exc:
            last_error = exc
            # Wikidata può rispondere 429 quando si fanno più ricerche ravvicinate.
            if "429" in str(exc) and attempt == 0:
                time.sleep(0.7)
                continue
            raise
        except Exception as exc:
            raise CoverSearchError(str(exc)) from exc
        try:
            return json.loads(payload.decode("utf-8", "replace"))
        except ValueError as exc:
            raise CoverSearchError("Risposta non valida dal servizio online") from exc
    raise last_error or CoverSearchError("Servizio online non disponibile")


def _result(title, year, image_url, source, kind, preview_url=None, detail=""):
    title = (title or "").strip()
    image_url = (image_url or "").strip()
    if not title or not image_url:
        return None
    return {
        "title": title,
        "year": str(year or "").strip(),
        "image_url": image_url,
        "preview_url": preview_url or image_url,
        "source": source,
        "kind": kind,
        "detail": detail,
        "score": 0,
    }


def _imdb_suggestions(query, kind, timeout):
    slug = urllib.parse.quote(query.strip().casefold().replace(" ", "_"))
    url = f"https://v3.sg.media-imdb.com/suggestion/x/{slug}.json"
    data = _get_json(url, timeout)
    results = []
    for item in data.get("d", []) or []:
        qid = item.get("qid") or ""
        if kind == "film" and qid not in ("movie", "tvMovie"):
            continue
        if kind == "serie" and qid not in ("tvSeries", "tvMiniSeries"):
            continue
        image = item.get("i") or {}
        image_url = image.get("imageUrl") or ""
        result = _result(
            item.get("l") or "",
            item.get("y") or "",
            image_url,
            "IMDb",
            "serie" if qid in ("tvSeries", "tvMiniSeries") else "film",
            detail=item.get("q") or "",
        )
        if result:
            results.append(result)
    return results


def _tvmaze_shows(query, timeout):
    url = "https://api.tvmaze.com/search/shows?" + urllib.parse.urlencode({"q": query})
    data = _get_json(url, timeout)
    results = []
    for entry in data or []:
        show = entry.get("show") or {}
        image = show.get("image") or {}
        image_url = image.get("original") or image.get("medium") or ""
        year = (show.get("premiered") or "")[:4]
        network = ((show.get("network") or {}).get("name")
                   or (show.get("webChannel") or {}).get("name") or "")
        result = _result(
            show.get("name") or "",
            year,
            image_url,
            "TVmaze",
            "serie",
            preview_url=image.get("medium") or image_url,
            detail=network,
        )
        if result:
            results.append(result)
    return results


def _itunes_tv(query, timeout):
    params = {
        "term": query,
        "media": "tvShow",
        "entity": "tvSeason",
        "limit": "8",
        "country": "US",
    }
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(params)
    data = _get_json(url, timeout)
    results = []
    for item in data.get("results", []) or []:
        artwork = item.get("artworkUrl100") or item.get("artworkUrl60") or ""
        if not artwork:
            continue
        image_url = re.sub(
            r"/\d+x\d+bb\.(jpg|png|webp)$",
            r"/600x600bb.\1",
            artwork,
            flags=re.IGNORECASE,
        )
        name = item.get("collectionName") or item.get("trackName") or ""
        # "Serie, Season 2" -> titolo della serie, mantenendo comunque la
        # stagione nel dettaglio mostrato all'utente.
        clean_name = re.sub(r",\s*(?:Season|Stagione)\s*\d+.*$", "", name, flags=re.IGNORECASE)
        year = (item.get("releaseDate") or "")[:4]
        result = _result(
            clean_name or name,
            year,
            image_url,
            "iTunes",
            "serie",
            detail=name if clean_name != name else "",
        )
        if result:
            results.append(result)
    return results


def _description_matches_kind(description, kind):
    text = (description or "").casefold()
    if not text:
        return False
    if kind == "film":
        return (
            "film" in text
            or "cinematograf" in text
            or "pellicola" in text
        )
    if kind == "serie":
        return any(
            word in text
            for word in (
                "serie televisiva", "serie tv", "miniserie", "webserie",
                "docuserie", "serie animata", "serie web",
            )
        )
    return True


def _wikidata_imdb_results(query, kind, timeout=8):
    """Converte un titolo localizzato in un ID IMDb tramite Wikidata.

    Serve per i film italiani o per i titoli tradotti che IMDb non collega
    direttamente alla query originale.
    """
    params = {
        "action": "wbsearchentities",
        "search": query,
        "language": "it",
        "uselang": "it",
        "type": "item",
        "limit": "8",
        "format": "json",
    }
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(params)
    data = _get_json(url, timeout)
    matches = []
    for item in data.get("search", []) or []:
        description = item.get("description") or ""
        if _description_matches_kind(description, kind):
            matches.append(item)
    if not matches:
        return []

    ids = [item["id"] for item in matches[:3] if item.get("id")]
    if not ids:
        return []
    claims_url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "wbgetentities",
            "ids": "|".join(ids),
            "props": "claims",
            "format": "json",
        }
    )
    claims = _get_json(claims_url, timeout)
    entities = claims.get("entities", {}) or {}
    trusted = len(matches) == 1
    results = []
    for entity_id in ids:
        entity = entities.get(entity_id, {}) or {}
        p345 = (entity.get("claims", {}) or {}).get("P345") or []
        imdb_id = None
        for claim in p345:
            try:
                imdb_id = claim["mainsnak"]["datavalue"]["value"]
            except (KeyError, TypeError):
                continue
            if imdb_id:
                break
        if not imdb_id:
            continue
        try:
            found = _imdb_suggestions(imdb_id, kind, timeout)
        except CoverSearchError:
            continue
        for result in found[:1]:
            result["source"] = "IMDb · Wikidata"
            result["trusted"] = trusted
            result["detail"] = next(
                (
                    item.get("description") or ""
                    for item in matches
                    if item.get("id") == entity_id
                ),
                "",
            )
            results.append(result)
    return results


def _source_imdb(query, kind):
    return _imdb_suggestions(query, kind, timeout=8)


def _source_tvmaze(query, kind):
    return _tvmaze_shows(query, timeout=8)


def _source_itunes(query, kind):
    return _itunes_tv(query, timeout=8)


def search_covers(query, kind=None):
    """Cerca copertine online e restituisce i risultati ordinati per pertinenza."""
    query = (query or "").strip()
    if not query:
        return []

    sources = [_source_imdb]
    if kind in (None, "serie"):
        sources.extend((_source_tvmaze, _source_itunes))

    results = []
    failures = 0
    for source in sources:
        try:
            results.extend(source(query, kind))
        except CoverSearchError:
            failures += 1
        except Exception:
            failures += 1

    if not results and failures == len(sources):
        raise CoverSearchError("Connessione non disponibile")

    def score_results(items):
        for result in items:
            score = match_score(
                query, f"{result['title']} {result.get('year') or ''}"
            )
            if result.get("trusted"):
                score = max(score, 80)
            result["score"] = score

    score_results(results)
    best_score = max((result["score"] for result in results), default=0)
    if best_score < AUTO_IMPORT_SCORE:
        try:
            fallback = _wikidata_imdb_results(query, kind)
        except Exception:
            fallback = []
        if fallback:
            score_results(fallback)
            results.extend(fallback)

    results.sort(
        key=lambda item: (
            -item["score"],
            0 if item["source"].startswith("IMDb") else 1,
            item["title"].casefold(),
        )
    )

    unique = []
    seen = set()
    for result in results:
        key = (
            normalize_text(result["title"]),
            result.get("year") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
        if len(unique) >= 16:
            break
    return unique


def download_cover(url, timeout=20):
    """Scarica i byte di una copertina."""
    if not url:
        raise CoverSearchError("Indirizzo immagine mancante")
    try:
        with _open(url, timeout) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
    except CoverSearchError:
        raise
    except Exception as exc:
        raise CoverSearchError(str(exc)) from exc
    if not data:
        raise CoverSearchError("Immagine vuota")
    if len(data) > MAX_IMAGE_BYTES:
        raise CoverSearchError("Immagine troppo grande")
    return data


def image_extension(url):
    """Estensione da usare per salvare l'immagine scaricata."""
    path = urllib.parse.urlparse(url or "").path.lower()
    extension = os.path.splitext(path)[1]
    if extension in (".png", ".webp", ".bmp", ".gif"):
        return extension
    return ".jpg"


class CoverSearchTask(QObject):
    """Esegue search_covers in un thread demone e ne emette l'esito."""

    results_ready = pyqtSignal(list)
    search_failed = pyqtSignal(str)

    def __init__(self, query, kind, parent=None):
        super().__init__(parent)
        self.query = query
        self.kind = kind

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            results = search_covers(self.query, self.kind)
        except Exception as exc:
            try:
                self.search_failed.emit(str(exc) or "Ricerca non disponibile")
            except RuntimeError:
                pass
        else:
            try:
                self.results_ready.emit(results)
            except RuntimeError:
                pass


class CoverDownloadTask(QObject):
    """Scarica un'immagine in un thread demone."""

    downloaded = pyqtSignal(bytes)
    download_failed = pyqtSignal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            data = download_cover(self.url)
        except Exception as exc:
            try:
                self.download_failed.emit(str(exc) or "Download non riuscito")
            except RuntimeError:
                pass
        else:
            try:
                self.downloaded.emit(data)
            except RuntimeError:
                pass
