"""Cytolux main window."""
import glob
import json
import re
import math
import os
import sys
import traceback

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from . import transforms as tx
from . import wsp
from .assistant import NO_MATCH, Assistant
from .help_text import MENU_TIPS, TAB_TIPS, WIDGET_TIPS
from .engine import (STATS, Workspace, apply_template, compute_stat, gate_outline, is_scatter,
                     stat_name, stats_table, template_dict)
from .stats_ui import AddStatDialog, AnnotateDialog, export_excel, fmt_value
from .uncertainty_ui import FragilityDialog, UncertaintyDock
from .plot import GatePlot, LUT, density_levels

APP = "Cytolux"
HIST = "[Histogram]"
HERE = os.path.dirname(os.path.abspath(__file__))


def icon(name):
    p = os.path.join(HERE, "icons", name + ".svg")
    return QtGui.QIcon(p) if os.path.exists(p) else QtGui.QIcon()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.ws = Workspace()
        self.cur_sample = None
        self.cur_pop = "root"
        self.view = {}            # population path -> (x, y) last used axes
        self.fj_counts = None
        self.dirty = False
        self.settings = QtCore.QSettings("Cytolux", "Cytolux")
        self.setWindowIcon(icon("cytolux"))
        self.resize(1400, 900)
        self._build()
        self._update_title()

    # ================================================================== layout
    def _build(self):
        # ---- left: samples + gate tree
        self.sample_list = QtWidgets.QListWidget()
        self.sample_list.currentRowChanged.connect(self._sample_changed)
        self.sample_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.sample_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.sample_list.customContextMenuRequested.connect(self._sample_menu)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Population", "Count", "% Parent", "% Total"])
        hdr = self.tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        for c in (1, 2, 3):
            hdr.setSectionResizeMode(c, QtWidgets.QHeaderView.ResizeToContents)
        self.tree.setIndentation(14)
        self.tree.itemSelectionChanged.connect(self._pop_changed)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        left = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        w1 = QtWidgets.QWidget(); l1 = QtWidgets.QVBoxLayout(w1); l1.setContentsMargins(4, 4, 4, 4)
        self.sample_filter = QtWidgets.QLineEdit()
        self.sample_filter.setPlaceholderText("Filter samples…")
        self.sample_filter.setClearButtonEnabled(True)
        self.sample_filter.setToolTip(WIDGET_TIPS["sample_filter"])
        self.sample_filter.textChanged.connect(self._filter_samples)
        l1.addWidget(QtWidgets.QLabel("<b>Samples</b>"))
        l1.addWidget(self.sample_filter)
        l1.addWidget(self.sample_list)
        w2 = QtWidgets.QWidget(); l2 = QtWidgets.QVBoxLayout(w2); l2.setContentsMargins(4, 4, 4, 4)
        l2.addWidget(QtWidgets.QLabel("<b>Gates</b> (new gates go on every sample; italic = adjusted for this sample)"))
        l2.addWidget(self.tree)
        left.addWidget(w1); left.addWidget(w2); left.setSizes([350, 450])

        # ---- plot tab
        self.plot = GatePlot()
        self.plot.gate_created.connect(self._gate_created)
        self.plot.quad_moved.connect(self._quad_moved)
        self.plot.gate_edited.connect(self._gate_edited)
        self.plot.gate_open.connect(self._select_pop)
        self.plot.gate_menu.connect(lambda path, pos: self._pop_menu(path, pos))
        self.cb_x, self.cb_y = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        self.cb_xf_x, self.cb_xf_y = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        for cb in (self.cb_xf_x, self.cb_xf_y):
            cb.addItems(["Linear", "Log", "Biex", "Biex (FlowJo)"])
            cb.setItemData(3, "The biexponential FlowJo used for this channel, read from the "
                              "imported workspace", QtCore.Qt.ToolTipRole)
        self.sp_w_x, self.sp_w_y = QtWidgets.QDoubleSpinBox(), QtWidgets.QDoubleSpinBox()
        for sp in (self.sp_w_x, self.sp_w_y):
            sp.setRange(0.0, 2.0); sp.setSingleStep(0.1); sp.setDecimals(2); sp.setPrefix("W ")
            sp.setToolTip("Biex width: how much of the axis is given to the region around zero")
        for w in (self.cb_x, self.cb_y):
            w.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
            w.currentIndexChanged.connect(self._axes_changed)
        self.cb_xf_x.currentIndexChanged.connect(lambda: self._xf_changed("x"))
        self.cb_xf_y.currentIndexChanged.connect(lambda: self._xf_changed("y"))
        self.sp_w_x.valueChanged.connect(lambda: self._xf_changed("x"))
        self.sp_w_y.valueChanged.connect(lambda: self._xf_changed("y"))
        self.cb_mode = QtWidgets.QComboBox(); self.cb_mode.addItems(["Pseudocolor", "Contour", "Dots"])
        self.cb_mode.currentIndexChanged.connect(self._mode_changed)
        for _w, _k in ((self.sample_list, "sample_list"), (self.tree, "tree"),
                       (self.cb_x, "cb_x"), (self.cb_y, "cb_y"),
                       (self.cb_xf_x, "cb_xf_x"), (self.cb_xf_y, "cb_xf_y"),
                       (self.cb_mode, "cb_mode")):
            _w.setToolTip(WIDGET_TIPS[_k])
        self.lbl_info = QtWidgets.QLabel()
        bar = QtWidgets.QGridLayout()
        bar.addWidget(QtWidgets.QLabel("Y"), 0, 0); bar.addWidget(self.cb_y, 0, 1)
        bar.addWidget(self.cb_xf_y, 0, 2); bar.addWidget(self.sp_w_y, 0, 3)
        bar.addWidget(QtWidgets.QLabel("X"), 1, 0); bar.addWidget(self.cb_x, 1, 1)
        bar.addWidget(self.cb_xf_x, 1, 2); bar.addWidget(self.sp_w_x, 1, 3)
        bar.addWidget(QtWidgets.QLabel("Display"), 0, 4); bar.addWidget(self.cb_mode, 0, 5)
        bar.addWidget(self.lbl_info, 1, 4, 1, 3)
        bar.setColumnStretch(6, 1)
        ptab = QtWidgets.QWidget(); pl = QtWidgets.QVBoxLayout(ptab)
        pl.addLayout(bar); pl.addWidget(self.plot, 1)

        # ---- overview tab
        self.ov_area = QtWidgets.QScrollArea(); self.ov_area.setWidgetResizable(True)
        self.ov_inner = QtWidgets.QWidget(); self.ov_grid = QtWidgets.QGridLayout(self.ov_inner)
        self.ov_area.setWidget(self.ov_inner)
        otab = QtWidgets.QWidget(); ol = QtWidgets.QVBoxLayout(otab)
        orow = QtWidgets.QHBoxLayout()
        self.ov_note = QtWidgets.QLabel()
        b = QtWidgets.QPushButton("Refresh"); b.clicked.connect(self._refresh_overview)
        orow.addWidget(self.ov_note, 1); orow.addWidget(b)
        ol.addLayout(orow); ol.addWidget(self.ov_area, 1)

        # ---- statistics tab
        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectColumns)
        self.table.horizontalHeader().setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self._stat_header_menu)
        self.table.horizontalHeader().sectionDoubleClicked.connect(self._rename_stat)
        self.stat_hint = QtWidgets.QLabel(
            "No statistics yet. <b>Add statistic</b> picks populations, a statistic (count, %, median…) and channels; "
            "<b>Count + % of parent for every gate</b> adds the usual set in one click.")
        self.stat_hint.setWordWrap(True)
        stab = QtWidgets.QWidget(); sl = QtWidgets.QVBoxLayout(stab)
        srow = QtWidgets.QHBoxLayout()
        for text, fn, tip in (
                ("Σ Add statistic…", lambda: self.add_stat(), "Add columns: populations × statistic × channels"),
                ("Count + % of parent for every gate", self._add_standard_stats, "One click: the usual table"),
                ("Remove column", self._remove_stat_cols, "Remove the selected column(s)"),
                ("Move left", lambda: self._move_stat(-1), "Move column left"),
                ("Move right", lambda: self._move_stat(1), "Move column right"),
                ("Annotate samples…", self.annotate, "Donor, dose, condition… as leading columns"),
        ):
            b = QtWidgets.QPushButton(text); b.setToolTip(tip); b.clicked.connect(lambda _=False, f=fn: self._safe(f))
            srow.addWidget(b)
        srow.addStretch(1)
        b = QtWidgets.QPushButton("Copy table"); b.setToolTip("Copy to the clipboard, ready to paste into Excel or Prism")
        b.clicked.connect(self._copy_table); srow.addWidget(b)
        b = QtWidgets.QPushButton("Export to Excel…"); b.clicked.connect(lambda: self._safe(self.export_stats))
        srow.addWidget(b)
        sl.addLayout(srow); sl.addWidget(self.stat_hint); sl.addWidget(self.table, 1)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(ptab, "Gating")
        self.tabs.addTab(otab, "All samples")
        self.tabs.addTab(stab, "Statistics")
        for _i in range(self.tabs.count()):
            self.tabs.setTabToolTip(_i, TAB_TIPS.get(self.tabs.tabText(_i), ""))
        self.tabs.currentChanged.connect(self._tab_changed)

        split = QtWidgets.QSplitter()
        split.addWidget(left); split.addWidget(self.tabs); split.setSizes([380, 1020])
        self.setCentralWidget(split)
        self.statusBar()

        # ---- tools
        tb = self.addToolBar("Tools"); tb.setIconSize(QtCore.QSize(26, 26))
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        self.tool_group = QtGui.QActionGroup(self)
        tips = {
            "pointer": "Select and edit gates (drag gates and their handles)",
            "rect": "Rectangle gate: drag a box",
            "poly": "Polygon gate: click the corners; double-click, Enter or click the first point to close",
            "ellipse": "Ellipse gate: drag a box, then rotate/resize with the handles",
            "quad": "Quadrant gates: click the crossing point",
            "range": "Range gate on a histogram: drag across the peak",
        }
        names = {"pointer": "Select", "rect": "Rectangle", "poly": "Polygon", "ellipse": "Ellipse",
                 "quad": "Quadrant", "range": "Range"}
        self.tool_actions = {}
        for i, (t, nm) in enumerate(names.items(), start=1):
            a = QtGui.QAction(icon(t), nm, self, checkable=True)
            a.setToolTip(tips[t] + f"  [{i}]"); a.setShortcut(str(i))
            a.triggered.connect(lambda _=False, tt=t: self.set_tool(tt))
            self.tool_group.addAction(a); tb.addAction(a)
            self.tool_actions[t] = a
        self.tool_actions["pointer"].setChecked(True)
        tb.addSeparator()
        a = QtGui.QAction(icon("up"), "Parent", self); a.setShortcut("Backspace")
        a.setToolTip("Go up to the parent population [Backspace]")
        a.triggered.connect(self._go_parent); tb.addAction(a)
        a = QtGui.QAction(icon("prev"), "Prev sample", self); a.setShortcut("PgUp")
        a.setToolTip(WIDGET_TIPS["prev_sample"])
        a.triggered.connect(lambda: self._step_sample(-1)); tb.addAction(a)
        a = QtGui.QAction(icon("next"), "Next sample", self); a.setShortcut("PgDown")
        a.setToolTip(WIDGET_TIPS["next_sample"])
        a.triggered.connect(lambda: self._step_sample(1)); tb.addAction(a)
        tb.addSeparator()
        self.act_local = QtGui.QAction(icon("pointer"), "Edit: this sample", self, checkable=True)
        self.act_local.setToolTip("On (FlowJo style): dragging a gate changes it for the current sample only.\n"
                                  "Off: dragging a gate changes it for every sample.  [L]")
        self.act_local.setShortcut("L")
        self.act_local.setChecked(self.settings.value("edit_local", True, type=bool))
        self.act_local.toggled.connect(self._local_toggled)
        tb.addAction(self.act_local)
        self._local_toggled(self.act_local.isChecked())
        esc = QtGui.QShortcut(QtGui.QKeySequence("Escape"), self)
        esc.activated.connect(lambda: self.set_tool("pointer"))

        # ---- menus
        m = self.menuBar().addMenu("&File"); m.setToolTipsVisible(True)
        self._act(m, "Open FCS folder…", self.open_folder, "Ctrl+O")
        self._act(m, "Add FCS files…", self.add_files)
        m.addSeparator()
        self._act(m, "Open workspace…", self.open_workspace, "Ctrl+Shift+O")
        self._act(m, "Save workspace", self.save_workspace, "Ctrl+S")
        self._act(m, "Save workspace as…", lambda: self.save_workspace(True), "Ctrl+Shift+S")
        m.addSeparator()
        self._act(m, "Import FlowJo workspace (.wsp)…", self.import_wsp, "Ctrl+I")
        m.addSeparator()
        self._act(m, "Save gating template…", self.save_template)
        self._act(m, "Apply gating template to these samples…", self.apply_template_file)
        self._act(m, "New analysis: FCS folder + gating template…", self.new_from_template, "Ctrl+N")
        m.addSeparator()
        self._act(m, "Export statistics to Excel…", self.export_stats, "Ctrl+E")
        self._act(m, "Export plot as image…", self.export_plot)
        m.addSeparator()
        self.recent_menu = m.addMenu("Recent workspaces")
        self._fill_recent()
        m.addSeparator()
        self._act(m, "Quit", self.close, "Ctrl+Q")
        m = self.menuBar().addMenu("&Compensation"); m.setToolTipsVisible(True)
        self._act(m, "Use the matrix stored in the files (FlowJo: acquisition-defined)", lambda: self.set_comp("file"))
        self._act(m, "No compensation", lambda: self.set_comp("none"))
        self._act(m, "Load matrix from CSV…", self.load_comp_csv)
        self._act(m, "View / edit matrix…", self.edit_comp)
        m = self.menuBar().addMenu("&Edit"); m.setToolTipsVisible(True)
        self.act_undo = self._act(m, "Undo", self.do_undo, "Ctrl+Z",
                                  tip="Step back one edit. Gates, renames, deletions and "
                                      "per-sample adjustments are all undoable.")
        self.act_redo = self._act(m, "Redo", self.do_redo, "Ctrl+Shift+Z",
                                  tip="Step forward again after an undo.")
        m.addSeparator()
        m.aboutToShow.connect(self._sync_undo_actions)
        self._act(m, "Rename channels (marker names)…", self.edit_labels)
        self._act(m, "Delete selected gate", self._delete_selected, "Delete")
        self._act(m, "Annotate samples (donor, dose…)…", self.annotate)
        self._act(m, "Add statistic…", lambda: self.add_stat(), "Ctrl+T")
        m = self.menuBar().addMenu("Confide&nce"); m.setToolTipsVisible(True)
        self._act(m, "Measure confidence for this sample", self.show_confidence, "Ctrl+U")
        self._act(m, "Find the weakest gates in this workspace…", self.show_fragility)
        m = self.menuBar().addMenu("&Help"); m.setToolTipsVisible(True)
        self._act(m, "Find how to do something…", self.show_assistant, "Ctrl+/",
                  tip="Search the built-in help in plain language. Works offline, "
                      "and never sends anything anywhere.")
        self._act(m, "Quick guide", self.show_help, "F1")
        self._act(m, "Check against FlowJo counts", self.show_fj_check)

    def _act(self, menu, text, fn, shortcut=None, tip=None):
        a = QtGui.QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        tip = tip or MENU_TIPS.get(text)
        if tip:
            if shortcut:
                tip = "%s  [%s]" % (tip, shortcut)
            a.setToolTip(tip)
            a.setStatusTip(tip)
        a.triggered.connect(lambda _=False: self._safe(fn))
        menu.addAction(a)
        return a

    def _safe(self, fn):
        try:
            fn()
        except Exception as e:
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(self, APP, f"{type(e).__name__}: {e}")

    def _update_title(self):
        nm = os.path.basename(self.ws.path) if self.ws.path else "untitled"
        self.setWindowTitle(f"{APP} — {nm}{' *' if self.dirty else ''}")

    def _mark(self):
        self.dirty = True
        self._update_title()
        # Any edit may have moved a boundary, so measured intervals no longer describe
        # what is on screen. Blanking them is deliberate: an interval that silently
        # followed a moved gate would be worse than none.
        if getattr(self, "_conf_dock", None) is not None:
            self._conf_panel.set_stale()

    # ================================================================== files
    def open_folder(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Folder with FCS files",
                                                       self.settings.value("lastdir", os.path.expanduser("~")))
        if not d:
            return
        self.settings.setValue("lastdir", d)
        files = sorted(glob.glob(os.path.join(d, "*.fcs")) + glob.glob(os.path.join(d, "*.FCS")))
        if not files:
            QtWidgets.QMessageBox.information(self, APP, "No .fcs files in that folder.")
            return
        self._load_files(files)

    def add_files(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "FCS files", self.settings.value("lastdir", os.path.expanduser("~")), "FCS files (*.fcs *.FCS)")
        if files:
            self.settings.setValue("lastdir", os.path.dirname(files[0]))
            self._load_files(files)

    def _load_files(self, files):
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            added = self.ws.add_files(files)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self._fill_samples()
        self._mark()
        self.statusBar().showMessage(f"Loaded {len(added)} files ({len(self.ws.samples)} in workspace)", 6000)

    def _fill_samples(self, keep=None):
        self.sample_list.blockSignals(True)
        self.sample_list.clear()
        for s in self.ws.samples:
            it = QtWidgets.QListWidgetItem(s.name)
            it.setToolTip(f"{s.path}\n{s.event_count:,} events")
            self.sample_list.addItem(it)
        self.sample_list.blockSignals(False)
        if getattr(self, "sample_filter", None) and self.sample_filter.text():
            self._filter_samples(self.sample_filter.text())
        if self.ws.samples:
            names = [s.name for s in self.ws.samples]
            row = names.index(keep) if keep in names else 0
            self.sample_list.setCurrentRow(row)
            self._sample_changed(row)

    def _filter_samples(self, text):
        """Hide samples that do not match, without disturbing the selection."""
        t = (text or "").strip().lower()
        shown = 0
        for i in range(self.sample_list.count()):
            it = self.sample_list.item(i)
            hit = t in it.text().lower()
            it.setHidden(bool(t) and not hit)
            shown += hit or not t
        if t:
            self.statusBar().showMessage("%d of %d samples match \u2018%s\u2019"
                                         % (shown, self.sample_list.count(), text), 3000)

    def open_workspace(self, path=None):
        if not path:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Open workspace", self.settings.value("lastdir", os.path.expanduser("~")),
                "Cytolux workspace (*.fgw)")
        if not path:
            return
        if not self._maybe_save():
            return

        def relocate(p):
            QtWidgets.QMessageBox.information(self, APP, f"Can't find:\n{p}\nPlease show me the folder it moved to.")
            d = QtWidgets.QFileDialog.getExistingDirectory(self, "Folder with " + os.path.basename(p))
            return os.path.join(d, os.path.basename(p)) if d else None
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self.ws = Workspace.load(path, relocate=relocate)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.cur_pop = "root"
        self.view = {}
        self.dirty = False
        self._add_recent(path)
        self._fill_samples()
        self._update_title()

    def save_workspace(self, save_as=False):
        path = self.ws.path
        if save_as or not path:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save workspace", path or os.path.join(self.settings.value("lastdir", os.path.expanduser("~")), "workspace.fgw"),
                "Cytolux workspace (*.fgw)")
            if not path:
                return False
            if not path.endswith(".fgw"):
                path += ".fgw"
        self.ws.save(path)
        self.dirty = False
        self._add_recent(path)
        self._update_title()
        self.statusBar().showMessage(f"Saved {path}", 5000)
        return True

    def _maybe_save(self):
        if not self.dirty or not self.ws.samples:
            return True
        r = QtWidgets.QMessageBox.question(self, APP, "Save changes to the current workspace?",
                                           QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel)
        if r == QtWidgets.QMessageBox.Save:
            return self.save_workspace()
        return r == QtWidgets.QMessageBox.Discard

    def closeEvent(self, ev):
        if self._maybe_save():
            ev.accept()
        else:
            ev.ignore()

    def _add_recent(self, path):
        rec = [p for p in self._recent() if p != path]
        rec.insert(0, path)
        self.settings.setValue("recent", rec[:8])
        self._fill_recent()

    def _recent(self):
        v = self.settings.value("recent") or []
        if isinstance(v, str):          # QSettings returns a lone entry as a plain string
            v = [v]
        return [p for p in v if p.endswith(".fgw") and os.path.exists(p)]

    def _fill_recent(self):
        self.recent_menu.clear()
        for p in self._recent():
            a = self.recent_menu.addAction(p)
            a.triggered.connect(lambda _=False, pp=p: self._safe(lambda: self.open_workspace(pp)))

    def import_wsp(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "FlowJo workspace", self.settings.value("lastdir", os.path.expanduser("~")), "FlowJo workspace (*.wsp)")
        if not path:
            return
        if not self.ws.samples:
            files, n = wsp.fcs_candidates(path)
            if len(files) < n:
                QtWidgets.QMessageBox.information(
                    self, APP, f"The workspace lists {n} FCS files; found {len(files)} of them. "
                               "Please choose the folder that holds the FCS files.")
                d = QtWidgets.QFileDialog.getExistingDirectory(self, "Folder with the FCS files", os.path.dirname(path))
                if d:
                    files = sorted(glob.glob(os.path.join(d, "*.fcs")))
            if not files:
                return
            self.ws.add_files(files)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            n, self.fj_counts, skipped = wsp.import_into(self.ws, path)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        # FlowJo's gates are on linear axes; show those channels linear at first so they can be edited
        for p in self.ws.pops:
            for d, xf in zip(p["gate"]["dims"], p["gate"]["xf"]):
                if is_scatter(self.ws.raw_channel(d)):
                    self.ws.set_xform(d, xf)
        self._fill_samples()
        self._mark()
        msg = f"Imported gates for {n} samples, {len(self.ws.pops)} populations."
        if skipped:
            msg += f"\nSkipped unsupported gates: {skipped}"
        msg += "\n\nHelp → Check against FlowJo counts compares every count with FlowJo's."
        QtWidgets.QMessageBox.information(self, APP, msg)

    def export_stats(self):
        if not self.ws.samples:
            return
        if not self.ws.stat_defs:
            r = QtWidgets.QMessageBox.question(
                self, APP, "No statistics are defined yet. Add Count and % of parent for every gate, then export?")
            if r != QtWidgets.QMessageBox.Yes:
                return
            self._add_standard_stats()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export statistics", os.path.join(self.settings.value("lastdir", os.path.expanduser("~")), "statistics.xlsx"),
            "Excel (*.xlsx)")
        if not path:
            return
        if not path.endswith(".xlsx"):
            path += ".xlsx"
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            nrow, ncol = export_excel(self.ws, path)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.settings.setValue("lastdir", os.path.dirname(path))
        r = QtWidgets.QMessageBox.question(
            self, APP, f"Saved {os.path.basename(path)}: {nrow} samples × {ncol} statistics, plus every gate's "
                       "counts on the 'All gates' sheet.\n\nOpen it now?")
        if r == QtWidgets.QMessageBox.Yes:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    EXPORT_SIZES = [
        ("Figure panel, 300 dpi (3.5 in wide)", 1050, 300),
        ("Figure panel, 600 dpi (3.5 in wide)", 2100, 600),
        ("Full width, 300 dpi (7 in wide)", 2100, 300),
        ("Full width, 600 dpi (7 in wide)", 4200, 600),
        ("Slide, 150 dpi (10 in wide)", 1500, 150),
        ("Screen size", 0, 0),
    ]

    def export_plot(self):
        """Save the plot at a size worth putting in a figure.

        Journals ask for 300 dpi at the printed width, so the useful question is which
        width on the page, not how many pixels. The density grid is rebinned at the
        chosen size, so a 600 dpi export really carries 600 dpi of data.
        """
        if self.plot.ctx is None:
            QtWidgets.QMessageBox.information(self, APP, "Open a sample and draw a plot first.")
            return
        labels = [s[0] for s in self.EXPORT_SIZES]
        choice, ok = QtWidgets.QInputDialog.getItem(
            self, "Export plot", "Size and resolution:", labels, 2, False)
        if not ok:
            return
        _, width, dpi = self.EXPORT_SIZES[labels.index(choice)]
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export plot",
            os.path.join(self.settings.value("lastdir", os.path.expanduser("~")), "plot.png"),
            "PNG (*.png)")
        if not path:
            return
        if not path.endswith(".png"):
            path += ".png"
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            if width:
                self.plot.export_png(path, width=width, dpi=dpi)
            else:
                self.plot.export_png(path, width=int(self.plot.width()), dpi=0)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        img = QtGui.QImage(path)
        self.statusBar().showMessage(
            "Saved %s  (%d x %d px%s)" % (os.path.basename(path), img.width(), img.height(),
                                          ", %d dpi" % dpi if dpi else ""), 8000)

    # ================================================================== compensation / labels
    def set_comp(self, mode):
        self.ws.comp_mode = mode
        self.ws.changed(events=True)
        self._mark()
        self._sample_changed(self.sample_list.currentRow())

    def load_comp_csv(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Spillover matrix (CSV, channel names as header)",
                                                        "", "CSV (*.csv)")
        if not path:
            return
        df = pd.read_csv(path, index_col=0)
        chans = [str(c) for c in df.columns]
        mat = df.values.astype(float)
        if mat.max() > 2:       # given in percent
            mat = mat / 100.0
        self.ws.custom_comp = (chans, mat)
        self.set_comp("custom")

    def edit_comp(self):
        s = self.cur_sample
        if s is None:
            return
        comp = self.ws.comp_for(s)
        if comp is None:
            QtWidgets.QMessageBox.information(self, APP, "No compensation matrix in use.")
            return
        chans, mat = comp
        dlg = QtWidgets.QDialog(self); dlg.setWindowTitle("Spillover matrix (row = fluor, column = detector, %)")
        t = QtWidgets.QTableWidget(len(chans), len(chans))
        lab = [f"{c}\n{s.markers.get(c, '')}" for c in chans]
        t.setHorizontalHeaderLabels(lab); t.setVerticalHeaderLabels(lab)
        for i in range(len(chans)):
            for j in range(len(chans)):
                t.setItem(i, j, QtWidgets.QTableWidgetItem(f"{100 * mat[i, j]:.3f}"))
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.addWidget(QtWidgets.QLabel("Edit values to adjust compensation. OK applies them to all samples."))
        lay.addWidget(t); lay.addWidget(bb); dlg.resize(900, 500)
        if dlg.exec():
            new = np.array([[float(t.item(i, j).text()) / 100 for j in range(len(chans))] for i in range(len(chans))])
            if not np.allclose(new, mat):
                self.ws.custom_comp = (list(chans), new)
                self.set_comp("custom")

    def edit_labels(self):
        s = self.cur_sample
        if s is None:
            return
        dlg = QtWidgets.QDialog(self); dlg.setWindowTitle("Channel names")
        t = QtWidgets.QTableWidget(len(s.channels), 2)
        t.setHorizontalHeaderLabels(["Channel", "Name shown"])
        for i, c in enumerate(s.channels):
            a = QtWidgets.QTableWidgetItem(c); a.setFlags(QtCore.Qt.ItemIsEnabled)
            t.setItem(i, 0, a)
            t.setItem(i, 1, QtWidgets.QTableWidgetItem(self.ws.labels.get(c, s.markers.get(c, ""))))
        t.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        lay = QtWidgets.QVBoxLayout(dlg); lay.addWidget(t); lay.addWidget(bb); dlg.resize(520, 600)
        if dlg.exec():
            for i, c in enumerate(s.channels):
                v = t.item(i, 1).text().strip()
                if v != s.markers.get(c, ""):
                    self.ws.labels[c] = v
                else:
                    self.ws.labels.pop(c, None)
            self._mark()
            self._fill_axes()
            self.refresh()

    # ================================================================== selection
    def _sample_changed(self, row):
        if row < 0 or row >= len(self.ws.samples):
            self.cur_sample = None
            return
        self.cur_sample = self.ws.samples[row]
        if getattr(self, "_conf_dock", None) is not None:
            self._conf_panel.set_sample(self.cur_sample)
        self._fill_axes()
        self._fill_tree()
        self.refresh()

    def _step_sample(self, d):
        n = self.sample_list.count()
        if n:
            self.sample_list.setCurrentRow((self.sample_list.currentRow() + d) % n)

    def _fill_axes(self):
        s = self.cur_sample
        chans = self.ws.display_channels(s)
        cur_x, cur_y = self.cb_x.currentData(), self.cb_y.currentData()
        for cb, extra in ((self.cb_x, []), (self.cb_y, [HIST])):
            cb.blockSignals(True)
            cb.clear()
            for e in extra:
                cb.addItem(e, None)
            for c in chans:
                cb.addItem(self.ws.label(c, s), c)
            cb.blockSignals(False)
        if self.cur_pop in self.view:
            x, y = self.view[self.cur_pop]
        elif self.ws.children(self.cur_pop):
            d = self.ws.children(self.cur_pop)[0]["gate"]["dims"]
            x, y = d[0], (d[1] if len(d) > 1 else None)
        elif cur_x is not None:
            x, y = cur_x, cur_y
        else:
            x, y = None, ""
        if x is None or x not in chans:
            x = next((c for c in chans if c.startswith("FSC-A")), chans[0])
        if y is not None and y not in chans:
            y = next((c for c in chans if c.startswith("SSC-A")), chans[min(1, len(chans) - 1)])
        self._set_axes(x, y)

    def _set_axes(self, x, y):
        for cb, v in ((self.cb_x, x), (self.cb_y, y)):
            cb.blockSignals(True)
            i = cb.findData(v) if v is not None else cb.findText(HIST)
            cb.setCurrentIndex(max(i, 0))
            cb.blockSignals(False)
        self._sync_xf_widgets()

    def _sync_xf_widgets(self):
        s = self.cur_sample
        for cb, xfcb, sp in ((self.cb_x, self.cb_xf_x, self.sp_w_x), (self.cb_y, self.cb_xf_y, self.sp_w_y)):
            ch = cb.currentData()
            xfcb.blockSignals(True); sp.blockSignals(True)
            if ch is None:
                xfcb.setEnabled(False); sp.setEnabled(False)
            else:
                spec = self.ws.xform(ch, s)
                xfcb.setEnabled(True)
                xfcb.setCurrentIndex({"linear": 0, "log": 1, "biex": 2, "wspbiex": 3}[spec["kind"]])
                sp.setEnabled(spec["kind"] == "biex")
                sp.setValue(spec.get("W", 0.5) if spec["kind"] == "biex" else 0.5)
            xfcb.blockSignals(False); sp.blockSignals(False)

    def _axes_changed(self):
        self._sync_xf_widgets()
        self.view[self.cur_pop] = (self.cb_x.currentData(), self.cb_y.currentData())
        self.refresh()

    def _xf_changed(self, which):
        cb, xfcb, sp = (self.cb_x, self.cb_xf_x, self.sp_w_x) if which == "x" else (self.cb_y, self.cb_xf_y, self.sp_w_y)
        ch = cb.currentData()
        if ch is None:
            return
        s = self.cur_sample
        T = s.ranges.get(self.ws.raw_channel(ch), 262144.0)
        kind = xfcb.currentText().lower()
        old = self.ws.xform(ch, s)
        if kind == "linear":
            spec = tx.linear(T)
        elif kind == "log":
            spec = tx.log(T)
        elif kind.startswith("biex (flowjo"):
            if old["kind"] == "wspbiex":
                return
            spec = tx.wspbiex(T, width=-10.0, positive=4.5 + math.log10(T / 262144.0))
        else:
            W = sp.value() if old["kind"] == "biex" else 0.5
            M = 4.5 + math.log10(T / 262144.0)
            W = min(W, M / 2 - 0.01)
            spec = tx.biex(T, W=W, M=M)
        self.ws.set_xform(ch, spec)
        self._sync_xf_widgets()
        self._mark()
        self.refresh()

    def _mode_changed(self):
        self.plot.mode = ("density", "contour", "dots")[self.cb_mode.currentIndex()]
        self.refresh()

    # ================================================================== tree
    def _fill_tree(self):
        s = self.cur_sample
        if s is None:
            return
        stats = self.ws.stats(s)
        self.tree.blockSignals(True)
        self.tree.clear()
        root = QtWidgets.QTreeWidgetItem([s.name, f"{stats['root'][0]:,}", "", ""])
        root.setData(0, QtCore.Qt.UserRole, "root")
        self.tree.addTopLevelItem(root)
        items = {"root": root}
        for p in self.ws.pops:
            par = items.get(p["parent"])
            if par is None:
                continue
            c, pp, pt = stats.get(p["path"], (0, 0, 0))
            it = QtWidgets.QTreeWidgetItem([p["name"], f"{c:,}", f"{pp:.2f}", f"{pt:.2f}"])
            it.setData(0, QtCore.Qt.UserRole, p["path"])
            for col in (1, 2, 3):
                it.setTextAlignment(col, QtCore.Qt.AlignRight)
            if self.ws.has_override(p["path"], s.name):
                f = it.font(0); f.setItalic(True); it.setFont(0, f)
                it.setToolTip(0, "Gate adjusted for this sample only")
            par.addChild(it)
            items[p["path"]] = it
        grey = QtGui.QBrush(QtGui.QColor(70, 90, 150))
        for k, d in enumerate(self.ws.stat_defs):
            par = items.get(d["pop"])
            if par is None or d["stat"] in ("Count", "% of parent", "% of total"):
                continue                       # already shown in the tree's own columns
            v = compute_stat(self.ws, s, d)
            name = stat_name(d, self.ws, s).split(" | ", 1)[-1]
            it = QtWidgets.QTreeWidgetItem(["Σ " + name, fmt_value(d["stat"], v), "", ""])
            it.setData(0, QtCore.Qt.UserRole, f"stat:{k}")
            it.setForeground(0, grey); it.setForeground(1, grey)
            it.setTextAlignment(1, QtCore.Qt.AlignRight)
            par.addChild(it)
        self.tree.expandAll()
        sel = items.get(self.cur_pop, root)
        if self.cur_pop not in items:
            self.cur_pop = "root"
        self.tree.setCurrentItem(sel)
        self.tree.blockSignals(False)

    def _pop_changed(self):
        it = self.tree.currentItem()
        if it is None:
            return
        data = it.data(0, QtCore.Qt.UserRole)
        if data.startswith("stat:"):
            return
        self.cur_pop = data
        if self.cur_pop in self.view:
            self._set_axes(*self.view[self.cur_pop])
        else:
            # default view for a new level: the axes the first child gate was drawn on
            kids = self.ws.children(self.cur_pop)
            if kids:
                d = kids[0]["gate"]["dims"]
                self._set_axes(d[0], d[1] if len(d) > 1 else None)
        self.refresh()

    def _select_pop(self, path):
        it = self._find_item(path)
        if it is not None:
            self.tree.setCurrentItem(it)

    def _find_item(self, path):
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while it.value():
            if it.value().data(0, QtCore.Qt.UserRole) == path:
                return it.value()
            it += 1
        return None

    def _go_parent(self):
        if self.cur_pop != "root":
            self._select_pop(self.ws.pop(self.cur_pop)["parent"])

    def _tree_menu(self, pos):
        it = self.tree.itemAt(pos)
        if it is None:
            return
        path = it.data(0, QtCore.Qt.UserRole)
        gpos = self.tree.viewport().mapToGlobal(pos)
        if path.startswith("stat:"):
            k = int(path[5:])
            m = QtWidgets.QMenu(self)
            m.addAction("Remove this statistic", lambda: self._remove_stats([k]))
            m.exec(gpos)
        elif path == "root":
            m = QtWidgets.QMenu(self)
            self._add_stat_submenu(m, "root")
            m.exec(gpos)
        else:
            self._pop_menu(path, gpos)

    def _pop_menu(self, path, gpos):
        s = self.cur_sample
        m = QtWidgets.QMenu(self)
        m.addAction("Open this population", lambda: self._select_pop(path))
        self._add_stat_submenu(m, path)
        m.addAction("Rename…", lambda: self._rename(path))
        m.addAction("Delete (with its sub-gates)", lambda: self._delete(path))
        m.addSeparator()
        a = m.addAction("Edits apply to this sample only")
        a.setCheckable(True)
        a.setChecked(self.ws.has_override(path, s.name))
        a.toggled.connect(lambda on: self._toggle_override(path, on))
        if self.ws.has_override(path, s.name):
            m.addAction("Use the group gate again for this sample", lambda: self._clear_override(path))
            m.addAction("Copy this sample's gate to all samples", lambda: self._promote(path))
        g = self.ws.gate_for(path, s.name)
        if g["type"] in ("poly", "ellipse"):
            m.addAction("Convert gate to the current axis scales (to edit on these axes)",
                        lambda: self._convert_gate(path))
        m.exec(gpos)

    def _rename(self, path):
        name, ok = QtWidgets.QInputDialog.getText(self, APP, "New name:", text=path.rsplit("/", 1)[1])
        if ok and name.strip():
            new = self.ws.rename_pop(path, name.strip().replace("/", "-"))
            self.view = {(new + k[len(path):] if k == path or k.startswith(path + "/") else k): v
                         for k, v in self.view.items()}
            if self.cur_pop == path or self.cur_pop.startswith(path + "/"):
                self.cur_pop = new + self.cur_pop[len(path):]
            self._after_gate_change()

    def _delete(self, path):
        if QtWidgets.QMessageBox.question(self, APP, f"Delete {path.rsplit('/', 1)[1]} and every gate under it?") \
                != QtWidgets.QMessageBox.Yes:
            return
        if self.cur_pop == path or self.cur_pop.startswith(path + "/"):
            self.cur_pop = self.ws.pop(path)["parent"]
        self.ws.delete_pop(path)
        self._after_gate_change()

    def _delete_selected(self):
        if self.cur_pop != "root":
            self._delete(self.cur_pop)

    def _toggle_override(self, path, on):
        s = self.cur_sample
        if on:
            self.ws.set_gate(path, dict(self.ws.gate_for(path, s.name)), sname=s.name)
        else:
            self.ws.clear_override(path, s.name)
        self._after_gate_change()

    def _clear_override(self, path):
        self.ws.clear_override(path, self.cur_sample.name)
        self._after_gate_change()

    def _promote(self, path):
        s = self.cur_sample
        g = self.ws.gate_for(path, s.name)
        self.ws.set_gate(path, g)
        for ov in self.ws.overrides.values():
            ov.pop(path, None)
        self._after_gate_change()

    def _convert_gate(self, path):
        s = self.cur_sample
        g = self.ws.gate_for(path, s.name)
        x, y = g["dims"]
        xf = [self.ws.xform(x, s), self.ws.xform(y, s)]
        if g["type"] == "poly":
            v = np.asarray(g["vertices"], float)
            nv = np.column_stack([tx.apply(xf[0], tx.inverse(g["xf"][0], v[:, 0])),
                                  tx.apply(xf[1], tx.inverse(g["xf"][1], v[:, 1]))])
            ng = dict(g, xf=xf, vertices=nv.tolist())
        else:
            pts = gate_outline(g, xf[0], xf[1], n=2)[::4]
            ng = {"type": "poly", "dims": [x, y], "xf": xf, "vertices": pts[:-1].tolist()}
            if g.get("invert"):
                ng["invert"] = True
        before = self.ws.stats(s).get(path, (0,))[0]
        self.ws.set_gate(path, ng, sname=s.name if self.ws.has_override(path, s.name) else None)
        after = self.ws.stats(s).get(path, (0,))[0]
        self._after_gate_change()
        self.statusBar().showMessage(f"Converted. Count on this sample {before:,} → {after:,}", 8000)

    # ================================================================== gates
    def set_tool(self, tool):
        self.tool_actions[tool].setChecked(True)
        self.plot.set_tool(tool)
        self.statusBar().showMessage(self.tool_actions[tool].toolTip(), 5000)

    def _gate_created(self, tool, geom):
        s = self.cur_sample
        x, y = self.cb_x.currentData(), self.cb_y.currentData()
        if s is None or x is None:
            return
        xfx = self.ws.xform(x, s)
        if y is None and tool != "range":
            QtWidgets.QMessageBox.information(self, APP, "On a histogram, use the Range tool.")
            return
        if y is not None and tool == "range":
            QtWidgets.QMessageBox.information(self, APP, "The Range tool is for histograms: set Y to [Histogram].")
            return
        xfy = self.ws.xform(y, s) if y else None
        mx = self._short(x)
        my = self._short(y) if y else ""
        if tool == "quad":
            cx, cy = geom
            quads = [(f"{mx}- {my}+", [None, cy], [cx, None]), (f"{mx}+ {my}+", [cx, cy], [None, None]),
                     (f"{mx}+ {my}-", [cx, None], [None, cy]), (f"{mx}- {my}-", [None, None], [cx, cy])]
            for name, lo, hi in quads:
                self.ws.add_pop(self.cur_pop, name, {"type": "rect", "dims": [x, y], "xf": [xfx, xfy],
                                                     "min": lo, "max": hi})
            self._after_gate_change()
            self.set_tool("pointer")
            return
        default = {"range": f"{mx}+", "rect": f"{mx} {my}", "poly": f"{mx} {my}", "ellipse": f"{mx} {my}"}[tool]
        name, ok = QtWidgets.QInputDialog.getText(self, APP, "Name for this population:", text=default)
        if not ok or not name.strip():
            self.refresh()
            return
        name = name.strip().replace("/", "-")
        if tool == "range":
            l, _, r, _ = geom
            g = {"type": "rect", "dims": [x], "xf": [xfx], "min": [l], "max": [r]}
        elif tool == "rect":
            l, t, r, b = geom
            g = {"type": "rect", "dims": [x, y], "xf": [xfx, xfy], "min": [l, t], "max": [r, b]}
        elif tool == "ellipse":
            l, t, r, b = geom
            g = {"type": "ellipse", "dims": [x, y], "xf": [xfx, xfy], "center": [(l + r) / 2, (t + b) / 2],
                 "axes": [(r - l) / 2, (b - t) / 2], "angle": 0.0}
        else:
            g = {"type": "poly", "dims": [x, y], "xf": [xfx, xfy], "vertices": [list(p) for p in geom]}
        self.ws.add_pop(self.cur_pop, name, g)
        self._after_gate_change()
        self.set_tool("pointer")

    def _short(self, ch):
        rc = self.ws.raw_channel(ch)
        lab = self.ws.marker(rc)
        lab = re.sub(r"-[AHW]$", "", lab.strip())
        if not lab:
            return re.sub(r"-[AHW]$", "", rc)
        return lab.split()[0].split("-")[0] or rc

    def _gate_edited(self, path, gate):
        s = self.cur_sample
        per_sample = self.ws.has_override(path, s.name) or self.act_local.isChecked()
        self.ws.set_gate(path, gate, sname=s.name if per_sample else None)
        self._after_gate_change(redraw=False)
        if per_sample:
            self.statusBar().showMessage(f"Gate changed for {s.name} only", 5000)

    def _local_toggled(self, on):
        self.settings.setValue("edit_local", on)
        self.act_local.setText("Edit: this sample" if on else "Edit: all samples")

    def _sync_undo_actions(self):
        u, r = self.ws.undo_label(), self.ws.redo_label()
        self.act_undo.setEnabled(self.ws.can_undo)
        self.act_redo.setEnabled(self.ws.can_redo)
        self.act_undo.setText("Undo %s" % u if u else "Undo")
        self.act_redo.setText("Redo %s" % r if r else "Redo")

    def do_undo(self):
        label = self.ws.undo()
        if label is None and not self.ws.can_redo:
            self.statusBar().showMessage("Nothing to undo", 3000)
            return
        self._after_undo("Undid %s" % label if label else "Undone")

    def do_redo(self):
        label = self.ws.redo()
        if label is None:
            self.statusBar().showMessage("Nothing to redo", 3000)
            return
        self._after_undo("Redid %s" % label if label else "Redone")

    def _after_undo(self, msg):
        keep = self.ws.samples[self.sample_list.currentRow()].name \
            if self.ws.samples and self.sample_list.currentRow() >= 0 else None
        self._fill_tree()
        self._sync_xf_widgets()
        self.refresh()
        if self.tabs.currentIndex() == 2:
            self._refresh_table()
        self._mark()
        self._sync_undo_actions()
        self.statusBar().showMessage(msg, 4000)

    def _quad_moved(self, members, cx, cy):
        """A crosshair arm was dragged: rewrite all four quadrants from the new centre.

        Honours the same per-sample / all-samples switch as dragging an ordinary gate,
        so a crosshair nudged on one well in Edit-this-sample mode stays local to it.
        """
        s = self.cur_sample
        per_sample = self.act_local.isChecked() if hasattr(self, "act_local") else False
        self.ws.move_quad(members, cx, cy, sname=s.name if per_sample else None)
        self._after_gate_change()

    def _after_gate_change(self, redraw=True):
        self._mark()
        self._fill_tree()
        self.refresh()
        if self.tabs.currentIndex() == 2:
            self._refresh_table()

    # ================================================================== drawing
    def refresh(self):
        s = self.cur_sample
        if s is None or self.tabs.currentIndex() != 0:
            if self.tabs.currentIndex() == 1:
                self._refresh_overview()
            return
        x, y = self.cb_x.currentData(), self.cb_y.currentData()
        if x is None:
            return
        gates = [(p["path"], self.ws.gate_for(p["path"], s.name)) for p in self.ws.children(self.cur_pop)]
        ctx = {"ws": self.ws, "sample": s, "pop": self.cur_pop, "x": x, "y": y,
               "xf_x": self.ws.xform(x, s), "xf_y": self.ws.xform(y, s) if y else None, "gates": gates}
        try:
            self.plot.show_population(ctx)
        except Exception as e:
            traceback.print_exc()
            self.statusBar().showMessage(f"Could not draw: {e}", 8000)
            return
        n = self.ws.stats(s).get(self.cur_pop, (0,))[0]
        pname = "All events" if self.cur_pop == "root" else self.cur_pop.rsplit("/", 1)[1]
        self.lbl_info.setText(f"<b>{pname}</b> · {n:,} events · {s.name}")

    def _tab_changed(self, i):
        if i == 0:
            self.refresh()
        elif i == 1:
            self._refresh_overview()
        else:
            self._refresh_table()

    def _refresh_overview(self):
        while self.ov_grid.count():
            w = self.ov_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not self.ws.samples:
            return
        x, y = self.cb_x.currentData(), self.cb_y.currentData()
        if x is None or y is None:
            self.ov_note.setText("Choose two axes (not a histogram) on the Gating tab.")
            return
        s0 = self.cur_sample
        xfx, xfy = self.ws.xform(x, s0), self.ws.xform(y, s0)
        pname = "All events" if self.cur_pop == "root" else self.cur_pop.rsplit("/", 1)[1]
        self.ov_note.setText(f"<b>{pname}</b>: {self.ws.label(y, s0)} vs {self.ws.label(x, s0)} · "
                             "click a plot to open that sample")
        cols = max(3, (self.ov_area.viewport().width() - 20) // 210)
        prog = QtWidgets.QProgressDialog("Drawing all samples…", "Stop", 0, len(self.ws.samples), self)
        prog.setWindowModality(QtCore.Qt.WindowModal); prog.setMinimumDuration(400)
        for i, s in enumerate(self.ws.samples):
            prog.setValue(i)
            if prog.wasCanceled():
                break
            try:
                pix = self._thumb(s, x, y, xfx, xfy)
            except Exception as e:
                pix = None
                print(e)
            lab = ClickLabel(i)
            lab.clicked.connect(self._thumb_clicked)
            if pix is not None:
                lab.setPixmap(pix)
            lab.setToolTip(s.name)
            self.ov_grid.addWidget(lab, i // cols, i % cols)
        prog.setValue(len(self.ws.samples))

    def _thumb(self, s, x, y, xfx, xfy, size=200, bins=128):
        ed = self.ws.events(s)
        m = self.ws.masks(s)[self.cur_pop]
        X = np.clip(tx.apply(xfx, ed.col(x)[m]), 0, 1)
        Y = np.clip(tx.apply(xfy, ed.col(y)[m]), 0, 1)
        H, _, _ = np.histogram2d(X, Y, bins=bins, range=[[0, 1], [0, 1]])
        lvl = density_levels(H).astype(np.uint8)
        rgba = LUT[lvl]                       # (x, y, 4)
        rgba = np.ascontiguousarray(np.flipud(rgba.transpose(1, 0, 2)))   # rows = y, top = high
        rgba[rgba[..., 3] == 0] = (255, 255, 255, 255)
        qi = QtGui.QImage(rgba.data, bins, bins, 4 * bins, QtGui.QImage.Format_RGBA8888).copy()
        pix = QtGui.QPixmap.fromImage(qi.scaled(size, size, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation))
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0), 1.3))
        stats = self.ws.stats(s)
        for c in self.ws.children(self.cur_pop):
            g = self.ws.gate_for(c["path"], s.name)
            if len(g["dims"]) != 2 or set(g["dims"]) != {x, y}:
                continue
            pts = gate_outline(g, xfx, xfy, swap=g["dims"] != [x, y], n=8)
            poly = QtGui.QPolygonF([QtCore.QPointF(px * size, (1 - py) * size) for px, py in pts])
            p.drawPolyline(poly)
            inside = pts[(pts[:, 0] > 0) & (pts[:, 0] < 1) & (pts[:, 1] > 0) & (pts[:, 1] < 1)]
            if len(inside):
                cx, cy = inside.mean(0)
                p.drawText(QtCore.QPointF(cx * size - 18, (1 - cy) * size), f"{stats[c['path']][1]:.1f}%")
        p.setPen(QtGui.QColor(60, 60, 60))
        f = p.font(); f.setPointSize(7); p.setFont(f)
        p.drawText(QtCore.QRectF(2, 2, size - 4, 14), QtCore.Qt.AlignLeft, s.name[-28:])
        p.drawText(QtCore.QRectF(2, size - 14, size - 4, 12), QtCore.Qt.AlignRight, f"n={int(m.sum()):,}")
        p.setPen(QtGui.QPen(QtGui.QColor(160, 160, 160), 1))
        p.drawRect(0, 0, size - 1, size - 1)
        p.end()
        return pix

    def _thumb_clicked(self, i):
        self.sample_list.setCurrentRow(i)
        self.tabs.setCurrentIndex(0)

    def _refresh_table(self):
        self.table.clear()
        self.stat_hint.setVisible(not self.ws.stat_defs)
        if not self.ws.samples:
            return
        s0 = self.ws.samples[0]
        cols = self.ws.annot_cols
        defs = self.ws.stat_defs
        self.table.setRowCount(len(self.ws.samples))
        self.table.setColumnCount(len(cols) + len(defs))
        heads = list(cols) + [stat_name(d, self.ws, s0).replace(" | ", "\n") for d in defs]
        self.table.setHorizontalHeaderLabels(heads)
        for j, d in enumerate(defs):
            self.table.horizontalHeaderItem(len(cols) + j).setToolTip(
                f"{d['pop']}\n{STATS[d['stat']][1]}\nDouble-click to rename; right-click for options")
        self.table.setVerticalHeaderLabels([s.name for s in self.ws.samples])
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            for r, s in enumerate(self.ws.samples):
                ann = self.ws.annotations.get(s.name, {})
                for c, col in enumerate(cols):
                    self.table.setItem(r, c, QtWidgets.QTableWidgetItem(str(ann.get(col, ""))))
                for j, d in enumerate(defs):
                    it = QtWidgets.QTableWidgetItem(fmt_value(d["stat"], compute_stat(self.ws, s, d)))
                    it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                    if d["pop"] != "root" and self.ws.has_override(d["pop"], s.name):
                        f = it.font(); f.setItalic(True); it.setFont(f)
                    self.table.setItem(r, len(cols) + j, it)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setMinimumSectionSize(70)

    # ================================================================== statistics
    QUICK_STATS = ["Median", "Mean", "Geometric mean", "SD", "CV", "Robust CV"]

    def _add_stat_submenu(self, menu, path):
        """FlowJo's right-click route to a statistic: pick it, pick a channel, done.

        The dialog is still there under "More…", and it is the better tool for adding
        the same statistic to twelve populations at once. But the common case is one
        population and one marker, and that should not cost a dialog. The two channels
        currently on the axes come first, because they are nearly always the ones
        wanted, with the rest of the panel underneath.
        """
        sub = menu.addMenu("Σ Add statistic")
        sub.setToolTipsVisible(True)
        for st in ("Count", "% of parent", "% of total"):
            act = sub.addAction(st, lambda s=st: self._quick_stat(path, s))
            act.setToolTip(STATS[st][1])
        sub.addSeparator()
        chans = self._stat_channels()
        for st in self.QUICK_STATS:
            if not chans:
                break
            ch_menu = sub.addMenu(st)
            ch_menu.setToolTipsVisible(True)
            for ch, label, on_axis in chans:
                act = ch_menu.addAction(label, lambda s=st, c=ch: self._quick_stat(path, s, c))
                act.setToolTip(STATS[st][1])
                if on_axis:
                    f = act.font(); f.setBold(True); act.setFont(f)
            ch_menu.setToolTip(STATS[st][1])
        sub.addSeparator()
        sub.addAction("More statistics…", lambda: self.add_stat([path]))

    def _stat_channels(self):
        """(channel, label, is_on_an_axis) for the panel, axes first."""
        s = self.cur_sample
        if s is None:
            return []
        on_axis = [c for c in (self.cb_x.currentData(), self.cb_y.currentData()) if c]
        out = [(c, self.ws.label(c, s).split(" :: ")[-1], True) for c in on_axis]
        seen = set(on_axis)
        rest = [(c, self.ws.label(c, s).split(" :: ")[-1], False)
                for c in self.ws.display_channels(s) if c not in seen]
        return out + rest

    def _quick_stat(self, path, stat, channel=None):
        d = {"pop": path, "stat": stat, "channel": channel}
        if any(json.dumps(x, sort_keys=True) == json.dumps(d, sort_keys=True)
               for x in self.ws.stat_defs):
            self.statusBar().showMessage("That column is already in the table", 4000)
            return
        self.ws.stat_defs.append(d)
        self._stats_changed("Added %s" % stat_name(d, self.ws, self.cur_sample))

    def add_stat(self, preselect=None):
        if self.cur_sample is None:
            return
        if preselect is None:
            preselect = [self.cur_pop]
        dlg = AddStatDialog(self.ws, self.cur_sample, self, preselect=preselect, channel=self.cb_x.currentData())
        if dlg.exec():
            new = dlg.defs()
            if not new:
                QtWidgets.QMessageBox.information(self, APP, "Pick at least one population (and a channel for "
                                                             "intensity statistics).")
                return
            have = {json.dumps(d, sort_keys=True) for d in self.ws.stat_defs}
            self.ws.stat_defs += [d for d in new if json.dumps(d, sort_keys=True) not in have]
            self._stats_changed(f"Added {len(new)} statistic column(s)")

    def _add_standard_stats(self):
        have = {json.dumps(d, sort_keys=True) for d in self.ws.stat_defs}
        add = []
        for p in self.ws.pops:
            for st in ("Count", "% of parent"):
                d = {"pop": p["path"], "stat": st, "channel": None}
                if json.dumps(d, sort_keys=True) not in have:
                    add.append(d)
        self.ws.stat_defs += add
        self._stats_changed(f"Added {len(add)} columns")

    def _selected_stat_cols(self):
        n = len(self.ws.annot_cols)
        cols = sorted({i.column() for i in self.table.selectedIndexes()} |
                      {i.column() for i in self.table.selectionModel().selectedColumns()})
        return [c - n for c in cols if c >= n]

    def _remove_stat_cols(self):
        ks = self._selected_stat_cols()
        if not ks:
            QtWidgets.QMessageBox.information(self, APP, "Click a column header first (Ctrl-click for several).")
            return
        self._remove_stats(ks)

    def _remove_stats(self, ks):
        self.ws.stat_defs = [d for k, d in enumerate(self.ws.stat_defs) if k not in set(ks)]
        self._stats_changed(f"Removed {len(ks)} column(s)")

    def _move_stat(self, step):
        ks = self._selected_stat_cols()
        if len(ks) != 1:
            return
        k = ks[0]; t = k + step
        if 0 <= t < len(self.ws.stat_defs):
            d = self.ws.stat_defs
            d[k], d[t] = d[t], d[k]
            self._stats_changed()
            self.table.selectColumn(len(self.ws.annot_cols) + t)

    def _rename_stat(self, col):
        k = col - len(self.ws.annot_cols)
        if k < 0:
            return
        d = self.ws.stat_defs[k]
        name, ok = QtWidgets.QInputDialog.getText(self, APP, "Column name (empty = automatic):",
                                                  text=stat_name(d, self.ws, self.ws.samples[0]))
        if ok:
            d.pop("name", None)
            if name.strip() and name.strip() != stat_name(d, self.ws, self.ws.samples[0]):
                d["name"] = name.strip()
            self._stats_changed()

    def _stat_header_menu(self, pos):
        col = self.table.horizontalHeader().logicalIndexAt(pos)
        k = col - len(self.ws.annot_cols)
        m = QtWidgets.QMenu(self)
        if k >= 0:
            m.addAction("Rename column…", lambda: self._rename_stat(col))
            m.addAction("Remove column", lambda: self._remove_stats([k]))
            m.addAction("Show this population on the Gating tab",
                        lambda: (self.tabs.setCurrentIndex(0), self._select_pop(self.ws.stat_defs[k]["pop"])))
        else:
            m.addAction("Edit annotations…", self.annotate)
        m.exec(self.table.horizontalHeader().mapToGlobal(pos))

    def _stats_changed(self, msg=None):
        self._mark()
        self._fill_tree()
        self._refresh_table()
        if msg:
            self.statusBar().showMessage(msg, 5000)

    def _copy_table(self):
        df = stats_table(self.ws)
        QtWidgets.QApplication.clipboard().setText(df.to_csv(sep="\t", index=False))
        self.statusBar().showMessage(f"Copied {len(df)} rows × {df.shape[1]} columns", 5000)

    def annotate(self):
        if not self.ws.samples:
            return
        dlg = AnnotateDialog(self.ws, self)
        if dlg.exec():
            dlg.store()
            self._stats_changed("Annotations saved")

    # ================================================================== templates / samples
    def save_template(self):
        if not self.ws.pops:
            QtWidgets.QMessageBox.information(self, APP, "There are no gates to save yet.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save gating template", os.path.join(self.settings.value("lastdir", os.path.expanduser("~")),
                                                       "gating_template.fgt"), "Cytolux template (*.fgt)")
        if not path:
            return
        if not path.endswith(".fgt"):
            path += ".fgt"
        with open(path, "w") as f:
            json.dump(template_dict(self.ws), f, indent=1)
        self.statusBar().showMessage(f"Template saved: {path}", 6000)
        QtWidgets.QMessageBox.information(
            self, APP, f"Saved the gates, statistics, axis scales and channel names to\n{path}\n\n"
                       "Next time: File → New analysis: FCS folder + gating template.")

    def apply_template_file(self, path=None):
        if not self.ws.samples:
            QtWidgets.QMessageBox.information(self, APP, "Open the FCS files first.")
            return
        if not path:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Gating template", self.settings.value("lastdir", os.path.expanduser("~")),
                "Templates and workspaces (*.fgt *.fgw)")
        if not path:
            return
        if self.ws.pops and QtWidgets.QMessageBox.question(
                self, APP, "Replace the current gates with the template's?") != QtWidgets.QMessageBox.Yes:
            return
        d = json.load(open(path))
        missing = apply_template(self.ws, d)
        self.cur_pop = "root"
        self.view = {}
        self._mark()
        self._fill_samples()
        msg = f"Applied {len(self.ws.pops)} gates and {len(self.ws.stat_defs)} statistics to {len(self.ws.samples)} samples."
        if missing:
            msg += ("\n\nWarning: these channels are used by the template but are not in the new files:\n  "
                    + ", ".join(missing) + "\nGates on them will count 0 events. Check the panel.")
        msg += "\n\nNext: look through the samples (All samples tab) and adjust any gate that does not fit."
        QtWidgets.QMessageBox.information(self, APP, msg)

    def new_from_template(self):
        if not self._maybe_save():
            return
        tpl, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Step 1 of 2: choose the gating template", self.settings.value("lastdir", os.path.expanduser("~")),
            "Templates and workspaces (*.fgt *.fgw)")
        if not tpl:
            return
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Step 2 of 2: folder with the new FCS files",
                                                       os.path.dirname(tpl))
        if not d:
            return
        files = sorted(glob.glob(os.path.join(d, "*.fcs")) + glob.glob(os.path.join(d, "*.FCS")))
        if not files:
            QtWidgets.QMessageBox.information(self, APP, "No .fcs files in that folder.")
            return
        self.ws = Workspace()
        self.ws.add_files(files)
        self.dirty = False
        self.ws.pops = []
        self.apply_template_file(tpl)
        self._update_title()

    def _sample_menu(self, pos):
        rows = sorted({i.row() for i in self.sample_list.selectedIndexes()})
        if not rows:
            return
        m = QtWidgets.QMenu(self)
        m.addAction(f"Remove {len(rows)} sample(s) from the workspace", lambda: self._remove_samples(rows))
        m.exec(self.sample_list.viewport().mapToGlobal(pos))

    def _remove_samples(self, rows):
        names = {self.ws.samples[r].name for r in rows}
        self.ws.samples = [s for s in self.ws.samples if s.name not in names]
        for n in names:
            self.ws.overrides.pop(n, None)
            self.ws.annotations.pop(n, None)
        self.ws.changed(events=True)
        self._mark()
        self._fill_samples()

    # ================================================================== help
    def show_fj_check(self):
        if not self.fj_counts:
            QtWidgets.QMessageBox.information(self, APP, "Import a FlowJo workspace first (File → Import FlowJo workspace).")
            return
        lines, exact, total, worst = [], 0, 0, {}
        for sname, counts in self.fj_counts.items():
            s = self.ws.sample(sname)
            st = self.ws.stats(s)
            for path, c in counts.items():
                if path not in st:
                    continue
                mine = st[path][0]
                total += 1; exact += mine == c
                if path != "root":
                    par = self.ws.pop(path)["parent"]
                    d = abs(100 * c / counts[par] - st[path][1]) if counts.get(par) else 0
                    worst[path] = max(worst.get(path, 0), d)
        lines.append(f"Counts identical to FlowJo: {exact} of {total}.")
        lines.append("Largest difference in % of parent, per population:")
        for p, d in worst.items():
            lines.append(f"   {p.rsplit('/', 1)[1]:28s} {d:.3f} percentage points")
        lines.append("\nSmall differences come from FlowJo's own rounding of ellipse gates; "
                     "gates you edit here are exact.")
        box = QtWidgets.QMessageBox(self); box.setWindowTitle("Check against FlowJo")
        box.setText("<pre>" + "\n".join(lines) + "</pre>"); box.exec()

    def show_confidence(self):
        """Per-sample confidence, docked beside the gating tree.

        Opens blank. The measurement is a second or two of work and gating is a
        continuous activity, so it runs when asked rather than on every mouse release.
        """
        if not self.ws.samples:
            QtWidgets.QMessageBox.information(self, APP, "Open some samples first.")
            return
        if getattr(self, "_conf_dock", None) is None:
            panel = UncertaintyDock(self.ws, self)
            panel.btn.clicked.connect(panel.run)
            dock = QtWidgets.QDockWidget("Confidence", self)
            dock.setObjectName("confidence")
            dock.setWidget(panel)
            self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
            self._conf_dock, self._conf_panel = dock, panel
        self._conf_panel.ws = self.ws
        self._conf_panel.set_sample(self.cur_sample)
        self._conf_dock.show()
        self._conf_dock.raise_()

    def show_fragility(self):
        """The workspace-wide report: which gate is the weakest, across every sample."""
        if not self.ws.samples:
            QtWidgets.QMessageBox.information(self, APP, "Open some samples first.")
            return
        if not self.ws.pops:
            QtWidgets.QMessageBox.information(self, APP, "Draw at least one gate first.")
            return
        FragilityDialog(self.ws, self).exec()

    def show_assistant(self):
        """A dockable, offline help search. No network, no account, no key."""
        if getattr(self, "_assist_dock", None) is None:
            self._assistant = Assistant()
            dock = QtWidgets.QDockWidget("Find how to do something", self)
            dock.setObjectName("assistant")
            body = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(body)
            box = QtWidgets.QLineEdit()
            box.setPlaceholderText("Ask in your own words, for example: how do I export to Excel")
            box.setClearButtonEnabled(True)
            box.setToolTip("Type a question. Results update as you type. Everything stays on "
                           "this computer.")
            out = QtWidgets.QTextBrowser()
            out.setOpenExternalLinks(False)
            hint = QtWidgets.QLabel(
                "Try: " + " · ".join(self._assistant.suggestions()[:4]))
            hint.setWordWrap(True)
            hint.setStyleSheet("color: palette(mid);")
            lay.addWidget(box); lay.addWidget(out); lay.addWidget(hint)
            dock.setWidget(body)
            self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
            box.textChanged.connect(lambda t: out.setHtml(self._assistant_html(t)))
            self._assist_dock, self._assist_box, self._assist_out = dock, box, out
            out.setHtml(self._assistant_html(""))
        self._assist_dock.show()
        self._assist_dock.raise_()
        self._assist_box.setFocus()
        self._assist_box.selectAll()

    def _assistant_html(self, question):
        import html as _html
        if not (question or "").strip():
            return ("<p style='color:gray'>Type a question above. The answers come from this "
                    "application's own help, so nothing leaves your computer.</p>")
        hits = self._assistant.ask(question)
        if not hits:
            return "<p style='color:gray'>%s</p>" % _html.escape(NO_MATCH)
        parts = []
        for h in hits:
            where = ("<div style='color:#2a6'><b>%s</b></div>" % _html.escape(h.where)) if h.where else ""
            parts.append("<p><b>%s</b>%s<br>%s</p>"
                         % (_html.escape(h.title), where, _html.escape(h.body)))
        return "".join(parts)

    def show_help(self):
        QtWidgets.QMessageBox.information(self, "Cytolux quick guide", HELP)


