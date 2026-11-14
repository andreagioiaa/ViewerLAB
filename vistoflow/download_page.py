"""Pagina «Download»: il pannello di download (ex StreamingCommunity-downloader)."""

from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStackedLayout, QVBoxLayout, QWidget

from .i18n import _


def _is_panel(url: QUrl) -> bool:
    return url.host() == "127.0.0.1" or url.scheme() not in ("http", "https")


class _PanelPage(QWebEnginePage):
    """Il pannello resta qui; i link esterni (fonte, trailer, GitHub) vanno al browser."""

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


class DownloadPage(QWidget):
    def __init__(self, server, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._server = server
        self._loaded = False

        bar = QHBoxLayout()
        bar.setContentsMargins(16, 10, 16, 6)
        title = QLabel(_("Download"))
        title.setObjectName("PageTitle")
        reload_button = QPushButton(_("Ricarica"))
        reload_button.clicked.connect(lambda: self._view.reload())
        browser_button = QPushButton(_("Apri nel browser"))
        browser_button.clicked.connect(self._open_external)
        bar.addWidget(title)
        bar.addStretch(1)
        bar.addWidget(reload_button)
        bar.addWidget(browser_button)

        self._status = QLabel(_("Avvio del pannello di download…"))
        self._status.setWordWrap(True)
        self._status.setContentsMargins(24, 24, 24, 24)
        self._view = QWebEngineView()
        self._view.setPage(_PanelPage(self._view))
        # «Scarica» nel file manager del pannello: salva nella cartella Download di sistema.
        self._view.page().profile().downloadRequested.connect(lambda item: item.accept())

        self._stack = QStackedLayout()
        self._stack.addWidget(self._status)
        self._stack.addWidget(self._view)

        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addLayout(bar)
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
                _("Il pannello di download non si è avviato: {error}. Dettagli in vistoflow.log.")
                .format(error=self._server.error or _("errore sconosciuto"))
            )

    def _open_external(self) -> None:
        if self._server.ready:
            QDesktopServices.openUrl(QUrl(self._server.launch_url))
