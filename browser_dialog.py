"""Browser integrato per aprire pagine web senza lasciare VistoFlow.

Il browser è volutamente un normale Chromium/WebEngine: visualizza la pagina e
lascia all'utente login, cookie e interazioni. Non estrae flussi protetti e non
aggira Cloudflare, CAPTCHA o DRM.

QtWebEngine di PyQt6 non è stabile su tutte le installazioni Windows, quindi il
motore gira in un processo separato basato su PySide6 (``browser_engine.py``).
La sua finestra nativa viene incorporata in questo dialogo.
"""

from __future__ import annotations

import ctypes
import json
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtNetwork import QAbstractSocket, QHostAddress, QTcpServer, QTcpSocket
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

BROWSER_ENGINE = Path(__file__).with_name("browser_engine.py")

GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040


def normalize_browser_url(text: str) -> QUrl | None:
    """Converte l'input della barra in un URL http/https/about valido."""
    text = (text or "").strip()
    if not text:
        return None
    if text in ("about:blank", "about:newtab"):
        return QUrl(text)
    if "://" not in text:
        text = "https://" + text
    url = QUrl(text)
    if not url.isValid() or url.scheme() not in ("http", "https", "about"):
        return None
    if url.scheme() in ("http", "https") and not url.host():
        return None
    return url


