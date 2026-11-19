"""Sections tab: overview of the reference round with editable section rectangles."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                               QGraphicsRectItem, QGraphicsSimpleTextItem, QGraphicsView, QHBoxLayout,
                               QHeaderView, QLabel, QMessageBox, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..project import SectionSpec
from ..sections import detect_sections
from ..sources import open_source
from ..i18n import tr
from .widgets import ImageView, fit_spin, hint, page_layout, primary, to_display_u8

COLORS = ['#ff4d4d', '#4dd2ff', '#ffd24d', '#7dff4d', '#ff4dff', '#ff9f4d', '#4d79ff']


class _OverviewLoader(QThread):
    done = Signal(object, float, object, str)   # image, scale, bbox, error

    def __init__(self, path, channel, max_dim=4096):
        super().__init__()
        self.path, self.channel, self.max_dim = path, channel, max_dim

    def run(self):
        try:
            s = open_source(self.path)
            img, scale = s.overview(s.channel_index(self.channel), self.max_dim)
            self.done.emit(img, scale, s.bbox, '')
        except Exception as e:
            self.done.emit(None, 0.0, None, str(e))


class _Detector(QThread):
    done = Signal(object, str)

    def __init__(self, path, channel, kw):
        super().__init__()
        self.path, self.channel, self.kw = path, channel, kw

    def run(self):
        try:
            s = open_source(self.path)
            secs, _, _ = detect_sections(s, s.channel_index(self.channel), **self.kw)
            self.done.emit(secs, '')
        except Exception as e:
            self.done.emit(None, str(e))


class SectionRect(QGraphicsRectItem):
    def __init__(self, tab, sec: SectionSpec, rect: QRectF, color):
        super().__init__(QRectF(0, 0, rect.width(), rect.height()))
        self.tab, self.sec = tab, sec
        self.setPos(rect.topLeft())
        pen = QPen(QColor(color))
        pen.setWidth(2)
        pen.setCosmetic(True)
        self.setPen(pen)
        c = QColor(color)
        c.setAlpha(35)
        self.setBrush(QBrush(c))
        self.setFlags(QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemIsSelectable |
                      QGraphicsRectItem.ItemSendsGeometryChanges)
        self.label = QGraphicsSimpleTextItem(sec.name, self)
        self.label.setBrush(QBrush(QColor(color)))
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        self.label.setFont(f)
        self.label.setFlag(QGraphicsSimpleTextItem.ItemIgnoresTransformations)
        self.label.setPos(4, 4)

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.ItemPositionHasChanged:
            self.tab.rect_moved(self)
        return super().itemChange(change, value)


class OverviewView(ImageView):
    drawn = Signal(QRectF)

    def __init__(self):
        super().__init__()
        self.draw_mode = False
        self._origin = None
        self._rubber = None

    def set_draw_mode(self, on):
        self.draw_mode = on
        self.setDragMode(QGraphicsView.NoDrag if on else QGraphicsView.ScrollHandDrag)
        self.viewport().setCursor(Qt.CrossCursor if on else Qt.OpenHandCursor)

    def mousePressEvent(self, e):
        if self.draw_mode and e.button() == Qt.LeftButton:
            self._origin = self.mapToScene(e.position().toPoint())
            self._rubber = self.scene().addRect(QRectF(self._origin, self._origin), QPen(QColor('white'), 0, Qt.DashLine))
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.draw_mode and self._origin is not None:
            self._rubber.setRect(QRectF(self._origin, self.mapToScene(e.position().toPoint())).normalized())
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.draw_mode and self._origin is not None:
            r = self._rubber.rect()
            self.scene().removeItem(self._rubber)
            self._rubber, self._origin = None, None
            if r.width() > 3 and r.height() > 3:
                self.drawn.emit(r)
            return
        super().mouseReleaseEvent(e)


class SectionsTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._loading = False
        self.scale = 0.0
        self.bbox = None
        self._loader = None
        self._items = []
        lay = page_layout(self, tr('Coupes'),
                          tr('Chaque coupe produit sa propre image finale (recalage indépendant par coupe). '
                             'Détection automatique sur le canal de référence du round de référence ; vous pouvez '
                             'déplacer les rectangles, en dessiner, les renommer ou les désactiver. '
                             'Molette = zoom, glisser = déplacer la vue, double-clic = vue entière.'))

        top = QHBoxLayout()
        self.whole = QCheckBox(tr('Lame entière (une seule image, pas de découpage)'))
        self.whole.toggled.connect(self._whole_toggled)
        top.addWidget(self.whole)
        top.addStretch(1)
        top.addWidget(QLabel(tr('Canal affiché :')))
        self.channel = QComboBox()
        self.channel.currentTextChanged.connect(lambda _: self._loading or self.load_overview())
        top.addWidget(self.channel)
        reload_btn = QPushButton(tr('Recharger l\'aperçu'))
        reload_btn.clicked.connect(self.load_overview)
        top.addWidget(reload_btn)
        lay.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        self.view = OverviewView()
        self.view.set_placeholder(tr('Ajoutez des images (étape 1) pour afficher l\'aperçu du round de référence.'))
        self.view.drawn.connect(self._drawn)
        split.addWidget(self.view)
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([tr('Actif'), tr('Nom'), 'x', 'y', tr('largeur'), tr('hauteur')])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self._table_changed)
        self.table.itemSelectionChanged.connect(self._select_from_table)
        sl.addWidget(self.table, 1)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setVerticalSpacing(8)
        self.min_area = QDoubleSpinBox()
        self.min_area.setRange(0.001, 100)
        self.min_area.setValue(0.2)
        self.min_area.setSuffix(' mm²')
        fit_spin(self.min_area)
        form.addRow(tr('Aire minimale d\'une coupe :'), self.min_area)
        self.padding = QDoubleSpinBox()
        self.padding.setRange(0, 5000)
        self.padding.setValue(150)
        self.padding.setSuffix(' µm')
        fit_spin(self.padding)
        form.addRow(tr('Marge autour des coupes :'), self.padding)
        self.merge = QDoubleSpinBox()
        self.merge.setRange(0, 5000)
        self.merge.setValue(300)
        self.merge.setSuffix(' µm')
        fit_spin(self.merge)
        form.addRow(tr('Fusionner les fragments à moins de :'), self.merge)
        sl.addLayout(form)
        b1 = QHBoxLayout()
        self.detect_btn = primary(QPushButton(tr('Détecter automatiquement')))
        self.detect_btn.clicked.connect(self.detect)
        b1.addWidget(self.detect_btn)
        self.draw_btn = QPushButton(tr('Dessiner une coupe'))
        self.draw_btn.setCheckable(True)
        self.draw_btn.toggled.connect(self.view.set_draw_mode)
        b1.addWidget(self.draw_btn)
        sl.addLayout(b1)
        b2 = QHBoxLayout()
        for text, fn in [(tr('Supprimer'), self.delete), (tr('Tout supprimer'), self.clear), (tr('Renuméroter'), self.renumber)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            b2.addWidget(b)
        sl.addLayout(b2)
        self.status = hint()
        sl.addWidget(self.status)
        side.setMinimumWidth(360)
        side.setMaximumWidth(480)
        split.addWidget(side)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([1000, 380])
        lay.addWidget(split, 1)
        self._overview_key = None

    # ---------------------------------------------------------------- loading
    def load(self):
        p = self.win.project
        self._loading = True
        self.whole.setChecked(p.whole_slide)
        names = []
        if p.rounds:
            names = [c.channel for c in p.reference().channels]
        cur = self.channel.currentText() or p.reference_channel
        self.channel.clear()
        self.channel.addItems(names)
        if cur in names:
            self.channel.setCurrentText(cur)
        else:
            for n in names:
                if p.is_ref(n):
                    self.channel.setCurrentText(n)
                    break
        self._loading = False
        self._fill_table()
        key = (p.reference().path, self.channel.currentText()) if p.rounds else None
        if key != self._overview_key:
            self.load_overview()
        else:
            self._draw_rects()

    def load_overview(self):
        p = self.win.project
        if not p.rounds or not self.channel.currentText():
            self.view.set_image(None)
            self._overview_key = None
            return
        ref = p.reference()
        self._overview_key = (ref.path, self.channel.currentText())
        self.status.setText(tr('Chargement de l\'aperçu…'))
        self._loader = _OverviewLoader(ref.path, self.channel.currentText())
        self._loader.done.connect(self._overview_ready)
        self._loader.start()

    def _overview_ready(self, img, scale, bbox, err):
        if err:
            self.status.setText(tr('Aperçu impossible : {err}', err=err))
            return
        self.scale, self.bbox = scale, bbox
        self.view.set_image(to_display_u8(img, 1, 99.5))
        self.status.setText(tr('Aperçu : {w} × {h} px (échelle 1/{s:.0f}).', w=img.shape[1], h=img.shape[0], s=1 / scale))
        self._draw_rects()

    # ---------------------------------------------------------------- geometry
    def _to_scene(self, s: SectionSpec) -> QRectF:
        return QRectF((s.x - self.bbox.x) * self.scale, (s.y - self.bbox.y) * self.scale,
                      s.w * self.scale, s.h * self.scale)

    def _from_scene(self, r: QRectF):
        x = int(round(self.bbox.x + r.x() / self.scale))
        y = int(round(self.bbox.y + r.y() / self.scale))
        return x, y, int(round(r.width() / self.scale)), int(round(r.height() / self.scale))

    def _draw_rects(self):
        for it in self._items:
            self.view.scene().removeItem(it)
        self._items = []
        if not self.bbox or self.win.project.whole_slide:
            return
        for i, s in enumerate(self.win.project.sections):
            it = SectionRect(self, s, self._to_scene(s), COLORS[i % len(COLORS)])
            it.setOpacity(1.0 if s.enabled else 0.35)
            self.view.scene().addItem(it)
            self._items.append(it)

    def rect_moved(self, item: SectionRect):
        if self._loading or not self.scale:
            return
        r = QRectF(item.pos(), item.rect().size())
        item.sec.x, item.sec.y, _, _ = self._from_scene(r)
        self._fill_table()

    # ---------------------------------------------------------------- table
    def _fill_table(self):
        self._loading = True
        secs = self.win.project.sections
        self.table.setRowCount(len(secs))
        for i, s in enumerate(secs):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if s.enabled else Qt.Unchecked)
            self.table.setItem(i, 0, chk)
            for j, v in enumerate([s.name, s.x, s.y, s.w, s.h], 1):
                self.table.setItem(i, j, QTableWidgetItem(str(v)))
        self._loading = False

    def _table_changed(self, item):
        if self._loading:
            return
        s = self.win.project.sections[item.row()]
        c = item.column()
        try:
            if c == 0:
                s.enabled = item.checkState() == Qt.Checked
            elif c == 1:
                name = item.text().strip()
                if name and all(x.name != name for x in self.win.project.sections if x is not s):
                    s.name = name
            else:
                setattr(s, ['x', 'y', 'w', 'h'][c - 2], int(float(item.text())))
        except ValueError:
            pass
        self._fill_table()
        self._draw_rects()

    def _select_from_table(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        for i, it in enumerate(self._items):
            it.setSelected(i in rows)

    # ---------------------------------------------------------------- actions
    def _whole_toggled(self, v):
        if not self._loading:
            self.win.project.whole_slide = v
            self._draw_rects()

    def _drawn(self, r: QRectF):
        if not self.scale:
            return
        x, y, w, h = self._from_scene(r)
        secs = self.win.project.sections
        k = len(secs) + 1
        names = {s.name for s in secs}
        while f'S{k:02d}' in names:
            k += 1
        secs.append(SectionSpec(f'S{k:02d}', x, y, w, h))
        self.draw_btn.setChecked(False)
        self._fill_table()
        self._draw_rects()

    def detect(self):
        p = self.win.project
        if not p.rounds:
            return
        if p.sections and QMessageBox.question(self, tr('Détection'), tr('Remplacer les coupes existantes ?')) != QMessageBox.Yes:
            return
        self.detect_btn.setEnabled(False)
        self.status.setText(tr('Détection en cours…'))
        kw = dict(min_area_mm2=self.min_area.value(), padding_um=self.padding.value(), merge_um=self.merge.value(),
                  pixel_size_um=p.pixel_size_um or None)
        self._det = _Detector(p.reference().path, self.channel.currentText() or p.reference_channel, kw)
        self._det.done.connect(self._detected)
        self._det.start()

    def _detected(self, secs, err):
        self.detect_btn.setEnabled(True)
        if err:
            QMessageBox.warning(self, tr('Détection'), err)
            return
        self.win.project.sections = secs
        self.win.project.whole_slide = False
        self._loading = True
        self.whole.setChecked(False)
        self._loading = False
        self.status.setText(tr('{n} coupe(s) détectée(s).', n=len(secs)))
        self._fill_table()
        self._draw_rects()

    def delete(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        rows = rows or [i for i, it in enumerate(self._items) if it.isSelected()][::-1]
        for r in rows:
            self.win.project.sections.pop(r)
        self._fill_table()
        self._draw_rects()

    def clear(self):
        self.win.project.sections = []
        self._fill_table()
        self._draw_rects()

    def renumber(self):
        secs = self.win.project.sections
        secs.sort(key=lambda s: (s.x, s.y) if (self.bbox and self.bbox.w >= self.bbox.h) else (s.y, s.x))
        for i, s in enumerate(secs, 1):
            s.name = f'S{i:02d}'
        self._fill_table()
        self._draw_rects()
