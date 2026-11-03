"""Task asincroni condivisi dalla GUI VistoFlow.

Le coroutine e i download vengono eseguiti in thread demone; i risultati
tornano al thread Qt tramite segnali. Il modulo non conosce la UI, così può
essere usato sia dalla ricerca online sia dalla gestione dei link salvati.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from cover_fetcher import download_cover


class AsyncOperation(QObject):
    """Esegue una coroutine in un thread demone e ne emette l'esito."""

    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, factory: Callable[[], object], parent=None):
        super().__init__(parent)
        self._factory = factory

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            result = asyncio.run(self._factory())
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            try:
                self.failed.emit(message)
            except RuntimeError:
                pass
        else:
            try:
                self.completed.emit(result)
            except RuntimeError:
                pass


class ImageOperation(QObject):
    """Scarica una copertina in background."""

    loaded = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            data = download_cover(self.url)
        except Exception as exc:
            try:
                self.failed.emit(str(exc) or "Download non riuscito")
            except RuntimeError:
                pass
        else:
            try:
                self.loaded.emit(data)
            except RuntimeError:
                pass


__all__ = ["AsyncOperation", "ImageOperation"]
