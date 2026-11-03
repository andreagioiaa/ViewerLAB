"""Sottosistema Canali: loader, parser HTML ed engine asincrono."""

from .engine import ChannelEngine, score_match
from .loader import load_channels, load_channels_with_errors
from .parser import (
    ensure_absolute,
    parse_detail_embeds,
    parse_generic_embeds,
    parse_search_results,
)

__all__ = [
    "ChannelEngine",
    "ensure_absolute",
    "load_channels",
    "load_channels_with_errors",
    "parse_detail_embeds",
    "parse_generic_embeds",
    "parse_search_results",
    "score_match",
]
