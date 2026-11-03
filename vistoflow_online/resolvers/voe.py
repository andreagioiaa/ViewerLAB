"""Resolver per gli host Voe."""

from __future__ import annotations

from .html import HTMLStreamResolver
from .registry import register_resolver


@register_resolver
class VoeResolver(HTMLStreamResolver):
    """Voe pubblica tipicamente un manifest HLS dentro `sources` o script packer."""

    name = "voe"
    priority = 20
    domains = (
        "voe.sx",
        "voe.to",
        "voe.re",
        "voe.cx",
        "voe.com",
        "voe.eu",
    )
