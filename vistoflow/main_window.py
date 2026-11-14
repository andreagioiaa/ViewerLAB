"""Finestra unica di VistoFlow: libreria, ricerca IMDb, fonti online, player."""

from __future__ import annotations

import logging
import math
import sys
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QProcess, QRectF, QSize, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import config, i18n
from .i18n import _
from .dialogs import DirectLinkDialog, SourceEditorDialog
from .download_page import DownloadPage
from .html_site import resolve_site
from .imdb import ImdbError, Title, shared_client
from .models import ProbeResult, Source, StreamCandidate
from .player import MpvController, MpvError
from .player_panel import PlayerPanel, _format_time
from .probe import StreamProbe
from .resume import END_MARGIN_S, ResumeStore
from .search import SourceRepository
from .style import THEME

LOGGER = logging.getLogger(__name__)


def _describe_source(source: Source) -> str:
    if source.kind == "direct":
        return _("Link diretto")
    if source.kind == "json_api":
        return _("API JSON")
    if source.kind == "site":
        return _("Sito web")
    return _("Catalogo")


def _kind_label(candidate: StreamCandidate) -> str:
    if candidate.needs_resolution:
        return "SITO"
    return (candidate.kind or "stream").upper()


_POSTER_W, _POSTER_H = 150, 225
_DETAIL_W, _DETAIL_H = 240, 360
_GRADIENTS = (
    ("#e07a5f", "#3d2c4e"), ("#3b82f6", "#1e1b4b"), ("#22c55e", "#123524"),
    ("#f59e0b", "#4a2511"), ("#ec4899", "#3b0d2c"), ("#14b8a6", "#0f2e35"),
)


