"""Pulizia e normalizzazione dei titoli provenienti da nomi file e pagine web."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

_EXTENSION_RE = re.compile(
    r"\.(?:mkv|mp4|avi|mov|wmv|flv|webm|m4v|ts|m2ts|mpg|mpeg)$",
    re.IGNORECASE,
)
_BRACKETS_RE = re.compile(r"[\[\(\{][^\[\]\(\)\{\}]*[\]\)\}]")
_PARENTHESIZED_YEAR_RE = re.compile(
    r"[\(\[]\s*(?:19|20)\d{2}\s*[\)\]]"
)
_MULTI_SEPARATOR_RE = re.compile(r"[._]+")
_SPACES_RE = re.compile(r"\s+")
_EDGE_SEPARATOR_RE = re.compile(r"^[\s\-–—_|:;,]+|[\s\-–—_|:;,]+$")

_RELEASE_TAGS = (
    "2160p", "1080p", "720p", "480p", "360p", "4k", "8k", "uhd",
    "hdr10+", "hdr10", "hdr", "dolbyvision", "dv", "sdr",
    "webrip", "web-dl", "webdl", "bdrip", "brrip", "bluray",
    "blu-ray", "dvdrip", "hdtv", "hdrip", "hdts", "remux",
    "x264", "x265", "h264", "h265", "hevc", "avc", "10bit", "8bit",
    "aac", "aac2.0", "ac3", "eac3", "dts", "ddp5.1", "dd5.1", "atmos",
    "proper", "repack",
    "ita", "eng", "italian", "english", "sub", "subs", "dub", "multi",
    "md", "yts", "rarbg", "subsplease", "erai", "erai-raws",
    "horriblesubs", "eztv", "ettv", "cmrg", "noname",
)
_TAG_RE = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(re.escape(tag) for tag in sorted(_RELEASE_TAGS, key=len, reverse=True)) + r")(?![a-z0-9])",
    re.IGNORECASE,
)
_CODEC_RE = re.compile(
    r"(?<![a-z0-9])(?:h|hevc|avc|x)\s*[ .]?26[45](?![a-z0-9])",
    re.IGNORECASE,
)
_AUDIO_RE = re.compile(
    r"(?<![a-z0-9])(?:aac|ac3|eac3|dts|ddp?)\s*\d?(?:[ .]\d)?(?![a-z0-9])",
    re.IGNORECASE,
)
_RELEASE_HINT_RE = re.compile(
    r"(?<![a-z0-9])(?:2160p|1080p|720p|480p|360p|4k|uhd|webrip|web-dl|bdrip|brrip|bluray|blu-ray|dvdrip|hdtv|x264|x265|h264|h265|hevc|aac|ac3|eac3|dts|remux)(?![a-z0-9])",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_YEAR_BEFORE_TAG_RE = re.compile(
    r"(?<!\d)((?:19|20)\d{2})(?!\d)(?=\s*[.\-_ ]?\s*(?:"
    r"2160p|1080p|720p|480p|360p|4k|uhd|hdr|web|bd|blu|dvd|hd|"
    r"remux|x264|x265|h264|h265|hevc|aac|ac3|eac3|dts|ita|eng|"
    r"sub|dub|multi)\b)",
    re.IGNORECASE,
)
_TRAILING_YEAR_RE = re.compile(r"\s+((?:19|20)\d{2})\s*$")
_SEASON_EPISODE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"s\d{1,2}\s*e\d{1,3}|"
    r"s\d{1,2}|"
    r"\d{1,2}x\d{1,3}|"
    r"(?:stagione|season)\s*\d{1,2}|"
    r"(?:episodio|episode|ep)\s*\d{1,3}"
    r")(?![a-z0-9])",
    re.IGNORECASE,
)
_TRAILING_EPISODE_RE = re.compile(r"\s+[-–—]\s*\d{1,3}\s*$")
_SITE_RE = re.compile(
    r"(?<![a-z0-9])(?:www\.)?[a-z0-9-]+\.(?:com|net|org|mx|to|sx|tv|cc|me|io|xyz)(?![a-z0-9])",
    re.IGNORECASE,
)
_ARTICLES = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
    "the", "a", "an", "of", "di", "del", "della", "dei", "degli", "delle",
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def extract_year(raw_title: str) -> int | None:
    """Estrae l'ultimo anno plausibile dal titolo, senza usarlo come filtro obbligatorio."""

    matches = list(_YEAR_RE.finditer(raw_title or ""))
    if not matches:
        return None
    year = int(matches[-1].group(1))
    if year > datetime.now().year + 1:
        return None
    return year


def _plausible_year(value: int) -> bool:
    return value <= datetime.now().year + 1


def _remove_release_year(match: re.Match[str]) -> str:
    year = int(match.group(1))
    return " " if _plausible_year(year) else match.group(0)


def _remove_trailing_year(match: re.Match[str]) -> str:
    year = int(match.group(1))
    return " " if _plausible_year(year) else match.group(0)


def clean_title(raw_title: str) -> str:
    """Rimuove tag da release, lingua, qualità, episodi e punteggiatura superflua.

    Non rimuove un anno nudo dal titolo quando non ci sono altri indizi di
    release: in questo modo titoli come "Blade Runner 2049" o "2012" restano
    intatti. Gli anni tra parentesi e quelli seguiti da tag di release vengono
    invece eliminati.
    """

    if not raw_title:
        return ""

    text = str(raw_title).strip()
    text = _EXTENSION_RE.sub(" ", text)
    text = _PARENTHESIZED_YEAR_RE.sub(" ", text)

    had_release_hint = bool(_RELEASE_HINT_RE.search(text))
    text = _YEAR_BEFORE_TAG_RE.sub(_remove_release_year, text)
    text = _BRACKETS_RE.sub(" ", text)
    text = _MULTI_SEPARATOR_RE.sub(" ", text)
    text = text.replace("|", " ")
    text = _TAG_RE.sub(" ", text)
    text = _CODEC_RE.sub(" ", text)
    text = _AUDIO_RE.sub(" ", text)
    text = _SEASON_EPISODE_RE.sub(" ", text)
    text = _SITE_RE.sub(" ", text)
    text = _TRAILING_EPISODE_RE.sub(" ", text)

    if had_release_hint:
        text = re.sub(r"\s*[-–—]\s*$", " ", text)
        text = _TRAILING_YEAR_RE.sub(_remove_trailing_year, text)

    text = re.sub(r"\s*[-–—]\s*$", " ", text)
    text = re.sub(r"\s+[-–—]\s+", " - ", text)
    text = re.sub(r"\s*:\s*", ": ", text)
    text = _EDGE_SEPARATOR_RE.sub("", text)
    text = _SPACES_RE.sub(" ", text)
    return text.strip()


def normalize_for_match(value: str) -> str:
    """Normalizza un titolo per confronti non sensibili a maiuscole e accenti."""

    text = _strip_accents(value or "").casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [token for token in text.split() if token not in _ARTICLES]
    return " ".join(tokens)


def score_title(query: str, candidate: str) -> float:
    """Punteggio 0..1 usato per scegliere il risultato TMDB migliore."""

    left = normalize_for_match(query)
    right = normalize_for_match(candidate)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return 0.85
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)
