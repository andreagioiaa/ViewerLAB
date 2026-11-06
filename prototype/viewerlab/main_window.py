"""Finestra principale di ViewerLAB."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import config
from .dialogs import DirectLinkDialog, SourceEditorDialog
from .html_site import resolve_site
from .models import ProbeResult, Source, StreamCandidate
from .player import MpvController, MpvError
from .player_panel import PlayerPanel
from .probe import StreamProbe
from .search import SourceRepository

LOGGER = logging.getLogger(__name__)


def _describe_source(source: Source) -> str:
    if source.kind == "direct":
        return "Link diretto"
    if source.kind == "json_api":
        return "API JSON"
    if source.kind == "site":
        return "Sito web"
    return "Catalogo"


def _kind_label(candidate: StreamCandidate) -> str:
    if candidate.needs_resolution:
        return "SITO"
    return (candidate.kind or "stream").upper()


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
                self.failed.emit(self._purpose, "Fonte del contenuto non disponibile")
                return
            try:
                streams = resolve_site(self._source, target)
            except Exception as error:  # rete, HTML, selettori
                self.failed.emit(self._purpose, f"Risoluzione fallita: {error}")
                return
            if not streams:
                self.failed.emit(
                    self._purpose,
                    "Nessun flusso video trovato nella pagina del contenuto",
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


class MainWindow(QMainWindow):
    smoke_finished = Signal(bool, str)

    COLUMNS = ("Titolo", "Anno", "Tipo", "Fonte", "Stato")

    def __init__(
        self,
        mpv_path: str | None = None,
        autoplay_query: str | None = None,
        smoke_test: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("ViewerLAB — Media Center")
        self.resize(1180, 760)

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

        self._build_ui()
        self._reload_sources()

        self._state_timer = QTimer(self)
        self._state_timer.setInterval(300)
        self._state_timer.timeout.connect(self._poll_player)
        self._state_timer.start()

        if autoplay_query is not None or smoke_test:
            QTimer.singleShot(600, self._start_autoplay)

    # ---------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "Cerca un titolo nei cataloghi configurati (vuoto = mostra tutto)"
        )
        self.search_edit.returnPressed.connect(self._start_search)

        self.search_button = QPushButton("Cerca")
        self.search_button.clicked.connect(self._start_search)

        self.verify_button = QPushButton("Verifica flusso")
        self.verify_button.clicked.connect(self._verify_selected)

        self.play_button = QPushButton("Riproduci")
        self.play_button.setObjectName("PrimaryButton")
        self.play_button.clicked.connect(self._play_selected)

        self.sources_button = QPushButton("Fonti…")
        self.sources_button.clicked.connect(lambda: self._sources_dock.show())

        self.summary_label = QLabel("Nessuna ricerca")
        self.summary_label.setStyleSheet("color: #8a93a5;")

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.search_button)
        top.addWidget(self.verify_button)
        top.addWidget(self.play_button)
        top.addWidget(self.sources_button)

        self.results = QTableWidget(0, len(self.COLUMNS))
        self.results.setHorizontalHeaderLabels(self.COLUMNS)
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.setAlternatingRowColors(True)
        self.results.verticalHeader().setVisible(False)
        self.results.doubleClicked.connect(lambda _index: self._play_selected())
        header = self.results.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self.player_panel = PlayerPanel()
        self.player_panel.play_requested.connect(self._play_selected)
        self.player_panel.pause_requested.connect(self._toggle_pause)
        self.player_panel.stop_requested.connect(self._stop_playback)
        self.player_panel.seek_requested.connect(self._seek)
        self.player_panel.skip_requested.connect(self._skip)
        self.player_panel.volume_changed.connect(self._set_volume)
        self.player_panel.fullscreen_requested.connect(self._toggle_fullscreen)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.results)
        splitter.addWidget(self.player_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([280, 420])

        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addLayout(top)
        layout.addWidget(self.summary_label)
        layout.addWidget(splitter, 1)

        self._build_sources_dock()
        self.statusBar().showMessage("Pronto")

        quit_action = QAction(self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

        focus_action = QAction(self)
        focus_action.setShortcut(QKeySequence.StandardKey.Find)
        focus_action.triggered.connect(self._focus_search)
        self.addAction(focus_action)

        fullscreen_action = QAction(self)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        self.addAction(fullscreen_action)

        space_action = QAction(self)
        space_action.setShortcut(QKeySequence("Space"))
        space_action.triggered.connect(self._toggle_pause)
        self.addAction(space_action)

    def _build_sources_dock(self) -> None:
        self._sources_dock = QDockWidget("Fonti", self)
        self._sources_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._sources_dock.setMinimumWidth(300)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)

        self.sources_table = QTableWidget(0, 3)
        self.sources_table.setHorizontalHeaderLabels(("Attiva", "Nome", "Tipo"))
        self.sources_table.verticalHeader().setVisible(False)
        self.sources_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sources_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.sources_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.sources_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.sources_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.sources_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.sources_table.itemChanged.connect(self._on_source_item_changed)
        self.sources_table.doubleClicked.connect(lambda _index: self._edit_source())

        add_button = QPushButton("Aggiungi")
        add_button.clicked.connect(self._add_source)
        site_button = QPushButton("Sito web")
        site_button.clicked.connect(self._add_site)
        audio_button = QPushButton("Link diretto")
        audio_button.clicked.connect(self._add_direct_link)
        edit_button = QPushButton("Modifica")
        edit_button.clicked.connect(self._edit_source)
        remove_button = QPushButton("Rimuovi")
        remove_button.clicked.connect(self._remove_source)

        buttons_top = QHBoxLayout()
        buttons_top.addWidget(add_button)
        buttons_top.addWidget(site_button)
        buttons_top.addWidget(audio_button)
        buttons_top.addWidget(edit_button)
        buttons_top.addWidget(remove_button)

        hint = QLabel(
            "Le fonti sono cataloghi JSON, API JSON, siti web o link diretti che hai "
            "il diritto di usare. I flussi vengono verificati prima della riproduzione."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8a93a5;")

        layout.addWidget(self.sources_table, 1)
        layout.addLayout(buttons_top)
        layout.addWidget(hint)

        self._sources_dock.setWidget(container)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._sources_dock)

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
            QMessageBox.warning(self, "Salvataggio fallito", str(error))
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
            QMessageBox.warning(self, "Fonte duplicata", "Esiste già una fonte con lo stesso identificativo.")
            return
        self._sources.append(source)
        self._persist_sources()
        self.statusBar().showMessage(f"Fonte aggiunta: {source.name}", 5000)

    def _add_site(self) -> None:
        dialog = SourceEditorDialog(self, kind="site")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source = dialog.edited_source()
        if any(existing.id == source.id for existing in self._sources):
            QMessageBox.warning(
                self, "Fonte duplicata", "Esiste già una fonte con lo stesso identificativo."
            )
            return
        self._sources.append(source)
        self._persist_sources()
        self.statusBar().showMessage(f"Sito aggiunto: {source.name}", 5000)

    def _add_direct_link(self) -> None:
        dialog = DirectLinkDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source = dialog.added_source()
        self._sources.append(source)
        self._persist_sources()
        self.statusBar().showMessage(f"Link aggiunto: {source.title}", 5000)

    def _edit_source(self) -> None:
        source = self._selected_source()
        if source is None:
            QMessageBox.information(self, "Nessuna fonte", "Seleziona una fonte da modificare.")
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
        self.statusBar().showMessage(f"Fonte aggiornata: {updated.name}", 5000)

    def _remove_source(self) -> None:
        source = self._selected_source()
        if source is None:
            QMessageBox.information(self, "Nessuna fonte", "Seleziona una fonte da rimuovere.")
            return
        answer = QMessageBox.question(
            self,
            "Rimuovere la fonte?",
            f"Rimuovere «{source.name}»?",
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
        if self._search_task is not None and self._search_task.isRunning():
            return
        enabled = [source for source in self._sources if source.enabled]
        if not enabled:
            QMessageBox.information(
                self,
                "Nessuna fonte attiva",
                "Aggiungi o attiva almeno una fonte dalla sezione «Fonti».",
            )
            return

        query = self.search_edit.text().strip()
        self.search_button.setEnabled(False)
        self.summary_label.setText("Ricerca in corso…")
        self.statusBar().showMessage("Ricerca in corso…")

        self._search_task = SearchTask(enabled, query, self)
        self._search_task.progress.connect(
            lambda name, count: self.statusBar().showMessage(
                f"Fonte {name}: {count} risultati", 3000
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
        self.summary_label.setText("Ricerca non riuscita")
        self.statusBar().showMessage(message, 8000)
        if self._smoke:
            self._finish_smoke(False, f"ricerca non riuscita: {message}")

    def _on_search_completed(self, outcome) -> None:
        autoplay = self._autoplay_query
        self._autoplay_query = None
        self._last_outcome = outcome
        self._candidates = list(outcome.candidates)
        self.results.setRowCount(0)
        for candidate in self._candidates:
            row = self.results.rowCount()
            self.results.insertRow(row)
            self.results.setItem(row, 0, QTableWidgetItem(candidate.title))
            self.results.setItem(row, 1, QTableWidgetItem(candidate.display_year()))
            self.results.setItem(row, 2, QTableWidgetItem(_kind_label(candidate)))
            self.results.setItem(row, 3, QTableWidgetItem(candidate.source_name))
            cached = self._probes.get(candidate.key)
            self.results.setItem(
                row, 4, QTableWidgetItem(cached.label() if cached else "—")
            )

        elapsed = outcome.elapsed
        self.summary_label.setText(
            f"{len(self._candidates)} risultati in {elapsed:.1f}s "
            f"da {len(self._sources)} fonti configurate"
        )
        self.statusBar().showMessage(
            f"Ricerca completata: {len(self._candidates)} risultati", 6000
        )
        if outcome.errors:
            details = "; ".join(
                f"{error.source_name}: {error.message}" for error in outcome.errors
            )
            self.statusBar().showMessage(f"Fonti con errori — {details}", 12000)

        if self._candidates:
            self.results.selectRow(0)
            self.player_panel.set_title(self._candidates[0].title)
        elif self._smoke:
            self._finish_smoke(False, "nessun risultato")

        if autoplay is not None and self._candidates:
            candidate = self._candidates[0]
            QTimer.singleShot(150, lambda: self._request_play(candidate))

    # ----------------------------------------------------------- verifica

    def _selected_candidate(self) -> StreamCandidate | None:
        row = self.results.currentRow()
        if 0 <= row < len(self._candidates):
            return self._candidates[row]
        return None

    def _verify_selected(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            QMessageBox.information(
                self, "Nessun contenuto", "Esegui una ricerca e seleziona un risultato."
            )
            return
        self._start_probe(candidate, purpose="verify")

    def _start_probe(self, candidate: StreamCandidate, purpose: str) -> None:
        if self._probe_task is not None and self._probe_task.isRunning():
            self.statusBar().showMessage("Verifica già in corso…", 3000)
            return
        self._set_row_status(
            candidate, "Risoluzione pagina…" if candidate.needs_resolution else "Verifica…"
        )
        self.player_panel.set_status(
            "Ricerca del flusso nella pagina…"
            if candidate.needs_resolution
            else "Verifica del flusso…"
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
        self.player_panel.set_status(f"Verifica non riuscita: {message}")
        self.statusBar().showMessage(message, 10000)
        if self._smoke and purpose == "play":
            self._finish_smoke(False, f"verifica non riuscita: {message}")
        elif purpose == "play":
            QMessageBox.warning(self, "Flusso non trovato", message)

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
                label += " — flusso trovato nella pagina"
            self._set_row_status(candidate, label)

        if purpose == "verify":
            if result.ok:
                detail = f" — {stream.kind.upper()} {stream.url}" if resolved else ""
                self.statusBar().showMessage(
                    f"{result.label()} — HTTP {result.status} — {result.details}{detail}",
                    10000,
                )
                self.player_panel.set_status(
                    f"{result.label()}{' (pagina risolta)' if resolved else ''}"
                )
            else:
                self.statusBar().showMessage(f"Non disponibile: {result.error}", 8000)
                self.player_panel.set_status(f"Non disponibile: {result.error}")
            return

        if not result.ok:
            self.player_panel.set_status(f"Non disponibile: {result.error}")
            self.statusBar().showMessage(f"Flusso non disponibile: {result.error}", 8000)
            if self._smoke:
                self._finish_smoke(False, f"flusso non disponibile: {result.error}")
            else:
                QMessageBox.warning(
                    self,
                    "Flusso non disponibile",
                    f"Il flusso non è raggiungibile o non è riproducibile.\n\n{result.error}",
                )
            return

        self._pending_play = stream
        self._ensure_player(stream)

    def _set_row_status(self, candidate: StreamCandidate, text: str) -> None:
        try:
            row = self._candidates.index(candidate)
        except ValueError:
            return
        item = self.results.item(row, 4)
        if item is None:
            item = QTableWidgetItem()
            self.results.setItem(row, 4, item)
        item.setText(text)

    # ------------------------------------------------------------- player

    def _play_selected(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            QMessageBox.information(
                self, "Nessun contenuto", "Esegui una ricerca e seleziona un risultato."
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

    def _ensure_player(self, candidate: StreamCandidate) -> None:
        if self._player is not None and self._player.is_running:
            self._load_candidate(candidate)
            return

        if self._start_task is not None and self._start_task.isRunning():
            return

        if self._player is None:
            self._player = MpvController(self._mpv_path)
        if not self._player.is_available:
            message = (
                "mpv non è stato trovato.\n\n"
                "Imposta la variabile d'ambiente MPV_PATH oppure copia mpv.exe "
                "nella cartella bin/ accanto all'applicazione."
            )
            self.player_panel.set_status("mpv non disponibile")
            if self._smoke:
                self._finish_smoke(False, "mpv non trovato")
            else:
                QMessageBox.critical(self, "mpv non trovato", message)
            return

        window_id = int(self.player_panel.video.winId())
        if not window_id:
            self.player_panel.set_status("Superficie video non pronta")
            return

        self.player_panel.set_busy(True)
        self.player_panel.set_status("Avvio del player…")
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
        self.statusBar().showMessage("Player avviato", 4000)
        if self._pending_play is not None:
            self._load_candidate(self._pending_play)

    def _on_player_failed(self, message: str) -> None:
        self.player_panel.set_status(f"Errore player: {message}")
        self._pending_play = None
        if self._smoke:
            self._finish_smoke(False, f"player non avviato: {message}")
        else:
            QMessageBox.critical(self, "Errore del player", message)

    def _load_candidate(self, candidate: StreamCandidate) -> None:
        assert self._player is not None
        self._loading_candidate = candidate
        self.player_panel.set_active(True)
        self.player_panel.set_title(candidate.title)
        self.player_panel.set_status("Caricamento del flusso…")
        self.statusBar().showMessage(f"Apertura flusso: {candidate.url}", 6000)
        try:
            self._player.load(candidate)
        except (MpvError, OSError) as error:
            self.player_panel.set_status(f"Errore: {error}")
            if self._smoke:
                self._finish_smoke(False, f"caricamento non riuscito: {error}")
            else:
                QMessageBox.critical(self, "Errore di caricamento", str(error))
            return
        self._pending_play = None

    def _toggle_pause(self) -> None:
        if self._player is None or not self._player.is_running:
            if self._selected_candidate() is not None:
                self._play_selected()
            return
        try:
            self._player.toggle_pause()
        except (MpvError, OSError) as error:
            self.statusBar().showMessage(f"Comando non riuscito: {error}", 5000)

    def _stop_playback(self) -> None:
        self._loading_candidate = None
        if self._player is not None and self._player.is_running:
            try:
                self._player.stop()
            except (MpvError, OSError):
                pass
        self.player_panel.set_active(False)
        self.player_panel.set_status("Fermato")

    def _seek(self, value: float) -> None:
        if self._player is None or not self._player.is_running:
            return
        try:
            self._player.seek(max(0.0, value))
        except (MpvError, OSError) as error:
            self.statusBar().showMessage(f"Seek non riuscito: {error}", 5000)

    def _skip(self, delta: float) -> None:
        if self._player is None or not self._player.is_running:
            return
        try:
            self._player.seek_by(delta)
        except (MpvError, OSError) as error:
            self.statusBar().showMessage(f"Seek non riuscito: {error}", 5000)

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
            self.player_panel.set_status("In riproduzione")
            self.statusBar().showMessage(
                f"Flusso avviato: {candidate.title} — "
                f"{state['duration_ms'] / 1000:.1f}s",
                8000,
            )
            if (
                self._smoke
                and not self._smoke_done
                and state.get("position_ms", 0) >= 800
            ):
                self._finish_smoke(
                    True,
                    f"flusso avviato: {candidate.title} "
                    f"({state['duration_ms'] / 1000:.1f}s, "
                    f"{state.get('width', 0)}x{state.get('height', 0)}, "
                    f"posizione {state.get('position_ms', 0) / 1000:.1f}s)",
                )

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
            self._sources_dock.show()
            self.results.show()
        else:
            self.results.hide()
            self._sources_dock.hide()
            self.showFullScreen()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - API Qt
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self._toggle_fullscreen()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 - API Qt
        for task in (self._search_task, self._probe_task, self._start_task):
            if task is not None and task.isRunning():
                task.wait(3000)
        if self._player is not None:
            try:
                self._player.quit()
            except Exception:  # pragma: no cover - chiusura difensiva
                LOGGER.exception("Errore durante la chiusura di mpv")
        super().closeEvent(event)
