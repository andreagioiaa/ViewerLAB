"""Unpacker Python per script JavaScript protetti con il classico packer.

Non esegue JavaScript arbitrario: interpreta solo la struttura
`eval(function(p,a,c,k,e,d){...}('...',a,c,'...'.split('|'),0,{}))`.
"""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse, urlunparse

_PACKER_PREFIXES = (
    "eval(function(p,a,c,k,e,d)",
    "eval(function(p,a,c,k,e,r)",
    "function(p,a,c,k,e,d)",
)
_STREAM_RE = re.compile(
    r"(?:https?:)?//[^\s\"'<>\\]+?\.(?:m3u8|mp4)(?:\?[^\s\"'<>\\]*)?",
    re.IGNORECASE,
)
_ARGS_RE = re.compile(r"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'")
_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def _base36(value: int) -> str:
    if value < 0:
        return ""
    if value < 36:
        return _BASE36[value]
    return _base36(value // 36) + _BASE36[value % 36]


def _encode_token(value: int, base: int) -> str:
    if value < base:
        if value > 35:
            return chr(value + 29)
        return _base36(value)
    return _encode_token(value // base, base) + _encode_token(value % base, base)


def _read_js_string(source: str, start: int) -> tuple[str, int]:
    """Legge una stringa JS racchiusa da apici singoli, gestendo gli escape."""

    result: list[str] = []
    index = start
    while index < len(source):
        char = source[index]
        if char == "'":
            return "".join(result), index + 1
        if char != "\\":
            result.append(char)
            index += 1
            continue

        index += 1
        if index >= len(source):
            break
        escaped = source[index]
        mapping = {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "b": "\b",
            "f": "\f",
            "'": "'",
            '"': '"',
            "\\": "\\",
            "/": "/",
        }
        if escaped in mapping:
            result.append(mapping[escaped])
            index += 1
            continue
        if escaped == "x" and index + 2 < len(source):
            try:
                result.append(chr(int(source[index + 1 : index + 3], 16)))
                index += 3
                continue
            except ValueError:
                pass
        if escaped == "u" and index + 4 < len(source):
            try:
                result.append(chr(int(source[index + 1 : index + 5], 16)))
                index += 5
                continue
            except ValueError:
                pass
        result.append(escaped)
        index += 1
    raise ValueError("Stringa JavaScript non terminata")


def _unpack_at(source: str, prefix_index: int) -> tuple[str, int]:
    marker = source.find("}('", prefix_index)
    if marker < 0:
        raise ValueError("Payload del packer non trovato")
    payload, position = _read_js_string(source, marker + 3)

    args_match = _ARGS_RE.match(source, position)
    if not args_match:
        raise ValueError("Parametri del packer non riconosciuti")
    base = int(args_match.group(1))
    count = int(args_match.group(2))
    keywords, position = _read_js_string(source, args_match.end())
    words = keywords.split("|")
    if len(words) < count:
        words.extend([""] * (count - len(words)))

    for index in range(count - 1, -1, -1):
        word = words[index] if index < len(words) else ""
        if not word:
            continue
        token = _encode_token(index, base)
        payload = re.sub(
            r"(?<![a-zA-Z0-9])" + re.escape(token) + r"(?![a-zA-Z0-9])",
            lambda _match, replacement=word: replacement,
            payload,
        )
    return payload, position


def unpack(source: str) -> str:
    """Esegue l'unpack del primo blocco packer presente nella stringa."""

    for prefix in _PACKER_PREFIXES:
        index = source.find(prefix)
        if index >= 0:
            payload, _position = _unpack_at(source, index)
            return payload
    raise ValueError("Nessun blocco packer riconosciuto")


def unpack_all(source: str) -> list[str]:
    """Estrae l'unpack di tutti i blocchi packer presenti."""

    outputs: list[str] = []
    cursor = 0
    while cursor < len(source):
        candidates = [
            (index, prefix)
            for prefix in _PACKER_PREFIXES
            if (index := source.find(prefix, cursor)) >= 0
        ]
        if not candidates:
            break
        index, _prefix = min(candidates)
        try:
            payload, position = _unpack_at(source, index)
        except ValueError:
            cursor = index + 1
            continue
        outputs.append(payload)
        cursor = max(position, index + 1)
    return outputs


def normalize_url_text(text: str) -> str:
    """Normalizza escape comuni usati negli script degli host."""

    text = html.unescape(text or "")
    replacements = {
        "\\/": "/",
        "\\u002F": "/",
        "\\u002f": "/",
        "\\u002E": ".",
        "\\u002e": ".",
        "\\u003A": ":",
        "\\u003a": ":",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def extract_stream_urls(text: str) -> list[str]:
    """Estrae URL .mp4/.m3u8, preferendo HLS quando sono presenti entrambi."""

    normalized = normalize_url_text(text)
    results: list[str] = []
    seen: set[str] = set()
    for match in _STREAM_RE.finditer(normalized):
        raw = match.group(0).rstrip(");,")
        if raw.startswith("//"):
            raw = "https:" + raw
        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https"):
            continue
        cleaned = urlunparse(parsed)
        if cleaned in seen:
            continue
        seen.add(cleaned)
        results.append(cleaned)

    results.sort(key=lambda url: (0 if ".m3u8" in url.lower() else 1, url))
    return results


def mime_for_url(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".m3u8"):
        return "application/vnd.apple.mpegurl"
    if path.endswith(".mp4"):
        return "video/mp4"
    return "application/octet-stream"
