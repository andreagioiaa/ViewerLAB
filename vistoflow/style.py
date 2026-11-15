"""Foglio di stile delle pagine ViewerLAB (palette ispirata a Stream Goat)."""

THEME = """
QWidget {
    background-color: #0b0b10;
    color: #f3f3f6;
    font-size: 13px;
}
QFrame#Rail {
    background-color: #111117;
    border-right: 1px solid rgba(255, 255, 255, 0.06);
}
QLabel#RailLogo {
    background-color: #3b82f6;
    color: white;
    border-radius: 12px;
    font-size: 18px;
    min-height: 44px;
}
QToolButton#RailButton {
    background: transparent;
    color: #a0a0ad;
    border: none;
    border-radius: 12px;
    font-size: 22px;
    min-width: 46px;
    min-height: 46px;
}
QToolButton#RailButton:hover { background-color: #1d1d26; color: #f3f3f6; }
QToolButton#RailButton:checked { background-color: #172554; color: #3b82f6; }
QToolButton#RoundButton {
    background-color: #1d1d26;
    border: none;
    border-radius: 19px;
    font-size: 18px;
    min-width: 38px;
    min-height: 38px;
}
QToolButton#RoundButton:hover { background-color: #282832; }
QLabel#PageTitle { font-size: 22px; font-weight: 700; }
QLabel#DetailTitle { font-size: 30px; font-weight: 700; }
QLabel#Muted { color: #a0a0ad; }
QLabel#Chip {
    background-color: #1d1d26;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    color: #a0a0ad;
    font-size: 11px;
    padding: 3px 9px;
}
QFrame#Card {
    background-color: #15151c;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background-color: #15151c;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 10px;
    padding: 7px 10px;
    selection-background-color: #3b82f6;
}
QLineEdit#SearchField { font-size: 15px; padding: 11px 14px; border-radius: 12px; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #3b82f6;
}
QPushButton {
    background-color: #282832;
    border: none;
    border-radius: 10px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton:hover { background-color: #32323e; }
QPushButton:disabled { color: #6c6c79; background-color: #1d1d26; }
QPushButton#PrimaryButton { background-color: #3b82f6; color: white; }
QPushButton#PrimaryButton:hover { background-color: #5592f8; }
QPushButton#WhiteButton {
    background-color: #ffffff;
    color: #0b0b10;
    padding: 11px 34px;
    font-size: 14px;
}
QPushButton#WhiteButton:hover { background-color: #e6e6ec; }
QPushButton#WhiteButton:disabled { background-color: #282832; color: #6c6c79; }
QPushButton#GhostButton {
    background-color: #1d1d26;
    border: 1px solid rgba(255, 255, 255, 0.10);
    padding: 10px 18px;
}
QPushButton#FilterChip {
    background-color: #1d1d26;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    color: #a0a0ad;
    padding: 5px 14px;
    font-size: 12px;
}
QPushButton#FilterChip:checked { background-color: #3b82f6; border-color: #3b82f6; color: white; }
QListWidget#PosterGrid {
    background: transparent;
    border: none;
    outline: none;
    color: #a0a0ad;
}
QListWidget#PosterGrid::item {
    border-radius: 12px;
    padding: 4px;
}
QListWidget#PosterGrid::item:hover { background-color: #15151c; color: #f3f3f6; }
QListWidget#PosterGrid::item:selected { background-color: #172554; color: #f3f3f6; }
QTableWidget {
    background-color: #15151c;
    alternate-background-color: #1d1d26;
    gridline-color: transparent;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    selection-background-color: #172554;
    selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #15151c;
    color: #a0a0ad;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding: 8px;
}
QTableWidget::item { padding: 6px; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #282832; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QSlider::groove:horizontal { height: 4px; background: #282832; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px; background: #ffffff; }
QSlider::sub-page:horizontal { background: #3b82f6; border-radius: 2px; }
QStatusBar { color: #6c6c79; background-color: #0b0b10; }
QLabel#SectionTitle { font-size: 17px; font-weight: 700; margin-top: 4px; }
QLabel#ImdbBadge {
    background-color: #f5c518;
    color: #000000;
    border-radius: 5px;
    font-weight: 800;
    padding: 3px 8px;
}
QLabel#RatingChip {
    background-color: rgba(245, 197, 24, 0.12);
    border: 1px solid rgba(245, 197, 24, 0.45);
    border-radius: 6px;
    color: #f5c518;
    font-size: 11px;
    font-weight: 700;
    padding: 3px 9px;
}
QScrollArea { background: transparent; border: none; }
"""
