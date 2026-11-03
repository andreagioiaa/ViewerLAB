"""PyToExe Studio - GUI per creare eseguibili (.exe) da progetti Python.

Richiede PyInstaller (l'app propone di installarlo se manca):
    python -m pip install pyinstaller

Avvio:
    python build_exe.py
"""

import importlib.util
import os
import shlex
import shutil
import sys

from PyQt6.QtCore import (
    QPointF, QProcess, QProcessEnvironment, QRectF, QSettings, Qt, QTimer, QUrl,
)
from PyQt6.QtGui import (
    QColor, QDesktopServices, QIcon, QPainter, QPalette, QPixmap, QPolygonF,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QStyleFactory, QVBoxLayout, QWidget,
)

APP_NAME = "PyToExe Studio"
DATA_SEP = ";" if os.name == "nt" else ":"
EXE_SUFFIX = ".exe" if os.name == "nt" else ""


def make_icon(size=64):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#2ecc71"))
    painter.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), size * 0.24, size * 0.24)
    painter.setBrush(QColor("#07130b"))
    triangle = QPolygonF([
        QPointF(size * 0.38, size * 0.30),
        QPointF(size * 0.38, size * 0.70),
        QPointF(size * 0.72, size * 0.50),
    ])
    painter.drawPolygon(triangle)
    painter.setBrush(QColor("#07130b"))
    painter.drawRect(QRectF(size * 0.22, size * 0.46, size * 0.12, size * 0.08))
    painter.end()
    return QIcon(pixmap)


def apply_theme(app):
    app.setStyle(QStyleFactory.create("Fusion"))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#0d1117"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e6ebf2"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#161d26"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e6ebf2"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#1a222c"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e6ebf2"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2ecc71"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#07130b"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#5b6575"))
    app.setPalette(palette)
    app.setStyleSheet(QSS)


QSS = """
* { font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; }
QMainWindow, QDialog { background: #0d1117; }
QWidget { color: #e6ebf2; }
QFrame#TopBar { background: #10151c; border-bottom: 1px solid #202833; }
QFrame#LogPanel { background: #10151c; border: 1px solid #202833; border-radius: 10px; }
QLabel { background: transparent; }
QLabel#AppTitle { font-size: 20px; font-weight: 700; color: #ffffff; }
QLabel#AppSubtitle { color: #7d8797; font-size: 11px; }
QLabel#SectionTitle { color: #7d8797; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#Muted { color: #7d8797; }
QLabel#CommandLabel {
    background: #0b0f14;
    border: 1px solid #232d39;
    border-radius: 7px;
    padding: 8px 10px;
    color: #93a1b3;
    font-family: "Consolas", monospace;
    font-size: 11px;
}
QLineEdit#CommandLine {
    background: #0b0f14;
    border: 1px solid #232d39;
    border-radius: 7px;
    padding: 8px 10px;
    color: #93a1b3;
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 11px;
}
QLineEdit, QComboBox {
    background: #161d26;
    border: 1px solid #27313d;
    border-radius: 8px;
    padding: 8px 10px;
    color: #e6ebf2;
    selection-background-color: #2ecc71;
    selection-color: #07130b;
}
QLineEdit:focus, QComboBox:focus { border-color: #2ecc71; }
QLineEdit:read-only { color: #9aa5b4; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: #161d26;
    border: 1px solid #27313d;
    selection-background-color: #1c3a2a;
    selection-color: #fff;
    outline: none;
}
QPushButton {
    background: #1a222c;
    border: 1px solid #27313d;
    border-radius: 8px;
    padding: 8px 14px;
    color: #dfe6ee;
}
QPushButton:hover { background: #212c38; border-color: #354354; }
QPushButton:disabled { color: #55606f; background: #141a21; border-color: #1e2731; }
QPushButton#Primary { background: #2ecc71; border: none; color: #07130b; font-weight: 700; }
QPushButton#Primary:hover { background: #45d883; }
QPushButton#Primary:disabled { background: #20352a; color: #5c7d68; }
QPushButton#Ghost { background: transparent; border: 1px solid #27313d; }
QPushButton#Ghost:hover { background: #1a222c; }
QPushButton#Danger { background: transparent; border: 1px solid #6e2f2f; color: #ff9b9b; }
QPushButton#Danger:hover { background: #351b1b; }
QGroupBox {
    background: #11161d;
    border: 1px solid #232d39;
    border-radius: 10px;
    margin-top: 16px;
    padding: 16px 14px 14px 14px;
    font-weight: 600;
    color: #aab5c4;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #8b96a7;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QCheckBox { spacing: 8px; color: #cfd7e2; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #3a4656;
    border-radius: 4px;
    background: #161d26;
}
QCheckBox::indicator:hover { border-color: #2ecc71; }
QCheckBox::indicator:checked { background: #2ecc71; border-color: #2ecc71; }
QListWidget {
    background: #121821;
    border: 1px solid #232d39;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}
QListWidget::item { padding: 6px 8px; border-radius: 5px; color: #b9c4d2; }
QListWidget::item:selected { background: #1c3a2a; color: #fff; }
QPlainTextEdit {
    background: #0b0f14;
    border: none;
    border-radius: 8px;
    color: #c6d0dc;
    padding: 10px;
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 12px;
    selection-background-color: #2ecc71;
    selection-color: #07130b;
}
QProgressBar {
    background: #1a222c;
    border: none;
    border-radius: 4px;
    max-height: 8px;
    color: transparent;
}
QProgressBar::chunk { background: #2ecc71; border-radius: 4px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2a3542; min-height: 30px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: #3a4757; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #2a3542; min-width: 30px; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QToolTip {
    background: #1b222c;
    color: #e6ebf2;
    border: 1px solid #2b3542;
    padding: 6px;
    border-radius: 6px;
}
"""


