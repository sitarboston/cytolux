"""The confidence window: a frequency, the range it really covers, and what to do.

Two views of the same computation. One sample at a time, beside the gating tree, for
while the gates are being drawn; and the whole workspace at once, sorted worst first,
for the moment before the numbers go into a figure.

Colour carries the grade, because the grade is the only thing most people will read.
Green means quote it. Amber means quote the interval with it. Red means fix something
first, and the "Limited by" column says which something.
"""
import os

import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from .help_text import WIDGET_TIPS
from .uncertainty import (DEFAULT_LEVEL, DEFAULT_N, DEFAULT_SIGMA, fragility_report,
                          gate_uncertainty)

GRADE_BG = {
    "firm": QtGui.QColor(226, 245, 230),
    "soft": QtGui.QColor(255, 244, 214),
    "fragile": QtGui.QColor(253, 226, 226),
    "unknown": QtGui.QColor(238, 238, 238),
}
GRADE_FG = {
    "firm": QtGui.QColor(20, 90, 40),
    "soft": QtGui.QColor(125, 75, 0),
    "fragile": QtGui.QColor(145, 25, 25),
    "unknown": QtGui.QColor(110, 110, 110),
}
GRADE_NOTE = {
    "firm": "quote it as it stands",
    "soft": "quote the interval with it",
    "fragile": "fix something before quoting it",
    "unknown": "nothing to measure: the parent population was empty",
}

HEADER_TIPS = {
    "% of parent": "The frequency as the statistics table reports it, with no gates moved.",
    "Low": "Bottom of the interval, gate and counting error together.",
    "High": "Top of the interval, gate and counting error together.",
    "Half width": "Half the interval, in percentage points. The plus or minus.",
    "Relative": "The half interval as a fraction of the frequency itself. The figure to\n"
                "read: a tenth means the number could be a tenth bigger or smaller.",
    "Gate half width": "How much of the doubt comes from where the boundary sits.\n"
                       "Shrink it by redrawing the gate, or by picking a better pair of axes.",
    "Counting half width": "How much comes from the number of cells counted.\n"
                           "Shrink it only by acquiring more events.",
    "Limited by": "Which of the two is larger, and therefore which one to go and fix.",
    "Bias": "How far the replicates' centre sits from the reported number. A large\n"
            "value means the boundary is on a steep slope and the frequency is not\n"
            "symmetric about where it was drawn.",
    "Grade": "firm: quote it. soft: quote the interval with it. fragile: fix something first.",
}


