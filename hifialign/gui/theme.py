"""Light / dark / system theme: Fusion style + palette + stylesheet built from colour tokens."""
from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPalette, QPen, QPixmap, QFont
from PySide6.QtWidgets import QApplication

THEMES = ('system', 'light', 'dark')

TOKENS = {
    'light': dict(
        bg='#f5f6f8', side='#eceef3', surface='#ffffff', surface2='#f7f8fa', hover='#e6e9ef', pressed='#dadee7',
        border='#e1e4ea', border2='#cdd2db', text='#1d2025', muted='#6b7280', accent='#4f5bd5',
        accent_hover='#4350c4', accent_text='#ffffff', accent_soft='#e4e7fb', danger='#c93c3c', ok='#2f9e62',
        warn_bg='rgba(245, 158, 11, 0.22)', header='#f2f4f7', sel='#d9defa', sel_text='#1d2025',
        scroll='#c4c9d2', tooltip='#1d2025', tooltip_text='#ffffff', view_bg='#101114'),
    'dark': dict(
        bg='#16181c', side='#1d2025', surface='#22252b', surface2='#272b32', hover='#2d3139', pressed='#363b45',
        border='#30343c', border2='#414752', text='#e6e8ec', muted='#9aa2ae', accent='#6574f0',
        accent_hover='#7684f5', accent_text='#ffffff', accent_soft='#2b3058', danger='#f07474', ok='#4cc38a',
        warn_bg='rgba(245, 158, 11, 0.25)', header='#262a31', sel='#343a66', sel_text='#ffffff',
        scroll='#4a505b', tooltip='#e6e8ec', tooltip_text='#16181c', view_bg='#0c0d0f'),
}


def _svg(path, color, d):
    with open(path, 'w') as fh:
        fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
                 f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" '
                 f'stroke-linejoin="round"/></svg>')
    return path.replace('\\', '/')


def _assets(mode, t):
    d = os.path.join(tempfile.gettempdir(), 'hifialign_theme')
    os.makedirs(d, exist_ok=True)
    return dict(
        down=_svg(os.path.join(d, f'down_{mode}.svg'), t['muted'], 'M3 4.5 L6 7.5 L9 4.5'),
        up=_svg(os.path.join(d, f'up_{mode}.svg'), t['muted'], 'M3 7.5 L6 4.5 L9 7.5'),
        down_dis=_svg(os.path.join(d, f'down_dis_{mode}.svg'), t['border2'], 'M3 4.5 L6 7.5 L9 4.5'),
        up_dis=_svg(os.path.join(d, f'up_dis_{mode}.svg'), t['border2'], 'M3 7.5 L6 4.5 L9 7.5'),
        check=_svg(os.path.join(d, f'check_{mode}.svg'), t['accent_text'], 'M2.6 6.2 L5 8.5 L9.4 3.6'),
        dot=_dot(os.path.join(d, f'dot_{mode}.svg'), t['accent_text']),
    )


def _dot(path, color):
    with open(path, 'w') as fh:
        fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
                 f'<circle cx="6" cy="6" r="2.6" fill="{color}"/></svg>')
    return path.replace('\\', '/')


