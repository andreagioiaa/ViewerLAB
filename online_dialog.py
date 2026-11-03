"""Interfaccia di ricerca online integrata in VistoFlow Pro.

Il dialogo non lancia processi esterni: usa la pipeline ``vistoflow_online``
in un thread dedicato e, quando l'utente sceglie un flusso, lo passa al
riproduttore VLC già incorporato nella finestra principale.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QRectF, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from async_tasks import AsyncOperation, ImageOperation
from vistoflow_online import (
    OnlineService,
    PlayRequest,
    ResolveOutcome,
    SearchResult,
    StreamSource,
)
from vistoflow_online.metadata import extract_year

ACCENT = "#2ecc71"
AMBER = "#f5a623"
MUTED = "#7d8797"


# ------------------------------------------------------------------------ delegate
class OnlineResultDelegate(QStyledItemDelegate):
    """Card compatta con poster, titolo, canale e metadati TMDB."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.f_title = QFont("Segoe UI")
        self.f_title.setPixelSize(14)
        self.f_title.setWeight(QFont.Weight.DemiBold)
        self.f_small = QFont("Segoe UI")
        self.f_small.setPixelSize(11)
        self.f_badge = QFont("Segoe UI")
        self.f_badge.setPixelSize(10)
        self.f_badge.setWeight(QFont.Weight.DemiBold)

    def sizeHint(self, option, index):
        return QSize(80, 92)

    def paint(self, painter, option, index):
        record = index.data(Qt.ItemDataRole.UserRole) or {}
        result: SearchResult | None = record.get("result")
        if result is None:
            return
        rect = option.rect.adjusted(4, 4, -4, -4)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            background, border = QColor("#1b3327"), QColor(ACCENT)
        elif hover:
            background, border = QColor("#1a222c"), QColor("#2b3644")
        else:
            background, border = QColor("#141a21"), QColor("#202a35")
        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 9, 9)

        cover = record.get("cover")
        poster = QRectF(rect.left() + 12, rect.top() + 12, 48, 68)
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(poster, 5, 5)
        painter.setClipPath(clip)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0b0f14"))
        painter.drawRect(poster)
        if isinstance(cover, QPixmap) and not cover.isNull():
            painter.drawPixmap(poster.toRect(), cover)
        else:
            painter.setPen(QColor("#46525f"))
            painter.setFont(self.f_badge)
            painter.drawText(
                poster,
                Qt.AlignmentFlag.AlignCenter,
                "🎞",
            )
        painter.restore()

        text_left = poster.right() + 12
        title = result.media_item.title if result.media_item else result.title
        original = result.media_item.original_title if result.media_item else None
        if original and original.casefold() != title.casefold():
            title = f"{title}  ·  {original}"
        title_rect = QRectF(
            text_left, rect.top() + 11, max(20.0, rect.right() - text_left - 12), 21
        )
        painter.setFont(self.f_title)
        painter.setPen(QColor("#eef3f8") if selected else QColor("#dde5ee"))
        elided = QFontMetrics(self.f_title).elidedText(
            title, Qt.TextElideMode.ElideRight, int(title_rect.width())
        )
        painter.drawText(
            title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided
        )

        meta = [result.channel_name]
        year = result.media_item.year if result.media_item else extract_year(result.title)
        if year:
            meta.append(str(year))
        if result.media_item and result.media_item.rating is not None:
            meta.append(f"⭐ {result.media_item.rating:.1f}")
        if result.media_item:
            meta.append("TMDB")
        meta_rect = QRectF(
            text_left, rect.top() + 36, max(20.0, rect.right() - text_left - 12), 18
        )
        painter.setFont(self.f_small)
        painter.setPen(QColor(MUTED))
        meta_text = "  ·  ".join(meta)
        meta_text = QFontMetrics(self.f_small).elidedText(
            meta_text, Qt.TextElideMode.ElideRight, int(meta_rect.width())
        )
        painter.drawText(
            meta_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, meta_text
        )

        # Punteggio del matching, utile per capire l'ordine dei risultati.
        score = int(round(max(0.0, min(1.0, result.score)) * 100))
        score_text = f"match {score}%"
        score_rect = QRectF(
            text_left, rect.top() + 60, max(20.0, rect.right() - text_left - 12), 17
        )
        painter.setFont(self.f_badge)
        painter.setPen(QColor(ACCENT if score >= 70 else MUTED))
        painter.drawText(
            score_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, score_text
        )
        painter.restore()


