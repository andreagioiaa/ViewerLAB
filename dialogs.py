"""Finestre di dialogo di VistoFlow Pro."""

import os
import tempfile

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCompleter, QDialog, QFileDialog, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QRadioButton, QSpinBox, QVBoxLayout,
)

from cover_fetcher import (
    AUTO_IMPORT_SCORE, CoverDownloadTask, CoverSearchTask, image_extension,
)


class OnlineCoverDialog(QDialog):
    """Cerca copertine online, mostra le anteprime e le importa."""

    def __init__(
        self,
        manager,
        kind,
        name,
        parent=None,
        query=None,
        auto=False,
        apply_on_accept=True,
    ):
        super().__init__(parent)
        self.manager = manager
        self.kind = kind if kind in ("film", "serie") else "film"
        self.name = (name or "").strip()
        self.apply_on_accept = apply_on_accept
        self.imported = False
        self.cover_source = None
        self._results = []
        self._selected = None
        self._preview_bytes = None
        self._search_task = None
        self._download_task = None
        self._download_token = 0
        self._auto_pending = bool(auto)
        self._cancelled = False

        self.setWindowTitle("Copertina online")
        self.setModal(True)
        self.setMinimumSize(800, 560)
        self.resize(840, 600)
        self._build_ui(query or self.name)
        QTimer.singleShot(0, lambda: self._start_search(bool(auto)))

    # ---------------------------------------------------------------- UI
    def _build_ui(self, query):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        title = QLabel("Cerca copertina online")
        title.setObjectName("CollectionTitle")
        root.addWidget(title)

        target = QLabel(
            f"{'Film' if self.kind == 'film' else 'Serie'} «{self.name}»"
        )
        target.setObjectName("Muted")
        target.setWordWrap(True)
        root.addWidget(target)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_edit = QLineEdit(query or self.name)
        self.search_edit.setPlaceholderText("Titolo del film o della serie")
        self.search_edit.returnPressed.connect(self._manual_search)
        self.btn_search = QPushButton("🔎  Cerca")
        self.btn_search.setObjectName("Primary")
        self.btn_search.clicked.connect(self._manual_search)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.btn_search)
        root.addLayout(search_row)

        self.status = QLabel("Ricerca in corso…")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        content = QHBoxLayout()
        content.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.results_list = QListWidget()
        self.results_list.setObjectName("OnlineResults")
        self.results_list.setUniformItemSizes(True)
        self.results_list.setMinimumWidth(400)
        self.results_list.currentItemChanged.connect(self._on_selection_changed)
        left.addWidget(self.results_list, 1)
        results_hint = QLabel("Seleziona un risultato per vederne l'anteprima.")
        results_hint.setObjectName("Muted")
        left.addWidget(results_hint)
        content.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.preview = QLabel("Nessuna\nanteprima")
        self.preview.setObjectName("CoverPreview")
        self.preview.setFixedSize(200, 300)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setWordWrap(True)
        right.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)

        self.source_label = QLabel("")
        self.source_label.setObjectName("Muted")
        self.source_label.setWordWrap(True)
        self.source_label.setMinimumHeight(48)
        right.addWidget(self.source_label)

        self.btn_use = QPushButton("Usa questa copertina")
        self.btn_use.setObjectName("Primary")
        self.btn_use.setEnabled(False)
        self.btn_use.clicked.connect(self._use_current)
        right.addWidget(self.btn_use)
        right.addStretch()
        content.addLayout(right, 0)

        root.addLayout(content, 1)

        footer = QHBoxLayout()
        note = QLabel("Fonti: IMDb · TVmaze · iTunes — serve una connessione a Internet.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        footer.addWidget(note, 1)
        btn_close = QPushButton("Chiudi")
        btn_close.setObjectName("Ghost")
        btn_close.clicked.connect(self.reject)
        footer.addWidget(btn_close)
        root.addLayout(footer)

    # ------------------------------------------------------------ ricerca
    def _manual_search(self):
        self._auto_pending = False
        self._start_search(False)

    def _start_search(self, auto):
        if self._cancelled:
            return
        query = self.search_edit.text().strip()
        if not query:
            self.status.setText("Inserisci un titolo da cercare.")
            return

        self._auto_pending = bool(auto)
        self._results = []
        self._selected = None
        self._preview_bytes = None
        self._download_token += 1
        self.results_list.blockSignals(True)
        self.results_list.clear()
        self.results_list.blockSignals(False)
        self.preview.setPixmap(QPixmap())
        self.preview.setText("Ricerca…")
        self.source_label.setText("")
        self.btn_use.setEnabled(False)
        self.btn_search.setEnabled(False)
        self.status.setText("Ricerca in corso…")
        self.setCursor(Qt.CursorShape.BusyCursor)

        task = CoverSearchTask(query, self.kind, self)
        self._search_task = task
        task.results_ready.connect(self._on_results)
        task.search_failed.connect(self._on_search_failed)
        task.start()

    def _on_results(self, results):
        if self._cancelled:
            return
        self.unsetCursor()
        self.btn_search.setEnabled(True)
        self._results = list(results or [])
        self.results_list.blockSignals(True)
        self.results_list.clear()
        for index, result in enumerate(self._results):
            item = QListWidgetItem(self._format_result(result))
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(
                f"{result.get('title', '')}\n"
                f"Fonte: {result.get('source', '')}\n"
                f"Punteggio: {result.get('score', 0)}"
            )
            self.results_list.addItem(item)
        self.results_list.blockSignals(False)

        if not self._results:
            self._auto_pending = False
            self.status.setText("Copertina non trovata online")
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Nessuna\nanteprima")
            self.source_label.setText(
                "Prova a modificare il titolo nel campo di ricerca e premi «Cerca»."
            )
            self.btn_use.setEnabled(False)
            return

        if self._auto_pending and self._results[0].get("score", 0) >= AUTO_IMPORT_SCORE:
            self.status.setText(
                f"Trovata «{self._results[0]['title']}» — importazione automatica…"
            )
        else:
            self._auto_pending = False
            if len(self._results) == 1:
                self.status.setText("1 copertina trovata. Seleziona e conferma.")
            else:
                self.status.setText(
                    f"{len(self._results)} copertine trovate. Scegli quella giusta."
                )
        self.results_list.setCurrentRow(0)

    def _on_search_failed(self, message):
        if self._cancelled:
            return
        self.unsetCursor()
        self.btn_search.setEnabled(True)
        self._auto_pending = False
        self.status.setText("Copertina non trovata online")
        self.preview.setPixmap(QPixmap())
        self.preview.setText("Nessuna\nanteprima")
        short = (message or "").strip()
        if len(short) > 180:
            short = short[:177] + "…"
        self.source_label.setText(
            "Ricerca online non disponibile. Controlla la connessione e riprova."
            + (f"\n{short}" if short else "")
        )
        self.btn_use.setEnabled(False)

    @staticmethod
    def _format_result(result):
        parts = [result.get("title", "Senza titolo")]
        if result.get("year"):
            parts.append(f"({result['year']})")
        parts.append(f"— {result.get('source', 'Online')}")
        if result.get("detail"):
            parts.append(f"· {result['detail']}")
        return " ".join(parts)

    # ---------------------------------------------------------- anteprima
    def _on_selection_changed(self, current, _previous=None):
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        try:
            result = self._results[int(index)]
        except (TypeError, ValueError, IndexError):
            return
        auto_use = self._auto_pending
        self._auto_pending = False
        self._download_preview(result, auto_use=auto_use)

    def _download_preview(self, result, auto_use=False):
        self._selected = result
        self._preview_bytes = None
        self.btn_use.setEnabled(False)
        self.preview.setPixmap(QPixmap())
        self.preview.setText("Caricamento…")
        details = [result.get("title", "")]
        if result.get("year"):
            details.append(f"({result['year']})")
        details.append(f"· {result.get('source', '')}")
        if result.get("detail"):
            details.append(f"· {result['detail']}")
        self.source_label.setText(" ".join(part for part in details if part))
        if auto_use:
            self.status.setText("Copertina trovata: importazione automatica…")
        else:
            self.status.setText("Caricamento anteprima…")

        self._download_token += 1
        token = self._download_token
        task = CoverDownloadTask(result.get("image_url", ""), self)
        self._download_task = task
        task.downloaded.connect(
            lambda data, t=token, auto=auto_use: self._on_preview(data, t, auto)
        )
        task.download_failed.connect(
            lambda message, t=token: self._on_preview_failed(message, t)
        )
        task.start()

    def _on_preview(self, data, token, auto_use):
        if self._cancelled or token != self._download_token:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.status.setText("Immagine non leggibile. Scegli un altro risultato.")
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Anteprima\nnon disponibile")
            return
        self._preview_bytes = data
        self.preview.setPixmap(
            pixmap.scaled(
                190,
                290,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.btn_use.setEnabled(True)
        self.unsetCursor()
        if auto_use:
            self._use_current()
        else:
            self.status.setText("Anteprima pronta. Premi «Usa questa copertina» per applicarla.")

    def _on_preview_failed(self, message, token):
        if self._cancelled or token != self._download_token:
            return
        self.unsetCursor()
        self.status.setText("Impossibile scaricare l'anteprima. Prova un altro risultato.")
        self.source_label.setText((message or "")[:180])
        self.preview.setPixmap(QPixmap())
        self.preview.setText("Anteprima\nnon disponibile")

    # ---------------------------------------------------------- importazione
    def _use_current(self):
        if self._cancelled or not self._selected or not self._preview_bytes:
            return
        extension = image_extension(
            self._selected.get("image_url") or self._selected.get("preview_url")
        )
        temp_path = self._write_temp(self._preview_bytes, extension)
        if not temp_path:
            self.status.setText("Impossibile preparare l'immagine scaricata.")
            return

        if self.apply_on_accept:
            stored = self.manager.set_cover(self.kind, self.name, temp_path)
            try:
                os.remove(temp_path)
            except OSError:
                pass
            if stored:
                self.imported = True
                self.status.setText("Copertina importata.")
                self.accept()
            else:
                self.status.setText("Impossibile salvare la copertina.")
        else:
            self.cover_source = temp_path
            self.accept()

    @staticmethod
    def _write_temp(data, extension):
        try:
            fd, path = tempfile.mkstemp(prefix="visto_cover_", suffix=extension)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            return path
        except OSError:
            return None

    def done(self, result):
        if result != QDialog.DialogCode.Accepted:
            self._cancelled = True
        super().done(result)


class FileDetailsDialog(QDialog):
    """Permette di classificare un file come film/serie e modificarne i TAG."""

    def __init__(self, manager, record, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.record = record
        self._cover_path = None
        self._cover_source = None
        self._cover_temp = False
        self._cover_removed = False
        self.setWindowTitle("Dettagli e TAG")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._build_ui()
        self._load(record)

    # ------------------------------------------------------------------- UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        title = QLabel("Dettagli del file")
        title.setObjectName("CollectionTitle")
        root.addWidget(title)

        filename = QLabel(self.record.get("filename", ""))
        filename.setObjectName("Muted")
        filename.setWordWrap(True)
        root.addWidget(filename)

        # -------------------------------------------------------- classificazione
        box = QGroupBox("CLASSIFICAZIONE")
        box_lay = QVBoxLayout(box)
        box_lay.setSpacing(12)

        kind_row = QHBoxLayout()
        kind_row.setSpacing(18)
        self.radio_film = QRadioButton("🎬  Film")
        self.radio_serie = QRadioButton("📺  Serie TV")
        kind_row.addWidget(self.radio_film)
        kind_row.addWidget(self.radio_serie)
        kind_row.addStretch()
        box_lay.addLayout(kind_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText("Titolo visualizzato (vuoto = automatico)")
        self.edit_series = QLineEdit()
        self.edit_series.setPlaceholderText("Nome della serie")
        self.spin_season = QSpinBox()
        self.spin_season.setRange(1, 99)
        self.spin_episode = QSpinBox()
        self.spin_episode.setRange(1, 9999)

        grid.addWidget(QLabel("Titolo"), 0, 0)
        grid.addWidget(self.edit_title, 0, 1, 1, 3)
        grid.addWidget(QLabel("Serie"), 1, 0)
        grid.addWidget(self.edit_series, 1, 1, 1, 3)
        grid.addWidget(QLabel("Stagione"), 2, 0)
        grid.addWidget(self.spin_season, 2, 1)
        grid.addWidget(QLabel("Episodio"), 2, 2)
        grid.addWidget(self.spin_episode, 2, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        box_lay.addLayout(grid)

        hint = QLabel("Per un film vengono usati solo il titolo e i TAG.")
        hint.setObjectName("Muted")
        box_lay.addWidget(hint)
        root.addWidget(box)

        # ------------------------------------------------------------ copertina
        cover_box = QGroupBox("COPERTINA")
        cover_lay = QHBoxLayout(cover_box)
        cover_lay.setSpacing(16)

        self.cover_preview = QLabel("Nessuna\ncopertina")
        self.cover_preview.setObjectName("CoverPreview")
        self.cover_preview.setFixedSize(104, 150)
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_preview.setWordWrap(True)
        cover_lay.addWidget(self.cover_preview)

        cover_side = QVBoxLayout()
        cover_side.setSpacing(8)
        self.cover_target = QLabel("")
        self.cover_target.setWordWrap(True)
        cover_side.addWidget(self.cover_target)

        cover_buttons = QHBoxLayout()
        cover_buttons.setSpacing(8)
        self.btn_choose_cover = QPushButton("🖼  Scegli file…")
        self.btn_choose_cover.clicked.connect(self._choose_cover)
        self.btn_online_cover = QPushButton("🌐  Cerca online")
        self.btn_online_cover.setObjectName("Ghost")
        self.btn_online_cover.setToolTip("Cerca la copertina online per questo film o questa serie")
        self.btn_online_cover.clicked.connect(self._search_online_cover)
        self.btn_remove_cover = QPushButton("Rimuovi")
        self.btn_remove_cover.setObjectName("Ghost")
        self.btn_remove_cover.clicked.connect(self._remove_cover)
        cover_buttons.addWidget(self.btn_choose_cover)
        cover_buttons.addWidget(self.btn_online_cover)
        cover_buttons.addWidget(self.btn_remove_cover)
        cover_buttons.addStretch()
        cover_side.addLayout(cover_buttons)

        cover_hint = QLabel(
            "Per una serie la copertina è condivisa da tutti gli episodi. "
            "L'immagine viene copiata nella cartella «covers» accanto al file di configurazione."
        )
        cover_hint.setObjectName("Muted")
        cover_hint.setWordWrap(True)
        cover_side.addWidget(cover_hint)
        cover_side.addStretch()
        cover_lay.addLayout(cover_side, 1)
        root.addWidget(cover_box)

        # ------------------------------------------------------------------ TAG
        tag_box = QGroupBox("TAG")
        tag_lay = QVBoxLayout(tag_box)
        tag_lay.setSpacing(10)

        self.tag_list = QListWidget()
        self.tag_list.setFixedHeight(108)
        self.tag_list.setAlternatingRowColors(False)
        tag_lay.addWidget(self.tag_list)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.edit_tag = QLineEdit()
        self.edit_tag.setPlaceholderText("Nuovo TAG (invio per aggiungere)")
        completer = QCompleter(self.manager.all_tags(), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.edit_tag.setCompleter(completer)
        self.btn_add_tag = QPushButton("Aggiungi")
        self.btn_add_tag.clicked.connect(self._add_tag)
        self.btn_remove_tag = QPushButton("Rimuovi")
        self.btn_remove_tag.setObjectName("Ghost")
        self.btn_remove_tag.clicked.connect(self._remove_tag)
        add_row.addWidget(self.edit_tag, 1)
        add_row.addWidget(self.btn_add_tag)
        add_row.addWidget(self.btn_remove_tag)
        tag_lay.addLayout(add_row)

        tag_hint = QLabel("I TAG sono salvati nel file di configurazione e servono anche per filtrare la libreria.")
        tag_hint.setObjectName("Muted")
        tag_hint.setWordWrap(True)
        tag_lay.addWidget(tag_hint)
        root.addWidget(tag_box)

        root.addStretch()

        # ---------------------------------------------------------------- pulsanti
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #232d39;")
        root.addWidget(line)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Annulla")
        btn_cancel.setObjectName("Ghost")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Salva")
        btn_save.setObjectName("Primary")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self.accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_save)
        root.addLayout(buttons)

        self.radio_film.toggled.connect(self._update_kind_fields)
        self.edit_tag.returnPressed.connect(self._add_tag)
        self.edit_title.textChanged.connect(self._target_changed)
        self.edit_series.textChanged.connect(self._target_changed)

    def _load(self, record):
        kind = record.get("kind", "film")
        self.radio_serie.setChecked(kind == "serie")
        self.radio_film.setChecked(kind != "serie")

        self.edit_title.setText(record.get("title", ""))
        self.edit_series.setText(record.get("series", ""))
        try:
            self.spin_season.setValue(int(record.get("season") or 1))
        except (TypeError, ValueError):
            self.spin_season.setValue(1)
        try:
            self.spin_episode.setValue(int(record.get("episode") or 1))
        except (TypeError, ValueError):
            self.spin_episode.setValue(1)

        for tag in record.get("tags", []):
            self.tag_list.addItem(tag)
        self._update_kind_fields()
        self._reload_cover_preview()

    # --------------------------------------------------------------- azioni
    def _update_kind_fields(self):
        is_series = self.radio_serie.isChecked()
        for widget in (self.edit_series, self.spin_season, self.spin_episode):
            widget.setEnabled(is_series)
        self._target_changed()

    def _cover_target(self):
        """Tipo e nome della raccolta a cui associare la copertina."""
        if self.radio_serie.isChecked():
            name = self.edit_series.text().strip() or self.record.get("series", "")
            return "serie", name
        name = self.edit_title.text().strip() or self.record.get("title", "")
        return "film", name

    def _target_changed(self):
        kind, name = self._cover_target()
        if kind == "serie":
            self.cover_target.setText(
                f"Copertina della serie «{name or 'senza nome'}»"
            )
        else:
            self.cover_target.setText(
                f"Copertina del film «{name or 'senza nome'}»"
            )
        if self._cover_source is None and not self._cover_removed:
            self._reload_cover_preview()

    def _reload_cover_preview(self):
        kind, name = self._cover_target()
        self._cover_path = self.manager.get_cover(kind, name) if name else None
        self._refresh_cover_preview()

    def _refresh_cover_preview(self):
        path = self._cover_source or self._cover_path
        if path and not self._cover_removed:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.cover_preview.setPixmap(
                    pixmap.scaled(
                        96,
                        142,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.cover_preview.setText("")
                self.btn_remove_cover.setEnabled(True)
                return
        self.cover_preview.setPixmap(QPixmap())
        self.cover_preview.setText("Nessuna\ncopertina")
        self.btn_remove_cover.setEnabled(False)

    def _choose_cover(self):
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Scegli la copertina",
            "",
            "Immagini (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;Tutti i file (*.*)",
        )
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.warning(
                self, "Copertina non valida", "Il file scelto non è un'immagine leggibile."
            )
            return
        self._cleanup_temp()
        self._cover_source = os.path.normpath(path)
        self._cover_temp = False
        self._cover_removed = False
        self._refresh_cover_preview()

    def _search_online_cover(self):
        kind, name = self._cover_target()
        if not name:
            QMessageBox.information(
                self,
                "Copertina online",
                "Inserisci prima il titolo del film o il nome della serie.",
            )
            return
        dialog = OnlineCoverDialog(
            self.manager,
            kind,
            name,
            self,
            query=name,
            auto=False,
            apply_on_accept=False,
        )
        if dialog.exec() and dialog.cover_source:
            self._cleanup_temp()
            self._cover_source = dialog.cover_source
            self._cover_temp = True
            self._cover_removed = False
            self._cover_path = None
            self._refresh_cover_preview()

    def _cleanup_temp(self):
        if self._cover_temp and self._cover_source:
            try:
                os.remove(self._cover_source)
            except OSError:
                pass
        if self._cover_temp:
            self._cover_source = None
            self._cover_temp = False

    def _remove_cover(self):
        self._cleanup_temp()
        self._cover_source = None
        self._cover_removed = True
        self._cover_path = None
        self._refresh_cover_preview()

    def done(self, result):
        if result != QDialog.DialogCode.Accepted:
            self._cleanup_temp()
        super().done(result)

    def _add_tag(self):
        raw = self.edit_tag.text()
        if not raw.strip():
            return
        existing = {
            self.tag_list.item(i).text().casefold()
            for i in range(self.tag_list.count())
        }
        for part in raw.replace(";", ",").split(","):
            tag = part.strip()
            if tag and tag.casefold() not in existing:
                self.tag_list.addItem(tag)
                existing.add(tag.casefold())
        self.edit_tag.clear()
        self.edit_tag.setFocus()

    def _remove_tag(self):
        row = self.tag_list.currentRow()
        if row >= 0:
            self.tag_list.takeItem(row)

    def tags(self):
        return [self.tag_list.item(i).text() for i in range(self.tag_list.count())]

    def result_data(self):
        is_series = self.radio_serie.isChecked()
        title = self.edit_title.text().strip()
        data = {
            "kind": "serie" if is_series else "film",
            "title": title or None,
            "tags": self.tags(),
        }
        if is_series:
            series = self.edit_series.text().strip()
            data["series"] = series or None
            data["season"] = str(self.spin_season.value())
            data["episode"] = str(self.spin_episode.value())
        else:
            data["series"] = None
            data["season"] = None
            data["episode"] = None

        kind, name = self._cover_target()
        data["_cover"] = {
            "source": self._cover_source,
            "remove": self._cover_removed,
            "temp": self._cover_temp,
            "kind": kind,
            "name": name,
        }
        return data