class ClickLabel(QtWidgets.QLabel):
    clicked = QtCore.Signal(int)

    def __init__(self, idx):
        super().__init__()
        self.idx = idx
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def mousePressEvent(self, ev):
        self.clicked.emit(self.idx)


HELP = """<h3>Cytolux</h3>
<p><b>Start:</b> File → Open FCS folder, or File → Import FlowJo workspace (.wsp) to bring in your FlowJo gates.</p>
<p><b>Look:</b> pick the Y and X channels above the plot; choose Linear, Log or Biex for each axis
(W sets the biex width around zero). Click a population in the gate tree to see the events inside it.
PgUp / PgDown move between samples.</p>
<p><b>Gate:</b> pick a tool (keys 1–6), draw on the plot, name the population. The new gate sits under
the population you are looking at and applies to every sample. Double-click a gate to open it;
Backspace goes back up.</p>
<ul>
<li>Rectangle / Ellipse: drag. Polygon: click corners, then double-click or Enter.</li>
<li>Quadrant: click the crossing point. Range: on a histogram (Y = [Histogram]), drag across the peak.</li>
<li>Edit: drag the gate or its handles with Select (1). Statistics update when you let go.</li>
<li>Editing, FlowJo style: with <b>Edit: this sample</b> on (toolbar, key L), dragging a gate changes it for the
current sample only; the gate turns italic. Right-click → "Copy this sample's gate to all samples" to push it to all.
Switch to <b>Edit: all samples</b> to move the gate on every sample at once.</li>
</ul>
<p><b>All samples</b> tab: every sample on the current axes with the gates drawn on it.
<b>Statistics</b> tab: counts and percentages for every sample and gate; Export to Excel.</p>
<p><b>Confidence</b> (Ctrl+U): a frequency is a count divided by a line you drew with a mouse.
Cytolux moves every boundary by about as much as a careful hand would, re-gates the file, and reports
how far each percentage travelled. Green means quote it, amber means quote the interval with it, red
means fix something first. "Limited by" says which something: <b>gate</b> means redraw it,
<b>counting</b> means too few cells landed in the population and only more events will help.
Confidence → Find the weakest gates sweeps every sample and sorts worst first.</p>
<p><b>Save</b> the workspace (Ctrl+S) as a .fgw file; it remembers files, compensation, gates and axes.</p>
<p>Compensation uses the matrix written into the FCS files by default (FlowJo's "acquisition-defined").</p>"""


def main():
    QtWidgets.QApplication.setApplicationName(APP)
    # Must be set before the QApplication exists. Without it Qt rounds a 150% display
    # down to 100% and every plot is drawn at two thirds of the resolution the screen
    # can actually show, which is half of why the pictures looked soft.
    QtGui.QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QtWidgets.QApplication(sys.argv)
    app.setDesktopFileName("cytolux")
    w = MainWindow()
    w.show()
    for a in sys.argv[1:]:
        if a.endswith(".fgw"):
            w._safe(lambda: w.open_workspace(a))
        elif os.path.isdir(a):
            w._load_files(sorted(glob.glob(os.path.join(a, "*.fcs"))))
    sys.exit(app.exec())
