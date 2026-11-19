"""Images, Markers and Options pages. Every edit is written to the project immediately."""
from __future__ import annotations

import os
import shutil

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QCompleter, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QPushButton, QRadioButton, QScrollArea, QSpinBox,
                               QSplitter, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import make_round
from ..i18n import tr
from ..sources import SUPPORTED_EXT, open_source
from .widgets import PathPicker, fit_spin, hint, page_layout, primary


def img_filter():
    return tr('Images (*.czi *.tif *.tiff);;Tous les fichiers (*)')


def _form(box):
    f = QFormLayout(box)
    f.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    f.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
    f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
    f.setHorizontalSpacing(16)
    f.setVerticalSpacing(10)
    return f


def _table(cols, headers):
    t = QTableWidget(0, cols)
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setShowGrid(False)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setDefaultSectionSize(30)
    return t


# ============================================================================ Images
class ImagesTab(QWidget):
    roundsChanged = Signal()

    def __init__(self, win):
        super().__init__()
        self.win = win
        self._info = {}   # path -> source info dict
        lay = page_layout(self, tr('Images'),
                          tr('Ajoutez une image par round (CZI ou TIFF). Les canaux et la taille de pixel sont lus '
                             'dans les métadonnées. L\'ordre de la liste = l\'ordre des canaux dans l\'image '
                             'finale. Vous pouvez aussi glisser-déposer des fichiers ou un dossier dans la fenêtre.'))

        btns = QHBoxLayout()
        add = primary(QPushButton(tr('＋ Ajouter des images…')))
        add.clicked.connect(self.add_dialog)
        btns.addWidget(add)
        for text, fn in [(tr('Retirer'), self.remove), (tr('▲ Monter'), lambda: self.move(-1)),
                         (tr('▼ Descendre'), lambda: self.move(1)),
                         (tr('★ Définir comme référence'), self.set_reference)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

        self.table = _table(6, [tr('Actif'), tr('Nom du round'), tr('Canaux (ordre du fichier)'),
                                tr('Taille (px)'), tr('Pixel (µm)'), tr('Fichier')])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._item_changed)
        lay.addWidget(self.table, 1)

        form_box = QGroupBox(tr('Référence et fond'))
        form = _form(form_box)
        self.ref_channel = QComboBox()
        self.ref_channel.setEditable(True)
        self.ref_channel.setFixedWidth(200)
        self.ref_channel.currentTextChanged.connect(self._ref_channel_changed)
        form.addRow(tr('Canal de référence (recalage) :'), self.ref_channel)
        self.bg = PathPicker('file', tr('Image de fond'), img_filter())
        self.bg.changed.connect(self._bg_changed)
        bgrow = QHBoxLayout()
        bgrow.setSpacing(6)
        bgrow.addWidget(self.bg, 1)
        clear = QPushButton(tr('Aucun'))
        clear.clicked.connect(lambda: (self.bg.setText(''), self._bg_changed('')))
        bgrow.addWidget(clear)
        form.addRow(tr('Image de fond (optionnel) :'), bgrow)
        self.bg_mult = QDoubleSpinBox()
        self.bg_mult.setRange(0, 20)
        self.bg_mult.setSingleStep(0.1)
        fit_spin(self.bg_mult)
        self.bg_mult.valueChanged.connect(lambda v: setattr(self.win.project, 'background_multiplier', v))
        form.addRow(tr('Multiplicateur du fond :'), self.bg_mult)
        self.px = QDoubleSpinBox()
        self.px.setDecimals(4)
        self.px.setRange(0, 100)
        self.px.setSpecialValueText(tr('auto (métadonnées)'))
        fit_spin(self.px)
        self.px.valueChanged.connect(lambda v: setattr(self.win.project, 'pixel_size_um', v))
        form.addRow(tr('Taille de pixel (µm) :'), self.px)
        lay.addWidget(form_box)
        self._loading = False

    # ---------------------------------------------------------------- data
    def info(self, path):
        if path not in self._info:
            try:
                s = open_source(path)
                self._info[path] = s.info()
                s.close()
            except Exception as e:
                self._info[path] = {'error': str(e)}
        return self._info[path]

    def load(self):
        p = self.win.project
        self._loading = True
        self.table.setRowCount(0)
        bold = QFont()
        bold.setBold(True)
        for i, r in enumerate(p.rounds):
            self.table.insertRow(i)
            info = self.info(r.path)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if r.enabled else Qt.Unchecked)
            self.table.setItem(i, 0, chk)
            name = QTableWidgetItem(('★ ' if i == p.reference_round else '') + r.label)
            if i == p.reference_round:
                name.setFont(bold)
                name.setToolTip(tr('Round de référence : tous les autres sont recalés sur lui.'))
            self.table.setItem(i, 1, name)
            chans = ', '.join(c.channel for c in r.channels)
            if 'error' in info:
                size, pxs = tr('erreur'), info['error']
            else:
                bb = info['bbox']
                size = f'{bb[2]} × {bb[3]}'
                pxs = f'{info["pixel_size_um"]:.4f}' if info.get('pixel_size_um') else '?'
            for col, text in [(2, chans), (3, size), (4, pxs), (5, r.path)]:
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if not os.path.exists(r.path):
                    it.setForeground(QBrush(QColor('#e05252')))
                    it.setToolTip(tr('Fichier introuvable (partage réseau monté ?)'))
                self.table.setItem(i, col, it)
        names = []
        for r in p.rounds:
            for c in r.channels:
                if c.channel not in names:
                    names.append(c.channel)
        self.ref_channel.clear()
        self.ref_channel.addItems(names or ['DAPI'])
        self.ref_channel.setCurrentText(p.reference_channel)
        self.bg.setText(p.background_path)
        self.bg_mult.setValue(p.background_multiplier)
        self.px.setValue(p.pixel_size_um or 0)
        self._loading = False

    def _item_changed(self, item):
        if self._loading:
            return
        p = self.win.project
        r = p.rounds[item.row()]
        if item.column() == 0:
            r.enabled = item.checkState() == Qt.Checked
            self.roundsChanged.emit()
        elif item.column() == 1:
            new = item.text().replace('★', '').strip()
            if new and new != r.label:
                if any(x.label == new for x in p.rounds if x is not r):
                    QMessageBox.warning(self, tr('Nom déjà utilisé'),
                                        tr('Un autre round s\'appelle déjà « {name} ».', name=new))
                else:
                    r.label = new
            self.load()
            self.roundsChanged.emit()

    def add_files(self, paths):
        p = self.win.project
        added, errors = 0, []
        existing = {r.path for r in p.rounds}
        for path in paths:
            if not path.lower().endswith(SUPPORTED_EXT):
                continue
            path = os.path.abspath(path)
            if path in existing:
                continue
            try:
                r = make_round(path, p.reference_channel)
            except Exception as e:
                errors.append(f'{os.path.basename(path)} : {e}')
                continue
            labels = {x.label for x in p.rounds}
            base, k = r.label, 2
            while r.label in labels:
                r.label = f'{base}_{k}'
                k += 1
            p.rounds.append(r)
            added += 1
        if errors:
            QMessageBox.warning(self, tr('Fichiers non lus'), '\n'.join(errors))
        if added:
            self.load()
            self.roundsChanged.emit()

    def add_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr('Ajouter des images (rounds)'), self.win.last_dir(),
                                                img_filter())
        if paths:
            self.win.set_last_dir(os.path.dirname(paths[0]))
            self.add_files(sorted(paths))

    def _row(self):
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def remove(self):
        i = self._row()
        if i < 0:
            return
        p = self.win.project
        p.rounds.pop(i)
        if p.reference_round >= len(p.rounds):
            p.reference_round = max(0, len(p.rounds) - 1)
        elif i < p.reference_round:
            p.reference_round -= 1
        self.load()
        self.roundsChanged.emit()

    def move(self, d):
        i = self._row()
        p = self.win.project
        j = i + d
        if i < 0 or not (0 <= j < len(p.rounds)):
            return
        p.rounds[i], p.rounds[j] = p.rounds[j], p.rounds[i]
        if p.reference_round in (i, j):
            p.reference_round = j if p.reference_round == i else i
        self.load()
        self.table.selectRow(j)
        self.roundsChanged.emit()

    def set_reference(self):
        i = self._row()
        if i >= 0:
            self.win.project.reference_round = i
            self.load()
            self.roundsChanged.emit()

    def _ref_channel_changed(self, t):
        if not self._loading and t.strip():
            self.win.project.reference_channel = t.strip()
            self.roundsChanged.emit()

    def _bg_changed(self, path):
        p = self.win.project
        if path and not os.path.exists(path):
            QMessageBox.warning(self, tr('Fichier introuvable'), path)
            return
        p.background_path = path
        if path:
            info = self.info(path)
            if 'error' in info:
                QMessageBox.warning(self, tr('Fond illisible'), info['error'])
            else:
                missing = [c for r in p.rounds for c in r.channels
                           if c.marker and c.channel.lower() not in [x.lower() for x in info['channels']]]
                if missing:
                    QMessageBox.information(self, tr('Fond'), tr(
                        'Canaux du fond : {chans}\nLes canaux absents du fond ne seront pas corrigés.',
                        chans=', '.join(info['channels'])))