def _rounded(pixmap: QPixmap, radius: float = 12.0) -> QPixmap:
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(result.rect()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result


def _icon(pixmap: QPixmap) -> QIcon:
    icon = QIcon(pixmap)
    icon.addPixmap(pixmap, QIcon.Mode.Selected)  # niente tinta blu sulla locandina selezionata
    return icon


def _placeholder_poster(title: str, width: int, height: int) -> QPixmap:
    """Locandina generata (gradiente + titolo) quando la fonte non ne fornisce una."""
    top, bottom = _GRADIENTS[sum(map(ord, title)) % len(_GRADIENTS)]
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, 0, height)
    gradient.setColorAt(0, QColor(top))
    gradient.setColorAt(1, QColor(bottom))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), 12, 12)
    painter.fillPath(path, gradient)
    font = QFont()
    font.setBold(True)
    font.setPixelSize(max(14, width // 9))
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(
        QRectF(10, height * 0.45, width - 20, height * 0.5),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom | Qt.TextFlag.TextWordWrap,
        title,
    )
    painter.end()
    return pixmap


def change_language(parent: QWidget, code: str) -> None:
    """Salva la lingua e propone il riavvio."""
    if code == i18n.language():
        return
    try:
        i18n.save_language(code)
    except OSError as error:
        QMessageBox.warning(parent, _("Impostazioni"), str(error))
        return
    box = QMessageBox(parent)
    box.setWindowTitle(_("Lingua"))
    box.setText(_("La nuova lingua verrà applicata al riavvio di VistoFlow."))
    restart = box.addButton(_("Riavvia ora"), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(_("Più tardi"), QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is restart:
        arguments = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        QProcess.startDetached(sys.executable, arguments)
        parent.window().close()


class PosterGrid(QListWidget):
    """Griglia di locandine senza scroll proprio: cresce in altezza col contenuto."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PosterGrid")
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setWrapping(True)
        self.setSpacing(14)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(_POSTER_W, _POSTER_H))
        self.setGridSize(QSize(_POSTER_W + 22, _POSTER_H + 64))
        self.setWordWrap(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def fit(self) -> None:
        visible = sum(not self.item(i).isHidden() for i in range(self.count()))
        per_row = max(1, (self.viewport().width() - 4) // self.gridSize().width())
        rows = math.ceil(visible / per_row)
        self.setFixedHeight(rows * (self.gridSize().height() + 14) + 14 if visible else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - API Qt
        super().resizeEvent(event)
        self.fit()


class ImdbTask(QThread):
    """Ricerca o dettagli IMDb in background."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, query: str = "", title: Title | None = None, parent=None) -> None:
        super().__init__(parent)
        self._query = query
        self._title = title

    def run(self) -> None:  # noqa: D401 - QThread
        try:
            client = shared_client()
            if self._title is not None:
                result = client.details(self._title.imdb_id, self._title.kind)
            else:
                result = client.search(self._query)
        except ImdbError as error:
            self.failed.emit(str(error))
            return
        except Exception as error:  # pragma: no cover - difesa UI
            LOGGER.exception("IMDb")
            self.failed.emit(str(error))
            return
        self.completed.emit(result)


class SearchTask(QThread):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(str, int)

    def __init__(self, sources: list[Source], query: str, parent=None) -> None:
        super().__init__(parent)
        self._sources = list(sources)
        self._query = query

    def run(self) -> None:  # noqa: D401 - QThread
        repository = SourceRepository(self._sources)
        try:
            outcome = repository.search(
                self._query,
                progress=lambda name, count: self.progress.emit(name, count),
            )
        except Exception as error:  # pragma: no cover - difesa UI
            LOGGER.exception("Ricerca fallita")
            self.failed.emit(str(error))
            return
        finally:
            repository.close()
        self.completed.emit(outcome)


class ProbeTask(QThread):
    completed = Signal(object, str, object)
    failed = Signal(str, str)

    def __init__(
        self,
        candidate: StreamCandidate,
        purpose: str,
        source: Source | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._candidate = candidate
        self._purpose = purpose
        self._source = source

    def run(self) -> None:  # noqa: D401 - QThread
        target = self._candidate
        if target.needs_resolution:
            if self._source is None:
                self.failed.emit(self._purpose, _("Fonte del contenuto non disponibile"))
                return
            try:
                streams = resolve_site(self._source, target)
            except Exception as error:  # rete, HTML, selettori
                self.failed.emit(self._purpose, _(f"Risoluzione fallita: {error}"))
                return
            if not streams:
                self.failed.emit(
                    self._purpose,
                    _("Nessun flusso video trovato nella pagina del contenuto")
                    + " — "
                    + _("Pagina dinamica: il player viene creato da JavaScript e non è leggibile senza browser"),
                )
                return
            target = streams[0]

        try:
            with StreamProbe() as probe:
                result = probe.probe(target)
        except Exception as error:  # pragma: no cover - difesa UI
            self.failed.emit(self._purpose, str(error))
            return
        self.completed.emit(result, self._purpose, target)


class PlayerStartTask(QThread):
    ready = Signal()
    failed = Signal(str)

    def __init__(self, controller: MpvController, window_id: int, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._window_id = window_id

    def run(self) -> None:  # noqa: D401 - QThread
        try:
            self._controller.start(window_id=self._window_id, video=True)
        except (MpvError, OSError) as error:
            self.failed.emit(str(error))
            return
        self.ready.emit()


class _StreamBridge(QObject):
    """Porta al thread Qt i flussi che il pannello di download chiede di guardare."""

    play = Signal(str, str, str, str)  # url, referer, titolo, chiave del contenuto


class MainWindow(QMainWindow):
    smoke_finished = Signal(bool, str)

    def __init__(
        self,
        mpv_path: str | None = None,
        autoplay_query: str | None = None,
        smoke_test: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("VistoFlow")
        self.resize(1360, 880)

        self._mpv_path = mpv_path
        self._sources: list[Source] = []
        self._candidates: list[StreamCandidate] = []
        self._probes: dict[tuple[str, str], ProbeResult] = {}
        self._streams: dict[tuple[str, str], StreamCandidate] = {}
        self._player: MpvController | None = None
        self._search_task: SearchTask | None = None
        self._probe_task: ProbeTask | None = None
        self._start_task: PlayerStartTask | None = None
        self._probe_candidate: StreamCandidate | None = None
        self._pending_play: StreamCandidate | None = None
        self._loading_candidate: StreamCandidate | None = None
        self._saving = False

        self._smoke = smoke_test
        self._smoke_done = False
        self._smoke_deadline = time.monotonic() + 90.0
        self._autoplay_query = autoplay_query
        self._last_outcome = None

        # Posizione di riproduzione per contenuto (riprende da dove eri).
        self._resume = ResumeStore(config.data_dir() / "resume.json")
        self._resume_key = ""
        self._resume_title = ""
        self._resume_pending: float | None = None
        self._announced: StreamCandidate | None = None
        self._resume_saved_at = 0.0

        # Pannello di download (ex StreamingCommunity-downloader): server locale
        # avviato subito, così download programmati e serie seguite girano da sé.
        from vistoflow_dl.desktop import PanelServer

        self._download_server = PanelServer(config.data_dir())
        from vistoflow_dl.core import stream as dl_stream

        self._stream_bridge = _StreamBridge(self)
        self._stream_bridge.play.connect(self._play_download_stream)
        dl_stream.set_player(self._stream_bridge.play.emit)  # emesso dal thread del server
        if not smoke_test:
            self._download_server.start()

        self._build_ui()
        self._reload_sources()

        self._state_timer = QTimer(self)
        self._state_timer.setInterval(300)
        self._state_timer.timeout.connect(self._poll_player)
        self._state_timer.start()

        if autoplay_query is not None or smoke_test:
            QTimer.singleShot(600, self._start_autoplay)

    # ---------------------------------------------------------------- UI
    # Layout ispirato a Stream Goat: barra laterale a icone, pagine impilate
    # (Cerca → Dettagli → Player, Fonti, Impostazioni), griglia di locandine.

    (PAGE_LIBRARY, PAGE_SEARCH, PAGE_IMDB, PAGE_DETAILS, PAGE_PLAYER, PAGE_SOURCES,
     PAGE_SETTINGS, PAGE_DOWNLOAD) = range(8)

    def _build_ui(self) -> None:
        from .library.window import VistoFlowApp, make_app_icon

        central = QWidget()
        central.setObjectName("Root")
        self.setCentralWidget(central)
        self.setWindowIcon(make_app_icon())

        self._network = QNetworkAccessManager(self)
        self._posters: dict[str, QPixmap] = {}
        self._row_status: dict[tuple[str, str], str] = {}
        self._source_filter = ""
        self._detail_candidate: StreamCandidate | None = None
        self._imdb_results: list[Title] = []
        self._imdb_title: Title | None = None
        self._imdb_task: ImdbTask | None = None
        self._imdb_detail_task: ImdbTask | None = None

        # la libreria locale (ex VistoFlow) è un widget della finestra unica
        self.library = VistoFlowApp()
        self.library.setWindowFlags(Qt.WindowType.Widget)
        self.library.fullscreen_changed.connect(self._on_library_fullscreen)

        self.rail = self._build_rail()
        self.pages = QStackedWidget()
        self.pages.addWidget(self.library)
        self.pages.addWidget(self._build_search_page())
        self.pages.addWidget(self._build_imdb_page())
        self.pages.addWidget(self._build_details_page())
        self.pages.addWidget(self._build_player_page())
        self.pages.addWidget(self._build_sources_page())
        self.pages.addWidget(self._build_settings_page())
        self.pages.addWidget(DownloadPage(self._download_server))
        # lo stile scuro "Stream Goat" vale per le pagine nuove; la libreria tiene il suo
        self.rail.setStyleSheet(THEME)
        for index in range(1, self.pages.count()):
            self.pages.widget(index).setStyleSheet(THEME)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.rail)
        layout.addWidget(self.pages, 1)

        self.statusBar().showMessage(_("Pronto"))
        self._go(self.PAGE_LIBRARY)

        quit_action = QAction(self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)
        # scorciatoie limitate alla propria pagina: la libreria usa Spazio/Ctrl+F per sé
        for widget, shortcut, slot in (
            (self.pages.widget(self.PAGE_SEARCH), QKeySequence.StandardKey.Find, self._focus_search),
            (self.player_panel, QKeySequence("F11"), self._toggle_fullscreen),
            (self.player_panel, QKeySequence("Space"), self._toggle_pause),
        ):
            action = QAction(widget)
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(slot)
            widget.addAction(action)

    def _build_rail(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(76)
        box = QVBoxLayout(rail)
        box.setContentsMargins(14, 18, 14, 18)
        box.setSpacing(10)
        logo = QLabel("▶")
        logo.setObjectName("RailLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(logo)
        box.addSpacing(14)
        self._rail_group = QButtonGroup(self)
        self._rail_group.setExclusive(True)

        def rail_button(icon: str, tip: str, page: int | None, slot=None) -> QToolButton:
            button = QToolButton()
            button.setObjectName("RailButton")
            button.setText(icon)
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if page is not None:
                button.setCheckable(True)
                self._rail_group.addButton(button, page)
                button.clicked.connect(lambda: self._go(page))
            else:
                button.clicked.connect(slot)
            return button

        box.addWidget(rail_button("▦", _("Libreria"), self.PAGE_LIBRARY))
        box.addWidget(rail_button("⌕", _("Cerca"), self.PAGE_SEARCH))
        box.addWidget(rail_button("▶", _("Player"), self.PAGE_PLAYER))
        box.addWidget(rail_button("☰", _("Fonti"), self.PAGE_SOURCES))
        box.addWidget(rail_button("↓", _("Download"), self.PAGE_DOWNLOAD))
        box.addStretch(1)
        box.addWidget(rail_button("⚙", _("Impostazioni"), self.PAGE_SETTINGS))
        box.addWidget(rail_button("⛶", _("Schermo intero (F11)"), None, self._fullscreen_current))
        return rail

    def _go(self, page: int) -> None:
        self.pages.setCurrentIndex(page)
        rail_page = self.PAGE_SEARCH if page in (self.PAGE_DETAILS, self.PAGE_IMDB) else page
        button = self._rail_group.button(rail_page)
        if button is not None:
            button.setChecked(True)

    @staticmethod
    def _page(title: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(36, 28, 36, 20)
        box.setSpacing(12)
        if title:
            heading = QLabel(title)
            heading.setObjectName("PageTitle")
            box.addWidget(heading)
        return page, box

    def _build_search_page(self) -> QWidget:
        page, box = self._page(_("Cerca"))
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("SearchField")
        self.search_edit.setPlaceholderText(_("Cerca film e serie su IMDb e nelle tue fonti"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(760)
        self.search_edit.returnPressed.connect(self._start_search)
        self.search_button = QPushButton(_("Cerca"))
        self.search_button.setObjectName("PrimaryButton")
        self.search_button.clicked.connect(self._start_search)
        row = QHBoxLayout()
        row.addWidget(self.search_edit, 1)
        row.addWidget(self.search_button)
        row.addStretch(0)
        box.addLayout(row)

        content = QWidget()
        sections = QVBoxLayout(content)
        sections.setContentsMargins(0, 0, 0, 0)
        sections.setSpacing(10)

        self.imdb_header = QLabel(_("IMDb"))
        self.imdb_header.setObjectName("SectionTitle")
        self.imdb_summary = QLabel(_("Scrivi un titolo e premi Invio."))
        self.imdb_summary.setObjectName("Muted")
        self.imdb_grid = PosterGrid()
        self.imdb_grid.itemClicked.connect(lambda _item: self._open_imdb())
        sections.addWidget(self.imdb_header)
        sections.addWidget(self.imdb_summary)
        sections.addWidget(self.imdb_grid)

        self.sources_header = QLabel(_("Dalle tue fonti"))
        self.sources_header.setObjectName("SectionTitle")
        sections.addSpacing(10)
        sections.addWidget(self.sources_header)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(8)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        chips_row = QHBoxLayout()
        chips_row.addLayout(self.chips)
        chips_row.addStretch(1)
        sections.addLayout(chips_row)
        self.summary_label = QLabel(_("Nessuna ricerca"))
        self.summary_label.setObjectName("Muted")
        sections.addWidget(self.summary_label)
        self.results = PosterGrid()
        self.results.itemClicked.connect(lambda _item: self._open_details())
        self.results.itemActivated.connect(lambda _item: self._play_selected())
        sections.addWidget(self.results)
        sections.addStretch(1)

        self.search_scroll = QScrollArea()
        self.search_scroll.setWidgetResizable(True)
        self.search_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.search_scroll.setWidget(content)
        box.addWidget(self.search_scroll, 1)
        return page

    def _build_imdb_page(self) -> QWidget:
        page, box = self._page("")
        back = QToolButton()
        back.setObjectName("RoundButton")
        back.setText("←")
        back.setToolTip(_("Indietro"))
        back.clicked.connect(lambda: self._go(self.PAGE_SEARCH))
        badge = QLabel("IMDb")
        badge.setObjectName("ImdbBadge")
        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)
        top.addWidget(badge)
        box.addLayout(top)

        self.imdb_poster = QLabel()
        self.imdb_poster.setFixedSize(_DETAIL_W, _DETAIL_H)
        self.imdb_name = QLabel()
        self.imdb_name.setObjectName("DetailTitle")
        self.imdb_name.setWordWrap(True)
        self.imdb_meta = QHBoxLayout()
        self.imdb_meta.setSpacing(8)
        self.imdb_people = QLabel()
        self.imdb_people.setWordWrap(True)
        self.imdb_people.setTextFormat(Qt.TextFormat.RichText)
        self.imdb_plot = QLabel()
        self.imdb_plot.setObjectName("Muted")
        self.imdb_plot.setWordWrap(True)
        self.imdb_status = QLabel()
        self.imdb_status.setObjectName("Muted")
        self.imdb_status.setWordWrap(True)

        self.imdb_play_button = QPushButton("▶  " + _("Riproduci dalla libreria"))
        self.imdb_play_button.setObjectName("WhiteButton")
        self.imdb_play_button.clicked.connect(self._play_imdb_from_library)
        sources_button = QPushButton("⌕  " + _("Cerca nelle tue fonti"))
        sources_button.setObjectName("GhostButton")
        sources_button.clicked.connect(self._search_imdb_in_sources)
        open_button = QPushButton("↗  " + _("Apri su IMDb"))
        open_button.setObjectName("GhostButton")
        open_button.clicked.connect(
            lambda: self._imdb_title and QDesktopServices.openUrl(QUrl(self._imdb_title.url))
        )
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self.imdb_play_button)
        actions.addWidget(sources_button)
        actions.addWidget(open_button)
        actions.addStretch(1)

        info = QVBoxLayout()
        info.setSpacing(12)
        info.addWidget(self.imdb_name)
        info.addLayout(self.imdb_meta)
        info.addWidget(self.imdb_people)
        info.addWidget(self.imdb_plot)
        info.addSpacing(8)
        info.addLayout(actions)
        info.addWidget(self.imdb_status)
        info.addStretch(1)

        body = QHBoxLayout()
        body.setSpacing(36)
        body.addWidget(self.imdb_poster, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(info, 1)
        box.addSpacing(10)
        box.addLayout(body, 1)
        return page

    def _build_details_page(self) -> QWidget:
        page, box = self._page("")
        back = QToolButton()
        back.setObjectName("RoundButton")
        back.setText("←")
        back.setToolTip(_("Indietro"))
        back.clicked.connect(lambda: self._go(self.PAGE_SEARCH))
        self.detail_source = QLabel()
        self.detail_source.setObjectName("Chip")
        top = QHBoxLayout()
        top.addWidget(back)
        top.addStretch(1)
        top.addWidget(self.detail_source)
        box.addLayout(top)

        self.detail_poster = QLabel()
        self.detail_poster.setFixedSize(_DETAIL_W, _DETAIL_H)
        self.detail_title = QLabel()
        self.detail_title.setObjectName("DetailTitle")
        self.detail_title.setWordWrap(True)
        self.detail_meta = QHBoxLayout()
        self.detail_meta.setSpacing(8)
        self.detail_description = QLabel()
        self.detail_description.setObjectName("Muted")
        self.detail_description.setWordWrap(True)
        self.detail_status = QLabel()
        self.detail_status.setObjectName("Muted")
        self.detail_status.setWordWrap(True)

        self.play_button = QPushButton("▶  " + _("Riproduci"))
        self.play_button.setObjectName("WhiteButton")
        self.play_button.clicked.connect(self._play_selected)
        self.verify_button = QPushButton("✓  " + _("Verifica flusso"))
        self.verify_button.setObjectName("GhostButton")
        self.verify_button.clicked.connect(self._verify_selected)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self.play_button)
        actions.addWidget(self.verify_button)
        actions.addStretch(1)

        info = QVBoxLayout()
        info.setSpacing(12)
        info.addStretch(1)
        info.addWidget(self.detail_title)
        info.addLayout(self.detail_meta)
        info.addWidget(self.detail_description)
        info.addSpacing(8)
        info.addLayout(actions)
        info.addWidget(self.detail_status)
        info.addStretch(2)

        body = QHBoxLayout()
        body.setSpacing(36)
        body.addWidget(self.detail_poster, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(info, 1)
        box.addSpacing(10)
        box.addLayout(body)
        box.addStretch(1)
        return page

    def _build_player_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        self.player_panel = PlayerPanel()
        self.player_panel.play_requested.connect(self._play_selected)
        self.player_panel.pause_requested.connect(self._toggle_pause)
        self.player_panel.stop_requested.connect(self._stop_playback)
        self.player_panel.seek_requested.connect(self._seek)
        self.player_panel.skip_requested.connect(self._skip)
        self.player_panel.volume_changed.connect(self._set_volume)
        self.player_panel.fullscreen_requested.connect(self._toggle_fullscreen)
        box.addWidget(self.player_panel)
        return page

    def _build_sources_page(self) -> QWidget:
        page, box = self._page(_("Fonti"))
        hint = QLabel(
            _("Le fonti sono cataloghi JSON, API JSON, siti web o link diretti che hai "
            "il diritto di usare. I flussi vengono verificati prima della riproduzione.")
        )
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        box.addWidget(hint)

        self.sources_table = QTableWidget(0, 3)
        self.sources_table.setHorizontalHeaderLabels((_("Attiva"), _("Nome"), _("Tipo")))
        self.sources_table.verticalHeader().setVisible(False)
        self.sources_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sources_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sources_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.sources_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.sources_table.itemChanged.connect(self._on_source_item_changed)
        self.sources_table.doubleClicked.connect(lambda _index: self._edit_source())

        buttons = QHBoxLayout()
        for text, slot, primary in (
            (_("Aggiungi"), self._add_source, True),
            (_("Sito web"), self._add_site, False),
            (_("Link diretto"), self._add_direct_link, False),
            (_("Modifica"), self._edit_source, False),
            (_("Rimuovi"), self._remove_source, False),
        ):
            button = QPushButton(text)
            if primary:
                button.setObjectName("PrimaryButton")
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        box.addLayout(buttons)
        box.addWidget(self.sources_table, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page, box = self._page(_("Impostazioni"))
        card = QFrame()
        card.setObjectName("Card")
        form = QHBoxLayout(card)
        form.setContentsMargins(20, 16, 20, 16)
        label = QLabel(_("Lingua dell'interfaccia"))
        combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            combo.addItem(name, code)
        combo.setCurrentIndex(combo.findData(i18n.language()))
        combo.currentIndexChanged.connect(lambda: change_language(self, combo.currentData()))
        form.addWidget(label)
        form.addStretch(1)
        form.addWidget(combo)
        box.addWidget(card)
        box.addStretch(1)
        return page

    # ------------------------------------------------------- griglia/dettagli

    def _rebuild_chips(self) -> None:
        while self.chips.count():
            widget = self.chips.takeAt(0).widget()
            if widget is not None:
                self._chip_group.removeButton(widget)
                widget.deleteLater()
        names = sorted({candidate.source_name for candidate in self._candidates})
        for value, text in [("", _("Tutte"))] + [(name, name) for name in names]:
            chip = QPushButton(text)
            chip.setObjectName("FilterChip")
            chip.setCheckable(True)
            chip.setChecked(value == self._source_filter)
            chip.clicked.connect(lambda _checked=False, v=value: self._apply_filter(v))
            self._chip_group.addButton(chip)
            self.chips.addWidget(chip)

    def _apply_filter(self, source_name: str) -> None:
        self._source_filter = source_name
        for row, candidate in enumerate(self._candidates):
            self.results.item(row).setHidden(
                bool(source_name) and candidate.source_name != source_name
            )
        self.results.fit()

    def _add_result_item(self, candidate: StreamCandidate) -> None:
        item = QListWidgetItem(candidate.title)
        item.setToolTip(f"{candidate.title} · {candidate.source_name}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        item.setIcon(_icon(self._poster_for(candidate, _POSTER_W, _POSTER_H)))
        self.results.addItem(item)
        if candidate.poster and candidate.poster not in self._posters:
            self._fetch_poster(candidate.poster)

    def _add_imdb_item(self, title: Title) -> None:
        caption = title.name + (f"\n★ {title.rating}" if title.rating else f"\n{title.year}")
        item = QListWidgetItem(caption)
        item.setToolTip(f"{title.name} ({title.year}) — IMDb {title.imdb_id}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        item.setIcon(_icon(self._poster_for(title, _POSTER_W, _POSTER_H)))
        self.imdb_grid.addItem(item)
        if title.poster and title.poster not in self._posters:
            self._fetch_poster(title.poster)

    def _poster_for(self, candidate, width: int, height: int) -> QPixmap:
        label = getattr(candidate, "title", "") if isinstance(candidate, StreamCandidate) else candidate.name
        pixmap = self._posters.get(candidate.poster) if candidate.poster else None
        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(
                width,
                height,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            return _rounded(scaled.copy(0, 0, width, height))
        return _placeholder_poster(label, width, height)

    def _fetch_poster(self, url: str) -> None:
        self._posters[url] = QPixmap()  # segnaposto: evita richieste doppie
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "Mozilla/5.0 VistoFlow")
        reply = self._network.get(request)
        reply.finished.connect(lambda: self._on_poster_reply(url, reply))

    def _on_poster_reply(self, url: str, reply) -> None:
        pixmap = QPixmap()
        if reply.error() == reply.NetworkError.NoError:
            pixmap.loadFromData(reply.readAll())
        reply.deleteLater()
        if pixmap.isNull():
            return
        self._posters[url] = pixmap
        for row, candidate in enumerate(self._candidates):
            item = self.results.item(row)
            if candidate.poster == url and item is not None:
                item.setIcon(_icon(self._poster_for(candidate, _POSTER_W, _POSTER_H)))
        for row, title in enumerate(self._imdb_results):
            item = self.imdb_grid.item(row)
            if title.poster == url and item is not None:
                item.setIcon(_icon(self._poster_for(title, _POSTER_W, _POSTER_H)))
        if self._detail_candidate is not None and self._detail_candidate.poster == url:
            self._fill_details(self._detail_candidate)
        if self._imdb_title is not None and self._imdb_title.poster == url:
            self.imdb_poster.setPixmap(self._poster_for(self._imdb_title, _DETAIL_W, _DETAIL_H))

    def _open_details(self) -> None:
        row = self.results.currentRow()
        if not 0 <= row < len(self._candidates):
            return
        self._fill_details(self._candidates[row])
        self._go(self.PAGE_DETAILS)

    def _fill_details(self, candidate: StreamCandidate) -> None:
        self._detail_candidate = candidate
        self.detail_poster.setPixmap(self._poster_for(candidate, _DETAIL_W, _DETAIL_H))
        self.detail_title.setText(candidate.title)
        self.detail_source.setText(candidate.source_name)
        while self.detail_meta.count():
            widget = self.detail_meta.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for text in (_kind_label(candidate), candidate.display_year()):
            if text:
                chip = QLabel(text)
                chip.setObjectName("Chip")
                self.detail_meta.addWidget(chip)
        self.detail_meta.addStretch(1)
        self.detail_description.setText(candidate.description)
        self.detail_description.setVisible(bool(candidate.description))
        self.detail_status.setText(self._row_status.get(candidate.key, ""))
        self.player_panel.set_title(candidate.title)


    # --------------------------------------------------------------- IMDb

    def _start_imdb_search(self, query: str) -> None:
        if not query or (self._imdb_task is not None and self._imdb_task.isRunning()):
            return
        self.imdb_summary.setText(_("Ricerca su IMDb…"))
        self._imdb_task = ImdbTask(query=query, parent=self)
        self._imdb_task.completed.connect(self._on_imdb_results)
        self._imdb_task.failed.connect(lambda message: self.imdb_summary.setText(message))
        self._imdb_task.start()

    def _on_imdb_results(self, results: list) -> None:
        self._imdb_results = list(results)
        self.imdb_grid.clear()
        for title in self._imdb_results:
            self._add_imdb_item(title)
        self.imdb_grid.fit()
        self.imdb_summary.setText(
            _(f"{len(self._imdb_results)} titoli su IMDb") if self._imdb_results
            else _("Nessun titolo trovato su IMDb")
        )

    def _open_imdb(self) -> None:
        row = self.imdb_grid.currentRow()
        if not 0 <= row < len(self._imdb_results):
            return
        self._fill_imdb(self._imdb_results[row])
        self._go(self.PAGE_IMDB)
        self._imdb_detail_task = ImdbTask(title=self._imdb_results[row], parent=self)
        self._imdb_detail_task.completed.connect(self._fill_imdb)
        self._imdb_detail_task.failed.connect(lambda message: self.imdb_status.setText(message))
        self._imdb_detail_task.start()

    def _fill_imdb(self, title: Title) -> None:
        self._imdb_title = title
        self.imdb_poster.setPixmap(self._poster_for(title, _DETAIL_W, _DETAIL_H))
        self.imdb_name.setText(title.name)
        while self.imdb_meta.count():
            widget = self.imdb_meta.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        chips = [_("Serie TV") if title.kind == "series" else _("Film"), title.year,
                 f"★ {title.rating}" if title.rating else "", title.runtime]
        if title.kind == "series" and title.seasons:
            chips.append(_(f"{title.seasons} stagioni"))
        chips.extend(title.genres[:3])
        for text in chips:
            if text:
                chip = QLabel(text)
                chip.setObjectName("RatingChip" if text.startswith("★") else "Chip")
                self.imdb_meta.addWidget(chip)
        self.imdb_meta.addStretch(1)
        people = []
        if title.director:
            people.append(f"<b>{_('Regia')}</b>: " + ", ".join(title.director[:3]))
        if title.cast:
            people.append(f"<b>{_('Cast')}</b>: " + ", ".join(title.cast[:8]))
        self.imdb_people.setText("<br>".join(people))
        self.imdb_plot.setText(title.description)
        in_library = self.library.imdb_title_in_library(title)
        self.imdb_play_button.setEnabled(in_library)
        self.imdb_status.setText(
            _("Disponibile nella tua libreria.") if in_library
            else _("Non è nella tua libreria: cercalo nelle tue fonti.")
        )

    def _play_imdb_from_library(self) -> None:
        if self._imdb_title is not None and self.library.play_imdb_title(self._imdb_title):
            self._go(self.PAGE_LIBRARY)

    def _search_imdb_in_sources(self) -> None:
        if self._imdb_title is None:
            return
        self.search_edit.setText(self._imdb_title.name)
        self._go(self.PAGE_SEARCH)
        self._start_source_search(self._imdb_title.name, notify=True)
        self.search_scroll.ensureWidgetVisible(self.sources_header)

    # ----------------------------------------------------- schermo intero

    def _fullscreen_current(self) -> None:
        if self.pages.currentIndex() == self.PAGE_LIBRARY:
            self.library.toggle_fullscreen()
        else:
            self._toggle_fullscreen()

    def _on_library_fullscreen(self, full: bool) -> None:
        self.rail.setVisible(not full)
        self.statusBar().setVisible(not full)

    # ------------------------------------------------------------- fonti

    def _reload_sources(self) -> None:
        self._sources = config.load_sources()
        self._refresh_sources_view()

    def _refresh_sources_view(self) -> None:
        self._saving = True
        self.sources_table.setRowCount(len(self._sources))
        for row, source in enumerate(self._sources):
            enabled = QTableWidgetItem("")
            enabled.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEnabled
            )
            enabled.setCheckState(
                Qt.CheckState.Checked if source.enabled else Qt.CheckState.Unchecked
            )
            enabled.setData(Qt.ItemDataRole.UserRole, source.id)
            self.sources_table.setItem(row, 0, enabled)
            self.sources_table.setItem(row, 1, QTableWidgetItem(source.name))
            self.sources_table.setItem(row, 2, QTableWidgetItem(_describe_source(source)))
        self._saving = False

    def _persist_sources(self) -> None:
        try:
            config.save_sources(self._sources)
        except OSError as error:
            QMessageBox.warning(self, _("Salvataggio fallito"), str(error))
        self._refresh_sources_view()

    def _on_source_item_changed(self, item: QTableWidgetItem) -> None:
        if self._saving or item.column() != 0:
            return
        source_id = item.data(Qt.ItemDataRole.UserRole)
        for source in self._sources:
            if source.id == source_id:
                source.enabled = item.checkState() == Qt.CheckState.Checked
                break
        self._persist_sources()

    def _selected_source(self) -> Source | None:
        row = self.sources_table.currentRow()
        if 0 <= row < len(self._sources):
            return self._sources[row]
        return None

    def _add_source(self) -> None:
        dialog = SourceEditorDialog(self, kind="catalog")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source = dialog.edited_source()
        if any(existing.id == source.id for existing in self._sources):
            QMessageBox.warning(self, _("Fonte duplicata"), _("Esiste già una fonte con lo stesso identificativo."))
            return
        self._sources.append(source)
        self._persist_sources()
        self.statusBar().showMessage(_(f"Fonte aggiunta: {source.name}"), 5000)

    def _add_site(self) -> None:
        dialog = SourceEditorDialog(self, kind="site")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source = dialog.edited_source()
        if any(existing.id == source.id for existing in self._sources):
            QMessageBox.warning(
                self, _("Fonte duplicata"), _("Esiste già una fonte con lo stesso identificativo.")
            )
            return
        self._sources.append(source)
        self._persist_sources()
        self.statusBar().showMessage(_(f"Sito aggiunto: {source.name}"), 5000)

    def _add_direct_link(self) -> None:
        dialog = DirectLinkDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source = dialog.added_source()
        self._sources.append(source)
        self._persist_sources()
        self.statusBar().showMessage(_(f"Link aggiunto: {source.title}"), 5000)

    def _edit_source(self) -> None:
        source = self._selected_source()
        if source is None:
            QMessageBox.information(self, _("Nessuna fonte"), _("Seleziona una fonte da modificare."))
            return
        dialog = SourceEditorDialog(self, source=source)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.edited_source()
        for index, existing in enumerate(self._sources):
            if existing.id == source.id:
                self._sources[index] = updated
                break
        self._persist_sources()
        self.statusBar().showMessage(_(f"Fonte aggiornata: {updated.name}"), 5000)

    def _remove_source(self) -> None:
        source = self._selected_source()
        if source is None:
            QMessageBox.information(self, _("Nessuna fonte"), _("Seleziona una fonte da rimuovere."))
            return
        answer = QMessageBox.question(
            self,
            _("Rimuovere la fonte?"),
            _(f"Rimuovere «{source.name}»?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._sources = [item for item in self._sources if item.id != source.id]
        self._persist_sources()

    # ------------------------------------------------------------ ricerca

    def _focus_search(self) -> None:
        self.search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_edit.selectAll()

    def _start_search(self) -> None:
        query = self.search_edit.text().strip()
        self._go(self.PAGE_SEARCH)
        self._start_imdb_search(query)
        self._start_source_search(query, notify=not query)

    def _start_source_search(self, query: str, notify: bool = False) -> None:
        if self._search_task is not None and self._search_task.isRunning():
            return
        enabled = [source for source in self._sources if source.enabled]
        if not enabled:
            self.summary_label.setText(_("Nessuna fonte attiva: aggiungile dalla sezione «Fonti»."))
            if notify:
                QMessageBox.information(
                    self,
                    _("Nessuna fonte attiva"),
                    _("Aggiungi o attiva almeno una fonte dalla sezione «Fonti»."),
                )
            return

        self.search_button.setEnabled(False)
        self.summary_label.setText(_("Ricerca in corso…"))
        self.statusBar().showMessage(_("Ricerca in corso…"))

        self._search_task = SearchTask(enabled, query, self)
        self._search_task.progress.connect(
            lambda name, count: self.statusBar().showMessage(
                _(f"Fonte {name}: {count} risultati"), 3000
            )
        )
        self._search_task.completed.connect(self._on_search_completed)
        self._search_task.failed.connect(self._on_search_failed)
        self._search_task.finished.connect(self._on_search_finished)
        self._search_task.start()

    def _on_search_finished(self) -> None:
        self.search_button.setEnabled(True)
        if self._search_task is not None:
            self._search_task.deleteLater()
            self._search_task = None

    def _on_search_failed(self, message: str) -> None:
        self.summary_label.setText(_("Ricerca non riuscita"))
        self.statusBar().showMessage(message, 8000)
        if self._smoke:
            self._finish_smoke(False, f"ricerca non riuscita: {message}")

    def _on_search_completed(self, outcome) -> None:
        autoplay = self._autoplay_query
        self._autoplay_query = None
        self._last_outcome = outcome
        self._candidates = list(outcome.candidates)
        self.results.clear()
        self._source_filter = ""
        for candidate in self._candidates:
            self._add_result_item(candidate)
        self._rebuild_chips()
        self.results.fit()

        elapsed = outcome.elapsed
        self.summary_label.setText(
            _(f"{len(self._candidates)} risultati in {elapsed:.1f}s "
            f"da {len(self._sources)} fonti configurate")
        )
        self.statusBar().showMessage(
            _(f"Ricerca completata: {len(self._candidates)} risultati"), 6000
        )
        if outcome.errors:
            details = "; ".join(
                _(f"{error.source_name}: {error.message}") for error in outcome.errors
            )
            self.statusBar().showMessage(_(f"Fonti con errori — {details}"), 12000)

        if self._candidates:
            self.results.setCurrentRow(0)
            self.player_panel.set_title(self._candidates[0].title)
        elif self._smoke:
            self._finish_smoke(False, "nessun risultato")

        if autoplay is not None and self._candidates:
            candidate = self._candidates[0]
            QTimer.singleShot(150, lambda: self._request_play(candidate))

    # ----------------------------------------------------------- verifica

    def _selected_candidate(self) -> StreamCandidate | None:
        if self.pages.currentIndex() == self.PAGE_DETAILS and self._detail_candidate is not None:
            return self._detail_candidate
        row = self.results.currentRow()
        if 0 <= row < len(self._candidates):
            return self._candidates[row]
        return None

    def _verify_selected(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            QMessageBox.information(
                self, _("Nessun contenuto"), _("Esegui una ricerca e seleziona un risultato.")
            )
            return
        self._start_probe(candidate, purpose="verify")

    def _start_probe(self, candidate: StreamCandidate, purpose: str) -> None:
        if self._probe_task is not None and self._probe_task.isRunning():
            self.statusBar().showMessage(_("Verifica già in corso…"), 3000)
            return
        self._set_row_status(
            candidate, _("Risoluzione pagina…") if candidate.needs_resolution else _("Verifica…")
        )
        self.player_panel.set_status(
            _("Ricerca del flusso nella pagina…")
            if candidate.needs_resolution
            else _("Verifica del flusso…")
        )
        self.verify_button.setEnabled(False)
        self.play_button.setEnabled(False)

        source = next(
            (item for item in self._sources if item.id == candidate.source_id), None
        )
        self._probe_candidate = candidate
        self._probe_task = ProbeTask(candidate, purpose, source, self)
        self._probe_task.completed.connect(self._on_probe_completed)
        self._probe_task.failed.connect(self._on_probe_failed)
        self._probe_task.finished.connect(self._on_probe_finished)
        self._probe_task.start()

    def _on_probe_finished(self) -> None:
        self.verify_button.setEnabled(True)
        self.play_button.setEnabled(True)
        if self._probe_task is not None:
            self._probe_task.deleteLater()
            self._probe_task = None

    def _on_probe_failed(self, purpose: str, message: str) -> None:
        self.player_panel.set_status(_(f"Verifica non riuscita: {message}"))
        self.statusBar().showMessage(message, 10000)
        if self._smoke and purpose == "play":
            self._finish_smoke(False, f"verifica non riuscita: {message}")
        elif purpose == "play":
            QMessageBox.warning(self, _("Flusso non trovato"), message)

    def _on_probe_completed(
        self, result: ProbeResult, purpose: str, stream: StreamCandidate
    ) -> None:
        candidate = self._probe_candidate or self._selected_candidate()
        resolved = False
        if candidate is not None:
            self._probes[candidate.key] = result
            if result.ok:
                self._streams[candidate.key] = stream
                resolved = stream is not candidate
            label = ("✓ " if result.ok else "✗ ") + result.label()
            if resolved:
                label += _(" — flusso trovato nella pagina")
            self._set_row_status(candidate, label)

        if purpose == "verify":
            if result.ok:
                detail = _(f" — {stream.kind.upper()} {stream.url}") if resolved else ""
                self.statusBar().showMessage(
                    _(f"{result.label()} — HTTP {result.status} — {result.details}{detail}"),
                    10000,
                )
                self.player_panel.set_status(
                    _(f"{result.label()}{' (pagina risolta)' if resolved else ''}")
                )
            else:
                self.statusBar().showMessage(_(f"Non disponibile: {result.error}"), 8000)
                self.player_panel.set_status(_(f"Non disponibile: {result.error}"))
            return

        if not result.ok:
            self.player_panel.set_status(_(f"Non disponibile: {result.error}"))
            self.statusBar().showMessage(_(f"Flusso non disponibile: {result.error}"), 8000)
            if self._smoke:
                self._finish_smoke(False, f"flusso non disponibile: {result.error}")
            else:
                QMessageBox.warning(
                    self,
                    _("Flusso non disponibile"),
                    _(f"Il flusso non è raggiungibile o non è riproducibile.\n\n{result.error}"),
                )
            return

        self._pending_play = stream
        self._ensure_player(stream)

    def _set_row_status(self, candidate: StreamCandidate, text: str) -> None:
        self._row_status[candidate.key] = text
        if self._detail_candidate is candidate:
            self.detail_status.setText(text)

    # ------------------------------------------------------------- player

    def _play_selected(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            QMessageBox.information(
                self, _("Nessun contenuto"), _("Esegui una ricerca e seleziona un risultato.")
            )
            return
        self._request_play(candidate)

    def _request_play(self, candidate: StreamCandidate) -> None:
        cached = self._probes.get(candidate.key)
        if cached is not None and cached.ok:
            target = self._streams.get(candidate.key, candidate)
            self._pending_play = target
            self._ensure_player(target)
            return
        self._start_probe(candidate, purpose="play")

    def _play_download_stream(self, url: str, referer: str, title: str, key: str = "") -> None:
        """«Guarda» dal pannello di download: il flusso è già risolto, niente verifica."""
        candidate = StreamCandidate(
            source_id="download", source_name=_("Download"),
            title=title or _("Streaming"), url=url, referer=referer, resume_key=key,
        )
        if self._player is None:
            self._player = MpvController(self._mpv_path)
        if not self._player.is_available:
            # Senza mpv: il player VLC della libreria apre lo stesso HLS con il Referer.
            self._go(self.PAGE_LIBRARY)
            self.library._on_browser_stream_play(
                {"url": url, "referer": referer, "title": candidate.title}
            )
            return
        self._pending_play = candidate
        self._ensure_player(candidate)

    def _ensure_player(self, candidate: StreamCandidate) -> None:
        self._go(self.PAGE_PLAYER)  # la superficie video deve essere visibile per mpv
        vlc_player = self.library.player.player
        if vlc_player.is_playing():  # un solo audio alla volta
            self.library.player.toggle_pause()
        if self._player is not None and self._player.is_running:
            self._load_candidate(candidate)
            return

        if self._start_task is not None and self._start_task.isRunning():
            return

        if self._player is None:
            self._player = MpvController(self._mpv_path)
        if not self._player.is_available:
            message = (
                _("mpv non è stato trovato.\n\n"
                "Imposta la variabile d'ambiente MPV_PATH oppure copia mpv.exe "
                "nella cartella bin/ accanto all'applicazione.")
            )
            self.player_panel.set_status(_("mpv non disponibile"))
            if self._smoke:
                self._finish_smoke(False, "mpv non trovato")
            else:
                QMessageBox.critical(self, _("mpv non trovato"), message)
            return

        window_id = int(self.player_panel.video.winId())
        if not window_id:
            self.player_panel.set_status(_("Superficie video non pronta"))
            return

        self.player_panel.set_busy(True)
        self.player_panel.set_status(_("Avvio del player…"))
        self._start_task = PlayerStartTask(self._player, window_id, self)
        self._start_task.ready.connect(self._on_player_started)
        self._start_task.failed.connect(self._on_player_failed)
        self._start_task.finished.connect(self._on_player_task_finished)
        self._start_task.start()

    def _on_player_task_finished(self) -> None:
        self.player_panel.set_busy(False)
        if self._start_task is not None:
            self._start_task.deleteLater()
            self._start_task = None

    def _on_player_started(self) -> None:
        self.statusBar().showMessage(_("Player avviato"), 4000)
        if self._pending_play is not None:
            self._load_candidate(self._pending_play)

    def _on_player_failed(self, message: str) -> None:
        self.player_panel.set_status(_(f"Errore player: {message}"))
        self._pending_play = None
        if self._smoke:
            self._finish_smoke(False, f"player non avviato: {message}")
        else:
            QMessageBox.critical(self, _("Errore del player"), message)

    def _load_candidate(self, candidate: StreamCandidate) -> None:
        assert self._player is not None
        self._loading_candidate = candidate
        self._resume.save()  # il contenuto precedente, prima di cambiare
        self._resume_key = candidate.resume_key or candidate.page_url or candidate.url
        self._resume_title = candidate.title
        self._resume_pending = self._resume.get(self._resume_key)
        self.player_panel.set_active(True)
        self.player_panel.set_title(candidate.title)
        self.player_panel.set_status(_("Caricamento del flusso…"))
        self.statusBar().showMessage(_(f"Apertura flusso: {candidate.url}"), 6000)
        try:
            self._player.load(candidate)
        except (MpvError, OSError) as error:
            self.player_panel.set_status(_(f"Errore: {error}"))
            if self._smoke:
                self._finish_smoke(False, f"caricamento non riuscito: {error}")
            else:
                QMessageBox.critical(self, _("Errore di caricamento"), str(error))
            return
        self._pending_play = None
        self.player_panel.take_focus()

    def _toggle_pause(self) -> None:
        if self._player is None or not self._player.is_running:
            if self._selected_candidate() is not None:
                self._play_selected()
            return
        try:
            self._player.toggle_pause()
        except (MpvError, OSError) as error:
            self.statusBar().showMessage(_(f"Comando non riuscito: {error}"), 5000)

    def _stop_playback(self) -> None:
        self._loading_candidate = None
        self._resume.save()
        self._resume_key = ""
        if self._player is not None and self._player.is_running:
            try:
                self._player.stop()
            except (MpvError, OSError):
                pass
        self.player_panel.set_active(False)
        self.player_panel.set_status(_("Fermato"))

    def _seek(self, value: float) -> None:
        if self._player is None or not self._player.is_running:
            return
        try:
            self._player.seek(max(0.0, value))
        except (MpvError, OSError) as error:
            self.statusBar().showMessage(_(f"Seek non riuscito: {error}"), 5000)

    def _skip(self, delta: float) -> None:
        if self._player is None or not self._player.is_running:
            return
        try:
            self._player.seek_by(delta)
        except (MpvError, OSError) as error:
            self.statusBar().showMessage(_(f"Seek non riuscito: {error}"), 5000)

    def _set_volume(self, volume: int) -> None:
        if self._player is None or not self._player.is_running:
            return
        try:
            self._player.set_volume(volume)
        except (MpvError, OSError):
            pass

    def _poll_player(self) -> None:
        if self._player is None or not self._player.is_running:
            if self._smoke and time.monotonic() > self._smoke_deadline:
                self._finish_smoke(False, "timeout in attesa del player")
            return

        state = self._player.get_state()
        self.player_panel.update_state(state)

        candidate = self._loading_candidate
        if candidate is not None and state.get("duration_ms", 0) > 0:
            self.player_panel.set_status(_("In riproduzione"))
            if self._announced is not candidate:  # una volta: non deve coprire «Ripreso da»
                self._announced = candidate
                self.statusBar().showMessage(
                    _(f"Flusso avviato: {candidate.title} — "
                    f"{state['duration_ms'] / 1000:.1f}s"),
                    8000,
                )
            if (
                self._smoke
                and not self._smoke_done
                and state.get("position_ms", 0) >= 800
            ):
                self._finish_smoke(
                    True,
                    _(f"flusso avviato: {candidate.title} "
                    f"({state['duration_ms'] / 1000:.1f}s, "
                    f"{state.get('width', 0)}x{state.get('height', 0)}, "
                    f"posizione {state.get('position_ms', 0) / 1000:.1f}s)"),
                )
        self._track_resume(state)

        if self._smoke and not self._smoke_done and time.monotonic() > self._smoke_deadline:
            self._finish_smoke(False, "timeout: il flusso non si è avviato")

    # -------------------------------------------------------- autoplay/smoke

    def _start_autoplay(self) -> None:
        query = self._autoplay_query or "sintel"
        self.search_edit.setText(query)
        self._autoplay_query = query
        self._start_search()

    def _finish_smoke(self, ok: bool, message: str) -> None:
        if self._smoke_done:
            return
        self._smoke_done = True
        self.smoke_finished.emit(ok, message)

    # ------------------------------------------------------------ finestra

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.rail.show()
            self.statusBar().show()
        else:
            self.rail.hide()
            self.statusBar().hide()
            self._go(self.PAGE_PLAYER)
            self.showFullScreen()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - API Qt
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self._toggle_fullscreen()
            return
        super().keyPressEvent(event)

    def _track_resume(self, state: dict) -> None:
        """Riporta il contenuto dove eri arrivato, poi ne annota l'avanzamento."""
        duration = state.get("duration_ms", 0.0) / 1000.0
        if not self._resume_key or duration <= 0 or state.get("idle"):
            return
        if self._resume_pending is not None:
            target, self._resume_pending = self._resume_pending, None
            if target < duration - END_MARGIN_S:
                try:
                    self._player.seek(target)
                    self.statusBar().showMessage(
                        _("Ripreso da {time}").format(time=_format_time(target * 1000)), 8000
                    )
                except (MpvError, OSError):
                    pass
            return
        position = state.get("position_ms", 0.0) / 1000.0
        if position <= 0:
            return
        self._resume.update(self._resume_key, position, duration, self._resume_title)
        if time.monotonic() - self._resume_saved_at > 5.0:
            self._resume.save()
            self._resume_saved_at = time.monotonic()

    def closeEvent(self, event) -> None:  # noqa: N802 - API Qt
        self._resume.save()
        for task in (self._search_task, self._probe_task, self._start_task,
                     self._imdb_task, self._imdb_detail_task):
            if task is not None and task.isRunning():
                task.wait(3000)
        self.library.close()  # salva avanzamento e ferma VLC
        self._download_server.stop()
        if self._player is not None:
            try:
                self._player.quit()
            except Exception:  # pragma: no cover - chiusura difensiva
                LOGGER.exception("Errore durante la chiusura di mpv")
        super().closeEvent(event)
