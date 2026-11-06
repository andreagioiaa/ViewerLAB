"""Finestre di dialogo per la configurazione delle fonti."""

from __future__ import annotations

import re
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .models import Source

_KIND_LABELS = (
    ("catalog", "Catalogo JSON"),
    ("json_api", "API di ricerca JSON"),
    ("site", "Sito web (HTML)"),
    ("direct", "Link diretto"),
)


def slugify(text: str, fallback: str = "fonte") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    return (slug or fallback)[:40]


def parse_headers(text: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"Intestazione non valida (manca ':'): {line!r}")
        name, value = line.split(":", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            raise ValueError(f"Intestazione senza nome: {line!r}")
        headers[name] = value
    return headers


def format_headers(headers: dict[str, str]) -> str:
    return "\n".join(f"{name}: {value}" for name, value in headers.items())


class SourceEditorDialog(QDialog):
    """Crea o modifica una fonte: catalogo, API JSON, sito web o link diretto."""

    def __init__(
        self,
        parent: QWidget | None = None,
        source: Source | None = None,
        kind: str = "catalog",
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._is_new = source is None
        self.setWindowTitle("Modifica fonte" if source else "Aggiungi fonte")
        self.setMinimumWidth(560)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Es. La mia mediateca")

        self.kind_combo = QComboBox()
        for value, label in _KIND_LABELS:
            self.kind_combo.addItem(label, value)
        initial_kind = source.kind if source else kind
        index = self.kind_combo.findData(initial_kind)
        self.kind_combo.setCurrentIndex(index if index >= 0 else 0)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Titolo mostrato nei risultati")

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://... oppure percorso locale del catalogo")

        self.search_url_edit = QLineEdit()
        self.search_url_edit.setPlaceholderText("https://host/api/cerca?q={query}")

        self.year_spin = QSpinBox()
        self.year_spin.setRange(0, 2200)
        self.year_spin.setSpecialValueText("—")
        self.year_spin.setValue(0)

        self.referer_edit = QLineEdit()
        self.referer_edit.setPlaceholderText("Opzionale: Referer da inviare al server")

        self.ua_edit = QLineEdit()
        self.ua_edit.setPlaceholderText("Opzionale: User-Agent personalizzato")

        self.headers_edit = QPlainTextEdit()
        self.headers_edit.setPlaceholderText(
            "Intestazioni HTTP aggiuntive, una per riga:\nNome: valore"
        )
        self.headers_edit.setFixedHeight(90)

        self.enabled_check = QCheckBox("Fonte attiva")
        self.enabled_check.setChecked(True)

        self.item_selector_edit = QLineEdit()
        self.item_selector_edit.setPlaceholderText("Es. .card, article, li.result")
        self.title_selector_edit = QLineEdit()
        self.title_selector_edit.setPlaceholderText("Es. h3 a, .titolo")
        self.link_selector_edit = QLineEdit()
        self.link_selector_edit.setPlaceholderText("Es. a[href]")
        self.cover_selector_edit = QLineEdit()
        self.cover_selector_edit.setPlaceholderText("Es. img")

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #8a93a5;")

        self.form = QFormLayout()
        self.form.addRow("Nome", self.name_edit)
        self.form.addRow("Tipo", self.kind_combo)
        self.form.addRow("Titolo", self.title_edit)
        self.form.addRow("URL", self.url_edit)
        self.form.addRow("URL di ricerca", self.search_url_edit)
        self.form.addRow("Selettore risultati", self.item_selector_edit)
        self.form.addRow("Selettore titolo", self.title_selector_edit)
        self.form.addRow("Selettore link", self.link_selector_edit)
        self.form.addRow("Selettore copertina", self.cover_selector_edit)
        self.form.addRow("Anno", self.year_spin)
        self.form.addRow("Referer", self.referer_edit)
        self.form.addRow("User-Agent", self.ua_edit)
        self.form.addRow("Intestazioni", self.headers_edit)
        self.form.addRow("", self.enabled_check)
        self.form.addRow("", self.hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Salva")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annulla")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(self.form)
        layout.addWidget(buttons)

        self.kind_combo.currentIndexChanged.connect(self._sync_visibility)
        self._sync_visibility()

        if source is not None:
            self.name_edit.setText(source.name)
            self.title_edit.setText(source.title)
            self.url_edit.setText(source.url)
            self.search_url_edit.setText(source.search_url)
            self.year_spin.setValue(source.year or 0)
            self.referer_edit.setText(source.referer)
            self.ua_edit.setText(source.user_agent)
            self.headers_edit.setPlainText(format_headers(source.headers))
            self.item_selector_edit.setText(source.selectors.get("item", ""))
            self.title_selector_edit.setText(source.selectors.get("title", ""))
            self.link_selector_edit.setText(source.selectors.get("link", ""))
            self.cover_selector_edit.setText(source.selectors.get("cover", ""))
            self.enabled_check.setChecked(source.enabled)

    # ------------------------------------------------------------------ UI

    def _kind(self) -> str:
        return str(self.kind_combo.currentData())

    def _sync_visibility(self) -> None:
        kind = self._kind()
        is_direct = kind == "direct"
        is_api = kind == "json_api"
        is_site = kind == "site"

        self.form.setRowVisible(self.title_edit, is_direct)
        self.form.setRowVisible(self.search_url_edit, is_api or is_site)
        self.form.setRowVisible(self.item_selector_edit, is_site)
        self.form.setRowVisible(self.title_selector_edit, is_site)
        self.form.setRowVisible(self.link_selector_edit, is_site)
        self.form.setRowVisible(self.cover_selector_edit, is_site)
        self.form.setRowVisible(self.year_spin, is_direct)
        self.form.setRowVisible(self.url_edit, not is_api)
        self.form.setRowVisible(self.name_edit, True)

        if is_direct:
            self.url_edit.setPlaceholderText("https://host/video.mp4 oppure .../stream.m3u8")
            self.hint.setText(
                "Il link diretto punta a un file o manifest che hai il diritto di riprodurre. "
                "Nessun DRM viene aggirato."
            )
        elif is_api:
            self.search_url_edit.setPlaceholderText("https://host/api/cerca?q={query}")
            self.hint.setText(
                "L'API deve restituire JSON con una lista 'items'. "
                "Usa {query} nell'URL per passare il testo cercato."
            )
        elif is_site:
            self.url_edit.setPlaceholderText("https://www.esempio.it")
            self.search_url_edit.setPlaceholderText(
                "Opzionale: https://www.esempio.it/cerca?q={query}"
            )
            self.hint.setText(
                "Inserisci la home del sito: ViewerLAB cerca i contenuti e ricava il flusso "
                "dalla pagina del titolo. Se il sito non espone un modulo di ricerca, indica "
                "l'URL di ricerca con {query}. I selettori CSS sono opzionali. "
                "Nessun JavaScript viene eseguito e nessun DRM viene aggirato."
            )
        else:
            self.url_edit.setPlaceholderText(
                "https://host/catalogo.json oppure C:\\percorso\\catalogo.json"
            )
            self.hint.setText(
                "Il catalogo è un JSON con 'items'; ogni elemento ha 'title' e 'url' "
                "(o 'streams'). Sono supportati URL http/https e file locali."
            )

    # --------------------------------------------------------------- esito

    def _on_accept(self) -> None:
        try:
            source = self._build_source()
            source.validate()
        except ValueError as error:
            QMessageBox.warning(self, "Dati non validi", str(error))
            return
        self._result = source
        self.accept()

    def _build_source(self) -> Source:
        kind = self._kind()
        name = self.name_edit.text().strip()
        if self._source is not None:
            source_id = self._source.id
        else:
            source_id = f"{slugify(name)}-{uuid.uuid4().hex[:6]}"
        selectors: dict[str, str] = {}
        if kind == "site":
            for key, field in (
                ("item", self.item_selector_edit),
                ("title", self.title_selector_edit),
                ("link", self.link_selector_edit),
                ("cover", self.cover_selector_edit),
            ):
                value = field.text().strip()
                if value:
                    selectors[key] = value
        return Source(
            id=source_id,
            name=name,
            kind=kind,  # type: ignore[arg-type]
            url=self.url_edit.text().strip(),
            search_url=self.search_url_edit.text().strip(),
            title=self.title_edit.text().strip(),
            year=self.year_spin.value() or None,
            enabled=self.enabled_check.isChecked(),
            headers=parse_headers(self.headers_edit.toPlainText()),
            referer=self.referer_edit.text().strip(),
            user_agent=self.ua_edit.text().strip(),
            selectors=selectors,
        )

    def edited_source(self) -> Source:
        return self._result

    def showEvent(self, event) -> None:  # noqa: N802 - API Qt
        super().showEvent(event)
        self.name_edit.setFocus(Qt.FocusReason.OtherFocusReason)


class DirectLinkDialog(QDialog):
    """Inserimento rapido di un singolo flusso diretto."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aggiungi link diretto")
        self.setMinimumWidth(520)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Titolo del contenuto")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://host/video.mp4 oppure .../stream.m3u8")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Facoltativo: nome della fonte")
        self.referer_edit = QLineEdit()
        self.referer_edit.setPlaceholderText("Facoltativo: Referer")

        form = QFormLayout()
        form.addRow("Titolo", self.title_edit)
        form.addRow("URL del flusso", self.url_edit)
        form.addRow("Etichetta fonte", self.name_edit)
        form.addRow("Referer", self.referer_edit)

        note = QLabel(
            "Il flusso verrà verificato prima della riproduzione. "
            "Usa solo contenuti che hai il diritto di guardare."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a93a5;")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Aggiungi")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annulla")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        title = self.title_edit.text().strip()
        url = self.url_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Dati non validi", "Il titolo è obbligatorio.")
            return
        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(
                self, "Dati non validi", "Il link deve iniziare con http:// o https://."
            )
            return
        label = self.name_edit.text().strip() or "Link diretti"
        self._result = Source(
            id=f"direct-{uuid.uuid4().hex[:8]}",
            name=label,
            kind="direct",
            url=url,
            title=title,
            referer=self.referer_edit.text().strip(),
        )
        self.accept()

    def added_source(self) -> Source:
        return self._result
