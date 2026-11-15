"""Punto di ingresso Qt di VistoFlow."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from . import __version__, config, i18n
from .selftest import run_self_test

LOGGER = logging.getLogger(__name__)

def configure_logging(level: str = "INFO") -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    try:
        log_path = config.data_dir() / "vistoflow.log"
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vistoflow",
        description="VistoFlow — libreria, ricerca IMDb e fonti online.",
    )
    parser.add_argument(
        "--self-test",
        nargs="?",
        const="sintel",
        metavar="QUERY",
        help="Esegue l'autotest senza interfaccia (ricerca, verifica, mpv).",
    )
    parser.add_argument(
        "--autoplay",
        metavar="QUERY",
        help="Avvia l'interfaccia e riproduce automaticamente il primo risultato.",
    )
    parser.add_argument(
        "--smoke-test",
        nargs="?",
        const="sintel",
        metavar="QUERY",
        help="Avvia la GUI, riproduce il primo risultato ed esce con esito.",
    )
    parser.add_argument("--mpv", metavar="PATH", help="Percorso esplicito di mpv.")
    parser.add_argument(
        "--data-dir",
        metavar="DIR",
        help="Cartella per configurazione e log (default: LOCALAPPDATA/VistoFlow).",
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="Stampa le fonti configurate ed esce.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Livello di log (default: INFO).",
    )
    parser.add_argument("--version", action="version", version=f"VistoFlow {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    if args.data_dir:
        os.environ["VISTOFLOW_DATA"] = args.data_dir
    configure_logging(args.log_level)
    # Senza console (pythonw) un errore non gestito sparirebbe: finisce nel log.
    sys.excepthook = lambda kind, value, tb: LOGGER.critical(
        "Errore non gestito", exc_info=(kind, value, tb)
    )
    i18n.load_language()  # prima di importare le finestre (costanti tradotte)

    if args.self_test:
        return run_self_test(args.self_test)

    if args.list_sources:
        for source in config.load_sources():
            state = "attiva" if source.enabled else "disattiva"
            print(f"{source.id}\t{source.kind}\t{state}\t{source.name}\t{source.url or source.search_url}")
        return 0

    from .library.theme import apply_theme
    from .main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("VistoFlow")
    app.setOrganizationName("VistoFlow")
    apply_theme(app)

    smoke = args.smoke_test is not None
    window = MainWindow(
        mpv_path=args.mpv,
        autoplay_query=args.smoke_test or args.autoplay,
        smoke_test=smoke,
    )

    exit_code = {"value": 0}

    def on_smoke_finished(ok: bool, message: str) -> None:
        exit_code["value"] = 0 if ok else 1
        LOGGER.info("SMOKE %s — %s", "OK" if ok else "FAIL", message)
        try:
            sys.stdout.write(("SMOKE OK — " if ok else "SMOKE FAIL — ") + message + "\n")
            sys.stdout.flush()
        except (AttributeError, OSError, ValueError):
            pass
        finally:
            QTimer.singleShot(0, quit_application)

    def quit_application() -> None:
        window.close()
        app.quit()

    def force_quit() -> None:
        window._finish_smoke(False, "timeout globale")
        quit_application()

    if smoke:
        window.smoke_finished.connect(on_smoke_finished)
        QTimer.singleShot(120_000, force_quit)

    window.show()
    app.exec()

    if smoke:
        return exit_code["value"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
