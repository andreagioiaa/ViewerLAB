"""Sottosistema Resolver: registrazione, unpacker e motore di risoluzione."""

# L'import dei moduli concreti popola il registro tramite @register_resolver.
from . import direct as _direct  # noqa: E402,F401
from . import mixdrop as _mixdrop  # noqa: E402,F401
from . import streamtape as _streamtape  # noqa: E402,F401
from . import supervideo as _supervideo  # noqa: E402,F401
from . import voe as _voe  # noqa: E402,F401
from .base import BaseResolver
from .engine import ResolverEngine
from .html import HTMLStreamResolver
from .js_unpacker import extract_stream_urls, mime_for_url, unpack, unpack_all
from .registry import find_resolver, get_resolvers, register_resolver, supported_domains

__all__ = [
    "BaseResolver",
    "HTMLStreamResolver",
    "ResolverEngine",
    "extract_stream_urls",
    "find_resolver",
    "get_resolvers",
    "mime_for_url",
    "register_resolver",
    "supported_domains",
    "unpack",
    "unpack_all",
]
