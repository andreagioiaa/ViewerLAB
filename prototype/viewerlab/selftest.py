"""Autotest end-to-end: ricerca -> verifica -> avvio del flusso in mpv."""

from __future__ import annotations

import logging
import os
import sys
import time

from .config import bundled_path
from .models import Source
from .player import MpvController
from .probe import StreamProbe
from .search import SourceRepository


def _wait_for(predicate, timeout: float, label: str) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    print(f"  ✗ timeout: {label}")
    return False


def run_self_test(query: str = "sintel") -> int:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    print("ViewerLAB — autotest")
    print(f"Catalogo demo: {bundled_path('sources/demo_catalog.json')}")

    source = Source(
        id="demo-public",
        name="Demo — contenuti pubblici",
        kind="catalog",
        url="@bundled/sources/demo_catalog.json",
        enabled=True,
    )
    repository = SourceRepository([source])
    try:
        print(f"\n1. Ricerca: {query!r}")
        outcome = repository.search(query)
        for error in outcome.errors:
            print(f"  ! fonte {error.source_name}: {error.message}")
        if not outcome.candidates:
            print("  ✗ nessun risultato")
            return 1
        for index, candidate in enumerate(outcome.candidates[:5], start=1):
            print(
                f"  {index}. {candidate.title} ({candidate.display_year()}) "
                f"— {candidate.kind.upper()} — score {candidate.score:.0f}"
            )

        candidate = outcome.candidates[0]
        print(f"\n2. Verifica flusso: {candidate.url}")
        with StreamProbe() as probe:
            result = probe.probe(candidate)
        if not result.ok:
            print(f"  ✗ non disponibile: {result.error}")
            return 1
        print(
            f"  ✓ {result.label()} — HTTP {result.status}, "
            f"tipo {result.content_type or 'n/d'}"
        )

        print("\n3. Avvio mpv (modalità test senza finestra)")
        player = MpvController()
        if not player.is_available:
            print("  ✗ mpv non trovato: imposta MPV_PATH")
            return 1
        print(f"  binario: {player.binary_path}")
        player.start(video=False)
        print("  ✓ IPC connesso")
        player.load(candidate)

        loaded = _wait_for(
            lambda: player.get_state()["duration_ms"] > 0 or player.get_state()["eof"],
            timeout=35.0,
            label="caricamento flusso",
        )
        if not loaded:
            player.quit()
            return 1
        state = player.get_state()
        print(f"  ✓ flusso caricato — durata {state['duration_ms'] / 1000:.1f}s")

        if state["duration_ms"] > 4000:
            target = min(30.0, state["duration_ms"] / 2000.0)
            player.seek(target)
            if _wait_for(
                lambda: player.get_state()["position_ms"] >= target * 1000 - 1500,
                timeout=15.0,
                label="seek",
            ):
                print(f"  ✓ seek a {target:.0f}s")

        player.toggle_pause()
        if _wait_for(lambda: player.get_state()["paused"], timeout=5.0, label="pausa"):
            print("  ✓ pausa attiva")

        player.quit()
        print("\nAUTOTEST OK — il flusso è stato avviato e controllato.")
        return 0
    finally:
        repository.close()


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    query = args[0] if args else "sintel"
    return run_self_test(query)


if __name__ == "__main__":
    raise SystemExit(main())