class UncertaintyDock(QtWidgets.QWidget):
    """Per-sample confidence, meant to sit open while gates are being drawn.

    Nothing recomputes on its own. Re-gating a population invalidates the numbers here
    rather than silently refreshing them, because two hundred replicates on every mouse
    release would make the gating tab unusable, and a stale interval quietly following a
    moved gate would be worse than a blank one.
    """

    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.ws = ws
        self.sample = None
        self._stale = True
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        self.head = QtWidgets.QLabel()
        self.head.setWordWrap(True)
        lay.addWidget(self.head)

        row = QtWidgets.QHBoxLayout()
        self.btn = QtWidgets.QPushButton("Measure confidence")
        self.btn.setToolTip(WIDGET_TIPS["uncertainty_run"])
        row.addWidget(self.btn)
        row.addWidget(QtWidgets.QLabel("hand:"))
        self.sigma = QtWidgets.QDoubleSpinBox()
        self.sigma.setRange(0.1, 10.0)
        self.sigma.setSingleStep(0.1)
        self.sigma.setSuffix(" %")
        self.sigma.setDecimals(1)
        self.sigma.setValue(DEFAULT_SIGMA * 100)
        self.sigma.setToolTip(WIDGET_TIPS["uncertainty_sigma"])
        row.addWidget(self.sigma)
        row.addWidget(QtWidgets.QLabel("runs:"))
        self.reps = QtWidgets.QSpinBox()
        self.reps.setRange(10, 2000)
        self.reps.setSingleStep(50)
        self.reps.setValue(DEFAULT_N)
        self.reps.setToolTip(WIDGET_TIPS["uncertainty_reps"])
        row.addWidget(self.reps)
        row.addStretch(1)
        lay.addLayout(row)

        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Population", "% of parent", "Interval", "±", "Limited by", "Grade"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table, 1)

        self.note = QtWidgets.QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #555;")
        lay.addWidget(self.note)
        self.set_stale()

    # --- state
    def set_sample(self, s):
        if s is not self.sample:
            self.sample = s
            self.set_stale()

    def set_stale(self):
        """Mark the numbers as no longer describing the gates on screen."""
        self._stale = True
        self.table.setRowCount(0)
        name = self.sample.name if self.sample else "no sample"
        self.head.setText("<b>%s</b>" % name)
        self.note.setText(
            "Moving a gate changes these numbers, so they are not kept up to date on "
            "their own. Press <b>Measure confidence</b> when the gates are where you "
            "want them.")

    def run(self):
        if self.sample is None or not self.ws.pops:
            self.note.setText("Draw at least one gate first.")
            return
        sigma = self.sigma.value() / 100.0
        n = self.reps.value()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            u = gate_uncertainty(self.ws, self.sample, n=n, sigma=sigma)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self._fill(u, sigma, n)
        self._stale = False

    def _fill(self, u, sigma, n):
        rows = [(p["path"], u[p["path"]]) for p in self.ws.pops if p["path"] in u]
        self.table.setRowCount(len(rows))
        worst = None
        for r, (path, pu) in enumerate(rows):
            comb = pu.combined
            cells = [
                ("  " * (path.count("/") - 1) + pu.name, path),
                ("%.2f" % pu.parent_pct.value, None),
                ("%.2f to %.2f" % (comb.lo, comb.hi), None),
                ("%.2f" % comb.half_width, None),
                (pu.limited_by, HEADER_TIPS["Limited by"]),
                (pu.grade, GRADE_NOTE[pu.grade]),
            ]
            for c, (text, tip) in enumerate(cells):
                it = QtWidgets.QTableWidgetItem(text)
                if c:
                    it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                it.setBackground(GRADE_BG[pu.grade])
                if c == 5:
                    it.setForeground(GRADE_FG[pu.grade])
                    f = it.font(); f.setBold(True); it.setFont(f)
                if tip:
                    it.setToolTip(tip)
                self.table.setItem(r, c, it)
            if pu.grade == "fragile" and worst is None:
                worst = pu
        self.table.resizeColumnsToContents()
        self.head.setText("<b>%s</b> · %d runs · hand %.1f%% of each axis"
                          % (self.sample.name, n, sigma * 100))
        if worst is None:
            self.note.setText("No population here is fragile at this setting.")
        else:
            self.note.setText(
                "<b>%s</b> is the weakest: %.2f%% could be anywhere from %.2f to %.2f. "
                "Limited by <b>%s</b>, so %s."
                % (worst.name, worst.parent_pct.value, worst.combined.lo, worst.combined.hi,
                   worst.limited_by,
                   "redrawing that gate is what would help" if worst.limited_by == "gate"
                   else "only more events would help"))


def shared_prefix(names):
    """The leading text every name has in common, trimmed back to a word boundary.

    A plate is ninety-six files whose names are identical but for the well, so the
    first forty characters of the Sample column are the same on every row and the part
    that identifies the row is the part that gets cut off. What is common to all of
    them cannot distinguish any of them, so it can go.
    """
    names = [n for n in names if n]
    if len(names) < 2:
        return ""
    first, last = min(names), max(names)
    i = 0
    while i < min(len(first), len(last)) and first[i] == last[i]:
        i += 1
    cut = max(first.rfind(c, 0, i) for c in " _-/.")
    return first[:cut + 1] if cut > 0 else ""


def trim_front(text, prefix, keep=34):
    """Drop a known-uninformative prefix, then hard-trim from the left if still long."""
    out = text[len(prefix):] if prefix and text.startswith(prefix) else text
    if len(out) > keep:
        out = "…" + out[-keep:]
    return out or text