def stylesheet(mode: str) -> str:
    t = TOKENS[mode]
    a = _assets(mode, t)
    return f"""
* {{ outline: none; }}
QWidget {{ color: {t['text']}; font-size: 13px; }}
QMainWindow, #Content, QStackedWidget > QWidget {{ background: {t['bg']}; }}
QDialog, QMessageBox {{ background: {t['bg']}; }}
QToolTip {{ background: {t['tooltip']}; color: {t['tooltip_text']}; border: none; padding: 6px 8px;
            border-radius: 6px; }}

/* ---------- sidebar */
#Sidebar {{ background: {t['side']}; border-right: 1px solid {t['border']}; }}
#AppTitle {{ font-size: 18px; font-weight: 700; }}
#AppSubtitle {{ color: {t['muted']}; font-size: 11px; }}
#ProjectName {{ color: {t['muted']}; font-size: 12px; padding: 2px 0; }}
#NavButton {{ text-align: left; padding: 8px 10px; border: none; border-radius: 8px; background: transparent;
              font-size: 13px; color: {t['text']}; }}
#NavButton:hover {{ background: {t['hover']}; }}
#NavButton:checked {{ background: {t['accent_soft']}; color: {t['accent']}; font-weight: 600; }}
#NavButton:disabled {{ color: {t['muted']}; }}
#SideLabel {{ color: {t['muted']}; font-size: 11px; font-weight: 600; }}
#Sidebar QComboBox {{ background: {t['surface']}; }}

/* ---------- page headers & text roles */
#PageTitle {{ font-size: 22px; font-weight: 700; }}
#PageSubtitle {{ color: {t['muted']}; font-size: 13px; }}
#Hint {{ color: {t['muted']}; font-size: 12px; }}
#SectionTitle {{ font-size: 14px; font-weight: 600; }}
#StageLabel {{ font-weight: 600; }}
#Elapsed {{ color: {t['muted']}; }}

/* ---------- cards (group boxes) */
QGroupBox, #Card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 12px; }}
QGroupBox {{ margin-top: 26px; padding: 14px 14px 12px 14px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 2px; top: 2px;
                    padding: 0 2px; color: {t['muted']}; font-size: 12px; font-weight: 600; }}
QGroupBox QLabel, #Card QLabel {{ background: transparent; }}

/* ---------- buttons */
QPushButton, QToolButton {{ background: {t['surface']}; border: 1px solid {t['border2']}; border-radius: 7px;
                            padding: 6px 14px; min-height: 18px; }}
QPushButton:hover, QToolButton:hover {{ background: {t['hover']}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {t['pressed']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t['muted']}; background: {t['surface2']};
                                              border-color: {t['border']}; }}
QPushButton:checked {{ background: {t['accent_soft']}; border-color: {t['accent']}; color: {t['accent']}; }}
QPushButton[primary="true"] {{ background: {t['accent']}; color: {t['accent_text']}; border: 1px solid {t['accent']};
                               font-weight: 600; padding: 7px 18px; }}
QPushButton[primary="true"]:hover {{ background: {t['accent_hover']}; border-color: {t['accent_hover']}; }}
QPushButton[primary="true"]:disabled {{ background: {t['border2']}; border-color: {t['border2']};
                                        color: {t['surface']}; }}
QPushButton[danger="true"] {{ color: {t['danger']}; }}
QPushButton[danger="true"]:disabled {{ color: {t['muted']}; }}
QPushButton[flat="true"] {{ background: transparent; border: none; color: {t['accent']}; padding: 4px 6px; }}
QPushButton[flat="true"]:hover {{ background: {t['hover']}; }}

/* ---------- inputs */
QLineEdit, QComboBox, QAbstractSpinBox {{ background: {t['surface']}; border: 1px solid {t['border2']};
    border-radius: 7px; padding: 5px 8px; min-height: 18px; selection-background-color: {t['accent']};
    selection-color: {t['accent_text']}; }}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus {{ border: 1px solid {t['accent']}; }}
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {{ color: {t['muted']};
    background: {t['surface2']}; border-color: {t['border']}; }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 24px; border: none; }}
QComboBox::down-arrow {{ image: url("{a['down']}"); width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled {{ image: url("{a['down_dis']}"); }}
QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['border2']}; border-radius: 6px;
    padding: 4px; selection-background-color: {t['accent_soft']}; selection-color: {t['text']}; }}
QAbstractSpinBox {{ padding: 4px 26px 4px 4px; }}
QAbstractSpinBox QLineEdit {{ border: none; padding: 0; margin: 0; background: transparent; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 22px;
    border: none; background: transparent; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; margin-top: 2px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; margin-bottom: 2px; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {t['hover']};
    border-radius: 4px; }}
QAbstractSpinBox::up-arrow {{ image: url("{a['up']}"); width: 12px; height: 12px; }}
QAbstractSpinBox::down-arrow {{ image: url("{a['down']}"); width: 12px; height: 12px; }}
QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::up-arrow:off {{ image: url("{a['up_dis']}"); }}
QAbstractSpinBox::down-arrow:disabled, QAbstractSpinBox::down-arrow:off {{ image: url("{a['down_dis']}"); }}

QCheckBox, QRadioButton {{ spacing: 9px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator, QTableView::indicator, QListView::indicator {{ width: 16px;
    height: 16px; border: 1px solid {t['border2']}; background: {t['surface']}; }}
QCheckBox::indicator, QTableView::indicator, QListView::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover, QTableView::indicator:hover {{
    border-color: {t['accent']}; }}
QCheckBox::indicator:checked, QTableView::indicator:checked, QListView::indicator:checked {{
    background: {t['accent']}; border-color: {t['accent']}; image: url("{a['check']}"); }}
QRadioButton::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; image: url("{a['dot']}"); }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ background: {t['surface2']};
    border-color: {t['border']}; }}

/* ---------- tables, lists, text */
QTableView, QTableWidget, QListView, QListWidget, QPlainTextEdit, QTextEdit {{ background: {t['surface']};
    border: 1px solid {t['border']}; border-radius: 10px; gridline-color: {t['border']};
    selection-background-color: {t['sel']}; selection-color: {t['sel_text']};
    alternate-background-color: {t['surface2']}; }}
QTableView::item, QListView::item {{ padding: 3px 6px; }}
QListView::item {{ padding: 6px 8px; border-radius: 6px; }}
QListView::item:selected {{ background: {t['sel']}; color: {t['sel_text']}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {t['header']}; color: {t['muted']}; border: none;
    border-bottom: 1px solid {t['border']}; border-right: 1px solid {t['border']}; padding: 6px 8px;
    font-size: 12px; font-weight: 600; }}
QHeaderView::section:last {{ border-right: none; }}
QTableCornerButton::section {{ background: {t['header']}; border: none; border-bottom: 1px solid {t['border']}; }}
#Log {{ font-family: "Menlo", "SF Mono", "Consolas", monospace; font-size: 12px; padding: 6px; }}

/* ---------- progress, splitters, scrollbars */
QProgressBar {{ background: {t['hover']}; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 4px; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 10px; }}
QSplitter::handle:vertical {{ height: 10px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle {{ background: {t['scroll']}; border-radius: 3px; }}
QScrollBar::handle:vertical {{ min-height: 30px; }}
QScrollBar::handle:horizontal {{ min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QMenu {{ background: {t['surface']}; border: 1px solid {t['border2']}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {t['accent_soft']}; }}
QStatusBar {{ background: {t['bg']}; color: {t['muted']}; }}
#ImageView {{ background: {t['view_bg']}; border: 1px solid {t['border']}; border-radius: 10px; }}
"""


