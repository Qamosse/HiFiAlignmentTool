"""Run page (execution, log, QC) and Batch page."""
from __future__ import annotations

import copy
import csv
import os
import threading
import time
import traceback

import cv2
import numpy as np
from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..i18n import tr
from ..pipeline import Callbacks, Cancelled, Pipeline
from ..project import PROJECT_EXT, Project
from ..registration import RegistrationResult
from .widgets import ImageView, card, danger, hint, page_layout, primary

WARN_BG = QColor(245, 158, 11, 60)


def _fmt_elapsed(sec):
    return tr('{m} min {s:02d} s', m=int(sec // 60), s=int(sec % 60))


class PipelineThread(QThread):
    log = Signal(str)
    progress = Signal(str, int, int)
    qc = Signal(str, str, object)
    project_started = Signal(int)
    project_finished = Signal(int, bool, str)      # index, ok, message
    all_done = Signal()

    def __init__(self, projects: list[Project], do_register=True, do_write=True):
        super().__init__()
        self.projects = projects
        self.do_register, self.do_write = do_register, do_write
        self.cancel = threading.Event()
        self.results = {}

    def run(self):
        cb = Callbacks(log=self.log.emit, progress=self.progress.emit,
                       qc=lambda s, r, res: self.qc.emit(s, r, res))
        for i, p in enumerate(self.projects):
            if self.cancel.is_set():
                break
            self.project_started.emit(i)
            try:
                pl = Pipeline(p, cb, self.cancel)
                outs = pl.run(do_register=self.do_register, do_write=self.do_write)
                self.results[i] = outs
                self.project_finished.emit(i, True, '\n'.join(outs))
            except Cancelled:
                self.log.emit(tr('⛔ Annulé.'))
                self.project_finished.emit(i, False, tr('Annulé'))
                break
            except Exception as e:
                self.log.emit(tr('❌ Erreur : {e}', e=e) + f'\n{traceback.format_exc()}')
                self.project_finished.emit(i, False, str(e))
        self.all_done.emit()


class RunTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.thread = None
        self.qc_data = {}   # (section, round) -> RegistrationResult
        lay = page_layout(self, tr('Exécution et contrôle qualité'),
                          tr('« Recaler seulement » permet de vérifier le QC avant d\'écrire les images ; '
                             '« Générer les images » réutilise ensuite ce recalage.'))

        b = QHBoxLayout()
        self.btn_all = primary(QPushButton(tr('▶  Tout lancer (recalage + images)')))
        self.btn_all.clicked.connect(lambda: self.start(True, True))
        self.btn_reg = QPushButton(tr('Recaler seulement'))
        self.btn_reg.setToolTip(tr('Calcule le recalage et le QC sans écrire les images finales.'))
        self.btn_reg.clicked.connect(lambda: self.start(True, False))
        self.btn_write = QPushButton(tr('Générer les images'))
        self.btn_write.setToolTip(tr('Écrit les images finales en réutilisant le recalage existant.'))
        self.btn_write.clicked.connect(lambda: self.start(False, True))
        self.btn_cancel = danger(QPushButton(tr('Annuler')))
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel)
        self.btn_open = QPushButton(tr('Ouvrir le dossier de sortie'))
        self.btn_open.clicked.connect(self.open_output)
        for w in (self.btn_all, self.btn_reg, self.btn_write, self.btn_cancel):
            b.addWidget(w)
        b.addStretch(1)
        b.addWidget(self.btn_open)
        lay.addLayout(b)

        prog, pl = card()
        row = QHBoxLayout()
        self.stage = QLabel(tr('Prêt.'))
        self.stage.setObjectName('StageLabel')
        self.elapsed = QLabel('')
        self.elapsed.setObjectName('Elapsed')
        row.addWidget(self.stage, 1)
        row.addWidget(self.elapsed)
        pl.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setValue(0)
        pl.addWidget(self.bar)
        lay.addWidget(prog)

        vsplit = QSplitter(Qt.Vertical)
        hsplit = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        title = QLabel(tr('Contrôle qualité du recalage'))
        title.setObjectName('SectionTitle')
        lv.addWidget(title)
        lv.addWidget(hint(tr('Cliquez une ligne pour voir la superposition. Lignes orange : à vérifier.')))
        self.qc_table = QTableWidget(0, 10)
        self.qc_table.setHorizontalHeaderLabels([tr('Coupe'), tr('Round'), tr('Décalage x/y (µm)'),
                                                 tr('Rotation (°)'), tr('Corr. avant'), tr('Corr. après'),
                                                 tr('Patchs rigides'), tr('Déformation max (µm)'),
                                                 tr('Points de grille'), tr('Alertes')])
        self.qc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.qc_table.horizontalHeader().setStretchLastSection(True)
        self.qc_table.verticalHeader().setVisible(False)
        self.qc_table.setShowGrid(False)
        self.qc_table.verticalHeader().setDefaultSectionSize(28)
        self.qc_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.qc_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.qc_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.qc_table.itemSelectionChanged.connect(self._show_qc)
        lv.addWidget(self.qc_table, 1)
        hsplit.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        tog = QHBoxLayout()
        tog.setSpacing(0)
        self.r_before = QPushButton(tr('Avant'))
        self.r_after = QPushButton(tr('Après'))
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for bt in (self.r_before, self.r_after):
            bt.setCheckable(True)
            grp.addButton(bt)
            tog.addWidget(bt)
        self.r_after.setChecked(True)
        self.r_before.toggled.connect(self._show_qc)
        tog.addStretch(1)
        legend = QLabel('<span style="color:#e040e0">■</span> ' + tr('référence') +
                        '&nbsp;&nbsp;<span style="color:#40d040">■</span> ' + tr('round') +
                        '&nbsp;&nbsp;<span style="color:#c8c8c8">■</span> ' + tr('superposé'))
        legend.setObjectName('Hint')
        tog.addWidget(legend)
        rv.addLayout(tog)
        self.qc_view = ImageView()
        self.qc_view.set_placeholder(tr('Lancez un recalage pour voir ici la superposition avant/après de chaque '
                                        'round.'))
        rv.addWidget(self.qc_view, 1)
        hsplit.addWidget(right)
        hsplit.setStretchFactor(0, 3)
        hsplit.setStretchFactor(1, 2)
        hsplit.setSizes([700, 500])
        vsplit.addWidget(hsplit)

        logw = QWidget()
        ll = QVBoxLayout(logw)
        ll.setContentsMargins(0, 0, 0, 0)
        t2 = QLabel(tr('Journal'))
        t2.setObjectName('SectionTitle')
        ll.addWidget(t2)
        self.log = QPlainTextEdit()
        self.log.setObjectName('Log')
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(20000)
        ll.addWidget(self.log, 1)
        vsplit.addWidget(logw)
        vsplit.setStretchFactor(0, 3)
        vsplit.setStretchFactor(1, 1)
        vsplit.setSizes([560, 200])
        lay.addWidget(vsplit, 1)
        self._t0 = None

    # ---------------------------------------------------------------- run
    def busy(self):
        return self.thread is not None and self.thread.isRunning()

    def start(self, do_register, do_write, projects=None, batch_tab=None):
        if self.busy():
            return
        p = self.win.project
        if projects is None:
            errors = Pipeline(p).validate()
            if errors:
                QMessageBox.warning(self, tr('Projet incomplet'), '\n'.join(errors))
                return
            if do_write and not do_register and not p.transforms_valid():
                if QMessageBox.question(self, tr('Recalage'), tr(
                        'Aucun recalage valide pour la configuration actuelle. Lancer le recalage puis générer '
                        'les images ?')) != QMessageBox.Yes:
                    return
                do_register = True
            projects = [p]
            self.win.autosave()
        if do_register:
            self.clear_qc()
        self.log.clear()
        self.thread = PipelineThread(projects, do_register, do_write)
        self.thread.log.connect(self.append_log)
        self.thread.progress.connect(self.on_progress)
        self.thread.qc.connect(self.add_qc)
        self.thread.all_done.connect(self.finished)
        if batch_tab is not None:
            self.thread.project_started.connect(batch_tab.on_started)
            self.thread.project_finished.connect(batch_tab.on_finished)
        else:
            self.thread.project_finished.connect(self._single_finished)
        self._set_running(True)
        self._t0 = time.time()
        self.stage.setText(tr('Démarrage…'))
        self.bar.setMaximum(0)       # busy indicator until the first progress report
        self.thread.start()

    def _set_running(self, on):
        for w in (self.btn_all, self.btn_reg, self.btn_write):
            w.setEnabled(not on)
        self.btn_cancel.setEnabled(on)
        self.win.set_editing_enabled(not on)

    def cancel(self):
        if self.busy():
            self.thread.cancel.set()
            self.stage.setText(tr('Annulation en cours (fin des tâches en cours)…'))

    def append_log(self, msg):
        self.log.appendPlainText(msg)

    def on_progress(self, stage, done, total):
        el = time.time() - (self._t0 or time.time())
        self.stage.setText(f'{stage} : {done}/{total}')
        self.elapsed.setText(tr('{t} écoulées', t=_fmt_elapsed(el)))
        self.bar.setMaximum(max(total, 1))
        self.bar.setValue(done)

    def _single_finished(self, i, ok, msg):
        if ok and msg:
            self.append_log('\n' + tr('Fichiers créés :') + '\n' + msg)

    def finished(self):
        self._set_running(False)
        el = time.time() - (self._t0 or time.time())
        self.stage.setText(tr('Terminé.'))
        self.elapsed.setText(_fmt_elapsed(el))
        self.bar.setMaximum(1)
        self.bar.setValue(1)
        self.win.on_run_finished()

    # ---------------------------------------------------------------- QC
    def clear_qc(self):
        self.qc_data.clear()
        self.qc_table.setRowCount(0)
        self.qc_view.set_image(None, placeholder=tr('Lancez un recalage pour voir ici la superposition '
                                                    'avant/après de chaque round.'))

    def add_qc(self, section, rnd, res):
        self.qc_data[(section, rnd)] = res
        px = self.win.project.pixel_size_um or self._px()
        row = self.qc_table.rowCount()
        self.qc_table.insertRow(row)
        sec = tr('lame') if section == '__slide__' else section
        rl = tr('fond') if rnd == '__background__' else rnd
        if res.matrix is None and res.qc_after is None and not res.n_patches:
            vals = [sec, rl, '—', '—', '—', '—', '—', '—', '—', ' | '.join(res.warnings)]
        else:
            vals = [sec, rl, f'{res.shift_px[0] * px:+.1f} / {res.shift_px[1] * px:+.1f}',
                    f'{res.rotation_deg:+.3f}', f'{res.ncc_before:.2f}', f'{res.ncc_after:.2f}',
                    f'{res.n_inliers}/{res.n_patches}',
                    f'{res.deform_max_um:.1f}' if res.field_nodes else '—',
                    f'{res.field_valid}/{res.field_nodes}' if res.field_nodes else '—', ' | '.join(res.warnings)]
        bad = bool(res.warnings) or not (res.ncc_after >= 0.25)
        for j, v in enumerate(vals):
            it = QTableWidgetItem(v)
            it.setData(Qt.UserRole, (section, rnd))
            if j == len(vals) - 1 and v:
                it.setToolTip(v)
            if bad:
                it.setBackground(QBrush(WARN_BG))
            self.qc_table.setItem(row, j, it)
        # show the first result that has an overlay (an absent round has none)
        if res.qc_after is not None and not self._selected_has_image():
            self.qc_table.selectRow(row)
        elif not self.qc_table.selectedItems():
            self.qc_table.selectRow(row)

    def _selected_res(self):
        items = self.qc_table.selectedItems()
        if not items:
            return None
        key = items[0].data(Qt.UserRole)
        return self.qc_data.get(tuple(key))

    def _selected_has_image(self):
        r = self._selected_res()
        return r is not None and r.qc_after is not None

    def _px(self):
        try:
            return Pipeline(self.win.project).pixel_size()
        except Exception:
            return 0.325

    def _show_qc(self):
        res = self._selected_res()
        if res is None:
            return
        img = res.qc_before if self.r_before.isChecked() else res.qc_after
        if img is None:
            msg = (' '.join(res.warnings) if res.warnings else '') or tr('Pas d\'aperçu pour cette ligne.')
            self.qc_view.set_image(None, placeholder=tr('Pas d\'aperçu : {msg}', msg=msg))
        else:
            self.qc_view.set_image(img, fit=self.qc_view._auto_fit)

    def load_saved_qc(self):
        """Show the QC saved next to the outputs (registration_qc.csv + PNG pairs) of an already registered
        project, so the overlays are available after reopening it."""
        p = self.win.project
        if self.busy() or not p.transforms or not p.output.directory:
            return
        qc_dir = os.path.join(p.output.directory, f'{p.output.basename}_QC')
        path = os.path.join(qc_dir, 'registration_qc.csv')
        if not os.path.isfile(path) or not p.transforms_valid():
            return
        self.clear_qc()
        try:
            with open(path, newline='', encoding='utf-8') as fh:
                rows = list(csv.DictReader(fh))
        except OSError:
            return
        fl = lambda v, d=float('nan'): float(v) if v not in ('', None) else d  # noqa: E731
        for r in rows:
            try:
                valid, nodes = (int(x) for x in (r.get('deform_grid_valid') or '0/0').split('/'))
                res = RegistrationResult(
                    matrix=[], ncc_before=fl(r['ncc_before'], 0), ncc_after=fl(r['ncc_after'], 0),
                    n_patches=int(fl(r['patches'], 0)), n_inliers=int(fl(r['inliers'], 0)),
                    residual_px=fl(r['residual_px']), shift_px=(fl(r['shift_x_px'], 0), fl(r['shift_y_px'], 0)),
                    rotation_deg=fl(r['rotation_deg'], 0),
                    warnings=[w for w in (r.get('warnings') or '').split(' | ') if w],
                    field_nodes=nodes, field_valid=valid, deform_max_um=fl(r.get('deform_max_um'), 0))
            except (KeyError, ValueError):
                continue
            png = os.path.join(qc_dir, f"{r['section']}_{r['round']}".replace('/', '_') + '.png')
            if os.path.isfile(png):
                im = cv2.imread(png, cv2.IMREAD_COLOR)
                if im is not None:
                    im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
                    w = (im.shape[1] - 8) // 2
                    res.qc_before, res.qc_after = im[:, :w].copy(), im[:, w + 8:w + 8 + w].copy()
            if res.qc_after is None and not res.n_patches:
                res.matrix = None
            self.add_qc(r['section'], r['round'], res)
        if rows:
            self.stage.setText(tr('Contrôle qualité du dernier recalage (rechargé depuis {d}).', d=qc_dir))

    def open_output(self):
        d = self.win.project.output.directory
        if d and os.path.isdir(d):
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))


class BatchTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = page_layout(self, tr('Traitement par lots'),
                          tr('Chaque élément est un fichier projet (*.hifi.json), par exemple une lame. Ils sont '
                             'traités l\'un après l\'autre ; le journal et le QC s\'affichent dans la page '
                             '« Exécution ».'))
        b = QHBoxLayout()
        for text, fn in [(tr('Ajouter des projets…'), self.add), (tr('Ajouter le projet courant'), self.add_current),
                         (tr('Retirer'), self.remove), (tr('Créer des projets à partir de dossiers…'),
                                                        self.from_folders)]:
            w = QPushButton(text)
            w.clicked.connect(fn)
            b.addWidget(w)
        b.addStretch(1)
        self.run_btn = primary(QPushButton(tr('▶  Lancer le lot')))
        self.run_btn.clicked.connect(self.run)
        b.addWidget(self.run_btn)
        lay.addLayout(b)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        lay.addWidget(self.list, 1)

    def _add_path(self, path):
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == path:
                return
        it = QListWidgetItem(f'⏳  {path}')
        it.setData(Qt.UserRole, path)
        self.list.addItem(it)

    def add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr('Projets'), self.win.last_dir(),
                                                tr('Projets (*{ext})', ext=PROJECT_EXT))
        for p in paths:
            self._add_path(p)

    def add_current(self):
        path = self.win.save()
        if path:
            self._add_path(path)

    def remove(self):
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))

    def from_folders(self):
        """Clone the current project for other slides: one folder = one slide, files matched by order."""
        p = self.win.project
        if not p.rounds:
            QMessageBox.information(self, tr('Lots'), tr('Configurez d\'abord un projet modèle (images, marqueurs, '
                                                         'options).'))
            return
        dirs = []
        while True:
            d = QFileDialog.getExistingDirectory(
                self, tr('Dossier d\'une lame ({n} choisi(s) — Annuler pour terminer)', n=len(dirs)),
                self.win.last_dir())
            if not d:
                break
            dirs.append(d)
        made = []
        for d in dirs:
            files = sorted(f for f in os.listdir(d) if f.lower().endswith(('.czi', '.tif', '.tiff'))
                           and not f.startswith('.'))
            n_rounds = len(p.rounds)
            if len(files) < n_rounds:
                QMessageBox.warning(self, tr('Lots'), tr('{d} : {n} image(s) pour {r} rounds — ignoré.',
                                                         d=d, n=len(files), r=n_rounds))
                continue
            q = copy.deepcopy(p)
            q.transforms, q.transforms_signature, q.sections = {}, '', []
            q.whole_slide = p.whole_slide
            q.name = os.path.basename(d)
            for r, f in zip(q.rounds, files):
                r.path = os.path.join(d, f)
            q.output.basename = f'{os.path.basename(d)}_{p.output.basename}'
            if not q.whole_slide:
                from ..sections import detect_sections
                from ..sources import open_source
                s = open_source(q.reference().path)
                q.sections, _, _ = detect_sections(s, s.channel_index(q.reference_channel))
            path = q.save(os.path.join(d, os.path.basename(d)))
            made.append(path)
            self._add_path(path)
        if made:
            QMessageBox.information(self, tr('Lots'), tr(
                '{n} projet(s) créé(s). Les fichiers de chaque dossier sont associés aux rounds dans l\'ordre '
                'alphabétique : vérifiez-les en ouvrant les projets si besoin.', n=len(made)))

    def run(self):
        paths = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        if not paths:
            return
        projects, errors = [], []
        for path in paths:
            try:
                q = Project.load(path)
                e = Pipeline(q).validate()
                if e:
                    errors.append(f'{os.path.basename(path)} :\n  ' + '\n  '.join(e))
                projects.append(q)
            except Exception as ex:
                errors.append(f'{path} : {ex}')
        if errors:
            QMessageBox.warning(self, tr('Projets invalides'), '\n\n'.join(errors))
            return
        for i in range(self.list.count()):
            self.list.item(i).setText(f'⏳  {paths[i]}')
        self.win.show_run_tab()
        self.win.run_tab.start(True, True, projects=projects, batch_tab=self)

    def on_started(self, i):
        it = self.list.item(i)
        if it:
            it.setText(f'▶  {it.data(Qt.UserRole)}')

    def on_finished(self, i, ok, msg):
        it = self.list.item(i)
        if it:
            it.setText(f'{"✅" if ok else "❌"}  {it.data(Qt.UserRole)}' + ('' if ok else f'  —  {msg}'))
