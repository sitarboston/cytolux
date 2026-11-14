"""Statistics: the 'Add statistic' dialog, sample annotations and the Excel export."""
import datetime
import os

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from .engine import STATS, PERCENT_STATS, stat_name, stats_table
from . import brand


class AddStatDialog(QtWidgets.QDialog):
    """Pick populations x statistic x channels; one column is made for every combination."""

    def __init__(self, ws, sample, parent=None, preselect=None, channel=None):
        super().__init__(parent)
        self.ws, self.s = ws, sample
        self.setWindowTitle("Add statistic")
        self.pops = QtWidgets.QListWidget()
        self.pops.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        entries = [("root", "All events")] + [(p["path"], "   " * (p["path"].count("/") - 1) + p["name"])
                                              for p in ws.pops]
        for path, label in entries:
            it = QtWidgets.QListWidgetItem(label)
            it.setData(QtCore.Qt.UserRole, path)
            it.setToolTip(path)
            self.pops.addItem(it)
            if preselect and path in preselect:
                it.setSelected(True)
        self.stat = QtWidgets.QComboBox()
        for k, (_, desc) in STATS.items():
            self.stat.addItem(k)
            self.stat.setItemData(self.stat.count() - 1, desc, QtCore.Qt.ToolTipRole)
        self.desc = QtWidgets.QLabel(); self.desc.setWordWrap(True)
        self.chans = QtWidgets.QListWidget()
        self.chans.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        for c in ws.display_channels(sample):
            if c.lower().startswith("time"):
                continue
            it = QtWidgets.QListWidgetItem(ws.label(c, sample))
            it.setData(QtCore.Qt.UserRole, c)
            self.chans.addItem(it)
            if c == channel:
                it.setSelected(True)
        self.pct = QtWidgets.QDoubleSpinBox(); self.pct.setRange(0, 100); self.pct.setValue(50); self.pct.setSuffix(" th")
        self.anc = QtWidgets.QComboBox()
        for path, label in entries:
            self.anc.addItem(label.strip(), path)
        form = QtWidgets.QGridLayout()
        form.addWidget(QtWidgets.QLabel("<b>1. Populations</b> (Ctrl/Shift-click for several)"), 0, 0)
        form.addWidget(QtWidgets.QLabel("<b>2. Statistic</b>"), 0, 1)
        form.addWidget(self.pops, 1, 0, 6, 1)
        form.addWidget(self.stat, 1, 1)
        form.addWidget(self.desc, 2, 1)
        self.lbl_pct = QtWidgets.QLabel("Percentile"); form.addWidget(self.lbl_pct, 3, 1); form.addWidget(self.pct, 4, 1)
        self.lbl_anc = QtWidgets.QLabel("Percent of which population"); form.addWidget(self.lbl_anc, 3, 1); form.addWidget(self.anc, 4, 1)
        self.lbl_ch = QtWidgets.QLabel("<b>3. Channels</b> (for intensity statistics)")
        form.addWidget(self.lbl_ch, 5, 1)
        form.addWidget(self.chans, 6, 1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.button(QtWidgets.QDialogButtonBox.Ok).setText("Add")
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QtWidgets.QVBoxLayout(self); lay.addLayout(form); lay.addWidget(bb)
        self.stat.currentIndexChanged.connect(self._sync)
        self.resize(820, 560)
        self._sync()

    def _sync(self):
        st = self.stat.currentText()
        need_ch = STATS[st][0]
        self.desc.setText(STATS[st][1])
        self.chans.setEnabled(need_ch); self.lbl_ch.setEnabled(need_ch)
        for w in (self.lbl_pct, self.pct):
            w.setVisible(st == "Percentile")
        for w in (self.lbl_anc, self.anc):
            w.setVisible(st == "% of")

    def defs(self):
        st = self.stat.currentText()
        pops = [it.data(QtCore.Qt.UserRole) for it in self.pops.selectedItems()]
        chans = [it.data(QtCore.Qt.UserRole) for it in self.chans.selectedItems()] if STATS[st][0] else [None]
        out = []
        for p in pops:
            for c in chans:
                d = {"pop": p, "stat": st, "channel": c}
                if st == "Percentile":
                    d["arg"] = self.pct.value()
                if st == "% of":
                    d["arg"] = self.anc.currentData()
                out.append(d)
        return out


class AnnotateDialog(QtWidgets.QDialog):
    """A small spreadsheet: one row per sample, columns you name (Donor, Dose, Condition...).
    Paste a block straight from Excel with Ctrl+V."""

    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.ws = ws
        self.setWindowTitle("Sample annotations")
        self.cols = list(ws.annot_cols)
        self.t = QtWidgets.QTableWidget(len(ws.samples), len(self.cols))
        self.t.setVerticalHeaderLabels([s.name for s in ws.samples])
        self._headers()
        for r, s in enumerate(ws.samples):
            for c, col in enumerate(self.cols):
                self.t.setItem(r, c, QtWidgets.QTableWidgetItem(str(ws.annotations.get(s.name, {}).get(col, ""))))
        add = QtWidgets.QPushButton("Add column…"); add.clicked.connect(self._add_col)
        ren = QtWidgets.QPushButton("Rename column…"); ren.clicked.connect(self._ren_col)
        rem = QtWidgets.QPushButton("Remove column"); rem.clicked.connect(self._rem_col)
        well = QtWidgets.QPushButton("Fill 'Well' from file names"); well.clicked.connect(self._wells)
        imp = QtWidgets.QPushButton("Import from CSV/Excel…"); imp.clicked.connect(self._import)
        row = QtWidgets.QHBoxLayout()
        for b in (add, ren, rem, well, imp):
            row.addWidget(b)
        row.addStretch(1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("Describe each sample (donor, dose, condition…). These columns lead the "
                                       "statistics table and the Excel export. Tip: select a cell and press Ctrl+V "
                                       "to paste a block copied from Excel."))
        lay.addLayout(row); lay.addWidget(self.t, 1); lay.addWidget(bb)
        QtGui.QShortcut(QtGui.QKeySequence.Paste, self.t, activated=self._paste)
        self.resize(900, 650)

    def _headers(self):
        self.t.setColumnCount(len(self.cols))
        self.t.setHorizontalHeaderLabels(self.cols)

    def _add_col(self, name=None):
        if not name:
            name, ok = QtWidgets.QInputDialog.getText(self, "Add column", "Column name (e.g. Donor, Dose, Condition):")
            if not ok or not name.strip():
                return None
        name = name.strip()
        if name in self.cols:
            return self.cols.index(name)
        self.cols.append(name)
        self._headers()
        return len(self.cols) - 1

    def _ren_col(self):
        c = self.t.currentColumn()
        if c < 0:
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "Rename column", "New name:", text=self.cols[c])
        if ok and name.strip():
            self.cols[c] = name.strip()
            self._headers()

    def _rem_col(self):
        c = self.t.currentColumn()
        if c >= 0:
            self.t.removeColumn(c)
            del self.cols[c]

    def _wells(self):
        import re
        c = self._add_col("Well")
        for r, s in enumerate(self.ws.samples):
            m = re.findall(r"(?<![A-Za-z])([A-P])(\d{1,2})(?=\D*$)", os.path.splitext(s.name)[0])
            self.t.setItem(r, c, QtWidgets.QTableWidgetItem(f"{m[-1][0]}{int(m[-1][1])}" if m else ""))

    def _paste(self):
        text = QtWidgets.QApplication.clipboard().text()
        r0, c0 = max(self.t.currentRow(), 0), max(self.t.currentColumn(), 0)
        for i, line in enumerate(text.rstrip("\n").split("\n")):
            for j, val in enumerate(line.rstrip("\r").split("\t")):
                r, c = r0 + i, c0 + j
                if r >= self.t.rowCount():
                    break
                while c >= len(self.cols):
                    self._add_col(f"Column {len(self.cols) + 1}")
                self.t.setItem(r, c, QtWidgets.QTableWidgetItem(val))

    def _import(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Annotation table: first column = FCS file name", "", "Tables (*.csv *.xlsx *.xls)")
        if not path:
            return
        df = pd.read_csv(path) if path.lower().endswith(".csv") else pd.read_excel(path)
        key = df.columns[0]
        lookup = {str(v).strip(): i for i, v in enumerate(df[key])}
        hits = 0
        for col in df.columns[1:]:
            c = self._add_col(str(col))
            for r, s in enumerate(self.ws.samples):
                i = lookup.get(s.name, lookup.get(os.path.splitext(s.name)[0]))
                if i is not None:
                    v = df[col].iloc[i]
                    self.t.setItem(r, c, QtWidgets.QTableWidgetItem("" if pd.isna(v) else str(v)))
                    hits += 1
        QtWidgets.QMessageBox.information(self, "Import", f"Matched {hits // max(1, len(df.columns) - 1)} of "
                                                          f"{len(self.ws.samples)} samples by file name.")

    def store(self):
        self.ws.annot_cols = list(self.cols)
        self.ws.annotations = {}
        for r, s in enumerate(self.ws.samples):
            rec = {}
            for c, col in enumerate(self.cols):
                it = self.t.item(r, c)
                v = it.text().strip() if it else ""
                if v:
                    rec[col] = _num(v)
            if rec:
                self.ws.annotations[s.name] = rec


def _num(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() and "." not in v else f
    except ValueError:
        return v


def fmt_value(stat, v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    if stat == "Count":
        return f"{int(v):,}"
    if stat in PERCENT_STATS:
        return f"{v:.2f}"
    return f"{v:,.1f}" if abs(v) < 1000 else f"{v:,.0f}"


def export_excel(ws, path, version="0.2"):
    """Workbook: Statistics (your table), Definitions, All gates (every count), About."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    table = stats_table(ws)
    defs = pd.DataFrame([{
        "Column": stat_name(d, ws, ws.samples[0] if ws.samples else None),
        "Population": "All events" if d["pop"] == "root" else d["pop"],
        "Statistic": d["stat"],
        "Channel": ws.label(d["channel"], ws.samples[0]) if d.get("channel") and ws.samples else "",
        "Argument": d.get("arg", ""),
        "Meaning": STATS[d["stat"]][1]} for d in ws.stat_defs])
    rows = []
    for s in ws.samples:
        st = ws.stats(s)
        for p in [{"path": "root"}] + ws.pops:
            if p["path"] in st:
                c, pp, pt = st[p["path"]]
                r = {"Sample": s.name}
                for col in ws.annot_cols:
                    r[col] = ws.annotations.get(s.name, {}).get(col, "")
                r.update({"Population": "All events" if p["path"] == "root" else p["path"],
                          "Count": c, "% of parent": round(pp, 4), "% of total": round(pt, 4),
                          "Gate adjusted for this sample": ws.has_override(p["path"], s.name)})
                rows.append(r)
    long = pd.DataFrame(rows)
    comp = {"file": "matrix stored in each FCS file (acquisition-defined)", "none": "none",
            "custom": "custom matrix (loaded or edited)"}[ws.comp_mode]
    about = pd.DataFrame(
        {"Item": ["Exported", "Workspace", "Samples", "Compensation", "Software",
                  "Created by", "Copyright"],
         "Value": [datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), ws.path or "(not saved)",
                   len(ws.samples), comp, f"Cytolux {version}",
                   brand.CREATOR, brand.COPYRIGHT]})
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        # Workbook properties, so the attribution survives a copy of the file that
        # never has the About sheet opened.
        props = xw.book.properties
        props.creator = brand.CREATOR
        props.lastModifiedBy = brand.CREATOR
        props.title = "Cytolux statistics"
        props.description = brand.software_tag()
        table.to_excel(xw, sheet_name="Statistics", index=False)
        if len(defs):
            defs.to_excel(xw, sheet_name="Definitions", index=False)
        long.to_excel(xw, sheet_name="All gates", index=False)
        about.to_excel(xw, sheet_name="About", index=False)
        head = PatternFill("solid", fgColor="DCE6F1")
        kinds = {stat_name(d, ws, ws.samples[0]): d["stat"] for d in ws.stat_defs} if ws.samples else {}
        for name, sh in xw.sheets.items():
            for cell in sh[1]:
                cell.font = Font(bold=True)
                cell.fill = head
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            sh.freeze_panes = "B2"
            for j, col in enumerate(sh.iter_cols(min_row=1, max_row=min(sh.max_row, 200)), start=1):
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                sh.column_dimensions[get_column_letter(j)].width = min(max(10, width + 2), 48)
            if name == "Statistics":
                sh.row_dimensions[1].height = 45
                for j, cell in enumerate(sh[1], start=1):
                    st = kinds.get(cell.value)
                    if st is None:
                        continue
                    fmt = "#,##0" if st == "Count" else "0.00" if st in PERCENT_STATS else "#,##0.0"
                    for r in range(2, sh.max_row + 1):
                        sh.cell(r, j).number_format = fmt
                    sh.column_dimensions[get_column_letter(j)].width = 16
    return len(table), len(ws.stat_defs)
