"""Resolver per gli host Supervideo."""

from __future__ import annotations

from .html import HTMLStreamResolver
from .registry import register_resolver


@register_resolver
class SupervideoResolver(HTMLStreamResolver):
    """Supervideo usa spesso un player con `sources` e URL HLS/MP4."""

    name = "supervideo"
    priority = 30
    domains = (
        "supervideo.tv",
        "supervideo.cc",
        "supervideo.xyz",
        "supervideo.life",
        "supervideo.com",
    )
