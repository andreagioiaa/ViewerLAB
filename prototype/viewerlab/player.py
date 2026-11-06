"""Player mpv controllato via JSON IPC.

Su Windows usa una named pipe, altrove un socket Unix. Il video può essere
incorporato in un widget Qt passando l'HWND/identificativo finestra tramite
``--wid``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from .models import StreamCandidate

LOGGER = logging.getLogger(__name__)

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
_OBSERVED = (
    "time-pos",
    "duration",
    "pause",
    "idle-active",
    "eof-reached",
    "video-params/w",
    "video-params/h",
    "video-bitrate",
    "paused-for-cache",
    "media-title",
)


class MpvError(RuntimeError):
    pass


def resolve_mpv(explicit: str | None = None) -> str | None:
    """Trova mpv: argomento, MPV_PATH, PATH, bin/ accanto all'app."""
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env_path = os.environ.get("MPV_PATH")
    if env_path:
        candidates.append(env_path)

    local = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent
    ) / "bin"
    candidates.extend(
        [
            str(local / ("mpv.exe" if os.name == "nt" else "mpv")),
            shutil.which("mpv") or "",
            shutil.which("mpv.exe") or "",
        ]
    )

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path)
        found = shutil.which(candidate)
        if found:
            return found
    return None


class MpvController:
    def __init__(self, binary_path: str | None = None, extra_args: list[str] | None = None) -> None:
        self.binary_path = resolve_mpv(binary_path)
        self.extra_args = list(extra_args or [])
        self.pipe_name = ""
        self._process: subprocess.Popen[bytes] | None = None
        self._fd: int | None = None
        self._socket: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._pending: dict[int, dict[str, Any]] = {}
        self._request_id = 0
        self._props: dict[str, Any] = {name: None for name in _OBSERVED}
        self._events: deque[dict[str, Any]] = deque(maxlen=120)
        self._running = False
        self._closing = False

    # ------------------------------------------------------------------ stato

    @property
    def is_available(self) -> bool:
        return bool(self.binary_path and Path(self.binary_path).is_file())

    @property
    def is_running(self) -> bool:
        return self._running and self._process is not None and self._process.poll() is None

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            props = dict(self._props)
        return {
            "position_ms": max(0.0, float(props.get("time-pos") or 0.0) * 1000.0),
            "duration_ms": max(0.0, float(props.get("duration") or 0.0) * 1000.0),
            "paused": bool(props.get("pause")),
            "idle": bool(props.get("idle-active")),
            "eof": bool(props.get("eof-reached")),
            "buffering": bool(props.get("paused-for-cache")),
            "width": int(props.get("video-params/w") or 0),
            "height": int(props.get("video-params/h") or 0),
            "bitrate": int(props.get("video-bitrate") or 0),
            "title": str(props.get("media-title") or ""),
            "running": self.is_running,
        }

    def recent_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    # ---------------------------------------------------------------- avvio

    def start(
        self,
        window_id: int | None = None,
        video: bool = True,
        extra_args: list[str] | None = None,
    ) -> None:
        if self.is_running:
            return
        if not self.is_available:
            raise MpvError(
                "mpv non trovato. Imposta MPV_PATH o metti mpv(.exe) nella cartella bin/."
            )

        self._closing = False
        self.pipe_name = self._make_pipe_name()
        args = self._base_args(window_id, video)
        args.extend(extra_args or self.extra_args)

        LOGGER.info("Avvio mpv: %s", " ".join(args))
        popen_kwargs: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        mpv_log = os.environ.get("VIEWERLAB_MPV_LOG")
        if mpv_log:
            try:
                popen_kwargs["stderr"] = open(mpv_log, "wb")
            except OSError:
                pass
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        self._process = subprocess.Popen([self.binary_path, *args], **popen_kwargs)

        self._connect_ipc()
        LOGGER.debug("IPC connesso fd=%s socket=%s", self._fd, self._socket)
        self._reader = threading.Thread(
            target=self._read_loop, name="viewerlab-mpv-reader", daemon=True
        )
        self._reader.start()
        self._running = True

        for index, name in enumerate(_OBSERVED, start=1):
            try:
                self.command(["observe_property", index, name], timeout=3.0)
            except (MpvError, OSError):
                pass

    def _make_pipe_name(self) -> str:
        suffix = uuid.uuid4().hex[:8]
        if os.name == "nt":
            return rf"\\.\pipe\viewerlab-mpv-{os.getpid()}-{suffix}"
        return str(Path(tempfile.gettempdir()) / f"viewerlab-mpv-{os.getpid()}-{suffix}.sock")

    def _base_args(self, window_id: int | None, video: bool) -> list[str]:
        args = [
            f"--input-ipc-server={self.pipe_name}",
            "--idle=yes",
            "--keep-open=yes",
            "--no-terminal",
            "--no-config",
            "--load-scripts=no",
            "--ytdl=no",
            "--osc=no",
            "--hr-seek=yes",
            "--volume=100",
            "--title=ViewerLAB",
            "--input-default-bindings=no",
            "--input-vo-keyboard=no",
            "--hwdec=auto-safe",
            "--cache=yes",
        ]
        if window_id is not None:
            args.extend([f"--wid={int(window_id)}", "--force-window=no"])
        elif video:
            args.extend(["--force-window=yes", "--fullscreen"])
        else:
            args.extend(["--no-video", "--ao=null", "--force-window=no"])
        return args

    def _connect_ipc(self) -> None:
        assert self._process is not None
        deadline = time.monotonic() + 12.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise MpvError("mpv è terminato prima di aprire il canale IPC")
            try:
                if os.name == "nt":
                    # Un handle Windows sincrono blocca la pipe durante una
                    # lettura in attesa: la modalità non bloccante evita il
                    # deadlock tra thread lettore e scrittore.
                    self._fd = os.open(self.pipe_name, os.O_RDWR | os.O_BINARY)
                    os.set_blocking(self._fd, False)
                else:
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    sock.connect(self.pipe_name)
                    self._socket = sock
                return
            except OSError as error:
                last_error = error
                time.sleep(0.1)
        raise MpvError(f"Impossibile connettersi a mpv: {last_error}")

    # --------------------------------------------------------------- comandi

    def command(self, args: list[Any], timeout: float = 8.0) -> Any:
        if self._fd is None and self._socket is None:
            LOGGER.debug("Comando rifiutato (IPC assente): %s", args)
            raise MpvError("IPC mpv non connesso")
        with self._lock:
            request_id = self._request_id
            self._request_id += 1
            event = threading.Event()
            self._pending[request_id] = {"event": event, "response": None}

        try:
            self._write_json({"command": args, "request_id": request_id})
        except OSError as error:
            with self._lock:
                self._pending.pop(request_id, None)
            raise MpvError(f"Invio comando fallito: {error}") from error

        if not event.wait(timeout):
            with self._lock:
                self._pending.pop(request_id, None)
            raise MpvError(f"Timeout comando mpv: {args[0]}")

        with self._lock:
            slot = self._pending.pop(request_id, None)
        response = (slot or {}).get("response") or {}
        if response.get("error") != "success":
            raise MpvError(str(response.get("error") or "errore mpv"))
        return response.get("data")

    def set_property(self, name: str, value: Any) -> None:
        self.command(["set_property", name, value])

    def load(self, candidate: StreamCandidate) -> None:
        fields = self._header_fields(candidate)
        try:
            self.set_property("http-header-fields", fields)
        except MpvError:
            LOGGER.warning("Impossibile impostare gli header HTTP in mpv")
        self.command(["loadfile", candidate.url, "replace"])

    @staticmethod
    def _header_fields(candidate: StreamCandidate) -> list[str]:
        fields: list[str] = []
        seen: set[str] = set()

        def add(name: str, value: str) -> None:
            if not value or "\r" in value or "\n" in value or "\r" in name or "\n" in name:
                return
            key = name.lower()
            if key in seen:
                return
            seen.add(key)
            fields.append(f"{name}: {value}")

        add("User-Agent", candidate.user_agent or _DEFAULT_UA)
        add("Referer", candidate.referer)
        for name, value in candidate.headers.items():
            add(name, value)
        return fields

    def seek(self, seconds: float) -> None:
        self.command(["seek", max(0.0, float(seconds)), "absolute+exact"])

    def seek_by(self, delta: float) -> None:
        self.command(["seek", float(delta), "relative"])

    def toggle_pause(self) -> None:
        self.command(["cycle", "pause"])

    def set_pause(self, paused: bool) -> None:
        self.set_property("pause", bool(paused))

    def set_volume(self, volume: int) -> None:
        self.set_property("volume", max(0, min(100, int(volume))))

    def stop(self) -> None:
        try:
            self.command(["stop"], timeout=3.0)
        except (MpvError, OSError):
            pass

    def quit(self) -> None:
        self._closing = True
        if self.is_running:
            try:
                self.command(["quit"], timeout=2.0)
            except (MpvError, OSError):
                pass
        process = self._process
        if process is not None:
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
        self._cleanup()

    def _cleanup(self) -> None:
        self._running = False
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
        self._fd = None
        self._socket = None
        with self._lock:
            for slot in self._pending.values():
                slot["event"].set()
            self._pending.clear()
            self._props = {name: None for name in _OBSERVED}
        self._process = None

    # --------------------------------------------------------------- IPC I/O

    def _write_json(self, payload: dict[str, Any]) -> None:
        data = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        with self._write_lock:
            if self._fd is not None:
                written = 0
                while written < len(data):
                    try:
                        count = os.write(self._fd, data[written:])
                    except BlockingIOError:
                        time.sleep(0.005)
                        continue
                    if not count:
                        raise OSError("scrittura IPC interrotta")
                    written += count
            elif self._socket is not None:
                self._socket.sendall(data)
            else:
                raise OSError("IPC non connesso")

    def _read_loop(self) -> None:
        buffer = b""
        while True:
            try:
                if self._fd is not None:
                    try:
                        chunk = os.read(self._fd, 4096)
                    except BlockingIOError:
                        time.sleep(0.01)
                        continue
                elif self._socket is not None:
                    chunk = self._socket.recv(4096)
                else:
                    break
            except (OSError, ValueError):
                break
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                self._handle_message(message)
        self._running = False

    def _handle_message(self, message: dict[str, Any]) -> None:
        request_id = message.get("request_id")
        if isinstance(request_id, int):
            with self._lock:
                slot = self._pending.get(request_id)
            if slot is not None:
                slot["response"] = message
                slot["event"].set()
            return

        event = message.get("event")
        if not event:
            return
        with self._lock:
            self._events.append(message)
            if event == "property-change":
                name = message.get("name")
                if isinstance(name, str):
                    self._props[name] = message.get("data")
            elif event == "file-loaded":
                LOGGER.info("mpv: file caricato")
            elif event == "end-file":
                LOGGER.info("mpv: fine file (%s)", message.get("reason"))