# ------------------------------------------------------------------ stream picker
class StreamChoiceDialog(QDialog):
    """Sceglie fra più flussi e mostra il comando VLC equivalente."""

    def __init__(self, streams: list[StreamSource], title: str, parent=None):
        super().__init__(parent)
        self.streams = streams
        self.title_text = title
        self.chosen: StreamSource | None = None

        self.setWindowTitle("Scegli il flusso")
        self.setMinimumSize(760, 500)
        self.resize(820, 540)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        heading = QLabel(f"Flussi disponibili per «{title}»")
        heading.setObjectName("CollectionTitle")
        heading.setWordWrap(True)
        root.addWidget(heading)

        hint = QLabel(
            "Scegli il flusso da aprire nel riproduttore VLC integrato. "
            "Gli header User-Agent e Referer vengono applicati automaticamente."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.list = QListWidget()
        self.list.setObjectName("OnlineResults")
        self.list.setUniformItemSizes(True)
        for stream in streams:
            quality = stream.quality or "auto"
            mime = stream.mime_type or "video"
            label = f"{stream.resolver_name}  ·  {quality}  ·  {mime}"
            item = QListWidgetItem(label)
            item.setToolTip(stream.url)
            self.list.addItem(item)
        self.list.currentRowChanged.connect(self._on_row)
        self.list.itemDoubleClicked.connect(lambda _item: self._accept_current())
        root.addWidget(self.list, 1)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setFixedHeight(110)
        root.addWidget(self.details)

        footer = QHBoxLayout()
        self.btn_copy = QPushButton("⧉  Copia comando VLC")
        self.btn_copy.setObjectName("Ghost")
        self.btn_copy.clicked.connect(self._copy_command)
        footer.addWidget(self.btn_copy)
        footer.addStretch()
        btn_cancel = QPushButton("Annulla")
        btn_cancel.setObjectName("Ghost")
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)
        self.btn_play = QPushButton("▶  Riproduci")
        self.btn_play.setObjectName("Primary")
        self.btn_play.clicked.connect(self._accept_current)
        footer.addWidget(self.btn_play)
        root.addLayout(footer)

        if streams:
            self.list.setCurrentRow(0)
        self._on_row(self.list.currentRow())

    def _current(self) -> StreamSource | None:
        row = self.list.currentRow()
        if 0 <= row < len(self.streams):
            return self.streams[row]
        return None

    def _on_row(self, row):
        stream = self._current()
        self.btn_play.setEnabled(stream is not None)
        self.btn_copy.setEnabled(stream is not None)
        if stream is None:
            self.details.setPlainText("")
            return
        referer = OnlineService.header(stream, "referer") or stream.referer or "—"
        agent = OnlineService.header(stream, "user-agent") or "—"
        self.details.setPlainText(
            f"URL: {stream.url}\n"
            f"Referer: {referer}\n"
            f"User-Agent: {agent}\n"
            f"Comando VLC: {OnlineService.vlc_command(stream)}"
        )

    def _copy_command(self):
        stream = self._current()
        if stream is None:
            return
        QApplication.clipboard().setText(OnlineService.vlc_command(stream))
        self.details.appendPlainText("\nComando copiato negli appunti.")

    def _accept_current(self):
        stream = self._current()
        if stream is None:
            return
        self.chosen = stream
        self.accept()


