"""Player video basato su python-vlc con HUD ridisegnato."""

import sys
import time

import vlc
from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)


class VideoSurface(QFrame):
    """Superficie nera: riceve il doppio click quando VLC non lo cattura."""

    double_clicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class VideoPlayer(QFrame):
    double_clicked = pyqtSignal()
    close_requested = pyqtSignal()
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    SPEEDS = (1.0, 1.25, 1.5, 2.0, 0.75)
    START_TIMEOUT = 10.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Player")
        self._is_finished_emitted = False
        self._error_emitted = False
        self._started_playing = False
        self._user_stopped = False
        self._play_started_at = 0.0
        self._last_playing_at = 0.0
        self._speed_index = 0

        args = [
            "--no-video-title-show",
            "--quiet",
            "--mouse-hide-timeout=-1",
            "--no-osd",
            # Disabilita l'accelerazione hardware che causava errori D3D11.
            "--avcodec-hw=none",
        ]
        self.instance = vlc.Instance(args)
        self.player = self.instance.media_player_new()
        self.player.video_set_mouse_input(False)
        self.player.video_set_key_input(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ------------------------------------------------------------- superficie
        self.video_frame = VideoSurface()
        self.video_frame.setObjectName("VideoSurface")
        self.video_frame.setStyleSheet("background-color: #000000;")
        self.video_frame.setMinimumHeight(220)
        self.video_frame.double_clicked.connect(self.double_clicked)

        # --------------------------------------------------------------- controlli
        self.controls = QWidget()
        self.controls.setObjectName("PlayerControls")
        self.controls.setFixedHeight(86)
        self.controls.setStyleSheet(
            "QWidget#PlayerControls { background: #11161d; border-top: 1px solid #1d2732; }"
        )
        ctrl = QVBoxLayout(self.controls)
        ctrl.setContentsMargins(14, 6, 14, 6)
        ctrl.setSpacing(4)

        self.hud_slider = QSlider(Qt.Orientation.Horizontal)
        self.hud_slider.setObjectName("Seek")
        self.hud_slider.setRange(0, 0)
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setObjectName("TimeLabel")
        self.lbl_time.setMinimumWidth(96)
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(self.hud_slider, 1)
        row1.addWidget(self.lbl_time)

        row2 = QHBoxLayout()
        row2.setSpacing(4)
        self.btn_pause = QPushButton("▶")
        self.btn_pause.setObjectName("PlayButton")
        self.btn_pause.setToolTip("Play / Pausa (Spazio)")
        self.btn_stop = QPushButton("■")
        self.btn_stop.setObjectName("IconButton")
        self.btn_stop.setToolTip("Stop")
        self.btn_back = QPushButton("⏪")
        self.btn_back.setObjectName("IconButton")
        self.btn_back.setToolTip("-10 secondi (Ctrl+←)")
        self.btn_fwd = QPushButton("⏩")
        self.btn_fwd.setObjectName("IconButton")
        self.btn_fwd.setToolTip("+10 secondi (Ctrl+→)")

        self.btn_mute = QPushButton("🔊")
        self.btn_mute.setObjectName("IconButton")
        self.btn_mute.setToolTip("Muto (M)")
        self.btn_mute.setStyleSheet("font-size: 15px;")

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setObjectName("Volume")
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(86)

        self.btn_speed = QPushButton("1×")
        self.btn_speed.setObjectName("SpeedButton")
        self.btn_speed.setToolTip("Velocità di riproduzione")

        self.lbl_meta = QLabel("Nessun video in riproduzione")
        self.lbl_meta.setObjectName("PlayerMeta")
        self.lbl_meta.setMinimumWidth(80)

        self.btn_full = QPushButton("⛶")
        self.btn_full.setObjectName("IconButton")
        self.btn_full.setToolTip("Schermo intero (F)")

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("ClosePlayerButton")
        self.btn_close.setFixedSize(30, 30)
        self.btn_close.setToolTip("Chiudi il riproduttore per più spazio")

        row2.addWidget(self.btn_pause)
        row2.addWidget(self.btn_stop)
        row2.addSpacing(4)
        row2.addWidget(self.btn_back)
        row2.addWidget(self.btn_fwd)
        row2.addSpacing(10)
        row2.addWidget(self.btn_mute)
        row2.addWidget(self.vol_slider)
        row2.addSpacing(6)
        row2.addWidget(self.btn_speed)
        row2.addSpacing(10)
        row2.addWidget(self.lbl_meta, 1)
        row2.addWidget(self.btn_full)
        row2.addWidget(self.btn_close)

        ctrl.addLayout(row1)
        ctrl.addLayout(row2)

        root.addWidget(self.video_frame, 1)
        root.addWidget(self.controls, 0)

        # ---------------------------------------------------------------- connessioni
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_back.clicked.connect(lambda: self.jump(-10000))
        self.btn_fwd.clicked.connect(lambda: self.jump(10000))
        self.btn_mute.clicked.connect(self.toggle_mute)
        self.btn_speed.clicked.connect(self.cycle_speed)
        self.btn_close.clicked.connect(self.close_requested)
        self.vol_slider.valueChanged.connect(self.set_volume)
        self.hud_slider.sliderMoved.connect(self.set_position)

        self.timer = QTimer(self)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._tick)

        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(3200)
        self.hide_timer.timeout.connect(self._hide_ui)

        QApplication.instance().installEventFilter(self)

    # ---------------------------------------------------------------- finestra
    def showEvent(self, event):
        super().showEvent(event)
        self.set_window_id()

    def set_window_id(self):
        try:
            wid = int(self.video_frame.winId())
            if sys.platform.startswith("win"):
                self.player.set_hwnd(wid)
            elif sys.platform == "darwin":
                self.player.set_nsobject(wid)
            else:
                self.player.set_xwindow(wid)
        except Exception:
            pass

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    # -------------------------------------------------------------------- HUD
    def _show_controls(self):
        if self.controls.isHidden():
            self.controls.show()
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        if self.player.get_state() == vlc.State.Playing:
            self.hide_timer.start()

    def _hide_ui(self):
        if self.player.get_state() == vlc.State.Playing and not self.controls.underMouse():
            self.controls.hide()
            QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
        else:
            self.controls.show()
            while QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        self.hide_timer.stop()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove:
            self._show_controls()
        return super().eventFilter(obj, event)

    # --------------------------------------------------------------- riproduzione
    def play_file(self, path, start=0, meta=""):
        """Riproduce un file locale (compatibilità con la libreria)."""
        self.play_media(path, start=start, meta=meta)

    def play_url(self, url, headers=None, start=0, meta=""):
        """Riproduce un flusso HTTP/HLS applicando gli header del resolver.

        VLC riceve User-Agent e Referer come opzioni del singolo media, così
        non vengono modificati gli header globali usati dalla libreria locale.
        """
        self.play_media(url, start=start, meta=meta, headers=headers)

    def play_media(self, target, start=0, meta="", headers=None):
        self.lbl_meta.setText(meta or "Video")
        self._is_finished_emitted = False
        try:
            self.player.stop()
        except Exception:
            pass
        self._error_emitted = False
        self._started_playing = False
        self._user_stopped = False
        self._play_started_at = time.monotonic()
        self._last_playing_at = self._play_started_at

        media = self.instance.media_new(target)
        if start and start > 0:
            media.add_option(f"start-time={start / 1000.0}")

        # Opzioni del singolo media: VLC le usa per la richiesta HTTP/HLS.
        for key, value in (headers or {}).items():
            if not value:
                continue
            lowered = str(key).lower()
            if lowered == "user-agent":
                media.add_option(f":http-user-agent={value}")
            elif lowered == "referer":
                media.add_option(f":http-referrer={value}")
        if str(target).lower().startswith(("http://", "https://")):
            # Un piccolo buffer rende più stabili i manifest HLS.
            media.add_option(":network-caching=1500")

        self.player.set_media(media)
        self.set_window_id()
        self.player.play()
        self.player.audio_set_volume(self.vol_slider.value())
        self.player.set_rate(self.SPEEDS[self._speed_index])
        self.timer.start()
        self.hud_slider.setValue(0)
        self.lbl_time.setText("00:00 / 00:00")
        self.controls.show()
        self.hide_timer.start()

    def stop(self):
        self._user_stopped = True
        try:
            self.player.stop()
        except Exception:
            pass
        self.timer.stop()
        self.hide_timer.stop()
        self._show_controls()
        self.hud_slider.setRange(0, 0)
        self.hud_slider.setValue(0)
        self.lbl_time.setText("00:00 / 00:00")
        self.btn_pause.setText("▶")

    def toggle_pause(self):
        if not self.player.get_media():
            return
        self.player.pause()
        self.controls.show()
        self.hide_timer.start()

    def jump(self, ms):
        if not self.player.get_media():
            return
        current = self.player.get_time()
        self.player.set_time(max(0, current + ms))
        self.controls.show()
        self.hide_timer.start()

    def set_position(self, ms):
        self.player.set_time(ms)

    def set_volume(self, vol):
        self.player.audio_set_volume(vol)
        self._update_mute_icon()

    def toggle_mute(self):
        if not self.player.get_media():
            return
        self.player.audio_toggle_mute()
        self._update_mute_icon()

    def _update_mute_icon(self):
        muted = False
        try:
            muted = bool(self.player.audio_get_mute())
        except Exception:
            pass
        if muted or self.vol_slider.value() == 0:
            self.btn_mute.setText("🔇")
        else:
            self.btn_mute.setText("🔊")

    def cycle_speed(self):
        self._speed_index = (self._speed_index + 1) % len(self.SPEEDS)
        rate = self.SPEEDS[self._speed_index]
        try:
            self.player.set_rate(rate)
        except Exception:
            pass
        self.btn_speed.setText(f"{rate:g}×")

    # --------------------------------------------------------------------- tick
    def _tick(self):
        state = self.player.get_state()
        playing = state == vlc.State.Playing
        paused = state == vlc.State.Paused
        self.btn_pause.setText("⏸" if playing else "▶")

        elapsed = time.monotonic() - self._play_started_at
        if state == vlc.State.Error:
            if not self._error_emitted and not self._user_stopped and elapsed > 0.8:
                self._error_emitted = True
                self.error.emit("Riproduzione non riuscita")
            return
        if not playing and not paused and not self._error_emitted:
            # Un link scaduto può restare in Opening/Buffering senza mai
            # arrivare allo stato Error: dopo un timeout chiediamo il refresh.
            pos = self.player.get_time()
            dur = self.player.get_length()
            at_end = dur > 0 and pos >= dur * 0.95
            stalled = state in (vlc.State.Opening, vlc.State.Buffering) and (
                (not self._started_playing and elapsed > self.START_TIMEOUT)
                or (
                    self._started_playing
                    and time.monotonic() - self._last_playing_at > 20.0
                )
            )
            failed_stop = (
                state in (vlc.State.Stopped, vlc.State.Ended)
                and not self._user_stopped
                and not self._is_finished_emitted
                and not at_end
            )
            if stalled or (failed_stop and elapsed > 2.0):
                self._error_emitted = True
                self.error.emit("Impossibile avviare la riproduzione")
            return
        if playing:
            self._started_playing = True
            self._last_playing_at = time.monotonic()

        pos = self.player.get_time()
        dur = self.player.get_length()
        if dur > 0:
            if self.hud_slider.maximum() != dur:
                self.hud_slider.setRange(0, dur)
                self.duration_changed.emit(dur)
        if not self.hud_slider.isSliderDown():
            self.hud_slider.setValue(max(0, pos))
        self.lbl_time.setText(f"{self._ms_to_str(pos)} / {self._ms_to_str(dur)}")

        if playing:
            self.position_changed.emit(pos)
            if dur > 0 and (pos / dur) > 0.95 and not self._is_finished_emitted:
                self._is_finished_emitted = True
                self.finished.emit()

    @staticmethod
    def _ms_to_str(ms):
        ms = max(0, int(ms or 0))
        s = (ms // 1000) % 60
        m = (ms // 60000) % 60
        h = ms // 3600000
        if h > 0:
            return f"{h:02}:{m:02}:{s:02}"
        return f"{m:02}:{s:02}"
