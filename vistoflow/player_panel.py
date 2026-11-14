"""Pannello video con controlli Qt e superficie per mpv (``--wid``)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from .i18n import _

_PLAY = "▶"
_PAUSE = "⏸"
_STOP = "■"


def _format_time(milliseconds: float) -> str:
    seconds = max(0, int(milliseconds // 1000))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class VideoSurface(QFrame):
    """Widget nativo in cui mpv disegna il video tramite HWND."""

    double_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("VideoSurface")
        self.setStyleSheet("#VideoSurface { background: #000000; }")
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._placeholder = QLabel(_("Nessun flusso in riproduzione"), self)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #6b7280; font-size: 13px; background: transparent;")

    def resizeEvent(self, event) -> None:  # noqa: N802 - API Qt
        super().resizeEvent(event)
        self._placeholder.setGeometry(self.rect())

    def set_placeholder(self, visible: bool, text: str = "") -> None:
        if text:
            self._placeholder.setText(text)
        self._placeholder.setVisible(visible)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - API Qt
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class ClickSlider(QSlider):
    """Slider che salta dove si clicca: un clic sulla barra è uno spostamento."""

    clicked_to = Signal(int)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            span = self.width() if self.orientation() == Qt.Orientation.Horizontal else self.height()
            pos = event.position().x() if self.orientation() == Qt.Orientation.Horizontal else event.position().y()
            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(pos), span)
            self.setValue(value)
            self.clicked_to.emit(value)
        super().mousePressEvent(event)


class PlayerPanel(QWidget):
    play_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    seek_requested = Signal(float)
    skip_requested = Signal(float)
    volume_changed = Signal(int)
    fullscreen_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._duration_ms = 0.0
        self._seeking = False
        self._paused = True
        self._active = False

        self.video = VideoSurface()
        self.video.double_clicked.connect(self.fullscreen_requested)

        self.title_label = QLabel(_("Player"))
        self.title_label.setStyleSheet("color: #dbe2ee; font-weight: 600;")
        self.status_label = QLabel(_("Pronto"))
        self.status_label.setStyleSheet("color: #8a93a5;")

        header = QHBoxLayout()
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.status_label)

        self.play_button = QPushButton(_PLAY)
        self.play_button.setToolTip(_("Riproduci / pausa"))
        self.play_button.setFixedWidth(44)
        self.play_button.clicked.connect(self._on_play_clicked)

        self.stop_button = QPushButton(_STOP)
        self.stop_button.setToolTip(_("Ferma"))
        self.stop_button.setFixedWidth(44)
        self.stop_button.clicked.connect(self.stop_requested)

        self.back_button = QPushButton("⏪")
        self.back_button.setToolTip(_("Indietro di 10 secondi"))
        self.back_button.setFixedWidth(44)
        self.back_button.clicked.connect(lambda: self.skip_requested.emit(-10.0))

        self.forward_button = QPushButton("⏩")
        self.forward_button.setToolTip(_("Avanti di 10 secondi"))
        self.forward_button.setFixedWidth(44)
        self.forward_button.clicked.connect(lambda: self.skip_requested.emit(10.0))

        self.position_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.setEnabled(False)
        self.position_slider.sliderPressed.connect(self._on_seek_start)
        self.position_slider.sliderReleased.connect(self._on_seek_end)
        self.position_slider.clicked_to.connect(lambda _v: self._on_seek_end())

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #aeb7c6; font-family: Consolas, monospace;")
        self.time_label.setMinimumWidth(130)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.volume_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.setToolTip(_("Volume"))
        self.volume_slider.valueChanged.connect(self.volume_changed)

        volume_icon = QLabel("🔊")
        volume_icon.setStyleSheet("color: #aeb7c6;")

        self.fullscreen_button = QPushButton("⛶")
        self.fullscreen_button.setToolTip(_("Schermo intero (F11)"))
        self.fullscreen_button.setFixedWidth(44)
        self.fullscreen_button.clicked.connect(self.fullscreen_requested)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        controls.addWidget(self.play_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.back_button)
        controls.addWidget(self.forward_button)
        controls.addWidget(self.position_slider, 1)
        controls.addWidget(self.time_label)
        controls.addWidget(volume_icon)
        controls.addWidget(self.volume_slider)
        controls.addWidget(self.fullscreen_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.video, 1)
        layout.addLayout(controls)

        # Tastiera: valgono finché il fuoco è nel pannello (vedi take_focus()).
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for key, slot in (
            ("K", self._on_play_clicked),
            ("Left", lambda: self.skip_requested.emit(-10.0)),
            ("Right", lambda: self.skip_requested.emit(10.0)),
            ("Up", lambda: self.volume_slider.setValue(self.volume_slider.value() + 5)),
            ("Down", lambda: self.volume_slider.setValue(self.volume_slider.value() - 5)),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

    # ------------------------------------------------------------- azioni

    def _on_play_clicked(self) -> None:
        if self._active:
            self.pause_requested.emit()  # alterna pausa / ripresa del flusso caricato
        else:
            self.play_requested.emit()

    def take_focus(self) -> None:
        """Porta la tastiera sul player (il fuoco può essere rimasto su un'altra pagina)."""
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_seek_start(self) -> None:
        self._seeking = True

    def _on_seek_end(self) -> None:
        self._seeking = False
        if self._duration_ms > 0:
            seconds = self.position_slider.value() / 1000.0 * self._duration_ms / 1000.0
            self.seek_requested.emit(seconds)

    # --------------------------------------------------------------- stato

    def set_title(self, title: str) -> None:
        self.title_label.setText(title or _("Player"))

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_busy(self, busy: bool) -> None:
        self.play_button.setEnabled(not busy)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.video.set_placeholder(not active)
        self.position_slider.setEnabled(active)
        self.play_button.setEnabled(True)
        if not active:
            self._duration_ms = 0.0
            self._paused = True
            self.play_button.setText(_PLAY)
            self.position_slider.setValue(0)
            self.time_label.setText("00:00 / 00:00")

    def update_state(self, state: dict) -> None:
        duration = float(state.get("duration_ms") or 0.0)
        position = float(state.get("position_ms") or 0.0)
        paused = bool(state.get("paused"))
        self._duration_ms = duration

        if duration > 0:
            self.position_slider.setEnabled(True)
            if not self._seeking:
                self.position_slider.setValue(int(min(1000, position / duration * 1000)))
        self.time_label.setText(_(f"{_format_time(position)} / {_format_time(duration)}"))

        if paused != self._paused:
            self._paused = paused
            self.play_button.setText(_PLAY if paused else _PAUSE)
        elif not self._active:
            self.play_button.setText(_PLAY)

        if state.get("buffering"):
            self.status_label.setText(_("Buffering…"))
        elif state.get("eof"):
            self.status_label.setText(_("Fine riproduzione"))
        elif state.get("running"):
            self.status_label.setText(_("In riproduzione") if not paused else _("In pausa"))
