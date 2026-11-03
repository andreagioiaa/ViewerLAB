"""Gestione dei link salvati e rigenerazione dei flussi scaduti."""

from __future__ import annotations

import datetime as dt
import uuid
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from async_tasks import AsyncOperation
from vistoflow_online import OnlineService, PlayRequest

KIND_LABELS = {
    "auto": "Automatico",
    "page": "Pagina da risolvere",
    "stream": "Flusso diretto",
}


def _default_title(url: str) -> str:
    parsed = urlparse(url)
    name = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    return name or parsed.netloc or "Link"


def _valid_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not host:
        return False
    # Evita valori come "https://streaming-community" senza dominio/TLD.
    return "." in host or host == "localhost" or ":" in host


def _load_links(manager) -> list[dict]:
    config = manager.data.setdefault("online", {})
    if not isinstance(config, dict):
        config = {}
        manager.data["online"] = config
    links = config.get("saved_links")
    if not isinstance(links, list):
        links = []
        config["saved_links"] = links
    return [item for item in links if isinstance(item, dict)]


def _save_links(manager, links: list[dict]) -> None:
    config = manager.data.setdefault("online", {})
    if not isinstance(config, dict):
        config = {}
        manager.data["online"] = config
    config["saved_links"] = links
    manager.save_config()


