"""Small reusable Qt widgets and helpers."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractSpinBox, QFileDialog, QFrame, QGraphicsPixmapItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..i18n import tr


def to_display_u8(img: np.ndarray, lo_pct=0.5, hi_pct=99.7) -> np.ndarray:
    f = img.astype(np.float32)
    nz = f[f > 0]
    if nz.size < 10:
        return np.zeros(img.shape, np.uint8)
    lo, hi = np.percentile(nz, [lo_pct, hi_pct])
    return (np.clip((f - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)


def to_qimage(arr: np.ndarray) -> QImage:
    arr = np.ascontiguousarray(arr)
    if arr.ndim == 2:
        if arr.dtype != np.uint8:
            arr = to_display_u8(arr)
        h, w = arr.shape
        return QImage(arr.data, w, h, w, QImage.Format_Grayscale8).copy()
    h, w, c = arr.shape
    arr = np.ascontiguousarray(arr[:, :, :3].astype(np.uint8))
    return QImage(arr.data, w, h, 3 * w, QImage.Format_RGB888).copy()


# ---------------------------------------------------------------------------- helpers
def primary(btn: QPushButton) -> QPushButton:
    btn.setProperty('primary', True)
    return btn


def danger(btn: QPushButton) -> QPushButton:
    btn.setProperty('danger', True)
    return btn


def hint(text='') -> QLabel:
    lab = QLabel(text)
    lab.setObjectName('Hint')
    lab.setWordWrap(True)
    return lab


def fit_spin(sb: QAbstractSpinBox, extra_texts=()) -> QAbstractSpinBox:
    """Give a spin box a fixed width large enough for its longest possible text (special value, suffix…)."""
    fm = sb.fontMetrics()
    texts = [sb.specialValueText(), *extra_texts]
    if hasattr(sb, 'textFromValue'):
        texts += [sb.prefix() + sb.textFromValue(v) + sb.suffix() for v in (sb.minimum(), sb.maximum())]
    w = max(fm.horizontalAdvance(t) for t in texts if t is not None) if texts else 60
    sb.setFixedWidth(max(110, w + 64))
    sb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    sb.lineEdit().setTextMargins(6, 0, 0, 0)   # stylesheet padding does not reach the inner line edit
    return sb


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = '', parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(4)
        t = QLabel(title)
        t.setObjectName('PageTitle')
        lay.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName('PageSubtitle')
            s.setWordWrap(True)
            lay.addWidget(s)


def page_layout(widget: QWidget, title: str, subtitle: str = '') -> QVBoxLayout:
    lay = QVBoxLayout(widget)
    lay.setContentsMargins(28, 22, 28, 22)
    lay.setSpacing(12)
    lay.addWidget(PageHeader(title, subtitle))
    return lay


def card(layout_cls=QVBoxLayout):
    f = QFrame()
    f.setObjectName('Card')
    lay = layout_cls(f)
    lay.setContentsMargins(14, 12, 14, 12)
    return f, lay


# ---------------------------------------------------------------------------- image view
class ImageView(QGraphicsView):
    """Zoomable (wheel) / pannable (drag) image view, with a message when empty."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('ImageView')
        self.setScene(QGraphicsScene(self))
        self._pix = QGraphicsPixmapItem()
        self._pix.setTransformationMode(Qt.SmoothTransformation)
        self.scene().addItem(self._pix)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFrameShape(QFrame.NoFrame)
        self._has_image = False
        self._auto_fit = True
        self._placeholder = ''

    def set_placeholder(self, text: str):
        self._placeholder = text
        self.viewport().update()

    def set_image(self, arr: np.ndarray | None, fit=True, placeholder: str | None = None):
        if placeholder is not None:
            self._placeholder = placeholder
        if arr is None:
            self._pix.setPixmap(QPixmap())
            self._has_image = False
            self.viewport().update()
            return
        self._pix.setPixmap(QPixmap.fromImage(to_qimage(arr)))
        self.scene().setSceneRect(QRectF(self._pix.pixmap().rect()))
        self._has_image = True
        if fit:
            self.fit()

    def fit(self):
        if self._has_image:
            self._auto_fit = True
            self.fitInView(self._pix, Qt.KeepAspectRatio)

    def wheelEvent(self, e):
        f = 1.25 if e.angleDelta().y() > 0 else 0.8
        self._auto_fit = False
        self.scale(f, f)

    def mouseDoubleClickEvent(self, e):
        self.fit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._auto_fit:
            self.fit()

    def showEvent(self, e):
        super().showEvent(e)
        if self._auto_fit:
            self.fit()

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self._has_image and self._placeholder:
            p = QPainter(self.viewport())
            p.setPen(QColor(150, 155, 165))
            r = self.viewport().rect().adjusted(30, 30, -30, -30)
            p.drawText(r, Qt.AlignCenter | Qt.TextWordWrap, self._placeholder)
            p.end()


class PathPicker(QWidget):
    changed = Signal(str)

    def __init__(self, mode='dir', caption='', filter_='', parent=None):
        super().__init__(parent)
        self.mode, self.caption, self.filter = mode, caption, filter_
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setMinimumWidth(220)
        self.edit.editingFinished.connect(lambda: self.changed.emit(self.edit.text().strip()))
        btn = QPushButton(tr('Parcourir…'))
        btn.clicked.connect(self._browse)
        lay.addWidget(self.edit, 1)
        lay.addWidget(btn)

    def _browse(self):
        start = self.edit.text().strip()
        if self.mode == 'dir':
            p = QFileDialog.getExistingDirectory(self, self.caption, start)
        else:
            p, _ = QFileDialog.getOpenFileName(self, self.caption, start, self.filter)
        if p:
            self.edit.setText(p)
            self.changed.emit(p)

    def text(self):
        return self.edit.text().strip()

    def setText(self, t):
        self.edit.setText(t or '')