# ============================================================================ Markers
class MarkersTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._loading = False
        lay = page_layout(self, tr('Marqueurs'),
                          tr('Indiquez le marqueur imagé dans chaque canal de chaque round. Case vide = canal non '
                             'exporté. Les cases grisées n\'existent pas dans le fichier. Les colonnes sont les noms '
                             'réels des canaux lus dans les fichiers (pas besoin de connaître leur ordre).'))
        b = QHBoxLayout()
        for text, fn in [(tr('Importer un CSV…'), self.import_csv), (tr('Exporter en CSV…'), self.export_csv)]:
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            b.addWidget(btn)
        b.addStretch(1)
        lay.addLayout(b)
        split = QSplitter(Qt.Horizontal)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.itemChanged.connect(self._changed)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        split.addWidget(self.table)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel()
        self.summary.setObjectName('SectionTitle')
        rl.addWidget(self.summary)
        self.preview = QListWidget()
        rl.addWidget(self.preview, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 300])
        lay.addWidget(split, 1)
        self.columns = []

    def load(self):
        p = self.win.project
        self._loading = True
        cols = []
        for r in p.rounds:
            for c in r.channels:
                if c.channel not in cols:
                    cols.append(c.channel)
        self.columns = cols
        self.table.clear()
        self.table.setColumnCount(len(cols))
        self.table.setRowCount(len(p.rounds))
        self.table.setHorizontalHeaderLabels([c + (tr(' (réf.)') if p.is_ref(c) else '') for c in cols])
        self.table.setVerticalHeaderLabels([('★ ' if i == p.reference_round else '') + r.label
                                            for i, r in enumerate(p.rounds)])
        grey = QBrush(QColor(128, 128, 128, 45))
        all_markers = sorted({c.marker for r in p.rounds for c in r.channels if c.marker})
        for i, r in enumerate(p.rounds):
            have = {c.channel: c for c in r.channels}
            for j, col in enumerate(cols):
                if col in have:
                    it = QTableWidgetItem(have[col].marker)
                    pos = [c.channel for c in r.channels].index(col) + 1
                    it.setToolTip(tr('{label} — canal {pos} du fichier : {col}', label=r.label, pos=pos, col=col))
                    if not r.enabled:
                        it.setForeground(QBrush(QColor('#888')))
                else:
                    it = QTableWidgetItem('—')
                    it.setFlags(Qt.NoItemFlags)
                    it.setBackground(grey)
                    it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, j, it)
        self.table.setItemDelegate(_CompleterDelegate(all_markers, self.table))
        self._loading = False
        self.update_preview()

    def _changed(self, item):
        if self._loading:
            return
        p = self.win.project
        r = p.rounds[item.row()]
        col = self.columns[item.column()]
        for c in r.channels:
            if c.channel == col:
                c.marker = item.text().strip()
        self.update_preview()

    def update_preview(self):
        p = self.win.project
        self.preview.clear()
        try:
            chans = p.output_channels() if p.rounds else []
        except ValueError:
            chans = []
        names = [p.channel_display_name(r, c) for r, c in chans]
        dup = {n for n in names if names.count(n) > 1}
        for i, n in enumerate(names, 1):
            self.preview.addItem(f'{i:>2}.  {n}' + (tr('   ⚠ doublon') if n in dup else ''))
        self.summary.setText(tr('Image finale : {n} canaux', n=len(names)))

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Importer channel_name.csv'), self.win.last_dir(),
                                              'CSV (*.csv)')
        if not path:
            return
        warnings = self.win.project.import_csv(path)
        self.load()
        if warnings:
            QMessageBox.warning(self, tr('Import CSV'),
                                tr('Import effectué avec des avertissements :') + '\n\n' + '\n'.join(warnings))

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Exporter le CSV'), os.path.join(self.win.last_dir(),
                                              'channel_name.csv'), 'CSV (*.csv)')
        if path:
            self.win.project.export_csv(path)


