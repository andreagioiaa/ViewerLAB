"""Resolver per gli host Streamtape."""

from __future__ import annotations

from .html import HTMLStreamResolver
from .registry import register_resolver


@register_resolver
class StreamtapeResolver(HTMLStreamResolver):
    """Streamtape costruisce il link in `norobotlink` o in script offuscati."""

    name = "streamtape"
    priority = 40
    domains = (
        "streamtape.com",
        "streamtape.net",
        "streamtape.to",
        "streamtape.xyz",
        "streamtape.site",
        "streamtape.cc",
        "streamtape.ai",
        "tapecontent.net",
    )
