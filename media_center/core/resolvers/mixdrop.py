"""Resolver per gli host Mixdrop."""

from __future__ import annotations

from .html import HTMLStreamResolver
from .registry import register_resolver


@register_resolver
class MixdropResolver(HTMLStreamResolver):
    """Mixdrop espone il flusso in `MDCore.wurl` o dentro script packer."""

    name = "mixdrop"
    priority = 10
    domains = (
        "mixdrop.co",
        "mixdrop.to",
        "mixdrop.bz",
        "mixdrop.ch",
        "mixdrop.sx",
        "mixdrop.ag",
        "mixdrop.vip",
        "mixdrop.ps",
        "mixdrop.is",
        "mixdrop.gl",
    )
