"""The Overlay tab: several populations on one axis, overlaid or stacked.

The work of comparing is done by the picture here, not by the reader's memory of
the plot before this one, so the controls stay few and the defaults are the ones
you would pick anyway: modal normalisation, overlaid, filled.
"""
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from . import overlay as ov
from . import theme
from . import transforms as tx
from .plot import TransformAxis

SOURCES = ("Selected samples, this population",
           "Every sample, this population",
           "This sample, every population")

TIPS = {
    "channel": "The marker on the X axis. Every curve is drawn on this channel's "
               "transform, so the curves are comparable.",
    "source": "What to lay over what: several samples on one gate (dose, donor, "
              "condition), or several gates within one sample (CD4 against CD8).",
    "norm": "mode: every curve peaks at the same height, which compares shapes when "
            "the populations differ in size (FlowJo calls this modal).\n"
            "area: each curve integrates to 1, so a smaller population draws a "
            "shorter curve.\ncount: raw counts, for when the sizes are the point.",
    "layout": "Overlaid puts every curve on one baseline. Stacked offsets them up the "
              "page, which stays readable past about six curves.",
    "fill": "Shade under each curve. Helps with two or three, crowds the picture "
            "with ten.",
    "draw": "Redraw from the current samples, gates and transforms.",
    "export": "Save at 300 dpi, on white, with no interface colour in the figure.",
}

MAX_CURVES = 24