def split_extra_args(text):
    """Divide una stringa di argomenti rispettando le virgolette."""
    if not text.strip():
        return []
    try:
        parts = shlex.split(text, posix=False)
    except ValueError:
        parts = text.split()
    cleaned = []
    for part in parts:
        if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'":
            part = part[1:-1]
        cleaned.append(part)
    return cleaned


def quote_command(arg):
    if not arg:
        return '""'
    if any(ch in arg for ch in " \t"):
        return f'"{arg}"'
    return arg


class BuilderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("VistoFlow", "PyToExe Studio")
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self._read_output)
        self.proc.finished.connect(self._process_finished)
        self.proc.errorOccurred.connect(self._process_error)

        self.mode = None                 # "check" | "install" | "build"
        self.process_running = False
        self.pyinstaller_ready = False
        self.pyinstaller_version = ""
        self._check_output = ""
        self._cancelled = False
        self._last_exe = ""
        self._last_output = ""
        self._last_work_dir = ""
        self._auto_name = ""
        self._auto_output = ""

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(1220, 820)
        self.setMinimumSize(980, 640)

        self._build_ui()
        self._restore_settings()
        QTimer.singleShot(300, self.check_pyinstaller)

    # ================================================================== UI
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        # ------------------------------------------------------------------ header
        header = QFrame()
        header.setObjectName("TopBar")
        header.setFixedHeight(74)
        header_lay = QHBoxLayout(header)
        header_lay.setContentsMargins(20, 12, 20, 12)
        header_lay.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(make_icon(38).pixmap(38, 38))
        header_lay.addWidget(icon_label)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("PyToExe <span style='color:#2ecc71'>Studio</span>")
        title.setObjectName("AppTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        subtitle = QLabel("Da progetto Python a eseguibile Windows, senza terminale")
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header_lay.addLayout(titles)
        header_lay.addStretch(1)

        self.status_chip = QLabel("PyInstaller: verifica…")
        self.status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_lay.addWidget(self.status_chip)

        self.btn_install = QPushButton("Installa PyInstaller")
        self.btn_install.setObjectName("Ghost")
        self.btn_install.clicked.connect(self.install_pyinstaller)
        header_lay.addWidget(self.btn_install)
        self._set_chip("Verifica PyInstaller…", "#1a222c", "#9aa5b4", "#2b3542")

        root.addWidget(header)

        # ------------------------------------------------------------------- body
        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(16, 16, 16, 16)
        body_lay.setSpacing(14)
        root.addWidget(body, 1)

        body_lay.addWidget(self._build_form(), 3)
        body_lay.addWidget(self._build_log_panel(), 2)

    def _build_form(self):
        wrapper = QWidget()
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(520)

        container = QWidget()
        scroll.setWidget(container)
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(4)

        # ---------------------------------------------------------------- sorgente
        source_box = QGroupBox("SORGENTE")
        source_lay = QVBoxLayout(source_box)
        source_lay.setSpacing(8)

        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("File .py oppure cartella del progetto")
        self.btn_source_file = QPushButton("File…")
        self.btn_source_file.clicked.connect(self.choose_source_file)
        self.btn_source_folder = QPushButton("Cartella…")
        self.btn_source_folder.clicked.connect(self.choose_source_folder)
        source_row.addWidget(self.source_edit, 1)
        source_row.addWidget(self.btn_source_file)
        source_row.addWidget(self.btn_source_folder)
        source_lay.addLayout(source_row)

        entry_row = QHBoxLayout()
        entry_row.setSpacing(8)
        entry_label = QLabel("File principale")
        entry_label.setObjectName("Muted")
        entry_label.setFixedWidth(88)
        self.entry_combo = QComboBox()
        self.entry_combo.currentIndexChanged.connect(self._on_entry_changed)
        entry_row.addWidget(entry_label)
        entry_row.addWidget(self.entry_combo, 1)
        source_lay.addLayout(entry_row)

        self.source_info = QLabel("Seleziona uno script o una cartella di progetto.")
        self.source_info.setObjectName("Muted")
        self.source_info.setWordWrap(True)
        source_lay.addWidget(self.source_info)
        lay.addWidget(source_box)

        # ------------------------------------------------------------------ output
        output_box = QGroupBox("OUTPUT")
        output_lay = QVBoxLayout(output_box)
        output_lay.setSpacing(8)

        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Cartella di destinazione dell'eseguibile")
        self.btn_output = QPushButton("Sfoglia…")
        self.btn_output.clicked.connect(self.choose_output_folder)
        out_row.addWidget(self.output_edit, 1)
        out_row.addWidget(self.btn_output)
        output_lay.addLayout(out_row)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_label = QLabel("Nome eseguibile")
        name_label.setObjectName("Muted")
        name_label.setFixedWidth(88)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nome del file .exe")
        name_row.addWidget(name_label)
        name_row.addWidget(self.name_edit, 1)
        output_lay.addLayout(name_row)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(8)
        icon_label = QLabel("Icona (.ico)")
        icon_label.setObjectName("Muted")
        icon_label.setFixedWidth(88)
        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText("Opzionale")
        self.btn_icon = QPushButton("Sfoglia…")
        self.btn_icon.clicked.connect(self.choose_icon)
        icon_row.addWidget(icon_label)
        icon_row.addWidget(self.icon_edit, 1)
        icon_row.addWidget(self.btn_icon)
        output_lay.addLayout(icon_row)

        checks = QHBoxLayout()
        checks.setSpacing(22)
        self.chk_onefile = QCheckBox("File unico (.exe)")
        self.chk_onefile.setChecked(True)
        self.chk_windowed = QCheckBox("Senza console")
        self.chk_clean = QCheckBox("Build pulita")
        self.chk_clean.setChecked(True)
        checks.addWidget(self.chk_onefile)
        checks.addWidget(self.chk_windowed)
        checks.addWidget(self.chk_clean)
        checks.addStretch()
        output_lay.addLayout(checks)
        lay.addWidget(output_box)

        # -------------------------------------------------------------- avanzate
        advanced_box = QGroupBox("OPZIONI AVANZATE")
        advanced_lay = QVBoxLayout(advanced_box)
        advanced_lay.setSpacing(8)

        hidden_label = QLabel("Import nascosti (separati da virgola)")
        hidden_label.setObjectName("Muted")
        self.hidden_edit = QLineEdit()
        self.hidden_edit.setPlaceholderText("es. PIL, numpy, requests")
        advanced_lay.addWidget(hidden_label)
        advanced_lay.addWidget(self.hidden_edit)

        data_label = QLabel("Dati aggiuntivi  (origine" + DATA_SEP + "destinazione)")
        data_label.setObjectName("Muted")
        advanced_lay.addWidget(data_label)

        data_row = QHBoxLayout()
        data_row.setSpacing(8)
        self.data_edit = QLineEdit()
        self.data_edit.setPlaceholderText(f"es. C:\\cartella{DATA_SEP}.")
        self.btn_data_file = QPushButton("File…")
        self.btn_data_file.clicked.connect(lambda: self._browse_data(False))
        self.btn_data_dir = QPushButton("Cartella…")
        self.btn_data_dir.clicked.connect(lambda: self._browse_data(True))
        self.btn_data_add = QPushButton("Aggiungi")
        self.btn_data_add.clicked.connect(self._add_data_item)
        data_row.addWidget(self.data_edit, 1)
        data_row.addWidget(self.btn_data_file)
        data_row.addWidget(self.btn_data_dir)
        data_row.addWidget(self.btn_data_add)
        advanced_lay.addLayout(data_row)

        self.data_list = QListWidget()
        self.data_list.setFixedHeight(76)
        advanced_lay.addWidget(self.data_list)
        data_actions = QHBoxLayout()
        data_actions.addStretch()
        self.btn_data_remove = QPushButton("Rimuovi selezionato")
        self.btn_data_remove.setObjectName("Ghost")
        self.btn_data_remove.clicked.connect(self._remove_data_item)
        data_actions.addWidget(self.btn_data_remove)
        advanced_lay.addLayout(data_actions)

        extra_label = QLabel("Argomenti extra PyInstaller")
        extra_label.setObjectName("Muted")
        self.extra_edit = QLineEdit()
        self.extra_edit.setPlaceholderText("es. --collect-all mypackage")
        advanced_lay.addWidget(extra_label)
        advanced_lay.addWidget(self.extra_edit)

        self.chk_clean_temp = QCheckBox("Rimuovi cartella temporanea di build al termine")
        self.chk_clean_temp.setChecked(True)
        advanced_lay.addWidget(self.chk_clean_temp)
        lay.addWidget(advanced_box)
        lay.addStretch()
        outer.addWidget(scroll, 1)

        # ------------------------------------------------------------- comando
        command_label = QLabel("COMANDO")
        command_label.setObjectName("SectionTitle")
        outer.addWidget(command_label)
        self.preview = QLineEdit()
        self.preview.setObjectName("CommandLine")
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Seleziona un sorgente per vedere il comando…")
        self.preview.setToolTip("Comando completo che verrà eseguito")
        outer.addWidget(self.preview)

        # ------------------------------------------------------------- pulsanti
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.btn_build = QPushButton("⚙  Crea eseguibile")
        self.btn_build.setObjectName("Primary")
        self.btn_build.setMinimumHeight(42)
        self.btn_build.clicked.connect(self.start_build)
        self.btn_cancel = QPushButton("Annulla")
        self.btn_cancel.setObjectName("Danger")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_process)
        self.btn_open_output = QPushButton("Apri cartella output")
        self.btn_open_output.setObjectName("Ghost")
        self.btn_open_output.clicked.connect(self.open_output_folder)
        buttons.addWidget(self.btn_build, 1)
        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_open_output)
        outer.addLayout(buttons)

        for widget in (
            self.source_edit, self.output_edit, self.name_edit, self.icon_edit,
            self.hidden_edit, self.data_edit, self.extra_edit,
        ):
            widget.textChanged.connect(self._update_preview)
        for widget in (self.chk_onefile, self.chk_windowed, self.chk_clean):
            widget.toggled.connect(self._update_preview)
        self.source_edit.editingFinished.connect(self._on_source_edited)
        return wrapper

    def _build_log_panel(self):
        panel = QFrame()
        panel.setObjectName("LogPanel")
        panel.setMinimumWidth(360)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("LOG DI BUILD")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()
        self.btn_clear_log = QPushButton("Pulisci")
        self.btn_clear_log.setObjectName("Ghost")
        self.btn_clear_log.setFixedHeight(28)
        self.btn_clear_log.clicked.connect(lambda: self.log.clear())
        header.addWidget(self.btn_clear_log)
        lay.addLayout(header)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText(
            "Qui compariranno i messaggi di PyInstaller…\n\n"
            "Suggerimento: se la build fallisce, controlla le ultime righe del log."
        )
        lay.addWidget(self.log, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        lay.addWidget(self.progress)

        self.status_label = QLabel("Pronto.")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        lay.addWidget(self.status_label)
        return panel

    # ============================================================== settings
    def _restore_settings(self):
        source = self.settings.value("source", "", type=str)
        if source:
            self._set_source(source)

        output = self.settings.value("output", "", type=str)
        if output:
            self.output_edit.setText(output)
        name = self.settings.value("name", "", type=str)
        if name:
            self.name_edit.setText(name)
        icon = self.settings.value("icon", "", type=str)
        if icon:
            self.icon_edit.setText(icon)

        self.chk_onefile.setChecked(self.settings.value("onefile", True, type=bool))
        self.chk_windowed.setChecked(self.settings.value("windowed", False, type=bool))
        self.chk_clean.setChecked(self.settings.value("clean", True, type=bool))
        self.chk_clean_temp.setChecked(
            self.settings.value("clean_temp", True, type=bool)
        )
        self.hidden_edit.setText(self.settings.value("hidden", "", type=str))
        self.extra_edit.setText(self.settings.value("extra", "", type=str))

        saved_entry = self.settings.value("entry", "", type=str)
        if saved_entry:
            index = self.entry_combo.findData(saved_entry)
            if index >= 0:
                self.entry_combo.setCurrentIndex(index)

        data_items = self.settings.value("data_items", [], type=list)
        for item in data_items or []:
            if isinstance(item, str) and item:
                self.data_list.addItem(item)
        self._update_preview()

    def _save_settings(self):
        self.settings.setValue("source", self.source_edit.text().strip())
        self.settings.setValue("entry", self._entry_script())
        self.settings.setValue("output", self.output_edit.text().strip())
        self.settings.setValue("name", self.name_edit.text().strip())
        self.settings.setValue("icon", self.icon_edit.text().strip())
        self.settings.setValue("onefile", self.chk_onefile.isChecked())
        self.settings.setValue("windowed", self.chk_windowed.isChecked())
        self.settings.setValue("clean", self.chk_clean.isChecked())
        self.settings.setValue("clean_temp", self.chk_clean_temp.isChecked())
        self.settings.setValue("hidden", self.hidden_edit.text().strip())
        self.settings.setValue("extra", self.extra_edit.text().strip())
        data_items = [self.data_list.item(i).text() for i in range(self.data_list.count())]
        self.settings.setValue("data_items", data_items)

    # ============================================================ selezione file
    def choose_source_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona script Python", "", "Python (*.py);;Tutti i file (*.*)"
        )
        if path:
            self._set_source(os.path.normpath(path))

    def choose_source_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Seleziona cartella del progetto")
        if path:
            self._set_source(os.path.normpath(path))

    def _set_source(self, path):
        self.source_edit.setText(path)
        self._last_typed_source = path
        self._populate_entry_combo(path)

        base_dir = path if os.path.isdir(path) else os.path.dirname(path)
        script = self._entry_script()
        default_name = os.path.splitext(os.path.basename(script))[0] if script else os.path.basename(base_dir)
        if not self.name_edit.text().strip() or self.name_edit.text().strip() == self._auto_name:
            self.name_edit.setText(default_name)
            self._auto_name = default_name

        default_output = os.path.join(base_dir, "dist")
        if not self.output_edit.text().strip() or self.output_edit.text().strip() == self._auto_output:
            self.output_edit.setText(default_output)
            self._auto_output = default_output

        self._update_source_info()
        self._update_preview()

    def _on_source_edited(self):
        path = self.source_edit.text().strip()
        if path == getattr(self, "_last_typed_source", None):
            return
        self._last_typed_source = path
        if path and os.path.exists(path):
            self._set_source(os.path.normpath(path))
        else:
            self._update_source_info()
            self._update_preview()

    def _populate_entry_combo(self, path):
        self.entry_combo.blockSignals(True)
        self.entry_combo.clear()

        if os.path.isdir(path):
            files = []
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames[:] = [
                    d for d in dirnames
                    if d not in ("__pycache__", "venv", ".venv", "env", ".git",
                                 "build", "dist", "node_modules")
                    and not d.startswith(".")
                ]
                for filename in filenames:
                    if filename.endswith(".py"):
                        files.append(os.path.join(dirpath, filename))
            files.sort(key=lambda p: p.casefold())
            for file in files:
                self.entry_combo.addItem(os.path.relpath(file, path), file)
            preferred = os.path.join(path, "main.py")
            index = self.entry_combo.findData(preferred)
            if index < 0:
                index = self.entry_combo.findData(os.path.join(path, "app.py"))
            if index < 0 and files:
                index = 0
            if index >= 0:
                self.entry_combo.setCurrentIndex(index)
            self.entry_combo.setEnabled(True)
        else:
            if os.path.isfile(path):
                self.entry_combo.addItem(os.path.basename(path), path)
            self.entry_combo.setEnabled(False)

        self.entry_combo.blockSignals(False)

    def _on_entry_changed(self, *_args):
        script = self._entry_script()
        if script:
            default_name = os.path.splitext(os.path.basename(script))[0]
            if not self.name_edit.text().strip() or self.name_edit.text().strip() == self._auto_name:
                self.name_edit.setText(default_name)
                self._auto_name = default_name
        self._update_source_info()
        self._update_preview()

    def _entry_script(self):
        source = self.source_edit.text().strip()
        if os.path.isdir(source):
            return self.entry_combo.currentData() or ""
        if os.path.isfile(source):
            return source
        return ""

    def _update_source_info(self):
        source = self.source_edit.text().strip()
        if not source:
            self.source_info.setText("Seleziona uno script o una cartella di progetto.")
            return
        if os.path.isdir(source):
            count = self.entry_combo.count()
            if count == 0:
                self.source_info.setText(
                    "⚠  Nessun file .py trovato nella cartella del progetto."
                )
            else:
                self.source_info.setText(
                    f"Progetto: {source}\nFile Python trovati: {count}. "
                    "Scegli il file principale dal menu qui sopra."
                )
        elif os.path.isfile(source):
            self.source_info.setText(f"Script selezionato: {source}")
        else:
            self.source_info.setText("⚠  Il percorso selezionato non esiste.")

    def choose_output_folder(self):
        start = self.output_edit.text().strip()
        if not os.path.isdir(start):
            start = os.path.dirname(self._entry_script()) if self._entry_script() else ""
        path = QFileDialog.getExistingDirectory(self, "Seleziona cartella di output", start)
        if path:
            self.output_edit.setText(os.path.normpath(path))
            self._auto_output = ""

    def choose_icon(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona icona", "", "Icone (*.ico);;Tutti i file (*.*)"
        )
        if path:
            self.icon_edit.setText(os.path.normpath(path))

    # ============================================================== dati extra
    def _browse_data(self, folder=False):
        if folder:
            path = QFileDialog.getExistingDirectory(self, "Seleziona cartella da includere")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Seleziona file da includere")
        if path:
            self.data_edit.setText(os.path.normpath(path))

    def _add_data_item(self):
        raw = self.data_edit.text().strip()
        if not raw:
            return
        if DATA_SEP in raw:
            entry = raw
            source = raw.split(DATA_SEP, 1)[0]
            if not os.path.exists(source):
                QMessageBox.warning(
                    self, "Dato non trovato", f"Il percorso di origine non esiste:\n{source}"
                )
                return
        else:
            if not os.path.exists(raw):
                QMessageBox.warning(
                    self, "Dato non trovato", f"Il percorso non esiste:\n{raw}"
                )
                return
            entry = f"{raw}{DATA_SEP}."
        existing = {self.data_list.item(i).text() for i in range(self.data_list.count())}
        if entry not in existing:
            self.data_list.addItem(entry)
        self.data_edit.clear()
        self._update_preview()

    def _remove_data_item(self):
        row = self.data_list.currentRow()
        if row >= 0:
            self.data_list.takeItem(row)
            self._update_preview()

    # ============================================================= costruzione
    def _build_arguments(self, validate=False):
        script = self._entry_script()
        if not script:
            if validate:
                QMessageBox.warning(
                    self, "Sorgente mancante",
                    "Seleziona uno script Python o una cartella di progetto e "
                    "scegli il file principale."
                )
            return None, None

        if not os.path.isfile(script) or not script.lower().endswith(".py"):
            if validate:
                QMessageBox.warning(
                    self, "Sorgente non valido",
                    f"Il file principale deve essere uno script .py esistente:\n{script}"
                )
            return None, None

        output = self.output_edit.text().strip()
        if not output:
            output = os.path.join(os.path.dirname(script), "dist")
        output = os.path.normpath(output)

        name = self.name_edit.text().strip()
        if not name:
            name = os.path.splitext(os.path.basename(script))[0]
        for char in '<>:"/\\|?*':
            name = name.replace(char, "_")
        name = name.strip(" .") or "app"

        icon = self.icon_edit.text().strip()
        if icon and not os.path.isfile(icon):
            if validate:
                QMessageBox.warning(
                    self, "Icona non trovata", f"Il file icona non esiste:\n{icon}"
                )
            return None, None

        if validate:
            try:
                os.makedirs(output, exist_ok=True)
            except OSError as exc:
                QMessageBox.critical(
                    self, "Cartella di output",
                    f"Impossibile creare la cartella di output:\n{output}\n\n{exc}"
                )
                return None, None

        work_dir = os.path.join(output, ".pyinstaller-build")
        args = ["-m", "PyInstaller", "--noconfirm"]
        if self.chk_clean.isChecked():
            args.append("--clean")
        args += [
            "--distpath", output,
            "--workpath", work_dir,
            "--specpath", work_dir,
            "--name", name,
        ]
        args.append("--onefile" if self.chk_onefile.isChecked() else "--onedir")
        if self.chk_windowed.isChecked():
            args.append("--windowed")
        if icon:
            args += ["--icon", icon]

        source = self.source_edit.text().strip()
        project_dir = source if os.path.isdir(source) else os.path.dirname(script)
        if project_dir:
            args += ["--paths", project_dir]

        # VistoFlow: il browser è un modulo separato eseguito dallo stesso .exe
        # con --browser-engine. PyInstaller deve includerlo e raccogliere i
        # plugin/dati di QtWebEngine forniti da PySide6.
        browser_engine = (
            os.path.join(project_dir, "browser_engine.py") if project_dir else ""
        )
        if browser_engine and os.path.isfile(browser_engine):
            if importlib.util.find_spec("PySide6") is not None:
                args += [
                    "--hidden-import", "browser_engine",
                    "--collect-all", "PySide6",
                ]

        hidden = [
            item.strip()
            for item in self.hidden_edit.text().replace(";", ",").split(",")
            if item.strip()
        ]
        for module in hidden:
            args += ["--hidden-import", module]

        for row in range(self.data_list.count()):
            entry = self.data_list.item(row).text().strip()
            if entry:
                args += ["--add-data", entry]

        args += split_extra_args(self.extra_edit.text())
        args.append(script)
        return args, {"script": script, "output": output, "name": name, "work_dir": work_dir}

    def _update_preview(self, *_args):
        args, info = self._build_arguments(validate=False)
        if not args:
            self.preview.setText("Seleziona un sorgente per vedere il comando…")
            return
        command = [sys.executable] + args
        text = " ".join(quote_command(part) for part in command)
        self.preview.setText(text)

    def _exe_path(self, output, name):
        if self.chk_onefile.isChecked():
            return os.path.join(output, name + EXE_SUFFIX)
        return os.path.join(output, name, name + EXE_SUFFIX)

    # =============================================================== processo
    def _set_chip(self, text, background, foreground, border):
        self.status_chip.setText(text)
        self.status_chip.setStyleSheet(
            "background: %s; color: %s; border: 1px solid %s;"
            "border-radius: 11px; padding: 5px 12px; font-size: 11px; font-weight: 600;"
            % (background, foreground, border)
        )

    def _set_busy(self, busy):
        self.process_running = busy
        self.btn_build.setEnabled(not busy)
        self.btn_install.setEnabled(not busy and not self.pyinstaller_ready)
        self.btn_cancel.setEnabled(busy)
        if busy:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)

    def _start_process(self, args, mode, status_text):
        self._cancelled = False
        self.mode = mode
        self._check_output = ""
        self._set_busy(True)
        self.status_label.setText(status_text)
        cwd = os.path.dirname(self._entry_script()) if self._entry_script() else ""
        if cwd:
            self.proc.setWorkingDirectory(cwd)
        self.proc.start(sys.executable, args)

    def check_pyinstaller(self):
        if self.process_running:
            return
        self._set_chip("Verifica PyInstaller…", "#1a222c", "#9aa5b4", "#2b3542")
        self.status_label.setText("Verifica dell'installazione di PyInstaller…")
        self._append_log("\n— Verifica PyInstaller —\n")
        self._start_process(["-m", "PyInstaller", "--version"], "check", "Verifica PyInstaller…")

    def install_pyinstaller(self):
        if self.process_running:
            return
        if QMessageBox.question(
            self, "Installa PyInstaller",
            "Installare PyInstaller nell'ambiente Python corrente?\n\n"
            f"{sys.executable}\n\nVerrà eseguito: python -m pip install --upgrade pyinstaller",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._append_log("\n— Installazione PyInstaller —\n")
        self._start_process(
            ["-m", "pip", "install", "--upgrade", "pyinstaller"],
            "install",
            "Installazione di PyInstaller in corso…",
        )
        self.status_label.setText("Installazione di PyInstaller in corso…")

    def start_build(self):
        if self.process_running:
            QMessageBox.information(
                self, "Attendere", "Un processo è già in esecuzione. Attendi o annullalo."
            )
            return
        if self.mode == "check" or (not self.pyinstaller_ready and self.pyinstaller_version == "missing"):
            if not self.pyinstaller_ready:
                answer = QMessageBox.question(
                    self, "PyInstaller non installato",
                    "PyInstaller non risulta installato. Vuoi installarlo ora?"
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self.install_pyinstaller()
                return

        self._save_settings()
        args, info = self._build_arguments(validate=True)
        if not args:
            return

        self._last_exe = self._exe_path(info["output"], info["name"])
        self._last_output = info["output"]
        self._last_work_dir = info["work_dir"]
        self._append_log(
            "\n" + "=" * 62 + "\n"
            + "BUILD: " + info["name"] + "\n"
            + "Sorgente: " + info["script"] + "\n"
            + "Output: " + info["output"] + "\n"
            + "=" * 62 + "\n\n"
        )
        self._start_process(args, "build", "Build in corso…")
        self.status_label.setText("Build in corso… PyInstaller sta preparando l'eseguibile.")

    def cancel_process(self):
        if not self.process_running:
            return
        self._cancelled = True
        self.status_label.setText("Annullamento in corso…")
        self.proc.kill()

    def _read_output(self):
        raw = bytes(self.proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not raw:
            return
        if self.mode == "check":
            self._check_output += raw
            return
        self._append_log(raw)

    def _append_log(self, text):
        if not text:
            return
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._set_busy(False)
            self.mode = None
            self.status_label.setText("Impossibile avviare il processo Python.")
            QMessageBox.critical(
                self, "Errore di avvio",
                f"Impossibile avviare:\n{sys.executable}\n\nControlla l'installazione di Python."
            )
        elif self.mode == "build":
            self._append_log(f"\n[errore processo: {error}]\n")

    def _process_finished(self, exit_code, _exit_status):
        mode = self.mode
        self.mode = None
        self._set_busy(False)

        if self._cancelled and mode in ("check", "install"):
            self._cancelled = False
            self.status_label.setText("Operazione annullata.")
            self._set_chip("Stato sconosciuto", "#1a222c", "#9aa5b4", "#2b3542")
            self.btn_install.setEnabled(True)
            return

        if mode == "check":
            output = self._check_output.strip()
            if exit_code == 0:
                self.pyinstaller_ready = True
                version = output.splitlines()[-1].strip() if output else ""
                self.pyinstaller_version = version or "ok"
                label = f"PyInstaller {version} pronto" if version else "PyInstaller pronto"
                self._set_chip(label, "#17291f", "#2ecc71", "#21402e")
                self.btn_install.setEnabled(False)
                self.status_label.setText("PyInstaller è installato. Puoi creare l'eseguibile.")
                self._append_log(
                    f"PyInstaller trovato: {version or 'ok'}\n"
                )
            else:
                self.pyinstaller_ready = False
                self.pyinstaller_version = "missing"
                self._set_chip("PyInstaller non installato", "#2c2418", "#f5a623", "#4a3a1c")
                self.btn_install.setEnabled(True)
                self.status_label.setText(
                    "PyInstaller non è installato: usa il pulsante in alto per installarlo."
                )
                self._append_log(
                    "PyInstaller non trovato in questo ambiente Python.\n"
                )
            return

        if mode == "install":
            if exit_code == 0:
                self._append_log("\nPyInstaller installato correttamente.\n")
                self.status_label.setText("Installazione completata. Verifica in corso…")
                self.pyinstaller_ready = False
                self.pyinstaller_version = ""
                QTimer.singleShot(400, self.check_pyinstaller)
            else:
                self.status_label.setText("Installazione di PyInstaller non riuscita.")
                self._append_log("\nInstallazione non riuscita.\n")
                QMessageBox.critical(
                    self, "Installazione fallita",
                    "Non è stato possibile installare PyInstaller.\n"
                    "Controlla il log e prova manualmente:\n\n"
                    "python -m pip install pyinstaller"
                )
            return

        if mode == "build":
            if self._cancelled:
                self.status_label.setText("Build annullata.")
                self._append_log("\nBuild annullata dall'utente.\n")
                return
            if exit_code == 0:
                self._append_log("\n" + "=" * 62 + "\nBUILD COMPLETATA\n" + "=" * 62 + "\n")
                self.status_label.setText(f"Eseguibile pronto: {self._last_exe}")
                if self.chk_clean_temp.isChecked():
                    self._clean_work_dir()
                self._set_chip("Eseguibile creato ✓", "#17291f", "#2ecc71", "#21402e")
                QMessageBox.information(
                    self, "Build completata",
                    f"Eseguibile creato:\n\n{self._last_exe}"
                )
            else:
                self.status_label.setText(
                    f"Build non riuscita (codice {exit_code}). Controlla il log."
                )
                self._append_log(
                    f"\nBuild non riuscita con codice {exit_code}. Controlla gli errori sopra.\n"
                )
                QMessageBox.critical(
                    self, "Build non riuscita",
                    "PyInstaller ha restituito un errore. Controlla il log per i dettagli."
                )

    def _clean_work_dir(self):
        try:
            work_dir = getattr(self, "_last_work_dir", "")
            if work_dir and os.path.isdir(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
                self._append_log("Cartella temporanea di build rimossa.\n")
        except Exception:
            pass

    def open_output_folder(self):
        folder = self.output_edit.text().strip()
        if not folder:
            QMessageBox.information(self, "Output", "Seleziona prima una cartella di output.")
            return
        if not os.path.isdir(folder):
            QMessageBox.information(
                self, "Output", f"La cartella non esiste ancora:\n{folder}"
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ================================================================ chiusura
    def closeEvent(self, event):
        self._save_settings()
        if self.process_running:
            self.proc.kill()
            self.proc.waitForFinished(1500)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_theme(app)
    window = BuilderWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
