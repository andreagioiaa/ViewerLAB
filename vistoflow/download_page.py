"""Le pagine del pannello di download (ex StreamingCommunity-downloader) dentro ViewerLAB."""

from __future__ import annotations

import json

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QStackedLayout, QVBoxLayout, QWidget

from .i18n import _


def _is_panel(url: QUrl) -> bool:
    return url.host() == "127.0.0.1" or url.scheme() not in ("http", "https")


class _PanelPage(QWebEnginePage):
    """Il pannello resta qui; i link esterni (fonte, trailer, GitHub) vanno al browser."""

    # messaggi del pannello a ViewerLAB («viewerlab:opened», «viewerlab:back»)
    message = Signal(str)

    def javaScriptConsoleMessage(self, level, text, line, source):  # noqa: N802 - API Qt
        if text.startswith("viewerlab:"):
            self.message.emit(text.split(":", 1)[1])
        else:
            super().javaScriptConsoleMessage(level, text, line, source)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802 - API Qt
        if is_main_frame and not _is_panel(url):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, _type):  # noqa: N802 - API Qt
        # target="_blank": una pagina usa-e-getta che gira la prima navigazione al browser.
        return _ExternalPage(self.profile(), self)


class _ExternalPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802 - API Qt
        QDesktopServices.openUrl(url)
        self.deleteLater()
        return False


# Il pannello vive dentro ViewerLAB: la sua barra laterale sparisce, le sue pagine
# (Cerca, Download, Serie seguite, File, Impostazioni) le apre la barra di ViewerLAB.
_EMBED_CSS = (
    "aside.navbar-vertical{display:none!important}"
    ".page-wrapper{margin-left:0!important;max-width:100%!important}"
)
_EMBED_JS = (
    "(function(){var s=document.createElement('style');"
    f"s.textContent={json.dumps(_EMBED_CSS)};"
    "(document.head||document.documentElement).appendChild(s);})();"
)


def _page_of(url: QUrl) -> str:
    """Pagina del pannello dall'indirizzo: «#/downloads?f=x» → «downloads»."""
    return url.fragment().lstrip("/").split("?")[0].split("/")[0]


class DownloadPage(QWidget):
    """Le funzioni del pannello di download, pilotate dalla barra di ViewerLAB."""

    page_changed = Signal(str)
    film_opened = Signal()  # il film chiesto con open_film() è sullo schermo
    back_requested = Signal()  # «← Watchlist» nella pagina del film
    message = Signal(str)  # gli altri «viewerlab:…» (es. «choose-root», «language:it»)
    panel_loaded = Signal()

    def __init__(self, server, extras: dict[str, QWidget] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._server = server
        self._loaded = False
        self._pending_hash = ""
        # widget di ViewerLAB mostrati sopra una pagina del pannello (es. «settings»)
        self._extras = extras or {}

        self._status = QLabel(_("Avvio del pannello di download…"))
        self._status.setWordWrap(True)
        self._status.setContentsMargins(24, 24, 24, 24)
        self._view = QWebEngineView()
        self._view.setPage(_PanelPage(self._view))
        self._view.page().message.connect(self._on_message)
        script = QWebEngineScript()
        script.setName("viewerlab-embed")
        script.setSourceCode(_EMBED_JS)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self._view.page().scripts().insert(script)
        # «Scarica» nel file manager del pannello: salva nella cartella Download di sistema.
        self._view.page().profile().downloadRequested.connect(lambda item: item.accept())
        self._view.loadFinished.connect(lambda _ok: (self._apply_hash(), self.panel_loaded.emit()))
        self._view.urlChanged.connect(self._on_url_changed)

        self._stack = QStackedLayout()
        self._stack.addWidget(self._status)
        self._stack.addWidget(self._view)

        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        for widget in self._extras.values():
            widget.hide()
            box.addWidget(widget)
        box.addLayout(self._stack, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._poll)

    def showEvent(self, event) -> None:  # noqa: N802 - API Qt
        super().showEvent(event)
        if not self._loaded:
            self._timer.start()

    def _poll(self) -> None:
        if self._server.ready:
            self._timer.stop()
            self._loaded = True
            self._view.load(QUrl(self._server.launch_url))
            self._stack.setCurrentWidget(self._view)
        elif self._server.finished:
            self._timer.stop()
            self._status.setText(
                _("Il pannello di download non si è avviato: {error}. Dettagli in viewerlab.log.")
                .format(error=self._server.error or _("errore sconosciuto"))
            )

    def show_view(self, view: str) -> None:
        """Apre una pagina del pannello: «search», «downloads», «settings», «search?q=…»."""
        self._run(f"location.hash = {json.dumps('#/' + view)}")
        self._show_extras(view.split("?")[0].split("/")[0])

    def open_film(self, name: str, year: str = "", tmdb_id: int = 0) -> None:
        """La pagina del film (Scarica / Guarda), o la ricerca se il film non è certo."""
        args = ", ".join(json.dumps(v) for v in (name, year, tmdb_id or None))
        self._run(f"openFilmByName({args})")
        self._show_extras("title")

    def _run(self, script: str) -> None:
        self._pending_hash = script  # eseguito appena il pannello è caricato
        if self._loaded:
            self._apply_hash()

    def _apply_hash(self) -> None:
        if self._pending_hash:
            self._view.page().runJavaScript(self._pending_hash)
            self._pending_hash = ""

    def _on_message(self, text: str) -> None:
        if text == "opened":
            self.film_opened.emit()
        elif text == "back":
            self.back_requested.emit()
        else:
            self.message.emit(text)

    def run_js(self, script: str) -> None:
        """Esegue subito, se il pannello è caricato (altrimenti ci pensa panel_loaded)."""
        if self._loaded:
            self._view.page().runJavaScript(script)

    def _on_url_changed(self, url: QUrl) -> None:
        page = _page_of(url)
        if page:
            self._show_extras(page)
            self.page_changed.emit(page)

    def _show_extras(self, page: str) -> None:
        for name, widget in self._extras.items():
            widget.setVisible(name == page)
