"""Metadati, pulizia titoli e arricchimento TMDB."""

from .title_cleaner import clean_title, extract_year, normalize_for_match, score_title
from .tmdb import TMDBClient

__all__ = [
    "TMDBClient",
    "clean_title",
    "extract_year",
    "normalize_for_match",
    "score_title",
]