class OverlayTab(QtWidgets.QWidget):
    """Needs a window carrying: ws, cur_sample, cur_pop, sample_list."""

    sample_opened = QtCore.Signal(str)

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self.series = []
        self.cb_channel = QtWidgets.QComboBox()
        self.cb_channel.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        self.cb_source = QtWidgets.QComboBox(); self.cb_source.addItems(SOURCES)
        self.cb_norm = QtWidgets.QComboBox()
        self.cb_norm.addItems(["Normalise to mode", "Normalise to area", "Raw count"])
        self.cb_layout = QtWidgets.QComboBox(); self.cb_layout.addItems(["Overlaid", "Stacked"])
        self.chk_fill = QtWidgets.QCheckBox("Fill"); self.chk_fill.setChecked(True)
        for w, k in ((self.cb_channel, "channel"), (self.cb_source, "source"),
                     (self.cb_norm, "norm"), (self.cb_layout, "layout"), (self.chk_fill, "fill")):
            w.setToolTip(TIPS[k])
        self.btn_draw = QtWidgets.QPushButton("Draw"); self.btn_draw.setToolTip(TIPS["draw"])
        self.btn_export = QtWidgets.QPushButton("Export figure…")
        self.btn_export.setToolTip(TIPS["export"])
        self.btn_draw.clicked.connect(self.draw)
        self.btn_export.clicked.connect(self.export)
        for w in (self.cb_channel, self.cb_source, self.cb_norm, self.cb_layout):
            w.currentIndexChanged.connect(self._auto)
        self.chk_fill.toggled.connect(self._auto)

        self.ax_x = TransformAxis("bottom")
        self.plot = pg.PlotWidget(axisItems={"bottom": self.ax_x})
        self.plot.setBackground(theme.CANVAS)
        self.plot.setMenuEnabled(False)
        for ax in ("bottom", "left"):
            a = self.plot.getPlotItem().getAxis(ax)
            a.setPen(pg.mkPen("k")); a.setTextPen(pg.mkPen("k"))
        self.plot.getPlotItem().getViewBox().setMouseEnabled(x=True, y=False)
        self.note = QtWidgets.QLabel(); self.note.setWordWrap(True)

        row = QtWidgets.QHBoxLayout()
        for w in (QtWidgets.QLabel("Channel"), self.cb_channel, self.cb_source,
                  self.cb_norm, self.cb_layout, self.chk_fill, self.btn_draw):
            row.addWidget(w)
        row.addStretch(1)
        row.addWidget(self.btn_export)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.note)
        lay.addWidget(self.plot, 1)

    # --------------------------------------------------------------- plumbing
    def _auto(self):
        if self.series:                      # only redraw something already on screen
            self.draw()

    def refresh_channels(self):
        """Keep the channel list current without losing what the user picked."""
        s = self.win.cur_sample
        if s is None:
            return
        want = self.cb_channel.currentData()
        chans = self.win.ws.display_channels(s)
        self.cb_channel.blockSignals(True)
        self.cb_channel.clear()
        for c in chans:
            self.cb_channel.addItem(self.win.ws.label(c, s), c)
        i = self.cb_channel.findData(want)
        self.cb_channel.setCurrentIndex(i if i >= 0 else 0)
        self.cb_channel.blockSignals(False)

    def pairs(self):
        """(sample, population) for each curve, in the order they will be drawn."""
        ws, win = self.win.ws, self.win
        mode = self.cb_source.currentIndex()
        if mode == 2:
            s = win.cur_sample
            if s is None:
                return []
            pops = [win.cur_pop] + [c["path"] for c in ws.children(win.cur_pop)]
            return [(s, p) for p in pops]
        if mode == 0:
            rows = [i.row() for i in win.sample_list.selectedIndexes()]
            chosen = [ws.samples[r] for r in sorted(rows) if r < len(ws.samples)]
            if not chosen and win.cur_sample is not None:
                chosen = [win.cur_sample]
        else:
            chosen = list(ws.samples)
        return [(s, win.cur_pop) for s in chosen]

    # ------------------------------------------------------------------ draw
    def draw(self):
        self.plot.clear()
        self.series = []
        ch = self.cb_channel.currentData()
        pairs = self.pairs()
        if ch is None or not pairs:
            self.note.setText("Pick a sample and a gate on the Gating tab, then Draw.")
            return
        over = len(pairs) - MAX_CURVES
        if over > 0:
            pairs = pairs[:MAX_CURVES]
        norm = ov.NORMS[self.cb_norm.currentIndex()]
        s0 = self.win.cur_sample
        xf = self.win.ws.xform(ch, s0)
        self.series = ov.build(self.win.ws, pairs, ch, norm=norm, xf=xf)
        if not self.series:
            self.note.setText("No events to draw. The channel may be missing from these samples.")
            return
        labels = ov.shorten([s.label for s in self.series])
        for s, short in zip(self.series, labels):
            s.label = short
        stacked = self.cb_layout.currentIndex() == 1
        tall = max((s.y.max() for s in self.series), default=1.0) or 1.0
        offs = ov.stack_offsets(len(self.series)) if stacked else [0.0] * len(self.series)
        if stacked:
            offs = [o * tall for o in offs]
        for s, off in zip(self.series, offs):
            pen = pg.mkPen(s.colour, width=1.8)
            y = s.y + off
            c = pg.PlotCurveItem(s.x, y, pen=pen)
            if self.chk_fill.isChecked():
                r, g, b = s.colour
                base = pg.PlotCurveItem(s.x, np.full_like(s.x, off), pen=pg.mkPen(None))
                fill = pg.FillBetweenItem(c, base, brush=pg.mkBrush(r, g, b, 60))
                self.plot.addItem(fill)
            self.plot.addItem(c)
        self.ax_x.set_spec(xf)
        self.plot.setLabel("bottom", self.win.ws.label(ch, s0))
        self.plot.setLabel("left", ov.NORM_LABEL[norm])
        top = max((s.y.max() + o for s, o in zip(self.series, offs)), default=1.0)
        self.plot.getPlotItem().getViewBox().setRange(
            xRange=(0, 1), yRange=(0, top * 1.06), padding=0.01)
        self.plot.getPlotItem().getAxis("left").setStyle(showValues=not stacked)
        self._legend(offs, stacked)
        thin = [s.label for s in self.series if s.thin and s.n]
        msg = "%d curves · %s" % (len(self.series), ov.NORM_LABEL[norm])
        if over > 0:
            msg += " · showing the first %d of %d" % (MAX_CURVES, MAX_CURVES + over)
        if thin:
            msg += " · under 100 events: " + ", ".join(thin[:4])
            if len(thin) > 4:
                msg += " and %d more" % (len(thin) - 4)
        self.note.setText(msg)

    def _legend(self, offs, stacked):
        """Names beside the curves when stacked, one block in the corner when not.

        A stacked plot already says which curve is which by position, so a legend
        that forces the eye back to a corner key is a step backwards.
        """
        vb = self.plot.getPlotItem().getViewBox()
        if stacked:
            # Each name sits on its own curve's baseline, at the left where the
            # curves are flat. Putting it at the peak instead lands it inside the
            # curve above, which is how a ridgeline becomes unreadable.
            for s, off in zip(self.series, offs):
                t = pg.TextItem(s.legend_text(), color=s.colour, anchor=(0, 1))
                t.setPos(0.008, off)
                self.plot.addItem(t)
            return
        html = "<div style='background:rgba(255,255,255,205);padding:3px'>"
        for s in self.series:
            r, g, b = s.colour
            html += "<div style='color:rgb(%d,%d,%d)'>%s</div>" % (r, g, b, s.legend_text())
        html += "</div>"
        right = self._free_side() == "right"
        t = pg.TextItem(html="", anchor=(1, 0) if right else (0, 0))
        t.setHtml(html)
        top = max((s.y.max() for s in self.series), default=1.0)
        t.setPos(0.995 if right else 0.005, top * 1.04)
        self.plot.addItem(t)
        vb.update()

    LEGEND_BAND = 0.30

    def _free_side(self):
        """Which outer band of the plot the curves leave free: where the key goes.

        Not the centre of mass: with modal normalisation a negative and a positive
        peak both reach the top, and the mean between them lands in the middle and
        decides nothing. The key only needs a band at one edge, so the question is
        which edge has less drawn in it.
        """
        lo = hi = 0.0
        for s in self.series:
            x = np.asarray(s.x, float)
            y = np.asarray(s.y, float)
            lo += float(y[x <= self.LEGEND_BAND].sum())
            hi += float(y[x >= 1.0 - self.LEGEND_BAND].sum())
        return "left" if lo <= hi else "right"

    # ---------------------------------------------------------------- export
    def export(self, path=None, width=2400, dpi=300):
        if not self.series:
            QtWidgets.QMessageBox.information(self, "Overlay", "Draw something first.")
            return None
        if path is None:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export overlay", "overlay.png", "PNG (*.png)")
            if not path:
                return None
        from pyqtgraph.exporters import ImageExporter
        self.plot.setBackground(theme.FIGURE)
        try:
            ex = ImageExporter(self.plot.getPlotItem())
            ex.parameters()["width"] = int(width)
            ex.export(path)
        finally:
            self.plot.setBackground(theme.CANVAS)
        img = QtGui.QImage(path)
        if not img.isNull() and dpi:
            per_m = int(round(dpi / 0.0254))
            img.setDotsPerMeterX(per_m); img.setDotsPerMeterY(per_m)
            img.save(path)
        return path

    def table(self):
        """The legend as rows, for pasting next to the figure."""
        rows = [("Curve", "n", "Median", "Mean")]
        for s in self.series:
            rows.append((s.label, str(s.n), ov._fmt(s.median), ov._fmt(s.mean)))
        return rows