class WebBrowserDialog(QDialog):
    """Finestra browser con barra degli indirizzi e intercettazione flussi .m3u8."""

    url_changed = pyqtSignal(str)
    stream_detected = pyqtSignal(dict)
    stream_play_requested = pyqtSignal(dict)

    def __init__(self, url: str = "", parent=None):
        super().__init__(parent)
        self._current_url = ""
        self._initial_url = (url or "").strip()
        self._started_url = "about:blank"
        self._pending_url = ""
        self._last_captured_stream: dict | None = None
        self._helper_hwnd = 0
        self._helper_ready = False
        self._closing = False
        self._socket_buffer = ""
        self._stderr_buffer = ""
        self._load_failed = False
        self._process: QProcess | None = None
        self._server: QTcpServer | None = None
        self._socket: QTcpSocket | None = None
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.setInterval(30000)
        self._load_timer.timeout.connect(self._on_load_timeout)

        self.setWindowTitle("Browser · VistoFlow Pro")
        self.resize(980, 700)
        self.setMinimumSize(720, 500)

        self._build_ui()
        self._start_helper()

    # ------------------------------------------------------------------- UI
    def _build_ui(self):
        self.btn_back = QPushButton("◀")
        self.btn_back.setObjectName("Ghost")
        self.btn_back.setFixedSize(34, 32)
        self.btn_back.setToolTip("Indietro")
        self.btn_back.clicked.connect(self._go_back)

        self.btn_forward = QPushButton("▶")
        self.btn_forward.setObjectName("Ghost")
        self.btn_forward.setFixedSize(34, 32)
        self.btn_forward.setToolTip("Avanti")
        self.btn_forward.clicked.connect(self._go_forward)

        self.btn_reload = QPushButton("⟳")
        self.btn_reload.setObjectName("Ghost")
        self.btn_reload.setFixedSize(34, 32)
        self.btn_reload.setToolTip("Ricarica")
        self.btn_reload.clicked.connect(self._reload)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Inserisci un indirizzo, es. https://…")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self._navigate_from_bar)
        self.url_edit.setMinimumWidth(240)

        self.btn_go = QPushButton("Vai")
        self.btn_go.setObjectName("Primary")
        self.btn_go.clicked.connect(self._navigate_from_bar)

        self.btn_copy = QPushButton("Copia URL")
        self.btn_copy.setObjectName("Ghost")
        self.btn_copy.setToolTip("Copia l'indirizzo corrente negli appunti")
        self.btn_copy.clicked.connect(self._copy_url)

        self.btn_external = QPushButton("Apri nel browser")
        self.btn_external.setObjectName("Ghost")
        self.btn_external.setToolTip("Apri la pagina con il browser di sistema")
        self.btn_external.clicked.connect(self._open_external)

        self.btn_close = QPushButton("Chiudi")
        self.btn_close.setObjectName("Ghost")
        self.btn_close.clicked.connect(self.accept)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.addWidget(self.btn_back)
        toolbar.addWidget(self.btn_forward)
        toolbar.addWidget(self.btn_reload)
        toolbar.addWidget(self.url_edit, 1)
        toolbar.addWidget(self.btn_go)
        toolbar.addWidget(self.btn_copy)
        toolbar.addWidget(self.btn_external)
        toolbar.addWidget(self.btn_close)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(3)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()

        self.error_banner = QLabel("")
        self.error_banner.setObjectName("BrowserErrorBanner")
        self.error_banner.setWordWrap(True)
        self.error_banner.setStyleSheet(
            "QLabel#BrowserErrorBanner {"
            " background: #3a1d1d;"
            " color: #ffb4b4;"
            " border: 1px solid #7a2b2b;"
            " border-radius: 6px;"
            " padding: 8px;"
            "}"
        )
        self.error_banner.hide()

        # Banner di notifica per flussi .m3u8 intercettati con Referer
        self.stream_banner = QFrame()
        self.stream_banner.setObjectName("StreamBanner")
        self.stream_banner.setStyleSheet("""
            QFrame#StreamBanner {
                background: #122118;
                border: 1px solid #1f5c35;
                border-radius: 8px;
                padding: 4px;
            }
            QLabel#StreamBannerText {
                color: #5ce68a;
                font-weight: 600;
                font-size: 12px;
            }
        """)
        self.stream_banner.hide()

        banner_layout = QHBoxLayout(self.stream_banner)
        banner_layout.setContentsMargins(10, 5, 8, 5)
        banner_layout.setSpacing(10)

        self.lbl_stream_info = QLabel("🎬 Flusso .m3u8 rilevato")
        self.lbl_stream_info.setObjectName("StreamBannerText")

        self.btn_play_stream = QPushButton("▶ Riproduci nel Player VistoFlow")
        self.btn_play_stream.setObjectName("Primary")
        self.btn_play_stream.setToolTip(
            "Invia il flusso catturato e il Referer direttamente al player VLC"
        )
        self.btn_play_stream.clicked.connect(self._play_captured_stream)

        self.btn_copy_stream = QPushButton("Copia M3U8")
        self.btn_copy_stream.setObjectName("Ghost")
        self.btn_copy_stream.setToolTip("Copia l'URL del flusso .m3u8 negli appunti")
        self.btn_copy_stream.clicked.connect(self._copy_captured_stream)

        def _dismiss_banner():
            self.stream_banner.hide()
            QTimer.singleShot(0, self._resize_helper)

        self.btn_dismiss_stream = QPushButton("✕")
        self.btn_dismiss_stream.setObjectName("Ghost")
        self.btn_dismiss_stream.setFixedSize(28, 28)
        self.btn_dismiss_stream.setToolTip("Nascondi avviso")
        self.btn_dismiss_stream.clicked.connect(_dismiss_banner)

        banner_layout.addWidget(self.lbl_stream_info, 1)
        banner_layout.addWidget(self.btn_play_stream)
        banner_layout.addWidget(self.btn_copy_stream)
        banner_layout.addWidget(self.btn_dismiss_stream)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)

        self.view_container = QWidget()
        view_layout = QVBoxLayout(self.view_container)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(0)
        self.notice = QLabel("Avvio del browser integrato…")
        self.notice.setObjectName("Muted")
        self.notice.setWordWrap(True)
        self.notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        view_layout.addWidget(self.notice, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)
        layout.addLayout(toolbar)
        layout.addWidget(self.progress)
        layout.addWidget(self.error_banner)
        layout.addWidget(self.stream_banner)
        layout.addWidget(self.view_container, 1)
        layout.addWidget(self.status_label)

        self._set_navigation_enabled(False)

        shortcut_url = QShortcut(QKeySequence("Ctrl+L"), self)
        shortcut_url.activated.connect(self._focus_url)
        shortcut_reload = QShortcut(QKeySequence("Ctrl+R"), self)
        shortcut_reload.activated.connect(self._reload)

        self.finished.connect(self._on_finished)

    # --------------------------------------------------------------- processo
    def _start_helper(self):
        frozen = bool(getattr(sys, "frozen", False))
        if not frozen and not BROWSER_ENGINE.exists():
            self._show_helper_error(
                "Motore browser non trovato: manca browser_engine.py."
            )
            return
        if sys.platform != "win32":
            self._show_helper_error(
                "L'incorporamento del browser è supportato solo su Windows. "
                "Usa «Apri nel browser»."
            )
            return

        start = self._initial_url
        target = normalize_browser_url(start)
        if target is None and start:
            self.status_label.setText(
                "Indirizzo iniziale non valido; inseriscilo nella barra."
            )
        if target is not None and target.toString() != "about:blank":
            self._started_url = target.toString()
            self._pending_url = self._started_url
            self.url_edit.setText(self._started_url)
        else:
            self._started_url = "about:blank"
            self._pending_url = ""
            self.url_edit.setFocus()

        server = QTcpServer(self)
        server.newConnection.connect(self._on_new_connection)
        if not server.listen(QHostAddress.SpecialAddress.LocalHost, 0):
            self._show_helper_error(
                "Impossibile avviare il canale di comunicazione del browser."
            )
            return
        self._server = server

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        work_dir = Path(sys.executable).parent if frozen else BROWSER_ENGINE.parent
        process.setWorkingDirectory(str(work_dir))
        process.readyReadStandardError.connect(self._read_stderr)
        process.errorOccurred.connect(self._on_process_error)
        process.finished.connect(self._on_process_finished)
        self._process = process
        port = str(server.serverPort())
        if frozen:
            arguments = [
                "--browser-engine",
                "--port",
                port,
                "--url",
                self._started_url,
            ]
        else:
            arguments = [
                str(BROWSER_ENGINE),
                "--port",
                port,
                "--url",
                self._started_url,
            ]
        process.start(sys.executable, arguments)
        self._start_load_timer()

    def _on_new_connection(self):
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            if self._socket is not None:
                socket.close()
                continue
            self._socket = socket
            self._socket_buffer = ""
            socket.readyRead.connect(self._read_socket)
            socket.disconnected.connect(self._on_socket_disconnected)
            socket.errorOccurred.connect(self._on_socket_error)
            self._read_socket()

    def _read_socket(self):
        if self._socket is None:
            return
        data = bytes(self._socket.readAll()).decode("utf-8", errors="replace")
        self._socket_buffer += data
        while "\n" in self._socket_buffer:
            line, self._socket_buffer = self._socket_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self._handle_event(message)

    def _on_socket_disconnected(self):
        if self._closing:
            return
        if self._helper_ready:
            self._show_load_error(
                "Browser disconnesso. Chiudi e riapri la finestra per continuare."
            )

    def _on_socket_error(self, _error):
        if self._closing:
            return
        self._show_load_error("Errore di comunicazione con il browser.")

    def _read_stderr(self):
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        )
        self._stderr_buffer = (self._stderr_buffer + data)[-4000:]

    def _handle_event(self, message: dict):
        event = str(message.get("event") or "")
        if event == "ready":
            try:
                hwnd = int(message.get("hwnd") or 0)
            except (TypeError, ValueError):
                hwnd = 0
            if hwnd:
                self._embed_helper(hwnd)
            else:
                self._show_helper_error("Il browser non ha restituito una finestra.")
        elif event == "url":
            self._on_url_changed(str(message.get("url") or ""))
        elif event == "title":
            self._on_title_changed(str(message.get("title") or ""))
        elif event == "progress":
            try:
                value = int(message.get("value") or 0)
            except (TypeError, ValueError):
                value = 0
            self._on_load_progress(value)
        elif event == "load_started":
            self._on_load_started()
        elif event == "load_error":
            self._on_load_error(str(message.get("error") or ""))
        elif event == "load":
            self._on_load_finished(bool(message.get("ok")))
        elif event == "stream_captured":
            url = str(message.get("url") or "").strip()
            referer = str(message.get("referer") or "").strip()
            user_agent = str(message.get("user_agent") or "").strip()
            title = str(message.get("title") or "").strip()
            page_url = str(message.get("page_url") or "").strip()
            if url:
                self._on_stream_captured(url, referer, user_agent, title, page_url)

    def _send(self, message: dict) -> bool:
        if self._socket is None:
            return False
        if self._socket.state() != QAbstractSocket.SocketState.ConnectedState:
            return False
        payload = json.dumps(message, ensure_ascii=True) + "\n"
        self._socket.write(payload.encode("utf-8"))
        self._socket.flush()
        return True

    def _embed_helper(self, hwnd: int):
        self._helper_hwnd = hwnd
        self._helper_ready = True
        self.notice.hide()
        parent = int(self.view_container.winId())
        user32 = ctypes.windll.user32
        user32.SetParent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.SetParent.restype = ctypes.c_void_p
        user32.SetParent(hwnd, parent)
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            user32.SetWindowLongPtrW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_void_p,
            ]
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW(hwnd, GWL_STYLE, WS_CHILD | WS_VISIBLE)
        else:
            user32.SetWindowLongW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.SetWindowLongW(hwnd, GWL_STYLE, WS_CHILD | WS_VISIBLE)
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        self._set_navigation_enabled(True)
        self._resize_helper()
        if not self._load_failed:
            self.status_label.setText("Browser pronto.")
        if self._pending_url and self._pending_url != self._started_url:
            self._send({"action": "load", "url": self._pending_url})
        self._pending_url = ""

    def _resize_helper(self):
        if not self._helper_hwnd:
            return
        width = max(1, self.view_container.width())
        height = max(1, self.view_container.height())
        ratio = self.view_container.devicePixelRatioF() or 1.0
        width = int(round(width * ratio))
        height = int(round(height * ratio))
        user32 = ctypes.windll.user32
        user32.SetWindowPos(
            self._helper_hwnd,
            0,
            0,
            0,
            width,
            height,
            SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _show_helper_error(self, message: str):
        self._stop_load_timer()
        self.progress.hide()
        self.notice.setText(
            f"{message}\n\n"
            "Puoi comunque usare il pulsante «Apri nel browser» qui sopra."
        )
        self.notice.show()
        self.status_label.setText(message)
        self._set_navigation_enabled(False)

    def _on_process_error(self, _error):
        if self._closing or self._process is None:
            return
        detail = self._stderr_buffer.strip().splitlines()
        suffix = f"\n\nUltimo messaggio:\n{detail[-1]}" if detail else ""
        self._show_helper_error(
            "Impossibile avviare il browser integrato (PySide6/WebEngine)."
            + suffix
        )

    def _on_process_finished(self, _code, _status):
        if self._closing:
            return
        if not self._helper_ready:
            detail = self._stderr_buffer.strip().splitlines()
            suffix = f"\n\nUltimo messaggio:\n{detail[-1]}" if detail else ""
            self._show_helper_error("Il browser integrato si è chiuso." + suffix)
        else:
            self._show_load_error(
                "Il browser integrato si è chiuso. Riapri la finestra per continuare."
            )

    def _stop_helper(self):
        if self._closing:
            return
        self._closing = True
        self._stop_load_timer()
        if self._socket is not None:
            self._send({"action": "quit"})
            try:
                self._socket.readyRead.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                self._socket.disconnected.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                self._socket.errorOccurred.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._socket.disconnectFromHost()
            if self._socket.state() != QAbstractSocket.SocketState.UnconnectedState:
                self._socket.abort()
            self._socket = None
        if self._server is not None:
            try:
                self._server.newConnection.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._server.close()
            self._server = None
        if self._process is None:
            return
        self._process.terminate()
        if not self._process.waitForFinished(400):
            self._process.kill()
            self._process.waitForFinished(300)

    def _on_finished(self, _result):
        self._stop_helper()

    # --------------------------------------------------------------- navigazione
    def _normalize_url(self, text: str) -> QUrl | None:
        return normalize_browser_url(text)

    def load_url(self, url: str):
        """Carica un URL; se vuoto apre una pagina bianca e seleziona la barra."""
        text = (url or "").strip()
        if not text:
            self.url_edit.setText("")
            self.status_label.setText(
                "Inserisci un indirizzo nella barra e premi Invio. "
                "Il browser non aggira protezioni o DRM."
            )
            self._load_engine("about:blank")
            self.url_edit.setFocus()
            return

        target = self._normalize_url(text)
        if target is None:
            QMessageBox.warning(
                self,
                "Indirizzo non valido",
                "Inserisci un indirizzo completo che inizi con http:// o https://.",
            )
            return
        self.url_edit.setText(target.toString())
        self._current_url = target.toString()
        self._load_engine(self._current_url)

    def _load_engine(self, url: str):
        self._pending_url = url
        self._start_load_timer()
        if self._helper_ready and self._send({"action": "load", "url": url}):
            self._pending_url = ""
        elif self._process is not None:
            self.status_label.setText("Avvio del browser…")

    def _navigate_from_bar(self):
        target = self._normalize_url(self.url_edit.text())
        if target is None:
            QMessageBox.warning(
                self,
                "Indirizzo non valido",
                "Inserisci un indirizzo completo che inizi con http:// o https://.",
            )
            return
        self.url_edit.setText(target.toString())
        self._current_url = target.toString()
        self._load_engine(self._current_url)

    def _go_back(self):
        self._send({"action": "back"})

    def _go_forward(self):
        self._send({"action": "forward"})

    def _reload(self):
        self._send({"action": "reload"})

    def _focus_url(self):
        self.url_edit.setFocus()
        self.url_edit.selectAll()

    def _set_navigation_enabled(self, enabled: bool):
        self.btn_back.setEnabled(enabled)
        self.btn_forward.setEnabled(enabled)
        self.btn_reload.setEnabled(enabled)
        self.btn_go.setEnabled(True)

    # ---------------------------------------------------------------- eventi
    def _on_url_changed(self, text: str):
        prev_url = self._current_url
        self._current_url = "" if text == "about:blank" else text
        if self.url_edit.text() != self._current_url:
            self.url_edit.setText(self._current_url)
        if prev_url and self._current_url != prev_url:
            self.stream_banner.hide()
            self._last_captured_stream = None
        self.url_changed.emit(self._current_url)

    def _on_stream_captured(
        self,
        stream_url: str,
        referer: str,
        user_agent: str,
        title: str,
        page_url: str,
    ):
        clean_title = (
            title
            or (self.windowTitle().split(" · ")[0] if " · " in self.windowTitle() else "")
            or "Flusso Web"
        )
        self._last_captured_stream = {
            "url": stream_url,
            "referer": referer or self._current_url,
            "user_agent": user_agent,
            "title": clean_title,
            "page_url": page_url or self._current_url,
        }
        display = stream_url.split("?")[0].split("/")[-1] or "video.m3u8"
        if len(display) > 38:
            display = display[:35] + "…"
        self.lbl_stream_info.setText(f"🎬 Flusso .m3u8 rilevato: {display} — Apertura in VLC…")
        self.stream_banner.show()
        QTimer.singleShot(0, self._resize_helper)
        ref_info = self._last_captured_stream["referer"]
        self.status_label.setText(
            f"Flusso .m3u8 catturato con Referer: {ref_info}. Avvio in VLC…"
        )
        self.stream_detected.emit(dict(self._last_captured_stream))
        # Avvia subito il player nativo per evitare che la WebView rimanga bloccata sul caricamento
        QTimer.singleShot(350, self._play_captured_stream)

    def _play_captured_stream(self):
        if not self._last_captured_stream:
            return
        payload = dict(self._last_captured_stream)
        self.stream_play_requested.emit(payload)
        self.accept()

    def _copy_captured_stream(self):
        if not self._last_captured_stream:
            return
        url = self._last_captured_stream.get("url", "")
        if url:
            QApplication.clipboard().setText(url)
            self.status_label.setText("Link .m3u8 copiato negli appunti.")

    def _on_title_changed(self, title: str):
        safe_title = (title or "").strip()
        self.setWindowTitle(
            f"{safe_title} · Browser VistoFlow"
            if safe_title
            else "Browser · VistoFlow Pro"
        )

    def _start_load_timer(self):
        self._load_failed = False
        self.error_banner.hide()
        self._load_timer.start()

    def _stop_load_timer(self):
        self._load_timer.stop()

    def _show_load_error(self, message: str):
        self._load_failed = True
        self._load_timer.stop()
        self.progress.hide()
        self.error_banner.setText(
            f"{message}\n"
            "Il sito potrebbe bloccare il browser integrato. "
            "Riprova con ⟳ oppure usa «Apri nel browser»."
        )
        self.error_banner.show()
        self.status_label.setText(message)

    def _on_load_started(self):
        self._start_load_timer()
        self.progress.setValue(0)
        self.progress.show()
        self.status_label.setText("Caricamento della pagina…")

    def _on_load_timeout(self):
        if not self._helper_ready:
            return
        self._show_load_error(
            "Caricamento non completato dopo 30 secondi."
        )

    def _on_load_error(self, reason: str):
        message = "La pagina non è stata caricata."
        reason = (reason or "").strip()
        if reason:
            message += f" Dettaglio: {reason}"
        self._show_load_error(message)

    def _on_load_progress(self, value: int):
        if 0 < value < 100:
            self.progress.show()
            self.progress.setValue(value)
        else:
            self.progress.hide()

    def _on_load_finished(self, ok: bool):
        self._stop_load_timer()
        self.progress.hide()
        if ok:
            self._load_failed = False
            self.error_banner.hide()
            self.status_label.setText("Caricamento completato.")
        elif not self._load_failed:
            self._show_load_error("La pagina non è stata caricata.")

    def _copy_url(self):
        text = self.url_edit.text().strip() or self._current_url
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.status_label.setText("URL copiato negli appunti.")

    def _open_external(self):
        text = self.url_edit.text().strip() or self._current_url
        target = self._normalize_url(text)
        if target is None:
            QMessageBox.warning(
                self,
                "Indirizzo non valido",
                "Inserisci un indirizzo completo che inizi con http:// o https://.",
            )
            return
        QDesktopServices.openUrl(target)
        self.status_label.setText("Pagina aperta nel browser di sistema.")

    # ---------------------------------------------------------------- layout
    def resizeEvent(self, event):  # noqa: N802 - API Qt
        super().resizeEvent(event)
        QTimer.singleShot(0, self._resize_helper)

    def showEvent(self, event):  # noqa: N802 - API Qt
        super().showEvent(event)
        QTimer.singleShot(0, self._resize_helper)
        if not self.url_edit.text():
            self.url_edit.setFocus()

    def closeEvent(self, event):  # noqa: N802 - API Qt
        self._stop_helper()
        super().closeEvent(event)


__all__ = ["WebBrowserDialog", "normalize_browser_url"]
