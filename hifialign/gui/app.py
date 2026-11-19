"""Main window and application entry point."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..i18n import LANGUAGES, language, set_language, tr
from ..project import PROJECT_EXT, Project
from .run_tab import BatchTab, RunTab
from .sections_tab import SectionsTab
from .tabs import ImagesTab, MarkersTab, OptionsTab
from .theme import ThemeManager, badge_icon


class Pages:
    """Sidebar navigation + stacked pages, with the small QTabWidget-like API used by the window."""

    def __init__(self, win, sidebar_layout, stack: QStackedWidget):
        self.win, self.stack = win, stack
        self.layout = sidebar_layout
        self.group = QButtonGroup(win)
        self.group.setExclusive(True)
        self.buttons, self.badges = [], []
        self._callbacks = []

    def add(self, widget, badge, text):
        btn = QPushButton(text.replace('&', '&&'))
        btn.setObjectName('NavButton')
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setIconSize(QSize(22, 22))
        i = self.stack.addWidget(widget)
        btn.clicked.connect(lambda: self.setCurrentIndex(i))
        self.group.addButton(btn, i)
        self.layout.addWidget(btn)
        self.buttons.append(btn)
        self.badges.append(badge)
        if i == 0:
            btn.setChecked(True)

    def set_icons(self, mode):
        for b, badge in zip(self.buttons, self.badges):
            b.setIcon(badge_icon(badge, mode))

    def setCurrentIndex(self, i):
        self.buttons[i].setChecked(True)
        if self.stack.currentIndex() != i:
            self.stack.setCurrentIndex(i)
            for cb in self._callbacks:
                cb(i)

    def setCurrentWidget(self, w):
        self.setCurrentIndex(self.stack.indexOf(w))

    def currentIndex(self):
        return self.stack.currentIndex()

    def widget(self, i):
        return self.stack.widget(i)

    def connect(self, cb):
        self._callbacks.append(cb)

    def set_enabled(self, widget, on):
        self.buttons[self.stack.indexOf(widget)].setEnabled(on)


class MainWindow(QMainWindow):
    def __init__(self, project_path=None, project: Project | None = None, theme: ThemeManager | None = None):
        super().__init__()
        self.settings = QSettings('UNIL', 'HiFiAlign')
        self.theme = theme
        self.project = project or Project()
        self.project_path = None
        self._replaced = False
        self.resize(1440, 920)
        self.setMinimumSize(1100, 700)
        self.setAcceptDrops(True)

        # ---- layout: sidebar | pages
        central = QWidget()
        central.setObjectName('Content')
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QFrame()
        side.setObjectName('Sidebar')
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 20, 14, 16)
        sl.setSpacing(4)
        title = QLabel('HiFi Align')
        title.setObjectName('AppTitle')
        sl.addWidget(title)
        sub = QLabel(tr('Recalage d\'images multiplex') + f' · v{__version__}')
        sub.setObjectName('AppSubtitle')
        sl.addWidget(sub)
        self.project_label = QLabel()
        self.project_label.setObjectName('ProjectName')
        self.project_label.setWordWrap(True)
        sl.addSpacing(6)
        sl.addWidget(self.project_label)
        sl.addSpacing(14)
        lab = QLabel(tr('ÉTAPES'))
        lab.setObjectName('SideLabel')
        sl.addWidget(lab)
        nav = QVBoxLayout()
        nav.setSpacing(2)
        sl.addLayout(nav)
        self.stack = QStackedWidget()
        self.tabs = Pages(self, nav, self.stack)

        self.images_tab = ImagesTab(self)
        self.markers_tab = MarkersTab(self)
        self.sections_tab = SectionsTab(self)
        self.options_tab = OptionsTab(self)
        self.run_tab = RunTab(self)
        self.batch_tab = BatchTab(self)
        for w, badge, t in [(self.images_tab, '1', tr('Images')), (self.markers_tab, '2', tr('Marqueurs')),
                            (self.sections_tab, '3', tr('Coupes')), (self.options_tab, '4', tr('Options')),
                            (self.run_tab, '5', tr('Exécution et QC'))]:
            self.tabs.add(w, badge, t)
        sl.addSpacing(14)
        lab = QLabel(tr('AUTRES'))
        lab.setObjectName('SideLabel')
        sl.addWidget(lab)
        nav2 = QVBoxLayout()
        nav2.setSpacing(2)
        sl.addLayout(nav2)
        self.tabs.layout = nav2
        self.tabs.add(self.batch_tab, '≡', tr('Lots'))
        sl.addStretch(1)

        # ---- appearance controls (bottom of the sidebar)
        lab = QLabel(tr('APPARENCE'))
        lab.setObjectName('SideLabel')
        sl.addWidget(lab)
        self.theme_combo = QComboBox()
        for key, text in [('system', tr('Thème : système')), ('light', tr('Thème : clair')),
                          ('dark', tr('Thème : sombre'))]:
            self.theme_combo.addItem(text, key)
        self.theme_combo.currentIndexChanged.connect(lambda i: self.set_theme(self.theme_combo.itemData(i)))
        sl.addWidget(self.theme_combo)
        self.lang_combo = QComboBox()
        for key, text in LANGUAGES.items():
            self.lang_combo.addItem(text, key)
        self.lang_combo.setCurrentIndex(max(0, self.lang_combo.findData(language())))
        self.lang_combo.currentIndexChanged.connect(lambda i: self.change_language(self.lang_combo.itemData(i)))
        sl.addWidget(self.lang_combo)

        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.tabs.connect(self._tab_changed)
        self.images_tab.roundsChanged.connect(self._rounds_changed)
        self._menus()
        self.statusBar()
        if self.theme is not None:
            self.theme.changed.connect(self._theme_changed)
            self._sync_theme_controls()
            self._theme_changed(self.theme.mode)
        if project is not None:
            self.project_path = project_path
            self.reload_all()
        elif project_path:
            self.open_path(project_path)
        else:
            self.new_project(ask=False)

    # ---------------------------------------------------------------- menus
    def _menus(self):
        m = self.menuBar().addMenu(tr('Fichier'))
        for text, key, fn in [(tr('Nouveau projet'), QKeySequence.New, self.new_project),
                              (tr('Ouvrir un projet…'), QKeySequence.Open, self.open_dialog),
                              (tr('Enregistrer'), QKeySequence.Save, self.save),
                              (tr('Enregistrer sous…'), QKeySequence.SaveAs, self.save_as)]:
            a = QAction(text, self)
            a.setShortcut(key)
            a.triggered.connect(lambda checked=False, f=fn: f())
            m.addAction(a)
        m.addSeparator()
        a = QAction(tr('Importer un channel_name.csv…'), self)
        a.triggered.connect(lambda: (self.tabs.setCurrentWidget(self.markers_tab), self.markers_tab.import_csv()))
        m.addAction(a)
        a = QAction(tr('Exporter en CSV…'), self)
        a.triggered.connect(self.markers_tab.export_csv)
        m.addAction(a)

        v = self.menuBar().addMenu(tr('Affichage'))
        tm = v.addMenu(tr('Thème'))
        self.theme_actions = QActionGroup(self)
        for key, text in [('system', tr('Comme le système')), ('light', tr('Clair')), ('dark', tr('Sombre'))]:
            a = QAction(text, self, checkable=True)
            a.setData(key)
            a.triggered.connect(lambda checked=False, k=key: self.set_theme(k))
            self.theme_actions.addAction(a)
            tm.addAction(a)
        lm = v.addMenu(tr('Langue'))
        self.lang_actions = QActionGroup(self)
        for key, text in LANGUAGES.items():
            a = QAction(text, self, checkable=True)
            a.setChecked(key == language())
            a.triggered.connect(lambda checked=False, k=key: self.change_language(k))
            self.lang_actions.addAction(a)
            lm.addAction(a)
        v.addSeparator()
        for i, (text, w) in enumerate([(tr('Images'), self.images_tab), (tr('Marqueurs'), self.markers_tab),
                                       (tr('Coupes'), self.sections_tab), (tr('Options'), self.options_tab),
                                       (tr('Exécution et QC'), self.run_tab)], 1):
            a = QAction(f'{i}. {text}', self)
            a.setShortcut(QKeySequence(f'Ctrl+{i}'))
            a.triggered.connect(lambda checked=False, w=w: self.tabs.setCurrentWidget(w))
            v.addAction(a)

        hm = self.menuBar().addMenu(tr('Aide'))
        a = QAction(tr('À propos'), self)
        a.setMenuRole(QAction.AboutRole)
        a.triggered.connect(lambda: QMessageBox.about(
            self, 'HiFi Align', tr('HiFi Align {v}\nRecalage d\'images multiplex (rounds CZI/TIFF), traitement par '
                                   'coupe, sortie OME-TIFF pyramidale.\nBasé sur HiFiAlignmentTool (jhausserlab).',
                                   v=__version__)))
        hm.addAction(a)

    # ---------------------------------------------------------------- appearance
    def set_theme(self, key):
        if self.theme is None or key == self.theme.choice:
            self._sync_theme_controls()
            return
        self.settings.setValue('theme', key)
        self.theme.set_theme(key)
        self._sync_theme_controls()

    def _sync_theme_controls(self):
        choice = self.theme.choice if self.theme else 'system'
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(choice)))
        self.theme_combo.blockSignals(False)
        for a in self.theme_actions.actions():
            a.setChecked(a.data() == choice)

    def _theme_changed(self, mode):
        self.tabs.set_icons(mode)
        self._sync_theme_controls()

    def change_language(self, lang):
        if lang == language():
            return
        if self.run_tab.busy():
            QMessageBox.information(self, 'HiFi Align', tr('La langue pourra être changée à la fin du traitement.'))
            self._sync_lang_controls()
            return
        self.settings.setValue('language', lang)
        set_language(lang)
        # rebuild the window in the new language, keeping the project, the page and the QC
        new = MainWindow(self.project_path, project=self.project, theme=self.theme)
        new.setGeometry(self.geometry())
        new.tabs.setCurrentIndex(self.tabs.currentIndex())
        new.run_tab.log.setPlainText(self.run_tab.log.toPlainText())
        if self.run_tab.qc_data:
            new.run_tab.clear_qc()
            for (s, r), res in self.run_tab.qc_data.items():
                new.run_tab.add_qc(s, r, res)
        if self.isMaximized():
            new.showMaximized()
        else:
            new.show()
        app = QApplication.instance()
        app._hifi_window = new
        self._replaced = True
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.close()

    def _sync_lang_controls(self):
        self.lang_combo.blockSignals(True)
        self.lang_combo.setCurrentIndex(max(0, self.lang_combo.findData(language())))
        self.lang_combo.blockSignals(False)

    # ---------------------------------------------------------------- state
    def last_dir(self):
        return self.settings.value('last_dir', os.path.expanduser('~'))

    def set_last_dir(self, d):
        self.settings.setValue('last_dir', d)

    def reload_all(self):
        self.images_tab.load()
        self.markers_tab.load()
        self.sections_tab.load()
        self.options_tab.load()
        self.run_tab.clear_qc()
        self.run_tab.load_saved_qc()
        self._title()

    def _title(self):
        name = os.path.basename(self.project_path) if self.project_path else tr('nouveau projet')
        self.setWindowTitle(f'HiFi Align — {name}')
        self.project_label.setText(name)
        self.project_label.setToolTip(self.project_path or '')

    def _rounds_changed(self):
        self.markers_tab.load()

    def _tab_changed(self, i):
        w = self.tabs.widget(i)
        if w is self.markers_tab:
            self.markers_tab.load()
        elif w is self.sections_tab:
            self.sections_tab.load()
        elif w is self.options_tab:
            self.options_tab.load()

    def set_editing_enabled(self, on):
        for w in (self.images_tab, self.markers_tab, self.sections_tab, self.options_tab, self.batch_tab):
            w.setEnabled(on)
        self.lang_combo.setEnabled(on)

    def show_run_tab(self):
        self.tabs.setCurrentWidget(self.run_tab)

    def on_run_finished(self):
        self.autosave()

    # ---------------------------------------------------------------- files
    def new_project(self, ask=True):
        if ask and self.project.rounds and QMessageBox.question(
                self, tr('Nouveau projet'), tr('Abandonner le projet courant (non enregistré) ?')) != QMessageBox.Yes:
            return
        self.project = Project()
        out = self.settings.value('last_output_dir', '')
        if out:
            self.project.output.directory = out
        self.project_path = None
        self.reload_all()

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Ouvrir un projet'), self.last_dir(),
                                              tr('Projets (*{ext})', ext=PROJECT_EXT))
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            self.project = Project.load(path)
        except Exception as e:
            QMessageBox.critical(self, tr('Ouverture impossible'), str(e))
            return
        self.project_path = path
        self.set_last_dir(os.path.dirname(path))
        self.reload_all()
        missing = [r.path for r in self.project.rounds if not os.path.exists(r.path)]
        if missing:
            QMessageBox.warning(self, tr('Fichiers introuvables'),
                                tr('Images introuvables (partage réseau monté ?) :') + '\n' + '\n'.join(missing))

    def save(self):
        if not self.project_path:
            return self.save_as()
        self.project.save(self.project_path)
        self.statusBar().showMessage(tr('Enregistré : {path}', path=self.project_path), 4000)
        return self.project_path

    def save_as(self):
        start = os.path.join(self.project.output.directory or self.last_dir(),
                             (self.project.output.basename or 'projet') + PROJECT_EXT)
        path, _ = QFileDialog.getSaveFileName(self, tr('Enregistrer le projet'), start,
                                              tr('Projets (*{ext})', ext=PROJECT_EXT))
        if not path:
            return None
        if path.endswith('.json') and not path.endswith(PROJECT_EXT):
            path = path[:-5]
        self.project_path = self.project.save(path)
        self.set_last_dir(os.path.dirname(self.project_path))
        self._title()
        return self.project_path

    def autosave(self):
        if self.project.output.directory:
            self.settings.setValue('last_output_dir', self.project.output.directory)
        if self.project_path:
            try:
                self.project.save(self.project_path)
            except OSError:
                pass

    # ---------------------------------------------------------------- drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        projs = [p for p in paths if p.endswith(PROJECT_EXT)]
        if projs:
            self.open_path(projs[0])
            return
        files = []
        for p in paths:
            if os.path.isdir(p):
                files += [os.path.join(p, f) for f in sorted(os.listdir(p)) if not f.startswith('.')]
            else:
                files.append(p)
        self.tabs.setCurrentWidget(self.images_tab)
        self.images_tab.add_files(files)

    def closeEvent(self, e):
        if self._replaced:
            e.accept()
            return
        if self.run_tab.busy():
            if QMessageBox.question(self, tr('Traitement en cours'),
                                    tr('Un traitement est en cours. Annuler et quitter ?')) != QMessageBox.Yes:
                e.ignore()
                return
            self.run_tab.thread.cancel.set()
            self.run_tab.thread.wait(30000)
        self.autosave()
        e.accept()


def initial_language(settings: QSettings) -> str:
    lang = settings.value('language', '')
    if lang in LANGUAGES:
        return lang
    return 'fr'          # default until a language is chosen in the sidebar or the View menu


def run_gui(project_path=None):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('HiFi Align')
    settings = QSettings('UNIL', 'HiFiAlign')
    set_language(initial_language(settings))
    theme = ThemeManager(app)
    theme.set_theme(settings.value('theme', 'system'))
    win = MainWindow(project_path, theme=theme)
    win.show()
    app._hifi_window = win
    return app.exec()
