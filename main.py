"""VistoFlow Pro - gestore di film e serie TV con player integrato."""

import os
import sys
import time

# Nell'eseguibile PyInstaller il processo del browser riusa lo stesso .exe.
# Questo dispatch deve avvenire prima di importare PyQt6: il motore usa
# PySide6 e i due binding Qt non devono convivere nello stesso processo.
if "--browser-engine" in sys.argv:
    from browser_engine import main as _browser_engine_main

    raise SystemExit(_browser_engine_main())

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QDesktopServices, QFont, QFontMetrics, QIcon,
    QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QSplitter, QStackedWidget, QStyle, QStyledItemDelegate, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from async_tasks import AsyncOperation
from browser_dialog import WebBrowserDialog
from dialogs import FileDetailsDialog, OnlineCoverDialog
from link_dialog import SavedLinksDialog
from media_manager import MediaManager
from online_dialog import OnlineSearchDialog
from player_widget import VideoPlayer
from theme import apply_theme
from vistoflow_online import OnlineService, PlayRequest, StreamSource

MUTED = "#7d8797"
ACCENT = "#2ecc71"
AMBER = "#f5a623"


def make_app_icon(size=64):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ACCENT))
    painter.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), size * 0.24, size * 0.24)
    painter.setBrush(QColor("#07130b"))
    triangle = QPolygonF([
        QPointF(size * 0.40, size * 0.29),
        QPointF(size * 0.40, size * 0.71),
        QPointF(size * 0.73, size * 0.50),
    ])
    painter.drawPolygon(triangle)
    painter.end()
    return QIcon(pixmap)


