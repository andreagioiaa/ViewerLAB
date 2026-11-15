"""Avvia il pannello di download dentro ViewerLAB: uvicorn in un thread su 127.0.0.1.

Il pannello resta un'app FastAPI a sé (stato dei download in memoria, un solo
processo): ViewerLAB lo ospita e lo mostra in una pagina QtWebEngine.
"""

from __future__ import annotations

import logging
import os
import secrets
import socket
import threading
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def configure_paths(data_dir: Path) -> None:
    """File del pannello sotto la cartella dati di ViewerLAB.

    Va chiamata prima di importare ``vistoflow_dl.config``, che legge l'ambiente
    all'import. Una variabile già impostata dall'utente vince.
    """
    root = data_dir / "download"
    root.mkdir(parents=True, exist_ok=True)
    defaults = {
        "DATA_FILE": root / "data.json",
        "DB_FILE": root / "panel.db",
        "SCHEDULE_FILE": root / "schedule.json",
        "TMP_DIR": root / "tmp",
        "VIDEOS_DIR": Path.home() / "Videos" / "ViewerLAB",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, str(value))


class PanelServer:
    """Il server del pannello, avviato una volta per sessione di ViewerLAB."""

    def __init__(self, data_dir: Path) -> None:
        configure_paths(data_dir)
        from vistoflow_dl.auth.deps import LAUNCH_QUERY, LAUNCH_TOKEN_ENV

        self.token = secrets.token_urlsafe(32)
        os.environ[LAUNCH_TOKEN_ENV] = self.token
        self._query = LAUNCH_QUERY
        # Socket aperto qui: la porta è nota subito e nessun altro può prenderla.
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self.port = self._sock.getsockname()[1]
        self._server = None
        self._thread: threading.Thread | None = None
        self.error: BaseException | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def launch_url(self) -> str:
        """Primo indirizzo da aprire: imposta il cookie e torna su ``/``."""
        return f"{self.base_url}/?{self._query}={self.token}"

    @property
    def ready(self) -> bool:
        return self._server is not None and self._server.started

    @property
    def finished(self) -> bool:
        return self._thread is not None and not self._thread.is_alive()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="vistoflow-download", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            import uvicorn

            from vistoflow_dl.main import app

            self._server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
            self._server.run(sockets=[self._sock])
        except BaseException as exc:  # anche SystemExit: il thread non deve sparire muto
            self.error = exc
            LOGGER.exception("Il pannello di download non si è avviato")

    def stop(self, timeout: float = 5.0) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout)
