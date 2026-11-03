"""Motore online integrato in VistoFlow Pro.

Il pacchetto contiene la pipeline già usata dal Media Center (canali,
resolver, TMDB) ma è pensato per essere importato direttamente dall'app
PyQt6: non avvia servizi separati e non richiede una CLI.
"""

from .errors import (
    ChannelConfigError,
    ChannelError,
    MediaCenterError,
    MetadataError,
    ResolverError,
    UnsupportedResolver,
)
from .models import (
    ChannelConfig,
    ChannelSelectors,
    MediaItem,
    MediaType,
    PlayRequest,
    ResolveReport,
    SearchReport,
    SearchResult,
    StreamSource,
)
from .service import OnlineService, ResolveOutcome, SearchOutcome

__version__ = "1.0.0"

__all__ = [
    "ChannelConfig",
    "ChannelConfigError",
    "ChannelError",
    "ChannelSelectors",
    "MediaCenterError",
    "MediaItem",
    "MediaType",
    "MetadataError",
    "OnlineService",
    "PlayRequest",
    "ResolveOutcome",
    "ResolveReport",
    "ResolverError",
    "SearchOutcome",
    "SearchReport",
    "SearchResult",
    "StreamSource",
    "UnsupportedResolver",
]