def _safe_int(value, default=10 ** 6):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def make_cover_pixmap(path, width, height):
    """Ritaglia e ridimensiona una copertina alle dimensioni richieste."""
    if not path:
        return QPixmap()
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return QPixmap()
    scaled = pixmap.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - width) // 2)
    y = max(0, (scaled.height() - height) // 2)
    return scaled.copy(x, y, width, height)


class ClickableLabel(QLabel):
    """Etichetta cliccabile usata per la copertina della raccolta."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MediaDelegate(QStyledItemDelegate):
    """Disegna ogni file come una card con stato, badge, TAG e avanzamento."""

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
        self.f_right = QFont("Segoe UI")
        self.f_right.setPixelSize(11)
        self.f_right.setWeight(QFont.Weight.DemiBold)

    def sizeHint(self, option, index):
        return QSize(80, 68)

    def paint(self, painter, option, index):
        record = index.data(Qt.ItemDataRole.UserRole) or {}
        rect = QRectF(option.rect).adjusted(3, 3, -3, -3)
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

        status = record.get("status", "nuovo")
        accent = QColor(
            {"visto": ACCENT, "iniziato": AMBER}.get(status, "#46525f")
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(
            QRectF(rect.left(), rect.top() + 11, 3, rect.height() - 22), 1.5, 1.5
        )

        left = rect.left() + 17
        top = rect.top() + 9

        cover = record.get("cover_pixmap")
        has_cover = isinstance(cover, QPixmap) and not cover.isNull()
        text_left = left
        if has_cover:
            poster = QRectF(left, top - 3, 36, 50)
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(poster, 4, 4)
            painter.setClipPath(clip)
            painter.drawPixmap(poster.toRect(), cover)
            painter.restore()
            text_left = left + 44

        # Badge SxxExx / FILM
        if record.get("kind") == "serie":
            badge = f"S{_safe_int(record.get('season'), 1):02d}E{_safe_int(record.get('episode'), 1):02d}"
            badge_bg, badge_fg = QColor("#17291f"), QColor(ACCENT)
        else:
            badge = "FILM"
            badge_bg, badge_fg = QColor("#2c2418"), QColor(AMBER)

        painter.setFont(self.f_badge)
        badge_width = QFontMetrics(self.f_badge).horizontalAdvance(badge) + 14
        painter.setBrush(badge_bg)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(text_left, top, badge_width, 19), 9.5, 9.5)
        painter.setPen(badge_fg)
        painter.drawText(
            QRectF(text_left, top, badge_width, 19),
            Qt.AlignmentFlag.AlignCenter,
            badge,
        )

        # Percentuale / stato a destra
        progress = float(record.get("progress") or 0)
        right_text = ""
        right_color = QColor(MUTED)
        if status == "visto":
            right_text = "✓ VISTO"
            right_color = QColor(ACCENT)
        elif progress > 0.001:
            right_text = f"{int(round(progress * 100))}%"
            right_color = QColor(AMBER if progress < 0.95 else ACCENT)

        right_width = 62
        if right_text:
            painter.setFont(self.f_right)
            painter.setPen(right_color)
            painter.drawText(
                QRectF(rect.right() - right_width - 13, top, right_width, 19),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                right_text,
            )

        # Titolo
        title_left = text_left + badge_width + 10
        title_rect = QRectF(
            title_left, top, max(20.0, rect.right() - right_width - title_left - 12), 20
        )
        painter.setFont(self.f_title)
        painter.setPen(QColor("#eef3f8") if selected else QColor("#dde5ee"))
        title = QFontMetrics(self.f_title).elidedText(
            record.get("title", ""), Qt.TextElideMode.ElideRight, int(title_rect.width())
        )
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )

        # Sottotitolo: TAG
        tags = record.get("tags") or []
        if tags:
            subtitle = "  •  ".join(tags[:3])
            if len(tags) > 3:
                subtitle += f"  +{len(tags) - 3}"
        else:
            subtitle = "Nessun TAG"
        painter.setFont(self.f_small)
        painter.setPen(QColor(MUTED))
        subtitle_rect = QRectF(
            text_left,
            rect.top() + 33,
            max(20.0, rect.right() - text_left - 17),
            16,
        )
        subtitle = QFontMetrics(self.f_small).elidedText(
            subtitle, Qt.TextElideMode.ElideRight, int(subtitle_rect.width())
        )
        painter.drawText(
            subtitle_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            subtitle,
        )

        # Barra di avanzamento
        if progress > 0.001:
            bar_y = rect.bottom() - 8
            bar_width = max(0.0, rect.right() - text_left - 17)
            painter.setBrush(QColor("#26303c"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(text_left, bar_y, bar_width, 3), 1.5, 1.5)
            painter.setBrush(QColor(ACCENT if status == "visto" else AMBER))
            painter.drawRoundedRect(
                QRectF(text_left, bar_y, bar_width * min(1.0, progress), 3), 1.5, 1.5
            )

        painter.restore()


class VistoFlowApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.manager = MediaManager()
        self.records = []
        self.collection = None          # {"kind": "film"/"serie", "name": str}
        self.current = None             # record selezionato
        self.current_file = None
        self.current_online = False     # True quando suona un flusso online
        self._online_dialog = None
        self._links_dialog = None
        self._browser_dialog = None
        self._online_request: PlayRequest | None = None
        self._online_refresh_worker: AsyncOperation | None = None
        self._online_refresh_attempts = 0
        self._online_play_token = 0
        self.kind_filter = "all"
        self.is_full = False
        self.player_closed = False
        self._cover_cache = {}
        self._was_maximized = False
        self._last_save = 0.0
        self._building = False

        self.setWindowTitle("VistoFlow Pro")
        self.setWindowIcon(make_app_icon())
        self.resize(1360, 900)
        self.setMinimumSize(1040, 680)

        self._build_ui()
        self._connect_shortcuts()
        self.reload(select_first=True)

    # ================================================================== UI
    def _build_ui(self):
        root_widget = QWidget()
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(root_widget)

        self.topbar = self._build_topbar()
        root.addWidget(self.topbar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.sidebar = self._build_sidebar()
        self.splitter.addWidget(self.sidebar)

        self.player = VideoPlayer()
        self.player.double_clicked.connect(self.toggle_fullscreen)
        self.player.btn_full.clicked.connect(self.toggle_fullscreen)
        self.player.close_requested.connect(self.close_player)
        self.player.position_changed.connect(self._update_progress)
        self.player.finished.connect(self._on_finished)
        self.player.error.connect(self._on_player_error)

        self.browser_panel = self._build_browser()

        self.player_bar = self._build_player_bar()
        self.player_bar.hide()

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setChildrenCollapsible(False)
        self.right_splitter.addWidget(self.player)
        self.right_splitter.addWidget(self.player_bar)
        self.right_splitter.addWidget(self.browser_panel)
        self.right_splitter.setStretchFactor(0, 4)
        self.right_splitter.setStretchFactor(1, 0)
        self.right_splitter.setStretchFactor(2, 2)
        self.right_splitter.setSizes([560, 0, 290])

        self.splitter.addWidget(self.right_splitter)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([285, 1075])
        root.addWidget(self.splitter, 1)

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(66)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 10, 18, 10)
        lay.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(make_app_icon(36).pixmap(36, 36))
        lay.addWidget(icon_label)

        brand = QVBoxLayout()
        brand.setSpacing(0)
        title = QLabel("VistoFlow <span style='color:#2ecc71'>Pro</span>")
        title.setObjectName("AppTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        subtitle = QLabel("Film, serie TV, copertine e TAG in un'unica libreria")
        subtitle.setObjectName("AppSubtitle")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        lay.addLayout(brand)
        lay.addStretch(1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Cerca serie, film o TAG…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(265)
        lay.addWidget(self.search)

        segment_box = QWidget()
        segment_lay = QHBoxLayout(segment_box)
        segment_lay.setContentsMargins(0, 0, 0, 0)
        segment_lay.setSpacing(0)
        self.kind_group = QButtonGroup(self)
        for index, (text, value) in enumerate(
            (("Tutti", "all"), ("🎬 Film", "film"), ("📺 Serie", "serie"))
        ):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setProperty("segment", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(value == "all")
            button.clicked.connect(lambda _checked, v=value: self._set_kind_filter(v))
            self.kind_group.addButton(button, index)
            segment_lay.addWidget(button)
        lay.addWidget(segment_box)

        self.tag_combo = QComboBox()
        self.tag_combo.setMinimumWidth(160)
        self.tag_combo.setToolTip("Filtra per TAG")
        lay.addWidget(self.tag_combo)

        self.btn_stream = QPushButton("🌐  Online")
        self.btn_stream.setObjectName("Ghost")
        self.btn_stream.setToolTip("Cerca film e serie sui canali online configurati")
        self.btn_stream.clicked.connect(self.open_online_search)
        lay.addWidget(self.btn_stream)

        self.btn_links = QPushButton("🔗  Link")
        self.btn_links.setObjectName("Ghost")
        self.btn_links.setToolTip("Salva, modifica e riproduci link video")
        self.btn_links.clicked.connect(self.open_saved_links)
        lay.addWidget(self.btn_links)

        self.btn_browser = QPushButton("🧭")
        self.btn_browser.setObjectName("Ghost")
        self.btn_browser.setFixedSize(38, 38)
        self.btn_browser.setToolTip("Browser integrato per aprire pagine web")
        self.btn_browser.clicked.connect(lambda: self.open_browser())
        lay.addWidget(self.btn_browser)

        self.btn_refresh = QPushButton("⟳")
        self.btn_refresh.setObjectName("Ghost")
        self.btn_refresh.setFixedSize(38, 38)
        self.btn_refresh.setToolTip("Ricarica la libreria")
        self.btn_refresh.clicked.connect(lambda: self.reload(select_first=False))
        lay.addWidget(self.btn_refresh)

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(lambda: self.build_tree(select_first=True))
        self.search.textChanged.connect(lambda: self.search_timer.start())

        self.tag_combo.currentIndexChanged.connect(
            lambda: self.build_tree(select_first=True)
        )
        return bar

    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setMinimumWidth(235)
        side.setMaximumWidth(390)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 16, 14, 14)
        lay.setSpacing(10)

        header = QHBoxLayout()
        label = QLabel("RACCOLTE")
        label.setObjectName("SectionTitle")
        self.collection_count = QLabel("")
        self.collection_count.setObjectName("Muted")
        header.addWidget(label)
        header.addStretch()
        header.addWidget(self.collection_count)
        lay.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setAnimated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.currentItemChanged.connect(self._on_tree_selected)
        lay.addWidget(self.tree, 1)

        self.stats = QLabel("")
        self.stats.setObjectName("Muted")
        self.stats.setWordWrap(True)
        lay.addWidget(self.stats)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.btn_add_dir = QPushButton("＋ Cartella")
        self.btn_add_dir.setToolTip("Aggiungi una cartella alla libreria")
        self.btn_add_dir.clicked.connect(self.add_library)
        self.btn_add_file = QPushButton("＋ File")
        self.btn_add_file.setToolTip("Aggiungi uno o più file video")
        self.btn_add_file.clicked.connect(self.add_single_file)
        self.btn_library = QPushButton("⋯")
        self.btn_library.setObjectName("Ghost")
        self.btn_library.setFixedWidth(38)
        self.btn_library.setToolTip("Gestisci i percorsi della libreria")
        self.btn_library.clicked.connect(self.show_library_menu)
        buttons.addWidget(self.btn_add_dir, 1)
        buttons.addWidget(self.btn_add_file, 1)
        buttons.addWidget(self.btn_library)
        lay.addLayout(buttons)

        hint = QLabel("Doppio click per riprodurre\nTasto destro per TAG e opzioni")
        hint.setObjectName("Muted")
        hint.setStyleSheet("font-size: 10px;")
        lay.addWidget(hint)
        return side

    def _build_player_bar(self):
        """Barra compatta mostrata quando il riproduttore è chiuso."""
        bar = QFrame()
        bar.setObjectName("PlayerBar")
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(10)

        icon = QLabel("🎬")
        icon.setStyleSheet("font-size: 18px;")
        lay.addWidget(icon)

        self.player_bar_label = QLabel(
            "Riproduttore chiuso — più spazio per selezionare i file"
        )
        self.player_bar_label.setObjectName("PlayerBarText")
        lay.addWidget(self.player_bar_label, 1)

        self.btn_bar_play = QPushButton("▶  Riproduci selezionato")
        self.btn_bar_play.setObjectName("Primary")
        self.btn_bar_play.setToolTip("Apre il riproduttore e avvia il file selezionato")
        self.btn_bar_play.clicked.connect(self.play_selected)
        lay.addWidget(self.btn_bar_play)

        self.btn_bar_open = QPushButton("⤢  Apri riproduttore")
        self.btn_bar_open.setObjectName("Ghost")
        self.btn_bar_open.clicked.connect(self.open_player)
        lay.addWidget(self.btn_bar_open)
        return bar

    def _build_browser(self):
        panel = QFrame()
        panel.setObjectName("BrowserPanel")
        panel.setMinimumHeight(220)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)
        self.cover_label = ClickableLabel()
        self.cover_label.setObjectName("CollectionCover")
        self.cover_label.setFixedSize(56, 80)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cover_label.setToolTip("Clic per cercare o scegliere la copertina")
        self.cover_label.clicked.connect(self.show_cover_menu)
        header.addWidget(self.cover_label)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.coll_title = QLabel("Nessuna raccolta selezionata")
        self.coll_title.setObjectName("CollectionTitle")
        self.coll_meta = QLabel("")
        self.coll_meta.setObjectName("CollectionMeta")
        titles.addWidget(self.coll_title)
        titles.addWidget(self.coll_meta)
        header.addLayout(titles)
        header.addStretch()

        self.season_combo = QComboBox()
        self.season_combo.setMinimumWidth(170)
        self.season_combo.currentIndexChanged.connect(self._season_changed)
        header.addWidget(self.season_combo)

        self.btn_online = QPushButton("🖼  Copertina")
        self.btn_online.setObjectName("Ghost")
        self.btn_online.setToolTip("Cerca e importa automaticamente la copertina online")
        self.btn_online.setEnabled(False)
        self.btn_online.clicked.connect(lambda: self.fetch_cover_online(auto=True))
        header.addWidget(self.btn_online)

        self.btn_details = QPushButton("🏷  Dettagli / TAG")
        self.btn_details.setObjectName("Ghost")
        self.btn_details.setEnabled(False)
        self.btn_details.clicked.connect(self.edit_selected_details)
        header.addWidget(self.btn_details)

        self.btn_seen = QPushButton("✔  Segna visto")
        self.btn_seen.setObjectName("Ghost")
        self.btn_seen.setEnabled(False)
        self.btn_seen.clicked.connect(self.toggle_selected_seen)
        header.addWidget(self.btn_seen)
        lay.addLayout(header)

        self.stack = QStackedWidget()

        empty_page = QWidget()
        empty_lay = QVBoxLayout(empty_page)
        empty_lay.setContentsMargins(0, 20, 0, 20)
        self.empty_label = QLabel("Seleziona una raccolta dalla barra laterale.")
        self.empty_label.setObjectName("Empty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        empty_lay.addWidget(self.empty_label)
        self.stack.addWidget(empty_page)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.setMouseTracking(True)
        self.file_list.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.file_list.setVerticalScrollMode(
            QListWidget.ScrollMode.ScrollPerPixel
        )
        self.file_list.setItemDelegate(MediaDelegate(self.file_list))
        self.file_list.itemDoubleClicked.connect(self._play_item)
        self.file_list.itemSelectionChanged.connect(self._on_file_selected)
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._show_context_menu)
        self.stack.addWidget(self.file_list)

        lay.addWidget(self.stack, 1)
        return panel

    # =========================================================== scorciatoie
    def _connect_shortcuts(self):
        for key, callback in (
            ("Space", self._shortcut_play),
            ("Ctrl+Left", lambda: self._shortcut_jump(-10000)),
            ("Ctrl+Right", lambda: self._shortcut_jump(10000)),
            ("F", self._shortcut_fullscreen),
            ("M", self._shortcut_mute),
            ("Escape", self._shortcut_escape),
            ("Ctrl+F", self._shortcut_search),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(callback)

    @staticmethod
    def _typing():
        widget = QApplication.focusWidget()
        return isinstance(widget, (QLineEdit, QComboBox, QSpinBox, QPlainTextEdit))

    def _shortcut_play(self):
        if self._typing():
            return
        if self.player_closed:
            self.play_selected()
            return
        if not self.player.player.get_media() and self.current:
            self._play_record(self.current)
        else:
            self.player.toggle_pause()

    def _shortcut_jump(self, ms):
        if not self._typing():
            self.player.jump(ms)

    def _shortcut_fullscreen(self):
        if not self._typing():
            self.toggle_fullscreen()

    def _shortcut_mute(self):
        if not self._typing():
            self.player.toggle_mute()

    def _shortcut_escape(self):
        if self.is_full:
            self.toggle_fullscreen()

    def _shortcut_search(self):
        self.search.setFocus()
        self.search.selectAll()

    # ============================================================== libreria
    def reload(self, select_first=False):
        self.records = [self.manager.describe(p) for p in self.manager.scan_libraries()]
        for record in self.records:
            record["cover_pixmap"] = self._cover_pixmap(
                record.get("cover"), 36, 50
            )
        self.records.sort(
            key=lambda r: (
                r["series"].casefold(),
                _safe_int(r["season"]),
                _safe_int(r["episode"]),
                r["title"].casefold(),
            )
        )
        self._refresh_tag_combo()
        self.build_tree(select_first=select_first)
        self._update_stats()

    def _refresh_tag_combo(self):
        current = self.tag_combo.currentData()
        tags = {tag.casefold(): tag for tag in self.manager.all_tags()}
        for record in self.records:
            for tag in record["tags"]:
                tags.setdefault(tag.casefold(), tag)

        self.tag_combo.blockSignals(True)
        self.tag_combo.clear()
        self.tag_combo.addItem("🏷  Tutti i TAG", None)
        for tag in sorted(tags.values(), key=str.casefold):
            self.tag_combo.addItem(tag, tag)
        if current:
            index = self.tag_combo.findData(current)
            if index >= 0:
                self.tag_combo.setCurrentIndex(index)
        self.tag_combo.blockSignals(False)

    def _update_stats(self):
        films = [r for r in self.records if r["kind"] == "film"]
        series = {r["series"].casefold() for r in self.records if r["kind"] == "serie"}
        episodes = [r for r in self.records if r["kind"] == "serie"]
        seen = sum(1 for r in self.records if r["status"] == "visto")
        self.stats.setText(
            f"{len(films)} film  ·  {len(series)} serie\n"
            f"{len(episodes)} episodi  ·  {seen} visti"
        )

    # --------------------------------------------------------------- copertine
    def _cover_pixmap(self, path, width, height):
        if not path:
            return QPixmap()
        key = (os.path.normcase(path), width, height)
        pixmap = self._cover_cache.get(key)
        if pixmap is None:
            pixmap = make_cover_pixmap(path, width, height)
            self._cover_cache[key] = pixmap
        return pixmap

    def _refresh_collection_cover(self, kind=None, name=None):
        if kind and name:
            pixmap = self._cover_pixmap(self.manager.get_cover(kind, name), 56, 80)
            caption = ""
        else:
            pixmap = QPixmap()
            caption = "Nessuna\nraccolta"
        if pixmap.isNull():
            self.cover_label.setPixmap(QPixmap())
            self.cover_label.setText(caption or "＋\nCopertina")
            self.cover_label.setStyleSheet(
                "QLabel#CollectionCover {"
                " background: #141a21; border: 1px dashed #33404f;"
                " border-radius: 8px; color: #5b6575; font-size: 10px;"
                "}"
            )
        else:
            self.cover_label.setPixmap(pixmap)
            self.cover_label.setText("")
            self.cover_label.setStyleSheet(
                "QLabel#CollectionCover {"
                " background: #0b0f14; border: 1px solid #27313d;"
                " border-radius: 8px;"
                "}"
            )

    def choose_cover(self, record=None):
        """Sceglie un'immagine e la associa al film o alla serie corrente."""
        record = record or self._collection_record() or self.current
        if not record:
            return
        kind = record.get("kind")
        name = record.get("series") or record.get("title")
        if not kind or not name:
            return
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Scegli la copertina",
            "",
            "Immagini (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;Tutti i file (*.*)",
        )
        if not path:
            return
        if QPixmap(path).isNull():
            QMessageBox.warning(
                self,
                "Copertina non valida",
                "Il file scelto non è un'immagine leggibile.\n"
                "Scegli un file PNG, JPG, WEBP, BMP o GIF.",
            )
            return
        if not self.manager.set_cover(kind, name, path):
            QMessageBox.warning(
                self,
                "Copertina non valida",
                "Non è stato possibile usare questa immagine.\n"
                "Scegli un file PNG, JPG, WEBP, BMP o GIF leggibile.",
            )
            return
        self._cover_cache.clear()
        self.reload(select_first=False)

    def _collection_record(self):
        """Restituisce un file della raccolta corrente (per la copertina)."""
        if not self.collection:
            return None
        kind = self.collection.get("kind")
        name = self.collection.get("name", "").casefold()
        if (
            self.current
            and self.current.get("kind") == kind
            and self.current.get("series", "").casefold() == name
        ):
            return self.current
        for record in self.records:
            if (
                record.get("kind") == kind
                and record.get("series", "").casefold() == name
            ):
                return record
        return None

    def show_cover_menu(self):
        record = self._collection_record()
        if not record:
            return
        kind = record.get("kind")
        name = record.get("series") or record.get("title")
        menu = QMenu(self)
        action_auto = menu.addAction("🌐  Cerca online (automatico)")
        action_search = menu.addAction("🔎  Cerca online…")
        action_local = menu.addAction("🖼  Scegli file locale…")
        action_remove = None
        if kind and name and self.manager.get_cover(kind, name):
            menu.addSeparator()
            action_remove = menu.addAction("🚫  Rimuovi copertina")

        chosen = menu.exec(self.cover_label.mapToGlobal(self.cover_label.rect().bottomLeft()))
        if chosen is action_auto:
            self.fetch_cover_online(record, auto=True)
        elif chosen is action_search:
            self.fetch_cover_online(record, auto=False)
        elif chosen is action_local:
            self.choose_cover(record)
        elif action_remove is not None and chosen is action_remove:
            self.remove_collection_cover(record)

    def fetch_cover_online(self, record=None, auto=True):
        """Cerca online la copertina e, se sicura, la importa automaticamente."""
        record = record or self._collection_record() or self.current
        if not record:
            return
        kind = record.get("kind")
        name = record.get("series") or record.get("title")
        if kind not in ("film", "serie") or not name:
            return
        dialog = OnlineCoverDialog(
            self.manager,
            kind,
            name,
            self,
            query=name,
            auto=auto,
        )
        dialog.exec()
        if dialog.imported:
            self._cover_cache.clear()
            self.reload(select_first=False)

    def remove_collection_cover(self, record=None):
        record = record or self._collection_record() or self.current
        if not record:
            return
        kind = record.get("kind")
        name = record.get("series") or record.get("title")
        if not kind or not name:
            return
        if self.manager.remove_cover(kind, name):
            self._cover_cache.clear()
            self.reload(select_first=False)

    def _set_kind_filter(self, kind):
        self.kind_filter = kind
        if self.collection and kind != "all" and self.collection["kind"] != kind:
            self.collection = None
        self.build_tree(select_first=True)

    # ================================================================ albero
    def build_tree(self, select_first=False):
        query = self.search.text().strip().casefold()
        tag_filter = self.tag_combo.currentData()
        kind_filter = self.kind_filter

        groups = {"film": {}, "serie": {}}
        for record in self.records:
            if kind_filter != "all" and record["kind"] != kind_filter:
                continue
            if tag_filter:
                if tag_filter.casefold() not in {t.casefold() for t in record["tags"]}:
                    continue
            haystack = " ".join(
                (record["series"], record["title"], record["filename"], *record["tags"])
            ).casefold()
            if query and query not in haystack:
                continue
            key = record["series"].casefold()
            bucket = groups[record["kind"]].setdefault(
                key, {"name": record["series"], "records": []}
            )
            bucket["records"].append(record)

        self._building = True
        self.tree.blockSignals(True)
        self.tree.clear()

        labels = {"film": "🎬  FILM", "serie": "📺  SERIE"}
        total_collections = 0
        for kind in ("film", "serie"):
            if kind_filter != "all" and kind_filter != kind:
                continue
            entries = sorted(groups[kind].values(), key=lambda e: e["name"].casefold())
            if not entries:
                continue
            total_collections += len(entries)
            group_item = QTreeWidgetItem([f"{labels[kind]}   ({len(entries)})"])
            group_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            group_item.setForeground(0, QBrush(QColor("#8b96a7")))
            group_font = group_item.font(0)
            group_font.setBold(True)
            group_item.setFont(0, group_font)
            self.tree.addTopLevelItem(group_item)

            for entry in entries:
                child = QTreeWidgetItem([entry["name"]])
                child.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {"kind": kind, "name": entry["name"]},
                )
                if kind == "serie":
                    child.setToolTip(
                        0, f"{len(entry['records'])} episodi · {entry['name']}"
                    )
                else:
                    child.setToolTip(0, entry["records"][0]["path"])
                group_item.addChild(child)

        self.tree.expandAll()
        self.tree.blockSignals(False)

        target = None
        if self.collection:
            for i in range(self.tree.topLevelItemCount()):
                group = self.tree.topLevelItem(i)
                for j in range(group.childCount()):
                    child = group.child(j)
                    data = child.data(0, Qt.ItemDataRole.UserRole)
                    if (
                        isinstance(data, dict)
                        and self.collection
                        and data.get("kind") == self.collection.get("kind")
                        and data.get("name", "").casefold()
                        == self.collection.get("name", "").casefold()
                    ):
                        target = child
                        break
                if target:
                    break

        if target is None and (select_first or self.collection is not None):
            for i in range(self.tree.topLevelItemCount()):
                group = self.tree.topLevelItem(i)
                if group.childCount() > 0:
                    target = group.child(0)
                    break

        if target is None:
            self.collection = None
            self.current = None
            self._show_empty(self._empty_message())
            self.tree.setCurrentItem(None)
        else:
            self.tree.setCurrentItem(target)

        self._building = False
        if target is not None:
            self._on_tree_selected()
        self.collection_count.setText(f"{total_collections} raccolte")

    def _empty_message(self):
        if not self.records:
            return "La libreria è vuota.\nAggiungi una cartella o un file per iniziare."
        if self.search.text().strip() or self.tag_combo.currentData() or self.kind_filter != "all":
            return "Nessun risultato con i filtri attivi.\nProva a rimuovere la ricerca o il TAG."
        return "Seleziona una raccolta dalla barra laterale."

    def _on_tree_selected(self, *_args):
        if self._building:
            return
        item = self.tree.currentItem()
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        self.collection = data
        self.show_collection()

    def show_collection(self):
        if not self.collection:
            self._show_empty(self._empty_message())
            return

        kind = self.collection["kind"]
        name = self.collection["name"]
        name_key = name.casefold()
        records = [
            r for r in self.records
            if r["kind"] == kind and r["series"].casefold() == name_key
        ]
        records.sort(
            key=lambda r: (_safe_int(r["season"]), _safe_int(r["episode"]), r["title"].casefold())
        )
        if not records:
            self._show_empty(self._empty_message())
            return

        self.coll_title.setText(name)
        self._refresh_collection_cover(kind, name)
        self.btn_online.setEnabled(True)

        if kind == "serie":
            seasons = sorted({r["season"] for r in records}, key=_safe_int)
            previous = self.season_combo.currentData()
            self.season_combo.blockSignals(True)
            self.season_combo.clear()
            self.season_combo.addItem("Tutte le stagioni", None)
            for season in seasons:
                self.season_combo.addItem(f"Stagione {_safe_int(season):02d}", season)
            if previous is not None:
                index = self.season_combo.findData(previous)
                if index >= 0:
                    self.season_combo.setCurrentIndex(index)
            self.season_combo.blockSignals(False)
            self.season_combo.show()
            seen = sum(1 for r in records if r["status"] == "visto")
            self.coll_meta.setText(
                f"Serie TV  ·  {len(seasons)} stagioni  ·  "
                f"{len(records)} episodi  ·  {seen} visti"
            )
        else:
            self.season_combo.hide()
            tags = sorted({t for r in records for t in r["tags"]}, key=str.casefold)
            detail = "Film"
            if tags:
                detail += "  ·  " + "  •  ".join(tags[:4])
            if len(records) > 1:
                detail += f"  ·  {len(records)} file"
            self.coll_meta.setText(detail)

        self.refresh_file_list()

    def _season_changed(self, *_args):
        self.refresh_file_list()

    def refresh_file_list(self):
        if not self.collection:
            self._show_empty(self._empty_message())
            return

        season = (
            self.season_combo.currentData()
            if self.collection["kind"] == "serie"
            else None
        )
        selected_path = self.current["path"] if self.current else None

        records = [
            r for r in self.records
            if r["kind"] == self.collection["kind"]
            and r["series"].casefold() == self.collection["name"].casefold()
            and (season is None or r["season"] == season)
        ]
        records.sort(
            key=lambda r: (_safe_int(r["season"]), _safe_int(r["episode"]), r["title"].casefold())
        )

        self.file_list.blockSignals(True)
        self.file_list.clear()
        selected_item = None
        for record in records:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, record)
            tooltip = [
                record["path"],
                "Tipo: " + ("Serie TV" if record["kind"] == "serie" else "Film"),
            ]
            if record["tags"]:
                tooltip.append("TAG: " + ", ".join(record["tags"]))
            item.setToolTip("\n".join(tooltip))
            item.setSizeHint(QSize(80, 68))
            self.file_list.addItem(item)
            if selected_path and record["path"] == selected_path:
                selected_item = item

        if records:
            self.stack.setCurrentIndex(1)
            if selected_item is None:
                selected_item = self.file_list.item(0)
            self.file_list.setCurrentItem(selected_item)
        else:
            self.stack.setCurrentIndex(0)
            self.empty_label.setText("Nessun episodio per questa stagione.")
        self.file_list.blockSignals(False)
        self._on_file_selected()

    def _show_empty(self, message):
        self.empty_label.setText(message)
        self.stack.setCurrentIndex(0)
        self.season_combo.hide()
        self.coll_title.setText("Nessuna raccolta selezionata")
        self.coll_meta.setText("")
        self._refresh_collection_cover()
        self.btn_online.setEnabled(False)
        self.current = None
        self.btn_details.setEnabled(False)
        self.btn_seen.setEnabled(False)
        self.file_list.blockSignals(True)
        self.file_list.clear()
        self.file_list.blockSignals(False)

    # =============================================================== selezione
    def _on_file_selected(self):
        items = self.file_list.selectedItems()
        if items:
            self.current = items[0].data(Qt.ItemDataRole.UserRole)
            self.btn_details.setEnabled(True)
            self.btn_seen.setEnabled(True)
            self.btn_seen.setText(
                "↺  Segna non visto"
                if self.current.get("status") == "visto"
                else "✔  Segna visto"
            )
        else:
            self.current = None
            self.btn_details.setEnabled(False)
            self.btn_seen.setEnabled(False)

    def _play_item(self, item):
        record = item.data(Qt.ItemDataRole.UserRole)
        if record:
            self._play_record(record)

    def _play_record(self, record):
        self.current = record
        self.current_online = False
        self._online_play_token += 1
        self._online_request = None
        if self.player_closed:
            self.open_player()
        self.current_file = record["path"]
        start = self.manager.get_start_time(record["path"])
        if record["kind"] == "serie":
            meta = (
                f"{record['series']}  ·  "
                f"S{_safe_int(record['season'], 1):02d}E{_safe_int(record['episode'], 1):02d}"
                f"  —  {record['title']}"
            )
        else:
            meta = record["title"]
        self.player.play_file(record["path"], start=start, meta=meta)
        self.setWindowTitle(f"VistoFlow Pro — {meta}")

    # --------------------------------------------------------- ricerca online
    def open_online_search(self):
        """Apre la ricerca sui canali online dentro VistoFlow."""
        if self._online_dialog is None:
            self._online_dialog = OnlineSearchDialog(self.manager, self)
            self._online_dialog.play_requested.connect(self._play_online_stream)
            self._online_dialog.links_requested.connect(self.open_saved_links)
            self._online_dialog.browser_requested.connect(self.open_browser)
            self._online_dialog.finished.connect(self._on_online_dialog_finished)
        self._online_dialog.show()
        self._online_dialog.raise_()
        self._online_dialog.activateWindow()

    def _on_online_dialog_finished(self, _result):
        dialog = self._online_dialog
        self._online_dialog = None
        if dialog is not None:
            dialog.deleteLater()

    def open_saved_links(self):
        """Apre la gestione dei link salvati, accessibile anche dalla topbar."""
        if self._links_dialog is None:
            self._links_dialog = SavedLinksDialog(self.manager, self)
            self._links_dialog.play_requested.connect(self._play_online_stream)
            self._links_dialog.browser_requested.connect(self.open_browser)
            self._links_dialog.finished.connect(self._on_links_dialog_finished)
        self._links_dialog.show()
        self._links_dialog.raise_()
        self._links_dialog.activateWindow()

    def _on_links_dialog_finished(self, _result):
        dialog = self._links_dialog
        self._links_dialog = None
        if dialog is not None:
            dialog.deleteLater()

    def open_browser(self, url: str = ""):
        """Apre una pagina nel browser WebEngine integrato.

        Il motore gira in un processo PySide6 separato e la sua finestra viene
        incorporata nel dialogo. Il browser è volutamente generico: non risolve
        né estrae flussi e non aggira protezioni. Serve per usare il player del
        sito con la propria sessione, restando dentro VistoFlow.
        """
        url = str(url or "").strip()
        if self._browser_dialog is None:
            self._browser_dialog = WebBrowserDialog(url, self)
            self._browser_dialog.finished.connect(self._on_browser_finished)
            self._browser_dialog.stream_play_requested.connect(
                self._on_browser_stream_play
            )
        elif url:
            self._browser_dialog.load_url(url)
        self._browser_dialog.show()
        self._browser_dialog.raise_()
        self._browser_dialog.activateWindow()

    def _on_browser_finished(self, _result):
        dialog = self._browser_dialog
        self._browser_dialog = None
        if dialog is not None:
            dialog.deleteLater()

    def _on_browser_stream_play(self, data: dict):
        """Avvia la riproduzione del flusso .m3u8 intercettato dalla WebView nel player VLC."""
        if self._browser_dialog is not None:
            try:
                self._browser_dialog.accept()
            except Exception:
                pass

        url = str(data.get("url") or "").strip()
        if not url:
            return
        referer = str(data.get("referer") or "").strip()
        user_agent = str(data.get("user_agent") or "").strip()
        title = str(data.get("title") or "").strip() or "Flusso Web"
        page_url = str(data.get("page_url") or "").strip() or referer

        if not user_agent:
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            )
        if not referer:
            referer = page_url or "about:blank"

        headers: dict[str, str] = {
            "Referer": referer,
            "User-Agent": user_agent,
        }

        if self._links_dialog is not None and self._links_dialog.isVisible():
            self._links_dialog.hide()
        if self._online_dialog is not None and self._online_dialog.isVisible():
            self._online_dialog.hide()

        try:
            stream = StreamSource(
                url=url,
                headers=headers,
                resolver_name="Browser Interceptor",
                referer=referer or None,
            )
            request = PlayRequest(
                stream=stream,
                title=title,
                source_url=page_url or referer or None,
                referer=referer or None,
                user_agent=user_agent or None,
            )
            self._play_online_stream(request)
        except Exception:
            self._persist_progress()
            self.current = None
            self.current_file = None
            self.current_online = True
            self.file_list.clearSelection()
            if self.player_closed:
                self.open_player()
            meta = f"{title} · Web Stream"
            self.player.play_url(url, headers=headers, meta=meta)
            self.setWindowTitle(f"VistoFlow Pro — {meta}")

    def _play_online_stream(self, request):
        """Riproduce un flusso online e conserva i dati per rigenerarlo."""
        if not isinstance(request, PlayRequest):
            return
        stream = request.stream
        self._persist_progress()
        self.current = None
        self.current_file = None
        self.current_online = True
        self.file_list.clearSelection()
        if self.player_closed:
            self.open_player()

        if not request.is_refresh:
            # Una nuova riproduzione manuale azzera i tentativi automatici.
            self._online_play_token += 1
            self._online_refresh_attempts = 0
            self._online_refresh_worker = None
        self._online_request = request

        quality = f"  ·  {stream.quality}" if stream.quality else ""
        meta = f"{request.title}{quality}  ·  {stream.resolver_name}"
        self.player.play_url(stream.url, headers=stream.headers, meta=meta)
        self.setWindowTitle(f"VistoFlow Pro — {meta}")

    # --------------------------------------------------- refresh link scaduti
    def _on_player_error(self, _message):
        """Se VLC fallisce su un link online, prova a rigenerare il flusso."""
        if not self.current_online or self._online_request is None:
            return
        request = self._online_request
        if not request.can_refresh:
            self.player.lbl_meta.setText("Riproduzione non riuscita")
            return
        if self._online_refresh_attempts >= 2:
            self.player.lbl_meta.setText("Link scaduto: aggiorna il link salvato")
            return
        if self._online_refresh_worker is not None:
            return

        self._online_refresh_attempts += 1
        self.player.lbl_meta.setText(
            f"Link scaduto: cerco un nuovo flusso… ({self._online_refresh_attempts}/2)"
        )
        token = self._online_play_token
        worker = AsyncOperation(
            lambda: self._resolve_online_request(request),
            parent=self,
        )
        self._online_refresh_worker = worker
        worker.completed.connect(
            lambda outcome, w=worker: self._on_online_refresh_done(
                outcome, w, request, token
            )
        )
        worker.failed.connect(
            lambda message, w=worker: self._on_online_refresh_failed(
                message, w, token
            )
        )
        worker.start()

    async def _resolve_online_request(self, request: PlayRequest):
        config = self.manager.data.get("online")
        service = OnlineService(config if isinstance(config, dict) else {})
        if request.source_result is not None:
            return await service.resolve_result(request.source_result)
        if not request.source_url:
            raise RuntimeError("Nessuna pagina sorgente per rigenerare il link")
        return await service.resolve_url(
            request.source_url,
            referer=request.referer,
            headers=request.headers,
            user_agent=request.user_agent,
        )

    def _on_online_refresh_done(self, outcome, worker, request, token):
        if self._online_refresh_worker is worker:
            self._online_refresh_worker = None
        worker.deleteLater()
        if token != self._online_play_token or not self.current_online:
            return
        if not outcome.streams:
            self.player.lbl_meta.setText(
                "Link scaduto: nessun nuovo flusso trovato"
            )
            return

        stream = outcome.streams[0]
        refreshed = PlayRequest(
            stream=stream,
            title=request.title,
            source_url=request.source_url,
            source_result=request.source_result,
            referer=request.referer,
            headers=dict(stream.headers),
            user_agent=request.user_agent,
            is_refresh=True,
        )
        self._play_online_stream(refreshed)

    def _on_online_refresh_failed(self, message, worker, token):
        if self._online_refresh_worker is worker:
            self._online_refresh_worker = None
        worker.deleteLater()
        if token != self._online_play_token:
            return
        self.player.lbl_meta.setText(f"Link scaduto: aggiornamento non riuscito ({message})")

    # ------------------------------------------------------- chiusura player
    def play_selected(self):
        record = self.current
        if not record:
            items = self.file_list.selectedItems()
            if items:
                record = items[0].data(Qt.ItemDataRole.UserRole)
        if record:
            self._play_record(record)

    def close_player(self):
        """Chiude il riproduttore liberando spazio per la selezione dei file."""
        if self.player_closed:
            return
        if self.is_full:
            self.toggle_fullscreen()
        self._persist_progress()
        self.player.stop()
        self.current_file = None
        self.current_online = False
        self._online_play_token += 1
        self._online_request = None
        self.player_closed = True
        self.player.hide()
        self.player_bar_label.setText(
            "Riproduttore chiuso — più spazio per selezionare i file"
        )
        self.player_bar.show()
        self.setWindowTitle("VistoFlow Pro")
        available = max(220, self.height() - 120)
        self.right_splitter.setSizes([0, self.player_bar.height(), available])
        self.file_list.setFocus()

    def open_player(self):
        """Riapre il riproduttore (il video riparte dal punto salvato)."""
        if not self.player_closed:
            return
        self.player_closed = False
        self.player_bar.hide()
        self.player.show()
        available = max(240, self.height() - 560)
        self.right_splitter.setSizes([520, 0, available])
        QTimer.singleShot(120, self.player.set_window_id)

    def _persist_progress(self):
        if not self.current_file or self.current_online:
            return
        try:
            position = self.player.player.get_time()
            duration = self.player.player.get_length()
            if position > 0 and duration > 0:
                self.manager.update_history(
                    self.current_file,
                    position,
                    duration,
                    finished=(position / duration) > 0.95,
                    save=True,
                )
        except Exception:
            pass

    # ============================================================ riproduzione
    def _update_progress(self, position):
        if not self.current_file or self.current_online:
            return
        duration = self.player.player.get_length()
        if duration <= 0:
            return
        now = time.time()
        persist = (now - self._last_save) > 5
        finished = (position / duration) > 0.95
        self.manager.update_history(
            self.current_file, position, duration, finished=finished, save=persist
        )
        if persist:
            self._last_save = now

    def _on_finished(self):
        if not self.current_file or self.current_online:
            return
        self.manager.force_mark_as_seen(self.current_file)
        self.reload(select_first=False)

    # ============================================================== azioni file
    def toggle_selected_seen(self):
        if not self.current:
            return
        if self.current.get("status") == "visto":
            self.manager.mark_unseen(self.current["path"])
        else:
            self.manager.force_mark_as_seen(self.current["path"])
        self.reload(select_first=False)

    def mark_path_seen(self, path, seen=True):
        if seen:
            self.manager.force_mark_as_seen(path)
        else:
            self.manager.mark_unseen(path)
        self.reload(select_first=False)

    def _selected_records(self):
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.file_list.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole)
        ]

    def edit_selected_details(self, path=None):
        if path is None:
            if not self.current:
                return
            path = self.current["path"]
        record = next((r for r in self.records if r["path"] == path), None)
        if not record:
            return
        dialog = FileDetailsDialog(self.manager, record, self)
        if dialog.exec():
            data = dialog.result_data()
            cover = data.pop("_cover", {}) or {}
            self.manager.update_meta(path, **data)
            self._apply_cover_action(record, cover)
            self._cover_cache.clear()
            self.reload(select_first=False)

    def _apply_cover_action(self, record, action):
        """Applica la scelta fatta nel dialogo dettagli alla raccolta giusta."""
        if not action:
            return
        kind = action.get("kind") or record.get("kind")
        name = action.get("name") or record.get("series") or record.get("title")
        old_kind = record.get("kind")
        old_name = record.get("series") or record.get("title")
        source = action.get("source")
        if source:
            self.manager.set_cover(kind, name, source)
            if action.get("temp"):
                try:
                    os.remove(source)
                except OSError:
                    pass
        elif action.get("remove"):
            self.manager.remove_cover(kind, name)
        elif old_name and (old_kind, old_name) != (kind, name):
            self.manager.move_cover(kind, old_name, name, old_kind=old_kind)

    def add_tags_to_paths(self, paths):
        if not paths:
            return
        label = (
            "Aggiungi TAG (separati da virgola):"
            if len(paths) == 1
            else f"Aggiungi TAG a {len(paths)} file (separati da virgola):"
        )
        text, ok = QInputDialog.getText(self, "Aggiungi TAG", label)
        if not ok or not text.strip():
            return
        tags = [t.strip() for t in text.replace(";", ",").split(",") if t.strip()]
        if not tags:
            return
        for path in paths:
            self.manager.add_tags(path, tags)
        self.reload(select_first=False)

    def set_paths_kind(self, records, kind):
        if not records:
            return
        if kind == "serie":
            existing = {r["series"] for r in records if r["kind"] == "serie"}
            default = next(iter(existing)) if len(existing) == 1 else ""
            name, ok = QInputDialog.getText(
                self,
                "Classifica come serie",
                "Nome della serie (vuoto = ricavalo dal nome/cartella):",
                text=default,
            )
            if not ok:
                return
            for record in records:
                self.manager.update_meta(
                    record["path"],
                    kind="serie",
                    series=name.strip() or None,
                )
        else:
            for record in records:
                self.manager.update_meta(
                    record["path"],
                    kind="film",
                    series=None,
                    season=None,
                    episode=None,
                )
        self.reload(select_first=False)

    def _show_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if item is None:
            return
        if item not in self.file_list.selectedItems():
            self.file_list.setCurrentItem(item)
        record = item.data(Qt.ItemDataRole.UserRole)
        if not record:
            return
        selected = self._selected_records() or [record]
        paths = [rec["path"] for rec in selected]
        seen_states = [rec.get("status") == "visto" for rec in selected]
        if all(seen_states):
            seen_label = "↺  Segna come non visto"
        elif not any(seen_states):
            seen_label = "✔  Segna come visto"
        else:
            seen_label = "⇄  Inverti stato di visione"

        menu = QMenu(self)
        action_play = menu.addAction("▶  Riproduci")
        action_details = menu.addAction("🏷  Dettagli e TAG…")
        action_online = menu.addAction("🌐  Copertina online (automatica)")
        action_online_search = menu.addAction("🔎  Cerca copertina online…")
        action_cover = menu.addAction("🖼  Scegli copertina da file…")
        action_remove_cover = None
        if self.manager.get_cover(record["kind"], record["series"]):
            action_remove_cover = menu.addAction("🚫  Rimuovi copertina")
        action_tags = menu.addAction(
            "➕  Aggiungi TAG…" if len(paths) == 1 else f"➕  Aggiungi TAG a {len(paths)} file…"
        )
        kind_menu = menu.addMenu("Classifica come")
        action_film = kind_menu.addAction("🎬  Film")
        action_serie = kind_menu.addAction("📺  Serie TV")
        menu.addSeparator()
        action_seen = menu.addAction(seen_label)
        menu.addSeparator()
        action_folder = menu.addAction("📂  Apri cartella")
        action_copy = menu.addAction("⧉  Copia percorso")
        action_remove = None
        library_keys = {os.path.normcase(p) for p in self.manager.data["library_paths"]}
        if os.path.normcase(record["path"]) in library_keys:
            menu.addSeparator()
            action_remove = menu.addAction("🗑  Rimuovi dalla libreria")

        chosen = menu.exec(self.file_list.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is action_play:
            self._play_record(record)
        elif chosen is action_details:
            self.edit_selected_details(record["path"])
        elif chosen is action_online:
            self.fetch_cover_online(record, auto=True)
        elif chosen is action_online_search:
            self.fetch_cover_online(record, auto=False)
        elif chosen is action_cover:
            self.choose_cover(record)
        elif action_remove_cover is not None and chosen is action_remove_cover:
            self.remove_collection_cover(record)
        elif chosen is action_tags:
            self.add_tags_to_paths(paths)
        elif chosen is action_film:
            self.set_paths_kind(selected, "film")
        elif chosen is action_serie:
            self.set_paths_kind(selected, "serie")
        elif chosen is action_seen:
            for rec in selected:
                if rec.get("status") == "visto":
                    self.manager.mark_unseen(rec["path"])
                else:
                    self.manager.force_mark_as_seen(rec["path"])
            self.reload(select_first=False)
        elif chosen is action_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(record["path"])))
        elif chosen is action_copy:
            QApplication.clipboard().setText(record["path"])
        elif action_remove is not None and chosen is action_remove:
            if QMessageBox.question(
                self,
                "Rimuovi dalla libreria",
                f"Rimuovere questo file dalla libreria?\n\n{record['path']}",
            ) == QMessageBox.StandardButton.Yes:
                self.manager.remove_library_path(record["path"])
                self.reload(select_first=False)

    # ============================================================== gestione libreria
    def add_library(self):
        path = QFileDialog.getExistingDirectory(self, "Seleziona cartella")
        if path:
            self.manager.add_library_path(path)
            self.reload(select_first=True)

    def add_single_file(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleziona video",
            "",
            "Video (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.flv *.wmv);;Tutti i file (*.*)",
        )
        if not files:
            return
        added = False
        for path in files:
            added = self.manager.add_library_path(os.path.normpath(path)) or added
        if added:
            self.reload(select_first=True)

    def show_library_menu(self):
        menu = QMenu(self)
        paths = self.manager.data.get("library_paths", [])
        if not paths:
            action = menu.addAction("Nessun percorso nella libreria")
            action.setEnabled(False)
        for path in paths:
            label = path if len(path) <= 46 else "…" + path[-45:]
            submenu = menu.addMenu(("📁  " if os.path.isdir(path) else "🎞  ") + label)
            open_action = submenu.addAction("Apri nel file manager")
            open_action.triggered.connect(
                lambda _checked=False, p=path: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(p if os.path.isdir(p) else os.path.dirname(p))
                )
            )
            remove_action = submenu.addAction("Rimuovi dalla libreria")
            remove_action.triggered.connect(
                lambda _checked=False, p=path: self._remove_library_path(p)
            )
        menu.exec(self.btn_library.mapToGlobal(self.btn_library.rect().bottomLeft()))

    def _remove_library_path(self, path):
        if QMessageBox.question(
            self,
            "Rimuovi percorso",
            f"Rimuovere dalla libreria questo percorso?\n\n{path}\n\n"
            "I file non verranno cancellati dal disco.",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.manager.remove_library_path(path)
        self.reload(select_first=False)

    # ============================================================ schermo intero
    def toggle_fullscreen(self):
        if not self.is_full and self.player_closed:
            self.open_player()
        if not self.is_full:
            self._was_maximized = self.isMaximized()
            self.is_full = True
            self.topbar.hide()
            self.sidebar.hide()
            self.browser_panel.hide()
            self.showFullScreen()
            self.player.btn_full.setText("❐")
            self.player.controls.show()
            self.player.hide_timer.start()
            self.player.setFocus()
        else:
            self.is_full = False
            if self._was_maximized:
                self.showMaximized()
            else:
                self.showNormal()
            self.topbar.show()
            self.sidebar.show()
            self.browser_panel.show()
            self.player.btn_full.setText("⛶")
        QTimer.singleShot(180, self.player.set_window_id)

    # ================================================================== chiusura
    def closeEvent(self, event):
        try:
            self._persist_progress()
            self.player.stop()
        except Exception:
            pass
        if self._browser_dialog is not None:
            try:
                self._browser_dialog.close()
            except Exception:
                pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VistoFlow Pro")
    apply_theme(app)
    window = VistoFlowApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
