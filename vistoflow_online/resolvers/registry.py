"""Registro dei resolver disponibili."""

from __future__ import annotations

from .base import BaseResolver

_RESOLVER_CLASSES: list[type[BaseResolver]] = []


def register_resolver(resolver_class: type[BaseResolver]) -> type[BaseResolver]:
    """Decorator per registrare un resolver senza duplicati."""

    if resolver_class not in _RESOLVER_CLASSES:
        _RESOLVER_CLASSES.append(resolver_class)
    return resolver_class


def get_resolvers() -> list[BaseResolver]:
    """Restituisce le istanze ordinate per priorità."""

    return sorted(
        (resolver_class() for resolver_class in _RESOLVER_CLASSES),
        key=lambda resolver: (resolver.priority, resolver.name),
    )


def find_resolver(url: str) -> BaseResolver | None:
    """Trova il primo resolver che riconosce l'URL."""

    for resolver in get_resolvers():
        if resolver.can_handle(url):
            return resolver
    return None


def supported_domains() -> dict[str, tuple[str, ...]]:
    """Mappa nome resolver -> domini, utile per doctor e documentazione."""

    return {resolver.name: resolver.domains for resolver in get_resolvers()}
