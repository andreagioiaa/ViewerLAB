"""Ricerca parallela su tutte le fonti abilitate."""

from __future__ import annotations

import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .models import SearchOutcome, Source, SourceError, StreamCandidate
from .sources import CatalogError, SourceLoader

ProgressCallback = Callable[[str, int], None]


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()


def score_candidate(candidate: StreamCandidate, query: str) -> float:
    """Punteggio semplice e prevedibile; 0 significa nessuna corrispondenza."""
    normalized_query = normalize(query)
    normalized_title = normalize(candidate.title)
    if not normalized_query:
        return 0.0
    if not normalized_title:
        return 0.0

    if normalized_title == normalized_query:
        base = 100.0
    elif normalized_title.startswith(normalized_query):
        base = 85.0
    elif any(word.startswith(normalized_query) for word in normalized_title.split()):
        base = 70.0
    elif normalized_query in normalized_title:
        base = 55.0
    else:
        tokens = normalized_query.split()
        if tokens and all(token in normalized_title for token in tokens):
            base = 40.0
        else:
            return 0.0

    year_match = re.search(r"\b(19|20)\d{2}\b", query)
    if year_match and candidate.year:
        if str(candidate.year) == year_match.group(0):
            base += 5.0
    return base


class SourceRepository:
    def __init__(
        self,
        sources: list[Source],
        loader: SourceLoader | None = None,
        max_workers: int = 8,
    ) -> None:
        self.sources = sources
        self.loader = loader or SourceLoader()
        self.max_workers = max_workers

    def close(self) -> None:
        self.loader.close()

    def enabled_sources(self) -> list[Source]:
        return [source for source in self.sources if source.enabled]

    def search(self, query: str, progress: ProgressCallback | None = None) -> SearchOutcome:
        started = time.perf_counter()
        enabled = self.enabled_sources()
        outcome = SearchOutcome()

        if not enabled:
            outcome.elapsed = time.perf_counter() - started
            return outcome

        workers = max(1, min(self.max_workers, len(enabled)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="viewerlab-search") as pool:
            futures = {
                pool.submit(self.loader.fetch, source, query): source for source in enabled
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    raw_candidates = future.result()
                except (CatalogError, OSError, ValueError) as error:
                    outcome.errors.append(
                        SourceError(source.id, source.name, str(error))
                    )
                    if progress:
                        progress(source.name, 0)
                    continue
                except Exception as error:  # difesa: una fonte non deve fermare le altre
                    outcome.errors.append(
                        SourceError(source.id, source.name, f"Errore imprevisto: {error}")
                    )
                    if progress:
                        progress(source.name, 0)
                    continue

                matches: list[StreamCandidate] = []
                for candidate in raw_candidates:
                    score = score_candidate(candidate, query)
                    if score <= 0 and normalize(query):
                        continue
                    candidate.score = score
                    matches.append(candidate)

                outcome.candidates.extend(matches)
                if progress:
                    progress(source.name, len(matches))

        outcome.candidates = self._deduplicate(outcome.candidates)
        outcome.candidates.sort(
            key=lambda item: (-item.score, normalize(item.title), item.year or 0, item.url)
        )
        outcome.elapsed = time.perf_counter() - started
        return outcome

    def fetch_all(self, progress: ProgressCallback | None = None) -> SearchOutcome:
        return self.search("", progress)

    @staticmethod
    def _deduplicate(candidates: list[StreamCandidate]) -> list[StreamCandidate]:
        best: dict[tuple[str, str], StreamCandidate] = {}
        for candidate in candidates:
            key = (normalize(candidate.title), candidate.url)
            current = best.get(key)
            if current is None or candidate.score > current.score:
                best[key] = candidate
        return list(best.values())