class LinkEditDialog(QDialog):
    """Editor di un singolo link salvato."""

    def __init__(self, link: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modifica link" if link else "Nuovo link")
        self.setMinimumWidth(560)
        self._link = dict(link or {})
        self._result: dict | None = None

        form = QFormLayout()
        form.setSpacing(10)

        self.title_edit = QLineEdit(self._link.get("title", ""))
        self.title_edit.setPlaceholderText("Es. Film, serie o nome del canale")
        form.addRow("Titolo", self.title_edit)

        self.url_edit = QLineEdit(self._link.get("url", ""))
        self.url_edit.setPlaceholderText(
            "https://sito.example/pagina-oppure-video.m3u8"
        )
        form.addRow("URL", self.url_edit)

        self.kind_combo = QComboBox()
        for kind, label in KIND_LABELS.items():
            self.kind_combo.addItem(label, kind)
        current_kind = self._link.get("kind", "auto")
        index = self.kind_combo.findData(current_kind)
        self.kind_combo.setCurrentIndex(max(index, 0))
        form.addRow("Tipo", self.kind_combo)

        self.source_edit = QLineEdit(self._link.get("source_url", ""))
        self.source_edit.setPlaceholderText(
            "Solo per flussi diretti: pagina che contiene il player"
        )
        form.addRow("Pagina sorgente", self.source_edit)

        self.referer_edit = QLineEdit(self._link.get("referer", ""))
        self.referer_edit.setPlaceholderText(
            "Opzionale: Referer richiesto dal server"
        )
        form.addRow("Referer", self.referer_edit)

        self.user_agent_edit = QLineEdit(self._link.get("user_agent", ""))
        self.user_agent_edit.setPlaceholderText(
            "Opzionale: User-Agent personalizzato"
        )
        form.addRow("User-Agent", self.user_agent_edit)

        hint = QLabel(
            "Se il link è una pagina con il player, scegli «Pagina da risolvere» "
            "o «Automatico»: il campo Pagina sorgente non serve. Se è già un "
            "flusso .m3u8/.mp4, scegli «Flusso diretto» e indica una pagina "
            "sorgente completa (es. https://sito.example/titolo) per rigenerarlo."
        )
        hint.setWordWrap(True)
        hint.setObjectName("Muted")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def _accept(self):
        url = self.url_edit.text().strip()
        if not _valid_http_url(url):
            QMessageBox.warning(
                self,
                "Link non valido",
                "Inserisci un URL completo che inizi con http:// o https://.",
            )
            return
        source_url = self.source_edit.text().strip()
        if source_url and not _valid_http_url(source_url):
            QMessageBox.warning(
                self,
                "Pagina sorgente non valida",
                "La pagina sorgente deve iniziare con http:// o https://.",
            )
            return

        title = self.title_edit.text().strip() or _default_title(url)
        link = dict(self._link)
        link.update(
            {
                "id": link.get("id") or uuid.uuid4().hex,
                "title": title,
                "url": url,
                "kind": self.kind_combo.currentData(),
                "source_url": source_url,
                "referer": self.referer_edit.text().strip(),
                "user_agent": self.user_agent_edit.text().strip(),
            }
        )
        self._result = link
        self.accept()

    @property
    def link(self) -> dict | None:
        return self._result


class SavedLinksDialog(QDialog):
    """Elenco persistente dei link, con aggiornamento e riproduzione."""

    play_requested = pyqtSignal(object)
    browser_requested = pyqtSignal(str)

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.links = _load_links(manager)
        self._workers: set[AsyncOperation] = set()
        self._busy = False

        self.setWindowTitle("I miei link · VistoFlow Pro")
        self.resize(820, 520)

        title = QLabel("🔗  I miei link")
        title.setObjectName("DialogTitle")
        subtitle = QLabel(
            "Salva una pagina o un flusso. Se il link scade, VistoFlow prova "
            "a rileggere la pagina sorgente e a ottenere un flusso nuovo."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("Muted")

        self.links_list = QListWidget()
        self.links_list.setObjectName("SavedLinks")
        self.links_list.itemDoubleClicked.connect(lambda _item: self._play_selected())
        self.links_list.currentItemChanged.connect(lambda *_args: self._update_buttons())

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("Muted")

        row_edit = QHBoxLayout()
        self.btn_add = QPushButton("＋  Aggiungi")
        self.btn_edit = QPushButton("✎  Modifica")
        self.btn_remove = QPushButton("🗑  Rimuovi")
        row_edit.addWidget(self.btn_add)
        row_edit.addWidget(self.btn_edit)
        row_edit.addWidget(self.btn_remove)
        row_edit.addStretch(1)

        row_actions = QHBoxLayout()
        self.btn_update = QPushButton("⟳  Aggiorna link")
        self.btn_browser = QPushButton("🌐  Apri pagina")
        self.btn_browser.setObjectName("Ghost")
        self.btn_browser.setToolTip(
            "Apri il link nel browser integrato, senza estrarre il flusso"
        )
        self.btn_play = QPushButton("▶  Riproduci")
        self.btn_play.setObjectName("Primary")
        self.btn_close = QPushButton("Chiudi")
        row_actions.addWidget(self.btn_update)
        row_actions.addWidget(self.btn_browser)
        row_actions.addWidget(self.btn_play)
        row_actions.addStretch(1)
        row_actions.addWidget(self.btn_close)

        self.btn_add.clicked.connect(self._add_link)
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_update.clicked.connect(self._update_selected)
        self.btn_browser.clicked.connect(self._browse_selected)
        self.btn_play.clicked.connect(self._play_selected)
        self.btn_close.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.links_list, 1)
        layout.addWidget(self.status_label)
        layout.addLayout(row_edit)
        layout.addLayout(row_actions)

        self._refresh_list()
        self._update_buttons()

    # ------------------------------------------------------------------ lista
    def _refresh_list(self, select_id: str | None = None):
        self.links_list.blockSignals(True)
        self.links_list.clear()
        selected_row = -1
        for row, link in enumerate(self.links):
            kind = KIND_LABELS.get(link.get("kind", "auto"), "Automatico")
            item = QListWidgetItem(f"{link.get('title') or 'Senza titolo'}\n{link.get('url', '')}")
            item.setData(Qt.ItemDataRole.UserRole, link.get("id"))
            tip = [f"Tipo: {kind}", f"URL: {link.get('url', '')}"]
            if link.get("source_url"):
                tip.append(f"Pagina sorgente: {link['source_url']}")
            if link.get("last_resolved_at"):
                tip.append(f"Ultimo aggiornamento: {link['last_resolved_at']}")
            item.setToolTip("\n".join(tip))
            self.links_list.addItem(item)
            if select_id and link.get("id") == select_id:
                selected_row = row
        self.links_list.blockSignals(False)
        if selected_row >= 0:
            self.links_list.setCurrentRow(selected_row)
        elif self.links_list.count():
            self.links_list.setCurrentRow(0)
        self._update_buttons()

    def _selected_link(self) -> dict | None:
        item = self.links_list.currentItem()
        if item is None:
            return None
        link_id = item.data(Qt.ItemDataRole.UserRole)
        return next((link for link in self.links if link.get("id") == link_id), None)

    def _update_buttons(self):
        selected = self._selected_link() is not None
        enabled = selected and not self._busy
        self.btn_edit.setEnabled(enabled)
        self.btn_remove.setEnabled(enabled)
        self.btn_update.setEnabled(enabled)
        self.btn_browser.setEnabled(enabled)
        self.btn_play.setEnabled(enabled)
        self.btn_add.setEnabled(not self._busy)
        self.links_list.setEnabled(not self._busy)
        if not self.links and not self._busy:
            self.status_label.setText(
                "Nessun link salvato. Usa «Aggiungi» per iniziare."
            )

    def _persist(self):
        _save_links(self.manager, self.links)

    def _set_busy(self, busy: bool, message: str = ""):
        self._busy = busy
        if message:
            self.status_label.setText(message)
        self._update_buttons()

    # ------------------------------------------------------------------ azioni
    def _add_link(self):
        dialog = LinkEditDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.link is None:
            return
        self.links.append(dialog.link)
        self._persist()
        self._refresh_list(dialog.link["id"])
        self.status_label.setText("Link aggiunto.")

    def _edit_selected(self):
        link = self._selected_link()
        if link is None:
            return
        dialog = LinkEditDialog(link, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.link is None:
            return
        link.update(dialog.link)
        self._persist()
        self._refresh_list(link.get("id"))
        self.status_label.setText("Link aggiornato.")

    def _remove_selected(self):
        link = self._selected_link()
        if link is None:
            return
        answer = QMessageBox.question(
            self,
            "Rimuovi link",
            f"Rimuovere «{link.get('title') or 'Senza titolo'}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.links = [item for item in self.links if item is not link]
        self._persist()
        self._refresh_list()
        self.status_label.setText("Link rimosso.")

    def _play_selected(self):
        link = self._selected_link()
        if link is not None:
            self._resolve(link, play=True)

    def _update_selected(self):
        link = self._selected_link()
        if link is not None:
            self._resolve(link, play=False)

    def _browse_selected(self):
        link = self._selected_link()
        if link is None:
            return
        url = link.get("url", "").strip()
        if not _valid_http_url(url):
            QMessageBox.warning(self, "Link non valido", "L'URL salvato non è valido.")
            return
        self.status_label.setText(
            "Apertura nel browser integrato. La riproduzione resta a carico del sito."
        )
        self.browser_requested.emit(url)

    # --------------------------------------------------------------- resolver
    def _resolve(self, link: dict, *, play: bool):
        if self._busy:
            return
        url = link.get("url", "").strip()
        if not _valid_http_url(url):
            QMessageBox.warning(self, "Link non valido", "L'URL salvato non è valido.")
            return

        raw_source = link.get("source_url", "").strip()
        source_url = raw_source if _valid_http_url(raw_source) else ""
        notice = ""
        if raw_source and not source_url:
            notice = "Pagina sorgente non valida: uso l'URL principale. "

        kind = link.get("kind", "auto")
        looks_direct = urlparse(url).path.lower().endswith((".m3u8", ".mp4"))
        # Per una pagina il link principale è già la sorgente. La pagina
        # sorgente separata serve solo per un flusso diretto da rigenerare.
        use_source = bool(source_url) and (kind == "stream" or looks_direct)
        target = source_url if use_source else url
        referer = link.get("referer", "").strip() or None
        user_agent = link.get("user_agent", "").strip() or None
        if use_source and not referer:
            referer = source_url

        self._set_busy(
            True,
            notice
            + (
                "Aggiornamento e risoluzione del link…"
                if play
                else "Aggiornamento del link…"
            ),
        )
        service = OnlineService(self._online_config())
        worker = AsyncOperation(
            lambda: service.resolve_url(
                target,
                referer=referer,
                user_agent=user_agent,
            ),
            parent=self,
        )
        self._workers.add(worker)
        worker.completed.connect(
            lambda outcome: self._on_resolved(
                outcome, link, play, target, referer, user_agent
            )
        )
        worker.failed.connect(self._on_failed)
        worker.completed.connect(lambda _outcome, w=worker: self._finish_worker(w))
        worker.failed.connect(lambda _message, w=worker: self._finish_worker(w))
        worker.start()

    def _online_config(self) -> dict:
        config = self.manager.data.get("online")
        return config if isinstance(config, dict) else {}

    def _on_resolved(
        self,
        outcome,
        link: dict,
        play: bool,
        target: str,
        referer: str | None,
        user_agent: str | None,
    ):
        self._set_busy(False)
        if not outcome.streams:
            errors = list(outcome.errors.values())[:4]
            detail = "\n".join(f"• {item}" for item in errors)
            self.status_label.setText(
                "Nessun flusso trovato."
                + (f"\n{detail}" if detail else " Controlla il link o la pagina sorgente.")
            )
            if play:
                self.status_label.setText(
                    "Host protetto da Cloudflare/JS. Apertura automatica nel browser per catturare il flusso .m3u8…"
                )
                self.browser_requested.emit(target)
            return

        stream = outcome.streams[0]
        link["last_stream_url"] = stream.url
        link["last_resolved_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        link["last_resolver"] = stream.resolver_name
        self._persist()
        self._refresh_list(link.get("id"))
        self.status_label.setText(
            f"Flusso trovato ({stream.resolver_name})."
            if play
            else f"Link aggiornato: {len(outcome.streams)} flusso/i disponibile/i."
        )

        if not play:
            return

        # Un URL di pagina può essere risolto di nuovo in caso di errore VLC.
        # Per un flusso diretto senza pagina sorgente non c'è nulla da
        # rigenerare, quindi non lo pubblichiamo come sorgente di refresh.
        target_looks_direct = urlparse(target).path.lower().endswith(
            (".m3u8", ".mp4")
        )
        refresh_url = None if target_looks_direct else target
        request = PlayRequest(
            stream=stream,
            title=link.get("title") or _default_title(target),
            source_url=refresh_url,
            referer=referer,
            headers=dict(stream.headers),
            user_agent=user_agent,
        )
        self.play_requested.emit(request)
        self.hide()

    def _on_failed(self, message: str):
        self._set_busy(False)
        self.status_label.setText(f"Errore durante l'aggiornamento: {message}")

    def _finish_worker(self, worker: AsyncOperation):
        self._workers.discard(worker)
        worker.deleteLater()