class _CompleterDelegate(QStyledItemDelegate):
    def __init__(self, words, parent):
        super().__init__(parent)
        self.words = words

    def createEditor(self, parent, option, index):
        ed = QLineEdit(parent)
        comp = QCompleter(self.words, ed)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        ed.setCompleter(comp)
        return ed


# ============================================================================ Options
class OptionsTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._loading = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget()
        scroll.setWidget(inner)
        lay = page_layout(inner, tr('Options'),
                          tr('Emplacement et format des images finales, méthode de recalage et ressources de calcul.'))
        cols = QHBoxLayout()
        cols.setSpacing(16)
        col1, col2 = QVBoxLayout(), QVBoxLayout()
        col1.setSpacing(4)
        col2.setSpacing(4)
        cols.addLayout(col1, 1)
        cols.addLayout(col2, 1)
        lay.addLayout(cols, 1)

        # --- output
        g = QGroupBox(tr('Image(s) finale(s)'))
        f = _form(g)
        self.out_dir = PathPicker('dir', tr('Dossier de sortie'))
        self.out_dir.changed.connect(lambda t: self._set('output', 'directory', t))
        f.addRow(tr('Dossier de sortie :'), self.out_dir)
        self.basename = QLineEdit()
        self.basename.editingFinished.connect(lambda: self._set('output', 'basename', self.basename.text().strip()
                                                                or 'final_image'))
        f.addRow(tr('Nom de base :'), self.basename)
        self.name_hint = hint()
        f.addRow('', self.name_hint)
        self.pyramidal = QCheckBox(tr('Pyramidale (recommandé pour QuPath)'))
        self.pyramidal.toggled.connect(lambda v: self._set('output', 'pyramidal', v))
        f.addRow(self.pyramidal)
        self.compression = QComboBox()
        for key, label in [('zlib', tr('zlib (recommandé)')), ('lzw', 'LZW'), ('none', tr('aucune'))]:
            self.compression.addItem(label, key)
        self.compression.currentIndexChanged.connect(
            lambda i: self._set('output', 'compression', self.compression.itemData(i)))
        f.addRow(tr('Compression (sans perte) :'), self.compression)
        self.downscale = QDoubleSpinBox()
        self.downscale.setRange(0.05, 1.0)
        self.downscale.setSingleStep(0.05)
        fit_spin(self.downscale)
        self.downscale.valueChanged.connect(lambda v: self._set('output', 'downscale', v))
        f.addRow(tr('Résolution de sortie (1 = pleine) :'), self.downscale)
        self.keep_ref = QCheckBox(tr('Garder le canal de référence de chaque round'))
        self.keep_ref.toggled.connect(lambda v: self._set('output', 'keep_all_reference', v))
        f.addRow(self.keep_ref)
        self.fullname = QCheckBox(tr('Noms complets « marqueur|canal|round »'))
        self.fullname.toggled.connect(lambda v: self._set('output', 'fullname', v))
        f.addRow(self.fullname)
        self.qc = QCheckBox(tr('Enregistrer le contrôle qualité (PNG + CSV)'))
        self.qc.toggled.connect(lambda v: self._set('output', 'qc', v))
        f.addRow(self.qc)
        self.markers_csv = QCheckBox(tr('Enregistrer le tableau des marqueurs (CSV) avec le QC'))
        self.markers_csv.setToolTip(tr('Copie du tableau de la page Marqueurs dans le dossier <nom>_QC, '
                                       'réimportable pour une autre lame (Marqueurs → Importer un CSV).'))
        self.markers_csv.toggled.connect(lambda v: self._set('output', 'markers_csv', v))
        f.addRow(self.markers_csv)
        col1.addWidget(g)

        # --- performance
        g = QGroupBox(tr('Performances'))
        f = _form(g)
        self.workers = QSpinBox()
        self.workers.setRange(0, 64)
        self.workers.setSpecialValueText(tr('auto ({n})', n=max(1, min((os.cpu_count() or 4) - 2, 12))))
        fit_spin(self.workers)
        self.workers.valueChanged.connect(lambda v: self._set('performance', 'workers', v))
        f.addRow(tr('Processus parallèles :'), self.workers)
        self.temp = PathPicker('dir', tr('Dossier temporaire'))
        self.temp.changed.connect(self._temp_changed)
        f.addRow(tr('Dossier temporaire :'), self.temp)
        self.temp_hint = hint()
        f.addRow('', self.temp_hint)
        col1.addWidget(g)
        col1.addStretch(1)

        # --- registration
        g = QGroupBox(tr('Recalage'))
        f = _form(g)
        self.precise = QRadioButton(tr('Précis : mesures à 1/2 résolution, 2 itérations (≈ 0,1–0,5 µm)'))
        self.fast = QRadioButton(tr('Rapide : mesures à 1/4 résolution, 1 itération (≈ 1–2 µm)'))
        self.precise.toggled.connect(lambda v: v and self._set('registration', 'mode', 'precise'))
        self.fast.toggled.connect(lambda v: v and self._set('registration', 'mode', 'fast'))
        f.addRow(self.precise)
        f.addRow(self.fast)
        self.rotation = QCheckBox(tr('Corriger aussi la rotation (rigide)'))
        self.rotation.toggled.connect(lambda v: self._set('registration', 'use_rotation', v))
        f.addRow(self.rotation)
        self.nonrigid = QCheckBox(tr('Corriger les déformations locales du tissu (non rigide)'))
        self.nonrigid.setToolTip(tr('Mesure le décalage local sur une grille de points et corrige les étirements, '
                                    'glissements ou plis du tissu entre les rounds.'))
        self.nonrigid.toggled.connect(lambda v: self._set('registration', 'nonrigid', v))
        f.addRow(self.nonrigid)
        self.grid = QDoubleSpinBox()
        self.grid.setRange(100, 5000)
        self.grid.setSingleStep(50)
        self.grid.setSuffix(' µm')
        fit_spin(self.grid)
        self.grid.valueChanged.connect(lambda v: self._set('registration', 'grid_spacing_um', v))
        f.addRow(tr('Espacement de la grille de déformation :'), self.grid)
        self.margin = QDoubleSpinBox()
        self.margin.setRange(10, 20000)
        self.margin.setSuffix(' µm')
        fit_spin(self.margin)
        self.margin.valueChanged.connect(lambda v: self._set('registration', 'search_margin_um', v))
        f.addRow(tr('Déplacement max. entre rounds :'), self.margin)
        self.patches = QSpinBox()
        self.patches.setRange(3, 200)
        fit_spin(self.patches)
        self.patches.valueChanged.connect(lambda v: self._set('registration', 'max_patches', v))
        f.addRow(tr('Nombre de patchs d\'affinage :'), self.patches)
        self.patch_size = QSpinBox()
        self.patch_size.setRange(128, 4096)
        self.patch_size.setSingleStep(128)
        self.patch_size.setSuffix(' px')
        fit_spin(self.patch_size)
        self.patch_size.valueChanged.connect(lambda v: self._set('registration', 'patch_size', v))
        f.addRow(tr('Taille des patchs :'), self.patch_size)
        col2.addWidget(g)
        col2.addStretch(1)

    def _set(self, group, key, value):
        if self._loading:
            return
        setattr(getattr(self.win.project, group), key, value)
        self._update_hints()

    def _temp_changed(self, t):
        self._set('performance', 'temp_dir', t)

    def _update_hints(self):
        p = self.win.project
        self.name_hint.setText('→ ' + os.path.basename(p.output_path('S01')) + ', '
                               + os.path.basename(p.output_path('S02')) + ' …')
        d = p.temp_dir()
        try:
            free = shutil.disk_usage(d).free / 1e9
            txt = tr('{d} — {free:.0f} Go libres.', d=d, free=free)
        except OSError:
            txt = tr('{d} — inaccessible.', d=d)
        self.temp_hint.setText(txt + ' ' + tr('Utilisez un disque local rapide (pas OneDrive ni le réseau) : '
                                              'il faut ~2 octets × canaux × pixels de la plus grande coupe.'))

    def load(self):
        p = self.win.project
        self._loading = True
        o, r, perf = p.output, p.registration, p.performance
        self.out_dir.setText(o.directory)
        self.basename.setText(o.basename)
        self.pyramidal.setChecked(o.pyramidal)
        i = self.compression.findData(o.compression)
        self.compression.setCurrentIndex(max(i, 0))
        self.downscale.setValue(o.downscale)
        self.keep_ref.setChecked(o.keep_all_reference)
        self.fullname.setChecked(o.fullname)
        self.qc.setChecked(o.qc)
        self.markers_csv.setChecked(o.markers_csv)
        (self.precise if r.mode == 'precise' else self.fast).setChecked(True)
        self.rotation.setChecked(r.use_rotation)
        self.nonrigid.setChecked(r.nonrigid)
        self.grid.setValue(r.grid_spacing_um)
        self.margin.setValue(r.search_margin_um)
        self.patches.setValue(r.max_patches)
        self.patch_size.setValue(r.patch_size)
        self.workers.setValue(perf.workers)
        self.temp.setText(perf.temp_dir)
        self._loading = False
        self._update_hints()