# --------------------------------------------------------------------- main dialog
class OnlineSearchDialog(QDialog):
    """Ricerca su canali configurabili, metadati TMDB e playback VLC."""

    play_requested = pyqtSignal(object)
    links_requested = pyqtSignal()
    browser_requested = pyqtSignal(str)

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._results: list[SearchResult] = []
        self._selected: SearchResult | None = None
        self._service = self._make_service()
        self._workers: set[AsyncOperation] = set()
        self._cover_cache: dict[str, QPixmap] = {}
        self._cover_loading: set[str] = set()
        self._cover_items: dict[str, list[QListWidgetItem]] = {}
        self._cover_queue: list[str] = []
        self._cover_active = 0
        self._cover_max = 6
        self._last_streams: list[StreamSource] = []
        self._last_title = ""
        self._initialized = False

        self._ensure_channels_dir()
        self.setWindowTitle("VistoFlow Pro — Ricerca online")
        self.setMinimumSize(960, 660)
        self.resize(1080, 760)
        self._build_ui()
        self._refresh_channel_status()
        self._initialized = True

    # ------------------------------------------------------------------- config
    def _make_service(self) -> OnlineService:
        config = self.manager.data.get("online")
        if not isinstance(config, dict):
            config = {}
        return OnlineService(config)

    def _ensure_channels_dir(self):
        try:
            os.makedirs(self._service.channels_dir, exist_ok=True)
        except OSError:
            pass

    def _online_config(self) -> dict:
        config = self.manager.data.setdefault("online", {})
        if not isinstance(config, dict):
            config = {}
            self.manager.data["online"] = config
        return config

    # ----------------------------------------------------------------------- UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("Ricerca online")
        title.setObjectName("CollectionTitle")
        subtitle = QLabel(
            "Canali autorizzati, metadati TMDB e flussi HLS/MP4 pronti per VLC"
        )
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        self.btn_menu = QPushButton("⋯")
        self.btn_menu.setObjectName("Ghost")
        self.btn_menu.setFixedWidth(40)
        self.btn_menu.setToolTip("Configurazione e strumenti")
        self.btn_menu.clicked.connect(self._show_menu)
        header.addWidget(self.btn_menu)
        root.addLayout(header)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔎  Cerca un film o una serie sui canali online…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.returnPressed.connect(self._start_search)
        search_row.addWidget(self.search_edit, 1)

        self.type_combo = QComboBox()
        self.type_combo.addItem("Auto", "auto")
        self.type_combo.addItem("🎬 Film", "movie")
        self.type_combo.addItem("📺 Serie", "tv")
        self.type_combo.setFixedWidth(120)
        search_row.addWidget(self.type_combo)

        self.btn_search = QPushButton("Cerca")
        self.btn_search.setObjectName("Primary")
        self.btn_search.clicked.connect(self._start_search)
        search_row.addWidget(self.btn_search)

        self.btn_direct = QPushButton("🔗  URL")
        self.btn_direct.setObjectName("Ghost")
        self.btn_direct.setToolTip("Risolvi un URL diretto o una pagina host")
        self.btn_direct.clicked.connect(self._resolve_direct_url)
        search_row.addWidget(self.btn_direct)
        root.addLayout(search_row)

        status_row = QHBoxLayout()
        self.status_label = QLabel("Pronto.")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        status_row.addWidget(self.status_label, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(150)
        self.progress.hide()
        status_row.addWidget(self.progress)
        self.channel_status = QLabel("")
        self.channel_status.setObjectName("Muted")
        status_row.addWidget(self.channel_status)
        root.addLayout(status_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(5)
        self.results_list = QListWidget()
        self.results_list.setObjectName("OnlineResults")
        self.results_list.setUniformItemSizes(True)
        self.results_list.setMouseTracking(True)
        self.results_list.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.results_list.setItemDelegate(OnlineResultDelegate(self.results_list))
        self.results_list.currentItemChanged.connect(self._on_selection_changed)
        self.results_list.itemDoubleClicked.connect(lambda _item: self._resolve_selected())
        left_lay.addWidget(self.results_list, 1)
        self.result_count = QLabel("Nessuna ricerca eseguita.")
        self.result_count.setObjectName("Muted")
        left_lay.addWidget(self.result_count)
        splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("BrowserPanel")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(16, 12, 16, 12)
        right_lay.setSpacing(7)
        self.detail_cover = QLabel("Seleziona\nun risultato")
        self.detail_cover.setObjectName("CoverPreview")
        self.detail_cover.setFixedSize(164, 246)
        self.detail_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_cover.setWordWrap(True)
        right_lay.addWidget(self.detail_cover, 0, Qt.AlignmentFlag.AlignHCenter)

        self.detail_title = QLabel("Nessun risultato selezionato")
        self.detail_title.setObjectName("CollectionTitle")
        self.detail_title.setWordWrap(True)
        right_lay.addWidget(self.detail_title)
        self.detail_meta = QLabel("")
        self.detail_meta.setObjectName("CollectionMeta")
        self.detail_meta.setWordWrap(True)
        right_lay.addWidget(self.detail_meta)

        self.detail_overview = QLabel(
            "Cerca un titolo per vedere qui poster, trama, anno e voto TMDB."
        )
        self.detail_overview.setObjectName("Muted")
        self.detail_overview.setWordWrap(True)
        self.detail_overview.setMinimumHeight(78)
        right_lay.addWidget(self.detail_overview)

        self.detail_url = QLabel("")
        self.detail_url.setObjectName("Muted")
        self.detail_url.setWordWrap(True)
        self.detail_url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right_lay.addWidget(self.detail_url)

        self.detail_streams = QLabel("")
        self.detail_streams.setObjectName("Muted")
        self.detail_streams.setWordWrap(True)
        right_lay.addWidget(self.detail_streams)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.btn_play = QPushButton("▶  Risolvi e riproduci")
        self.btn_play.setObjectName("Primary")
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self._resolve_selected)
        actions.addWidget(self.btn_play, 1)
        right_lay.addLayout(actions)

        secondary = QHBoxLayout()
        secondary.setSpacing(6)
        self.btn_page = QPushButton("🌐  Apri pagina")
        self.btn_page.setObjectName("Ghost")
        self.btn_page.setToolTip("Apri la pagina nel browser integrato")
        self.btn_page.setEnabled(False)
        self.btn_page.clicked.connect(self._open_page)
        secondary.addWidget(self.btn_page)
        self.btn_copy_page = QPushButton("Copia link")
        self.btn_copy_page.setObjectName("Ghost")
        self.btn_copy_page.setEnabled(False)
        self.btn_copy_page.clicked.connect(self._copy_page)
        secondary.addWidget(self.btn_copy_page)
        self.btn_vlc = QPushButton(" ⧉ VLC")
        self.btn_vlc.setObjectName("Ghost")
        self.btn_vlc.setEnabled(False)
        self.btn_vlc.setToolTip("Copia il comando VLC dell'ultimo flusso risolto")
        self.btn_vlc.clicked.connect(self._copy_last_vlc)
        secondary.addWidget(self.btn_vlc)
        right_lay.addLayout(secondary)
        right_lay.addStretch()

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([640, 360])
        root.addWidget(splitter, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.footer_status = QLabel("")
        self.footer_status.setObjectName("Muted")
        self.footer_status.setWordWrap(True)
        footer.addWidget(self.footer_status, 1)
        self.btn_links = QPushButton("🔗  I miei link")
        self.btn_links.setObjectName("Ghost")
        self.btn_links.setToolTip("Gestisci i link salvati e aggiornali se scadono")
        self.btn_links.clicked.connect(self._open_saved_links)
        footer.addWidget(self.btn_links)
        self.btn_channels = QPushButton("📁  Canali")
        self.btn_channels.setObjectName("Ghost")
        self.btn_channels.setToolTip("Apri la cartella dei canali JSON/YAML")
        self.btn_channels.clicked.connect(self._open_channels_dir)
        footer.addWidget(self.btn_channels)
        self.btn_tmdb = QPushButton("TMDB")
        self.btn_tmdb.setObjectName("Ghost")
        self.btn_tmdb.setToolTip("Configura la chiave API TMDB")
        self.btn_tmdb.clicked.connect(self._configure_tmdb)
        footer.addWidget(self.btn_tmdb)
        btn_close = QPushButton("Chiudi")
        btn_close.setObjectName("Ghost")
        btn_close.clicked.connect(self.close)
        footer.addWidget(btn_close)
        root.addLayout(footer)

    # ------------------------------------------------------------------ status
    def _refresh_channel_status(self):
        total, enabled, errors = self._service.channel_summary()
        if total:
            self.channel_status.setText(f"{enabled}/{total} canali attivi")
        else:
            self.channel_status.setText("Nessun canale")
        tooltip = [f"Cartella canali: {self._service.channels_dir}"]
        if errors:
            tooltip.append("Errori di configurazione:")
            tooltip.extend(f"• {name}: {message}" for name, message in errors.items())
        else:
            tooltip.append("Nessun errore di configurazione.")
        self.channel_status.setToolTip("\n".join(tooltip))
        self.btn_tmdb.setText("TMDB ✓" if self._service.settings.tmdb_api_key else "TMDB")
        self.btn_tmdb.setToolTip(
            "Chiave TMDB configurata"
            if self._service.settings.tmdb_api_key
            else "Configura la chiave API TMDB per poster, trama e voto"
        )
        if not self._initialized:
            return
        if total == 0:
            self.status_label.setText(
                "Nessun canale configurato: apri «Canali» e aggiungi un file JSON/YAML."
            )
        elif enabled == 0:
            self.status_label.setText(
                "I canali sono presenti ma disattivati: imposta \"enabled\": true."
            )
        else:
            self.status_label.setText(
                "Pronto: cerca un titolo o incolla un URL per risolvere un flusso."
            )

    def _set_busy(self, busy: bool, message: str = ""):
        self.progress.setVisible(busy)
        self.btn_search.setEnabled(not busy)
        self.btn_direct.setEnabled(not busy)
        self.results_list.setEnabled(not busy)
        if message:
            self.status_label.setText(message)
        self.setCursor(
            Qt.CursorShape.BusyCursor if busy else Qt.CursorShape.ArrowCursor
        )

    def _show_error(self, title: str, message: str):
        self.status_label.setText(title)
        self.detail_title.setText(title)
        self.detail_meta.setText("")
        self.detail_overview.setText(message)
        self.detail_cover.setPixmap(QPixmap())
        self.detail_cover.setText("Nessuna\nanteprima")
        self.detail_url.setText("")
        self.detail_streams.setText("")
        self._last_streams = []
        self.btn_play.setEnabled(False)
        self.btn_page.setEnabled(False)
        self.btn_copy_page.setEnabled(False)
        self.btn_vlc.setEnabled(False)

    # ------------------------------------------------------------------ ricerca
    def _start_search(self):
        if not self.btn_search.isEnabled():
            return
        query = self.search_edit.text().strip()
        if not query:
            self.status_label.setText("Inserisci un titolo da cercare.")
            self.search_edit.setFocus()
            return
        self._service = self._make_service()
        self._refresh_channel_status()
        self._results = []
        self._selected = None
        self._last_streams = []
        self._last_title = ""
        self.results_list.clear()
        self._cover_items.clear()
        self._set_busy(True, "Ricerca in corso sui canali configurati…")
        self.result_count.setText("Ricerca in corso…")
        self._show_error("Ricerca in corso", "Attendi il completamento della ricerca.")

        media_type = str(self.type_combo.currentData() or "auto")
        worker = AsyncOperation(
            lambda: self._service.search(query, media_type),
            parent=self,
        )
        self._workers.add(worker)
        worker.completed.connect(self._on_search_done)
        worker.failed.connect(self._on_search_failed)
        worker.completed.connect(lambda _result, w=worker: self._finish_worker(w))
        worker.failed.connect(lambda _message, w=worker: self._finish_worker(w))
        worker.start()

    def _finish_worker(self, worker):
        self._workers.discard(worker)
        worker.deleteLater()

    def _on_search_done(self, outcome):
        self._set_busy(False)
        self._results = list(outcome.results or [])
        self.results_list.clear()
        self._cover_items.clear()
        for result in self._results:
            item = QListWidgetItem()
            item.setData(
                Qt.ItemDataRole.UserRole,
                {"result": result, "cover": self._cover_cache.get(result.cover_url or "")},
            )
            item.setToolTip(
                f"{result.channel_name}\n{result.page_url}\n"
                f"Punteggio: {int(round(result.score * 100))}%"
            )
            item.setSizeHint(QSize(80, 92))
            self.results_list.addItem(item)
            if result.cover_url:
                self._cover_items.setdefault(result.cover_url, []).append(item)
                self._load_cover(result.cover_url)

        if not self._results:
            self.result_count.setText("0 risultati")
            details = []
            if outcome.warnings:
                details.extend(outcome.warnings)
            if outcome.errors:
                details.append("Errori dai canali:")
                details.extend(
                    f"• {name}: {message}"
                    for name, message in list(outcome.errors.items())[:8]
                )
            self._show_error(
                "Nessun risultato",
                "\n".join(details)
                or "Prova con un altro titolo o controlla i canali configurati.",
            )
            return

        self.result_count.setText(
            f"{len(self._results)} risultati da {outcome.enabled_channels} canali attivi"
        )
        status = f"{len(self._results)} risultati trovati."
        if outcome.warnings:
            status += "  " + outcome.warnings[0]
        if outcome.errors:
            status += f"  {len(outcome.errors)} errori isolati."
        self.status_label.setText(status)
        self.footer_status.setText(
            "Seleziona un risultato e premi «Risolvi e riproduci»."
        )
        self.results_list.setCurrentRow(0)

    def _on_search_failed(self, message):
        self._set_busy(False)
        self.result_count.setText("0 risultati")
        self._show_error("Ricerca non riuscita", message)
        self.footer_status.setText(
            "Controlla la connessione e la configurazione dei canali."
        )

    # ------------------------------------------------------------------ dettaglio
    def _on_selection_changed(self, current, _previous=None):
        if current is None:
            self._selected = None
            self.btn_play.setEnabled(False)
            self.btn_page.setEnabled(False)
            self.btn_copy_page.setEnabled(False)
            self.btn_vlc.setEnabled(False)
            return
        record = current.data(Qt.ItemDataRole.UserRole) or {}
        result: SearchResult | None = record.get("result")
        if result is None:
            return
        self._selected = result
        self._last_streams = []
        self._last_title = self._display_title(result)
        self.btn_vlc.setEnabled(False)
        self.detail_title.setText(self._display_title(result))
        media = result.media_item
        meta_parts = [result.channel_name]
        year = media.year if media else extract_year(result.title)
        if year:
            meta_parts.append(str(year))
        if media and media.rating is not None:
            meta_parts.append(f"⭐ {media.rating:.1f}")
        if media:
            meta_parts.append("TMDB")
        meta_parts.append(f"match {int(round(result.score * 100))}%")
        self.detail_meta.setText("  ·  ".join(meta_parts))
        self.detail_overview.setText(
            (media.overview if media else "")
            or "Trama non disponibile. Configura TMDB per arricchire i risultati."
        )
        self.detail_url.setText(result.page_url)
        self.detail_streams.setText("")
        self.btn_play.setEnabled(True)
        self.btn_page.setEnabled(True)
        self.btn_copy_page.setEnabled(True)
        cover = record.get("cover")
        if isinstance(cover, QPixmap) and not cover.isNull():
            self.detail_cover.setPixmap(self._fit_detail(cover))
            self.detail_cover.setText("")
        elif result.cover_url:
            cached = self._cover_cache.get(result.cover_url)
            if cached is not None and not cached.isNull():
                self.detail_cover.setPixmap(self._fit_detail(cached))
                self.detail_cover.setText("")
            else:
                self.detail_cover.setPixmap(QPixmap())
                self.detail_cover.setText("Caricamento\ncopertina…")
                self._load_cover(result.cover_url)
        else:
            self.detail_cover.setPixmap(QPixmap())
            self.detail_cover.setText("Nessuna\ncopertina")

    @staticmethod
    def _fit_detail(pixmap: QPixmap) -> QPixmap:
        """Adatta la copertina allo spazio del pannello dettaglio."""
        return pixmap.scaled(
            164,
            246,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    @staticmethod
    def _display_title(result: SearchResult) -> str:
        if result.media_item is not None:
            return result.media_item.title
        return result.title

    def _load_cover(self, url: str):
        if not url or url in self._cover_cache or url in self._cover_loading:
            return
        self._cover_loading.add(url)
        self._cover_queue.append(url)
        self._pump_covers()

    def _pump_covers(self):
        while self._cover_queue and self._cover_active < self._cover_max:
            url = self._cover_queue.pop(0)
            self._cover_active += 1
            task = ImageOperation(url, parent=self)
            task.loaded.connect(lambda data, u=url: self._on_cover_loaded(u, data))
            task.failed.connect(lambda _message, u=url: self._on_cover_failed(u))
            self._workers.add(task)
            task.loaded.connect(lambda _data, w=task: self._finish_worker(w))
            task.failed.connect(lambda _message, w=task: self._finish_worker(w))
            task.start()

    def _on_cover_loaded(self, url: str, data: bytes):
        self._cover_loading.discard(url)
        self._cover_active = max(0, self._cover_active - 1)
        pixmap = QPixmap()
        if not data or not pixmap.loadFromData(data):
            pixmap = QPixmap()
        if not pixmap.isNull():
            self._cover_cache[url] = pixmap
            for item in self._cover_items.get(url, []):
                record = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(record, dict):
                    record["cover"] = pixmap
                    item.setData(Qt.ItemDataRole.UserRole, record)
            if self._selected and self._selected.cover_url == url:
                self.detail_cover.setPixmap(self._fit_detail(pixmap))
                self.detail_cover.setText("")
            self.results_list.viewport().update()
        self._pump_covers()

    def _on_cover_failed(self, url: str):
        self._cover_loading.discard(url)
        self._cover_active = max(0, self._cover_active - 1)
        if self._selected and self._selected.cover_url == url:
            self.detail_cover.setPixmap(QPixmap())
            self.detail_cover.setText("Copertina\nnon disponibile")
        self._pump_covers()

    # ---------------------------------------------------------------- risoluzione
    def _resolve_selected(self):
        if self._selected is None or not self.btn_play.isEnabled():
            return
        result = self._selected
        self._service = self._make_service()
        self._set_busy(True, "Risoluzione del flusso video…")
        self.detail_streams.setText("Apertura pagina dettaglio e resolver…")
        self.btn_play.setEnabled(False)
        worker = AsyncOperation(
            lambda: self._service.resolve_result(result),
            parent=self,
        )
        self._workers.add(worker)
        worker.completed.connect(
            lambda outcome: self._on_resolve_done(
                outcome,
                self._display_title(result),
                source_result=result,
            )
        )
        worker.failed.connect(self._on_resolve_failed)
        worker.completed.connect(lambda _outcome, w=worker: self._finish_worker(w))
        worker.failed.connect(lambda _message, w=worker: self._finish_worker(w))
        worker.start()

    def _on_resolve_done(
        self,
        outcome: ResolveOutcome,
        title: str,
        *,
        source_result: SearchResult | None = None,
        source_url: str | None = None,
    ):
        self._set_busy(False)
        self.btn_play.setEnabled(True)
        self._last_streams = list(outcome.streams)
        self._last_title = outcome.title or title
        if not outcome.streams:
            details = list(outcome.errors.values())[:6]
            message = "\n".join(f"• {item}" for item in details) or (
                "Nessun flusso video trovato. Il canale potrebbe richiedere "
                "un resolver dedicato o il contenuto non è disponibile."
            )
            self.detail_streams.setText(message)
            self.status_label.setText("Nessun flusso riproducibile.")
            self.footer_status.setText(
                "Puoi provare un altro risultato o incollare un URL con «🔗 URL»."
            )
            self.btn_vlc.setEnabled(False)
            if source_url:
                self.status_label.setText(
                    "Apertura automatica nel browser integrato per catturare il flusso .m3u8…"
                )
                self.browser_requested.emit(source_url)
            return

        self.btn_vlc.setEnabled(True)
        self.detail_streams.setText(
            f"{len(outcome.streams)} flusso/i risolto/i: "
            + ", ".join(stream.resolver_name for stream in outcome.streams[:5])
        )
        if len(outcome.streams) == 1:
            self._play_stream(
                outcome.streams[0],
                self._last_title,
                source_result=source_result,
                source_url=source_url,
            )
            return
        picker = StreamChoiceDialog(outcome.streams, self._last_title, self)
        if picker.exec() == QDialog.DialogCode.Accepted and picker.chosen is not None:
            self._play_stream(
                picker.chosen,
                self._last_title,
                source_result=source_result,
                source_url=source_url,
            )

    def _on_resolve_failed(self, message):
        self._set_busy(False)
        self.btn_play.setEnabled(True)
        self.detail_streams.setText(message)
        self.status_label.setText("Risoluzione non riuscita.")
        self.footer_status.setText(
            "Controlla l'URL del canale o prova un altro risultato."
        )

    def _play_stream(
        self,
        stream: StreamSource,
        title: str,
        *,
        source_result: SearchResult | None = None,
        source_url: str | None = None,
    ):
        self._last_streams = [stream]
        self._last_title = title
        self.status_label.setText("Apertura nel riproduttore VLC…")
        self.detail_streams.setText(
            f"Flusso: {stream.resolver_name} · {stream.mime_type or 'video'}"
        )
        request = PlayRequest(
            stream=stream,
            title=title,
            source_url=source_url,
            source_result=source_result,
            referer=stream.referer,
            headers=dict(stream.headers),
            user_agent=stream.headers.get("User-Agent"),
        )
        self.play_requested.emit(request)
        self.hide()

    def _copy_last_vlc(self):
        if not self._last_streams:
            return
        QApplication.clipboard().setText(OnlineService.vlc_command(self._last_streams[0]))
        self.footer_status.setText("Comando VLC copiato negli appunti.")

    # ---------------------------------------------------------------- azioni
    def _open_page(self):
        if self._selected is None:
            return
        self.browser_requested.emit(self._selected.page_url)

    def _copy_page(self):
        if self._selected is None:
            return
        QApplication.clipboard().setText(self._selected.page_url)
        self.footer_status.setText("Link della pagina copiato negli appunti.")

    def _resolve_direct_url(self):
        if not self.btn_direct.isEnabled():
            return
        url, ok = QInputDialog.getText(
            self,
            "Risolvi URL",
            "Incolla un flusso .m3u8/.mp4 o una pagina con il player:",
        )
        if not ok or not url.strip():
            return
        target = url.strip()
        self._service = self._make_service()
        self._set_busy(True, "Risoluzione dell'URL…")
        self.btn_play.setEnabled(False)
        worker = AsyncOperation(
            lambda: self._service.resolve_url(target),
            parent=self,
        )
        self._workers.add(worker)
        worker.completed.connect(
            lambda outcome: self._on_resolve_done(
                outcome,
                target,
                source_url=target,
            )
        )
        worker.failed.connect(self._on_resolve_failed)
        worker.completed.connect(lambda _outcome, w=worker: self._finish_worker(w))
        worker.failed.connect(lambda _message, w=worker: self._finish_worker(w))
        worker.start()

    def _show_menu(self):
        menu = QMenu(self)
        action_reload = menu.addAction("⟳  Ricarica canali")
        action_folder = menu.addAction("📁  Apri cartella canali")
        action_choose = menu.addAction("📂  Scegli cartella canali…")
        menu.addSeparator()
        action_tmdb = menu.addAction("🔑  Imposta chiave TMDB…")
        action_language = menu.addAction("🌐  Lingua TMDB…")
        menu.addSeparator()
        action_direct = menu.addAction("🔗  Risolvi URL diretto…")
        action_info = menu.addAction("ℹ  Informazioni")
        chosen = menu.exec(self.btn_menu.mapToGlobal(self.btn_menu.rect().bottomLeft()))
        if chosen is action_reload:
            self._reload_channels()
        elif chosen is action_folder:
            self._open_channels_dir()
        elif chosen is action_choose:
            self._choose_channels_dir()
        elif chosen is action_tmdb:
            self._configure_tmdb()
        elif chosen is action_language:
            self._configure_language()
        elif chosen is action_direct:
            self._resolve_direct_url()
        elif chosen is action_info:
            QMessageBox.information(
                self,
                "Ricerca online",
                "VistoFlow Pro usa solo fonti autorizzate configurate in "
                f"{self._service.channels_dir}.\n\n"
                "Il motore non aggira DRM, paywall o autenticazioni. "
                "I resolver supportano URL HLS/MP4, Mixdrop, Voe, Supervideo "
                "e Streamtape quando il markup è compatibile.",
            )

    def _reload_channels(self):
        self._service = self._make_service()
        self._refresh_channel_status()
        self.footer_status.setText("Canali ricaricati.")

    def _open_saved_links(self):
        self.links_requested.emit()

    def _open_channels_dir(self):
        self._ensure_channels_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._service.channels_dir)))

    def _choose_channels_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Scegli la cartella dei canali",
            str(self._service.channels_dir),
        )
        if not directory:
            return
        config = self._online_config()
        config["channels_dir"] = directory
        self.manager.save_config()
        self._service = self._make_service()
        self._ensure_channels_dir()
        self._refresh_channel_status()
        self.footer_status.setText(f"Cartella canali: {directory}")

    def _configure_tmdb(self):
        config = self._online_config()
        current = str(config.get("tmdb_api_key") or "")
        key, ok = QInputDialog.getText(
            self,
            "Chiave API TMDB",
            "Inserisci la chiave API v3 di TMDB (vuoto per rimuoverla):",
            QLineEdit.EchoMode.Password,
            current,
        )
        if not ok:
            return
        key = key.strip()
        if key:
            config["tmdb_api_key"] = key
        else:
            config.pop("tmdb_api_key", None)
        self.manager.save_config()
        self._service = self._make_service()
        self._refresh_channel_status()
        self.footer_status.setText(
            "TMDB configurato." if key else "Chiave TMDB rimossa."
        )

    def _configure_language(self):
        config = self._online_config()
        current = str(config.get("tmdb_language") or self._service.settings.tmdb_language)
        languages = ["it-IT", "en-US", "en-GB", "fr-FR", "de-DE", "es-ES"]
        try:
            index = languages.index(current)
        except ValueError:
            languages.insert(0, current)
            index = 0
        language, ok = QInputDialog.getItem(
            self,
            "Lingua TMDB",
            "Lingua dei metadati TMDB:",
            languages,
            index,
            False,
        )
        if not ok or not language:
            return
        config["tmdb_language"] = language
        self.manager.save_config()
        self._service = self._make_service()
        self._refresh_channel_status()
        self.footer_status.setText(f"Lingua TMDB: {language}")


__all__ = ["OnlineSearchDialog", "StreamChoiceDialog"]