class FragilityDialog(QtWidgets.QDialog):
    """Every sample, every population, weakest first.

    The view that is worth having before results leave the building: it finds the gate
    that cannot carry the weight being put on it without anyone having to guess which
    one to check.
    """

    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.ws = ws
        self.df = pd.DataFrame()
        self.setWindowTitle("How much your numbers can move")
        self.resize(1080, 620)
        lay = QtWidgets.QVBoxLayout(self)

        intro = QtWidgets.QLabel(
            "Every boundary in the gating tree is moved by about as much as a careful "
            "hand would place it, every sample is re-gated from the root, and this is "
            "where the frequencies went. Weakest first.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Hand steadiness:"))
        self.sigma = QtWidgets.QDoubleSpinBox()
        self.sigma.setRange(0.1, 10.0); self.sigma.setSingleStep(0.1)
        self.sigma.setDecimals(1); self.sigma.setSuffix(" % of each axis")
        self.sigma.setValue(DEFAULT_SIGMA * 100)
        self.sigma.setToolTip(WIDGET_TIPS["uncertainty_sigma"])
        row.addWidget(self.sigma)
        row.addWidget(QtWidgets.QLabel("Runs per sample:"))
        self.reps = QtWidgets.QSpinBox()
        self.reps.setRange(10, 2000); self.reps.setSingleStep(50)
        self.reps.setValue(100)
        self.reps.setToolTip(WIDGET_TIPS["uncertainty_reps"])
        row.addWidget(self.reps)
        row.addWidget(QtWidgets.QLabel("Confidence:"))
        self.level = QtWidgets.QSpinBox()
        self.level.setRange(50, 99); self.level.setSuffix(" %")
        self.level.setValue(int(DEFAULT_LEVEL))
        self.level.setToolTip(WIDGET_TIPS["uncertainty_level"])
        row.addWidget(self.level)
        self.only_bad = QtWidgets.QCheckBox("Hide firm rows")
        self.only_bad.setToolTip(WIDGET_TIPS["uncertainty_only_bad"])
        self.only_bad.toggled.connect(self._show)
        row.addWidget(self.only_bad)
        row.addStretch(1)
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.setDefault(True)
        self.run_btn.clicked.connect(self.run)
        row.addWidget(self.run_btn)
        lay.addLayout(row)

        self.table = QtWidgets.QTableWidget(0, 0)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSortingEnabled(True)
        lay.addWidget(self.table, 1)

        self.summary = QtWidgets.QLabel("Press Run.")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

        btns = QtWidgets.QHBoxLayout()
        self.copy_btn = QtWidgets.QPushButton("Copy")
        self.copy_btn.clicked.connect(self._copy)
        self.xl_btn = QtWidgets.QPushButton("Export to Excel…")
        self.xl_btn.clicked.connect(self._export)
        for b in (self.copy_btn, self.xl_btn):
            b.setEnabled(False)
            btns.addWidget(b)
        btns.addStretch(1)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.reject)
        btns.addWidget(close)
        lay.addLayout(btns)

    def run(self):
        if not self.ws.pops or not self.ws.samples:
            self.summary.setText("There are no gates to measure yet.")
            return
        total = len(self.ws.samples)
        prog = QtWidgets.QProgressDialog("Re-gating every sample…", "Stop", 0, total, self)
        prog.setWindowModality(QtCore.Qt.WindowModal)
        prog.setMinimumDuration(400)

        def tick(done, n):
            prog.setValue(done)
            prog.setLabelText("Re-gating %s (%d of %d)…"
                              % (self.ws.samples[done].name, done + 1, n))
            QtWidgets.QApplication.processEvents()
            return prog.wasCanceled()

        self.df = fragility_report(
            self.ws, n=self.reps.value(), sigma=self.sigma.value() / 100.0,
            level=float(self.level.value()), progress=tick)
        prog.setValue(total)
        self._show()

    def _show(self):
        df = self.df
        if self.only_bad.isChecked() and len(df):
            df = df[df["Grade"] != "firm"]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels(list(df.columns))
        for c, name in enumerate(df.columns):
            if name in HEADER_TIPS:
                self.table.horizontalHeaderItem(c).setToolTip(HEADER_TIPS[name])
        prefixes = {name: shared_prefix(df[name].astype(str)) if len(df) else ""
                    for name in ("Sample", "Path")}
        for r in range(len(df)):
            row = df.iloc[r]
            grade = row["Grade"]
            for c, name in enumerate(df.columns):
                v = row[name]
                if name == "Relative":
                    text = "" if pd.isna(v) else "%.1f %%" % (100 * v)
                elif isinstance(v, float):
                    text = "" if pd.isna(v) else "%.3f" % v
                else:
                    text = str(v)
                if name in prefixes:
                    text = trim_front(text, prefixes[name])
                it = QtWidgets.QTableWidgetItem()
                if isinstance(v, float) and not pd.isna(v):
                    it.setData(QtCore.Qt.DisplayRole, float("%.4f" % v))
                    it.setText(text)
                    it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                else:
                    it.setText(text)
                it.setBackground(GRADE_BG[grade])
                if name in prefixes:
                    it.setToolTip(str(v))        # always the full, untrimmed value
                if name == "Grade":
                    it.setForeground(GRADE_FG[grade])
                    f = it.font(); f.setBold(True); it.setFont(f)
                    it.setToolTip(GRADE_NOTE[grade])
                self.table.setItem(r, c, it)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        for c, name in enumerate(df.columns):
            if name in ("Path", "Sample"):      # can be very long; the rest must stay visible
                self.table.setColumnWidth(c, min(self.table.columnWidth(c), 260))
        self._summarise(df)
        ok = bool(len(self.df))
        self.copy_btn.setEnabled(ok)
        self.xl_btn.setEnabled(ok)

    def _summarise(self, shown):
        if not len(self.df):
            self.summary.setText("Nothing to report.")
            return
        g = self.df["Grade"].value_counts()
        bits = ["%d %s" % (g.get(k, 0), k) for k in ("firm", "soft", "fragile") if g.get(k, 0)]
        bad = self.df[self.df["Grade"] == "fragile"]
        msg = "%d rows: %s." % (len(self.df), ", ".join(bits))
        if len(bad):
            by = bad["Limited by"].value_counts()
            pops = ", ".join(sorted(set(bad["Population"]))[:4])
            msg += ("  Fragile rows sit in: <b>%s</b>. %d of them are limited by the gate "
                    "(redraw it), %d by the event count (acquire more)."
                    % (pops, by.get("gate", 0), by.get("counting", 0)))
        if self.only_bad.isChecked():
            msg += "  Showing %d." % len(shown)
        self.summary.setText(msg)

    def _copy(self):
        QtWidgets.QApplication.clipboard().setText(self.df.to_csv(sep="\t", index=False))
        self.summary.setText("Copied %d rows to the clipboard." % len(self.df))

    def _export(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export confidence report",
            os.path.join(os.path.expanduser("~"), "confidence.xlsx"), "Excel (*.xlsx)")
        if not path:
            return
        if not path.endswith(".xlsx"):
            path += ".xlsx"
        export_confidence(self.ws, self.df, path,
                          sigma=self.sigma.value() / 100.0, n=self.reps.value(),
                          level=float(self.level.value()))
        self.summary.setText("Saved %s" % os.path.basename(path))
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))


