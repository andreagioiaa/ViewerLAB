"""Tema scuro condiviso dall'interfaccia di VistoFlow Pro."""

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QStyleFactory

ACCENT = "#2ecc71"
ACCENT_HOVER = "#45d883"
BG = "#0d1117"
PANEL = "#11161d"
CARD = "#161c24"
BORDER = "#232d39"
TEXT = "#e6ebf2"
MUTED = "#7d8797"


def apply_theme(app):
    """Applica palette Fusion + foglio di stile globale."""
    app.setStyle(QStyleFactory.create("Fusion"))

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(BG))
    p.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Base, QColor(CARD))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(PANEL))
    p.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Button, QColor(CARD))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#08130c"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(PANEL))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#5b6575"))
    app.setPalette(p)
    app.setStyleSheet(QSS)


QSS = """
* {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog { background: #0d1117; }
QWidget { color: #e6ebf2; }
QToolTip {
    background: #1b222c;
    color: #e6ebf2;
    border: 1px solid #2b3542;
    border-radius: 6px;
    padding: 6px 8px;
}

QFrame#TopBar {
    background: #10151c;
    border-bottom: 1px solid #202833;
}
QFrame#Sidebar {
    background: #10151c;
    border-right: 1px solid #202833;
}
QFrame#BrowserPanel {
    background: #0f141a;
    border-top: 1px solid #202833;
}
QFrame#Player { background: #000000; }
QFrame#PlayerBar {
    background: #10151c;
    border-top: 1px solid #202833;
    border-bottom: 1px solid #202833;
}
QLabel#PlayerBarText { color: #aab5c4; font-size: 12px; }

QLabel { background: transparent; }
QLabel#AppTitle { font-size: 19px; font-weight: 700; color: #ffffff; }
QLabel#AppSubtitle { color: #788394; font-size: 11px; }
QLabel#SectionTitle {
    color: #7d8797;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#Muted { color: #7d8797; }
QLabel#CollectionTitle { font-size: 19px; font-weight: 700; color: #ffffff; }
QLabel#CollectionMeta { color: #7d8797; font-size: 12px; }
QLabel#Empty { color: #5b6575; font-size: 14px; }
QLabel#Badge {
    background: #17291f;
    color: #2ecc71;
    border: 1px solid #21402e;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#StatusOk { color: #2ecc71; font-weight: 600; }
QLabel#StatusWarn { color: #f5a623; font-weight: 600; }
QLabel#TimeLabel {
    color: #c3ccd8;
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 11px;
}
QLabel#PlayerMeta { color: #e6ebf2; font-size: 13px; font-weight: 600; }
QLabel#TagChip {
    background: #182231;
    color: #9fb0c4;
    border: 1px solid #263140;
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 11px;
}
QLabel#CoverPreview {
    background: #141a21;
    border: 1px dashed #33404f;
    border-radius: 8px;
    color: #5b6575;
    font-size: 11px;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #161d26;
    border: 1px solid #27313d;
    border-radius: 8px;
    padding: 7px 10px;
    color: #e6ebf2;
    selection-background-color: #2ecc71;
    selection-color: #08130c;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #2ecc71;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
    color: #5b6575;
    background: #12171e;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: #161d26;
    border: 1px solid #27313d;
    border-radius: 8px;
    padding: 4px;
    outline: none;
    selection-background-color: #1c3a2a;
    selection-color: #ffffff;
}

QPushButton {
    background: #1a222c;
    border: 1px solid #27313d;
    border-radius: 8px;
    padding: 8px 14px;
    color: #dfe6ee;
}
QPushButton:hover { background: #212c38; border-color: #354354; }
QPushButton:pressed { background: #141b23; }
QPushButton:disabled { color: #55606f; background: #141a21; border-color: #1e2731; }
QPushButton#Primary {
    background: #2ecc71;
    border: none;
    color: #07130b;
    font-weight: 700;
}
QPushButton#Primary:hover { background: #45d883; }
QPushButton#Primary:disabled { background: #20352a; color: #5c7d68; }
QPushButton#Ghost { background: transparent; border: 1px solid #27313d; }
QPushButton#Ghost:hover { background: #1a222c; }
QPushButton#Danger {
    background: transparent;
    border: 1px solid #6e2f2f;
    color: #ff9b9b;
}
QPushButton#Danger:hover { background: #351b1b; }
QPushButton[segment="true"] {
    background: transparent;
    border: 1px solid #27313d;
    border-radius: 0px;
    padding: 7px 16px;
    color: #97a3b3;
    font-weight: 600;
}
QPushButton[segment="true"]:hover { background: #19212b; color: #dfe6ee; }
QPushButton[segment="true"]:checked {
    background: #193226;
    border-color: #2ecc71;
    color: #2ecc71;
}
QPushButton#IconButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #e6ebf2;
    font-size: 20px;
    padding: 4px;
}
QPushButton#IconButton:hover { background: #1e2833; color: #2ecc71; }
QPushButton#PlayButton {
    background: #2ecc71;
    border: none;
    border-radius: 18px;
    color: #07130b;
    font-size: 18px;
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    max-height: 36px;
    padding: 0px;
}
QPushButton#PlayButton:hover { background: #45d883; }
QPushButton#SpeedButton {
    background: transparent;
    border: 1px solid #2b3542;
    border-radius: 8px;
    color: #b6c1cf;
    font-size: 11px;
    font-weight: 600;
    padding: 5px 8px;
    min-width: 38px;
}
QPushButton#ClosePlayerButton {
    background: transparent;
    border: none;
    border-radius: 15px;
    color: #8b96a7;
    font-size: 15px;
}
QPushButton#ClosePlayerButton:hover { background: #3a1f1f; color: #ff9b9b; }

QTreeWidget, QListWidget, QTableWidget {
    background: transparent;
    border: none;
    outline: none;
}
QTreeWidget::item {
    padding: 7px 6px;
    border-radius: 7px;
    color: #cbd4df;
}
QTreeWidget::item:hover { background: #19212b; }
QTreeWidget::item:selected { background: #1a3527; color: #ffffff; }
QTreeWidget::branch { background: transparent; }

QListWidget::item { border: none; }
QListWidget::item:selected { background: transparent; }
QListWidget#SavedLinks::item {
    padding: 9px 10px;
    border-bottom: 1px solid #202833;
    color: #dfe6ee;
}
QListWidget#SavedLinks::item:hover { background: #19212b; }
QListWidget#SavedLinks::item:selected {
    background: #1a3527;
    color: #ffffff;
}
QListWidget#OnlineResults::item {
    padding: 7px 8px;
    border-radius: 5px;
}
QListWidget#OnlineResults::item:hover { background: #19212b; }
QListWidget#OnlineResults::item:selected {
    background: #1a3527;
    color: #ffffff;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #2a3542;
    min-height: 32px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: #3a4757; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #2a3542;
    min-width: 32px;
    border-radius: 4px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

QSlider::groove:horizontal {
    height: 5px;
    background: #26303c;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #2ecc71;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 13px;
    height: 13px;
    margin: -4px 0;
    border-radius: 6px;
    background: #ffffff;
}
QSlider::handle:horizontal:hover { background: #2ecc71; }
QSlider#Volume::groove:horizontal { height: 4px; background: #26303c; }
QSlider#Volume::sub-page:horizontal { background: #7d8797; }
QSlider#Volume::handle:horizontal { width: 10px; height: 10px; margin: -3px 0; background: #dfe6ee; }

QMenu {
    background: #151b23;
    border: 1px solid #27313d;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 26px 8px 12px;
    border-radius: 6px;
    color: #dfe6ee;
}
QMenu::item:selected { background: #1c3a2a; color: #ffffff; }
QMenu::item:disabled { color: #55606f; }
QMenu::separator { height: 1px; background: #27313d; margin: 5px 8px; }

QCheckBox, QRadioButton { spacing: 8px; color: #cfd7e2; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #3a4656;
    background: #161d26;
}
QCheckBox::indicator { border-radius: 4px; }
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: #2ecc71; }
QCheckBox::indicator:checked {
    background: #2ecc71;
    border-color: #2ecc71;
}
QRadioButton::indicator:checked {
    background: #2ecc71;
    border: 4px solid #0d1117;
    outline: 1px solid #2ecc71;
}

QGroupBox {
    background: #11161d;
    border: 1px solid #232d39;
    border-radius: 10px;
    margin-top: 14px;
    padding: 16px 14px 12px 14px;
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

QPlainTextEdit, QTextEdit {
    background: #0b0f14;
    border: 1px solid #232d39;
    border-radius: 8px;
    color: #cbd4df;
    padding: 8px;
    selection-background-color: #2ecc71;
    selection-color: #08130c;
}

QProgressBar {
    background: #1a222c;
    border: none;
    border-radius: 4px;
    max-height: 8px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk { background: #2ecc71; border-radius: 4px; }

QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: #1c2733; }
QStatusBar { background: #10151c; border-top: 1px solid #202833; color: #7d8797; }
"""
