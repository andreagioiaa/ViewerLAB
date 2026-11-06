"""Motore browser isolato basato su PySide6/QtWebEngine.

VistoFlow usa PyQt6 per l'interfaccia. QtWebEngine di PyQt6 non è affidabile
su tutte le installazioni Windows, quindi il browser viene eseguito in un
processo separato con PySide6. La finestra nativa del processo viene poi
incorporata nel dialogo Qt di VistoFlow.

Il processo comunica con il padre tramite un socket TCP su 127.0.0.1, così
funziona anche nell'eseguibile PyInstaller compilato senza console. I messaggi
sono righe JSON:

    {"action": "load", "url": "https://…"}
    {"action": "back"|"forward"|"reload"|"quit"}

e gli eventi inviati al padre sono:

    {"event": "ready", "hwnd": 12345}
    {"event": "url", "url": "https://…"}
    {"event": "title", "title": "…"}
    {"event": "progress", "value": 42}
    {"event": "load", "ok": true}
"""

from __future__ import annotations

import json
import socket
import sys
import threading

from PySide6.QtCore import QObject, QUrl, Qt, Signal
from PySide6.QtWebEngineCore import (
    QWebEngineLoadingInfo,
    QWebEnginePage,
    QWebEngineScript,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow


def _argument_value(option: str) -> str:
    for index, argument in enumerate(sys.argv):
        if argument == option and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return ""


def _is_stream_url(url: str) -> bool:
    """Verifica se l'URL corrisponde a un flusso o playlist .m3u8 valido."""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False
    lower = url.lower()
    if ".m3u8" in lower:
        if any(
            lower.endswith(ext) or (ext + "?") in lower
            for ext in (
                ".js",
                ".css",
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".webp",
                ".svg",
                ".html",
            )
        ):
            return False
        return True
    return False


class _MediaInterceptorBridge(QObject):
    stream_captured = Signal(str, str, str)


class _MediaRequestInterceptor(QWebEngineUrlRequestInterceptor):
    """Intercetta le richieste di rete per catturare i flussi .m3u8 con relativo Referer."""

    def __init__(self, bridge: _MediaInterceptorBridge):
        super().__init__()
        self._bridge = bridge
        self._seen_urls: set[str] = set()
        self._last_embed_urls: list[str] = []
        self._lock = threading.Lock()

    def clear_seen(self) -> None:
        with self._lock:
            self._seen_urls.clear()
            self._last_embed_urls.clear()

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:  # noqa: N802 - API Qt
        url = info.requestUrl().toString()
        if not url:
            return

        # Traccia le richieste verso player/iframe incorporati (es. vidxgo, vidhide)
        url_lower = url.lower()
        if any(kw in url_lower for kw in ("vidxgo", "embed", "player", "/e/", "/v/")) and not _is_stream_url(url):
            with self._lock:
                if url not in self._last_embed_urls:
                    self._last_embed_urls.append(url)
                    if len(self._last_embed_urls) > 10:
                        self._last_embed_urls.pop(0)

        if not _is_stream_url(url):
            return

        with self._lock:
            if url in self._seen_urls:
                return
            if len(self._seen_urls) > 300:
                self._seen_urls.clear()
            self._seen_urls.add(url)
            candidate_embed = self._last_embed_urls[-1] if self._last_embed_urls else ""

        headers = info.httpHeaders()
        referer = ""
        user_agent = ""
        for raw_k, raw_v in headers.items():
            k_lower = bytes(raw_k).lower()
            if k_lower == b"referer" and not referer:
                referer = bytes(raw_v).decode("utf-8", errors="replace")
            elif k_lower == b"user-agent" and not user_agent:
                user_agent = bytes(raw_v).decode("utf-8", errors="replace")

        # Se il referer catturato è solo l'origine (es. https://v.vidxgo.co/) ma abbiamo l'URL embed completo con percorso e parametri
        if candidate_embed:
            if not referer or referer.rstrip("/") == candidate_embed.split("?")[0].rstrip("/") or len(referer.strip()) <= len("https://v.vidxgo.co/"):
                referer = candidate_embed

        if not referer:
            first_party = info.firstPartyUrl().toString()
            initiator = info.initiator().toString()
            referer = candidate_embed or first_party or initiator

        self._bridge.stream_captured.emit(url, referer, user_agent)


class _Transport:
    """Socket JSON-lines verso il processo principale."""

    def __init__(self, port: int):
        self._socket = socket.create_connection(("127.0.0.1", port), timeout=10)
        self._socket.settimeout(None)
        self._lock = threading.Lock()

    def send(self, event: dict) -> None:
        line = json.dumps(event, ensure_ascii=True) + "\n"
        with self._lock:
            try:
                self._socket.sendall(line.encode("ascii"))
            except OSError:
                pass

    def start_reader(self, bridge: "_Bridge") -> None:
        def read_commands() -> None:
            try:
                stream = self._socket.makefile("r", encoding="utf-8")
                for line in stream:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(message, dict):
                        bridge.command.emit(message)
            except OSError:
                pass
            finally:
                bridge.command.emit({"action": "quit"})

        threading.Thread(target=read_commands, daemon=True).start()

    def close(self) -> None:
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._socket.close()
        except OSError:
            pass


class _BrowserPage(QWebEnginePage):
    """Blocca popup e finestre secondarie: il browser resta sulla stessa pagina."""

    def createWindow(self, _window_type):  # noqa: N802 - API Qt
        # None impedisce l'apertura di nuove finestre/tab/popup.
        return None


class _Bridge(QObject):
    command = Signal(object)


def main() -> int:
    port_text = _argument_value("--port")
    try:
        port = int(port_text)
    except ValueError:
        print("browser_engine: --port mancante o non valido", file=sys.stderr)
        return 2
    if not 0 < port < 65536:
        print("browser_engine: --port non valido", file=sys.stderr)
        return 2

    try:
        transport = _Transport(port)
    except OSError as exc:
        print(f"browser_engine: connessione al padre fallita: {exc}", file=sys.stderr)
        return 2

    start_url = _argument_value("--url") or "about:blank"
    # Gli argomenti di VistoFlow (--port/--url) non servono a Qt.
    app = QApplication([sys.argv[0]])

    window = QMainWindow()
    window.setWindowTitle("VistoFlow Browser Engine")
    window.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    window.resize(900, 650)
    window.move(-32000, -32000)

    view = QWebEngineView()
    page = _BrowserPage(view)
    view.setPage(page)
    window.setCentralWidget(view)

    view.loadStarted.connect(
        lambda: transport.send({"event": "load_started"})
    )

    def on_loading_changed(info) -> None:
        if info.status() == QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus:
            transport.send(
                {
                    "event": "load_error",
                    "url": info.url().toString(),
                    "error": info.errorString(),
                }
            )

    page.loadingChanged.connect(on_loading_changed)

    # Configura impostazioni ottimali per i player web
    settings = page.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)

    # User-Agent standard Chrome per superare i blocchi anti-bot
    chrome_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )
    profile = page.profile()
    profile.setHttpUserAgent(chrome_ua)
    default_ua = chrome_ua

    # AutoPlayTrigger: avvia automaticamente la riproduzione nei frame e negli iframe
    auto_play_script = QWebEngineScript()
    auto_play_script.setName("AutoPlayTrigger")
    auto_play_script.setSourceCode("""
    (function() {
        var triggered = false;
        function tryPlay() {
            if (triggered) return;
            var vids = document.querySelectorAll('video');
            for (var i = 0; i < vids.length; i++) {
                try {
                    vids[i].muted = true;
                    vids[i].play();
                    triggered = true;
                } catch(e) {}
            }
            var btns = document.querySelectorAll('.play-btn, .vjs-big-play-button, button.play, [class*="play"], [aria-label*="Play"], .jw-display-icon-container');
            for (var j = 0; j < btns.length; j++) {
                try {
                    btns[j].click();
                    triggered = true;
                } catch(e) {}
            }
        }
        if (document.readyState === 'complete' || document.readyState === 'interactive') {
            tryPlay();
        }
        document.addEventListener('DOMContentLoaded', tryPlay);
        var count = 0;
        var interval = setInterval(function() {
            tryPlay();
            count++;
            if (count > 8 || triggered) clearInterval(interval);
        }, 1000);
    })();
    """)
    auto_play_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    auto_play_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    auto_play_script.setRunsOnSubFrames(True)
    profile.scripts().insert(auto_play_script)

    media_bridge = _MediaInterceptorBridge()
    media_interceptor = _MediaRequestInterceptor(media_bridge)
    profile.setUrlRequestInterceptor(media_interceptor)
    window._media_interceptor = media_interceptor
    window._media_bridge = media_bridge

    def handle_stream_captured(stream_url: str, referer: str, user_agent: str) -> None:
        current_page = view.url().toString()
        ref = referer or (current_page if current_page != "about:blank" else "")
        ua = user_agent or default_ua
        title = window.windowTitle()
        transport.send({
            "event": "stream_captured",
            "url": stream_url,
            "referer": ref,
            "user_agent": ua,
            "title": title,
            "page_url": current_page,
        })

    media_bridge.stream_captured.connect(handle_stream_captured)

    bridge = _Bridge()

    def handle_command(message: dict) -> None:
        action = str(message.get("action") or "")
        if action == "load":
            url = str(message.get("url") or "").strip()
            if url:
                view.setUrl(QUrl(url))
        elif action == "back":
            view.back()
        elif action == "forward":
            view.forward()
        elif action == "reload":
            view.reload()
        elif action == "quit":
            app.quit()

    bridge.command.connect(handle_command)

    def on_url_changed(url: QUrl) -> None:
        media_interceptor.clear_seen()
        transport.send({"event": "url", "url": url.toString()})

    view.urlChanged.connect(on_url_changed)
    view.titleChanged.connect(
        lambda title: transport.send({"event": "title", "title": title})
    )
    view.loadProgress.connect(
        lambda value: transport.send({"event": "progress", "value": int(value)})
    )
    view.loadFinished.connect(
        lambda ok: transport.send({"event": "load", "ok": bool(ok)})
    )

    app.aboutToQuit.connect(transport.close)
    transport.start_reader(bridge)
    view.setUrl(QUrl(start_url or "about:blank"))
    window.show()
    transport.send({"event": "ready", "hwnd": int(window.winId())})
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