def export_confidence(ws, df, path, sigma, n, level, version="0.3"):
    """Two sheets: the report, and what was done to produce it.

    The second sheet is not decoration. An interval is meaningless without the
    assumption that generated it, and a spreadsheet outlives the conversation in which
    it was explained, so the settings travel with the numbers.
    """
    import datetime
    method = pd.DataFrame({"Item": [
        "Produced",
        "Workspace",
        "Samples measured",
        "Populations",
        "Runs per sample",
        "Hand steadiness (sigma)",
        "Confidence level",
        "Perturbation",
        "Gate error",
        "Counting error",
        "Interval",
        "Grades",
        "Software",
    ], "Value": [
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        ws.path or "(not saved)",
        int(df["Sample"].nunique()) if len(df) else 0,
        len(ws.pops),
        n,
        "%.2f %% of each axis, one standard deviation" % (sigma * 100),
        "%g %%" % level,
        "Every boundary in the tree is displaced independently and the whole hierarchy "
        "is recomputed from the root, so a child's interval already contains its "
        "parent's. Rectangle edges slide independently; polygons translate and then "
        "dilate about their centroid; ellipses move by centre and radii. Displacement "
        "is in display space, so one sigma means the same fraction of the plot on a "
        "biexponential axis as on a linear one.",
        "The spread of the frequency across the runs, at the stated confidence level.",
        "Binomial standard error of the population's share of its parent, widened to "
        "the same confidence level.",
        "Gate and counting error added in quadrature.",
        "firm: the interval is within 5 %% of the frequency, or under 0.05 percentage "
        "points. fragile: within 25 %% of it, or over 5 percentage points. soft: in "
        "between. Conventions, not findings.",
        "Cytolux %s" % version,
    ]})
    from openpyxl.utils import get_column_letter
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        (df if len(df) else pd.DataFrame({"": ["no rows"]})).to_excel(
            xl, sheet_name="Confidence", index=False)
        method.to_excel(xl, sheet_name="Method", index=False)
        for sheet, frame in (("Confidence", df), ("Method", method)):
            w = xl.sheets[sheet]
            for i, col in enumerate(frame.columns, start=1):
                width = max(len(str(col)), *(len(str(v)) for v in frame[col])) \
                    if len(frame) else len(str(col))
                w.column_dimensions[get_column_letter(i)].width = min(60, width + 2)
            w.freeze_panes = "A2"
    return len(df)
