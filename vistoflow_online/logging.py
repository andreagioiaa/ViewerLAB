"""Configurazione del logging applicativo."""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Configura il logging su stderr, evitando handler duplicati."""

    numeric = getattr(logging, (level or "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stderr,
        force=True,
    )
    # Evita che il debug di httpx/httpcore stampi query string con api_key.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(max(numeric, logging.WARNING))