def palette(mode: str) -> QPalette:
    t = TOKENS[mode]
    p = QPalette()
    c = lambda k: QColor(t[k])  # noqa: E731
    for role, key in [(QPalette.Window, 'bg'), (QPalette.WindowText, 'text'), (QPalette.Base, 'surface'),
                      (QPalette.AlternateBase, 'surface2'), (QPalette.Text, 'text'), (QPalette.Button, 'surface'),
                      (QPalette.ButtonText, 'text'), (QPalette.Highlight, 'accent'),
                      (QPalette.HighlightedText, 'accent_text'), (QPalette.ToolTipBase, 'tooltip'),
                      (QPalette.ToolTipText, 'tooltip_text'), (QPalette.PlaceholderText, 'muted'),
                      (QPalette.Link, 'accent'), (QPalette.Mid, 'border2'), (QPalette.Midlight, 'border'),
                      (QPalette.Dark, 'border2'), (QPalette.Light, 'surface'), (QPalette.Shadow, 'border2')]:
        p.setColor(role, c(key))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, c('muted'))
    return p


def tokens(mode: str) -> dict:
    return TOKENS[mode]


class ThemeManager(QObject):
    """Applies the chosen theme and follows the OS appearance in 'system' mode."""
    changed = Signal(str)      # effective mode: 'light' or 'dark'

    def __init__(self, app: QApplication):
        super().__init__(app)
        self.app = app
        self.choice = 'system'
        self.mode = 'light'
        app.setStyle('Fusion')
        hints = QGuiApplication.styleHints()
        if hasattr(hints, 'colorSchemeChanged'):
            hints.colorSchemeChanged.connect(lambda *_: self.choice == 'system' and self._apply())

    def set_theme(self, choice: str):
        self.choice = choice if choice in THEMES else 'system'
        hints = QGuiApplication.styleHints()
        if hasattr(hints, 'setColorScheme'):
            # also switches native dialogs (file pickers, message boxes) on macOS
            hints.setColorScheme({'light': Qt.ColorScheme.Light, 'dark': Qt.ColorScheme.Dark}
                                 .get(self.choice, Qt.ColorScheme.Unknown))
        self._apply()

    def _effective(self) -> str:
        if self.choice in ('light', 'dark'):
            return self.choice
        hints = QGuiApplication.styleHints()
        if hasattr(hints, 'colorScheme') and hints.colorScheme() == Qt.ColorScheme.Dark:
            return 'dark'
        return 'light'

    def _apply(self):
        self.mode = self._effective()
        self.app.setPalette(palette(self.mode))
        self.app.setStyleSheet(stylesheet(self.mode))
        self.changed.emit(self.mode)


def badge_icon(text: str, mode: str, size: int = 22) -> QIcon:
    """Round step badge for the sidebar (normal / checked states)."""
    t = TOKENS[mode]
    icon = QIcon()
    for state, fill, fg, ring in [(QIcon.Off, None, t['muted'], t['border2']),
                                  (QIcon.On, t['accent'], t['accent_text'], t['accent'])]:
        for scale in (1, 2):
            pm = QPixmap(size * scale, size * scale)
            pm.setDevicePixelRatio(scale)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(ring))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.setBrush(QColor(fill) if fill else Qt.NoBrush)
            p.drawEllipse(1, 1, size - 2, size - 2)
            f = QFont()
            f.setPixelSize(int(size * 0.5))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(fg))
            p.drawText(0, 0, size, size, Qt.AlignCenter, text)
            p.end()
            icon.addPixmap(pm, QIcon.Normal, state)
            icon.addPixmap(pm, QIcon.Active, state)
    return icon
