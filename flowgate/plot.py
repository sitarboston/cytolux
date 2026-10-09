"""The gating plot: density / dot / histogram display, FlowJo-style axes, gate drawing and editing."""
import math

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from . import transforms as tx
from .engine import gate_outline, reexpress_rect

pg.setConfigOptions(antialias=True, imageAxisOrder="col-major")

GATE_PEN = pg.mkPen((0, 0, 0), width=1.6)
GATE_HOVER = pg.mkPen((220, 30, 30), width=2.2)
READONLY_PEN = pg.mkPen((90, 90, 90), width=1.4, style=QtCore.Qt.DashLine)
DRAW_PEN = pg.mkPen((220, 30, 30), width=1.6, style=QtCore.Qt.DashLine)


def pseudocolor_lut():
    """FlowJo-like pseudocolor: blue -> cyan -> green -> yellow -> red; empty bins transparent."""
    stops = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    cols = np.array([[0, 0, 255], [0, 200, 255], [0, 220, 0], [255, 230, 0], [255, 0, 0]], float)
    x = np.linspace(0, 1, 256)
    lut = np.zeros((256, 4), np.uint8)
    for c in range(3):
        lut[:, c] = np.interp(x, stops, cols[:, c])
    lut[:, 3] = 255
    lut[0] = (255, 255, 255, 0)
    return lut


LUT = pseudocolor_lut()


class TransformAxis(pg.AxisItem):
    """Axis whose ticks are placed by the channel transform (decades on biex/log, raw values on linear)."""

    def __init__(self, orientation):
        super().__init__(orientation)
        self.spec = tx.linear(262144)
        self._labels = {}
        self.enableAutoSIPrefix(False)

    def set_spec(self, spec):
        self.spec = spec
        major, minor = tx.ticks(spec)
        self._major = major
        self._minor = minor
        self._labels = {round(p, 6): lab for p, lab in major}
        self.picture = None
        self.update()

    def tickValues(self, minVal, maxVal, size):
        major, minor = tx.ticks(self.spec)
        return [(1.0, [p for p, _ in major]), (0.5, minor)]

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            lab = self._labels.get(round(v, 6), "")
            out.append(_pretty(lab))
        return out


def _pretty(lab):
    sup = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
    if "10^" in lab:
        sign = "-" if lab.startswith("-") else ""
        e = lab.split("^")[1]
        return f"{sign}10{e.translate(sup)}"
    return lab


class GateView(pg.ViewBox):
    """ViewBox that turns mouse gestures into gate shapes when a drawing tool is active."""

    shape_drawn = QtCore.Signal(str, object)   # tool, geometry

    def __init__(self):
        super().__init__(enableMenu=False)
        self.tool = "pointer"
        self.hist_mode = False
        self._start = None
        self._temp = None
        self._poly = []
        self.setMouseEnabled(False, False)

    def set_tool(self, tool):
        self.tool = tool
        self._cancel()

    def _cancel(self):
        if self._temp is not None:
            self.removeItem(self._temp)
            self._temp = None
        self._poly = []
        self._start = None

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_Escape:
            self._cancel()
        elif ev.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and len(self._poly) >= 3:
            self._finish_poly()
        else:
            super().keyPressEvent(ev)

    def mouseDragEvent(self, ev, axis=None):
        if self.tool not in ("rect", "ellipse", "range") or ev.button() != QtCore.Qt.LeftButton:
            ev.ignore()
            return
        ev.accept()
        p = self.mapSceneToView(ev.scenePos())
        if ev.isStart():
            self._start = self.mapSceneToView(ev.buttonDownScenePos())
            if self.tool == "ellipse":
                self._temp = QtWidgets.QGraphicsEllipseItem()
            else:
                self._temp = QtWidgets.QGraphicsRectItem()
            self._temp.setPen(DRAW_PEN)
            self.addItem(self._temp)
        if self._start is None or self._temp is None:
            return
        x0, y0 = self._start.x(), self._start.y()
        x1, y1 = p.x(), p.y()
        if self.tool == "range":
            y0, y1 = 0, self.viewRange()[1][1]
        r = QtCore.QRectF(QtCore.QPointF(min(x0, x1), min(y0, y1)), QtCore.QPointF(max(x0, x1), max(y0, y1)))
        self._temp.setRect(r)
        if ev.isFinish():
            self._cancel()
            if r.width() > 0.005:
                self.shape_drawn.emit(self.tool, (r.left(), r.top(), r.right(), r.bottom()))

    def mouseClickEvent(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
            if ev.button() == QtCore.Qt.RightButton and self._poly:
                self._cancel()
            ev.ignore()
            return
        p = self.mapSceneToView(ev.scenePos())
        if self.tool == "quad":
            ev.accept()
            self.shape_drawn.emit("quad", (p.x(), p.y()))
        elif self.tool == "poly":
            ev.accept()
            if ev.double():
                if len(self._poly) >= 3:
                    self._finish_poly()
                return
            if len(self._poly) >= 3:
                # close when clicking near the first vertex (in screen pixels)
                first = self.mapViewToScene(QtCore.QPointF(*self._poly[0]))
                if (first - ev.scenePos()).manhattanLength() < 10:
                    self._finish_poly()
                    return
            self._poly.append((p.x(), p.y()))
            if self._temp is None:
                self._temp = pg.PlotCurveItem(pen=DRAW_PEN)
                self.addItem(self._temp)
            pts = np.array(self._poly)
            self._temp.setData(pts[:, 0], pts[:, 1])
        else:
            ev.ignore()

    def hoverEvent(self, ev):
        if self.tool == "poly" and self._poly and not ev.isExit() and self._temp is not None:
            p = self.mapSceneToView(ev.scenePos())
            pts = np.array(self._poly + [(p.x(), p.y())])
            self._temp.setData(pts[:, 0], pts[:, 1])

    def _finish_poly(self):
        pts = list(self._poly)
        self._cancel()
        self.shape_drawn.emit("poly", pts)


class GatePlot(pg.PlotWidget):
    """Shows one population of one sample on two axes, plus the child gates drawn on those axes."""

    gate_created = QtCore.Signal(str, object)          # tool, geometry dict in display coords
    gate_edited = QtCore.Signal(str, object)           # path, new gate dict
    gate_open = QtCore.Signal(str)                     # path (double-click / menu)
    gate_menu = QtCore.Signal(str, object)             # path, global pos

    def __init__(self):
        self.vb = GateView()
        self.ax_x = TransformAxis("bottom")
        self.ax_y = TransformAxis("left")
        super().__init__(viewBox=self.vb, axisItems={"bottom": self.ax_x, "left": self.ax_y})
        self.setBackground("w")
        for ax in (self.ax_x, self.ax_y):
            ax.setPen(pg.mkPen("k"))
            ax.setTextPen(pg.mkPen("k"))
        self.getPlotItem().hideButtons()
        self.vb.shape_drawn.connect(self._on_drawn)
        self.image = pg.ImageItem()
        self.image.setLookupTable(LUT)
        self.addItem(self.image)
        self.scatter = pg.ScatterPlotItem(size=2, pen=None, brush=pg.mkBrush(30, 30, 30, 140))
        self.addItem(self.scatter)
        self.curve = pg.PlotCurveItem(pen=pg.mkPen((40, 40, 120), width=1.5),
                                      brush=pg.mkBrush(120, 140, 220, 120), fillLevel=0)
        self.addItem(self.curve)
        self.gate_items = []
        self.mode = "density"
        self.bins = 256
        self.smooth = True
        self.ctx = None

    # ------------------------------------------------------------------ display
    def show_population(self, ctx):
        """ctx: dict(ws, sample, pop, x, y (None = histogram), xf_x, xf_y, gates=[(path, gate)])"""
        self.ctx = ctx
        ws, s = ctx["ws"], ctx["sample"]
        ed = ws.events(s)
        mask = ws.masks(s)[ctx["pop"]]
        X = tx.apply(ctx["xf_x"], ed.col(ctx["x"])[mask])
        hist = ctx["y"] is None
        self.vb.hist_mode = hist
        self.ax_x.set_spec(ctx["xf_x"])
        self.setLabel("bottom", ws.label(ctx["x"], s))
        self.image.clear()
        self.scatter.clear()
        self.curve.setData([], [])
        if hist:
            self.ax_y.setStyle(showValues=True)
            self.ax_y.set_spec(tx.linear(1))
            h, edges = np.histogram(np.clip(X, 0, 1), bins=self.bins, range=(0, 1))
            if self.smooth and h.size > 5:
                k = np.array([1, 2, 3, 2, 1], float)
                h = np.convolve(h, k / k.sum(), mode="same")
            top = max(h.max(), 1) * 1.08
            yy = h / top
            xs = np.repeat(edges, 2)[1:-1]
            self.curve.setData(xs, np.repeat(yy, 2))
            self.ax_y.set_spec({"kind": "linear", "T": top})
            self.setLabel("left", "Count")
        else:
            Y = tx.apply(ctx["xf_y"], ed.col(ctx["y"])[mask])
            self.ax_y.set_spec(ctx["xf_y"])
            self.setLabel("left", ws.label(ctx["y"], s))
            if self.mode == "density":
                H, _, _ = np.histogram2d(np.clip(X, 0, 1), np.clip(Y, 0, 1),
                                         bins=self.bins, range=[[0, 1], [0, 1]])
                lvl = density_levels(H, self.smooth)
                self.image.setImage(lvl, levels=(0, 255), autoLevels=False)
                self.image.setRect(QtCore.QRectF(0, 0, 1, 1))
            else:
                n = len(X)
                if n > 60000:
                    idx = np.random.default_rng(0).choice(n, 60000, replace=False)
                    X, Y = X[idx], Y[idx]
                self.scatter.setData(np.clip(X, 0, 1), np.clip(Y, 0, 1))
        self.vb.setRange(xRange=(0, 1), yRange=(0, 1), padding=0.01)
        self._draw_gates()

    def _clear_gates(self):
        for it in self.gate_items:
            self.removeItem(it)
        self.gate_items = []

    def _draw_gates(self):
        self._clear_gates()
        ctx = self.ctx
        ws, s = ctx["ws"], ctx["sample"]
        stats = ws.stats(s)
        for path, g in ctx["gates"]:
            dims = g["dims"]
            if ctx["y"] is None:
                if len(dims) != 1 or dims[0] != ctx["x"]:
                    continue
                self._add_range(path, g, stats)
                continue
            if len(dims) != 2:
                continue
            if dims == [ctx["x"], ctx["y"]]:
                swap = False
            elif dims == [ctx["y"], ctx["x"]]:
                swap = True
            else:
                continue
            self._add_gate(path, g, swap, stats)

    def _label(self, path, stats, x, y):
        name = path.rsplit("/", 1)[1]
        pct = stats.get(path, (0, 0.0, 0.0))[1]
        t = pg.TextItem(f"{name}\n{pct:.2f}%", color=(0, 0, 0), anchor=(0.5, 0.5),
                        fill=pg.mkBrush(255, 255, 255, 170))
        t.setPos(x, y)
        self.addItem(t)
        self.gate_items.append(t)

    def _add_range(self, path, g, stats):
        xf = self.ctx["xf_x"]
        lo = tx.convert(g["min"][0], g["xf"][0], xf)
        hi = tx.convert(g["max"][0], g["xf"][0], xf)
        lo = -0.05 if lo is None else lo
        hi = 1.05 if hi is None else hi
        item = pg.LinearRegionItem(values=(lo, hi), brush=pg.mkBrush(255, 80, 80, 40),
                                   pen=GATE_PEN, movable=True)
        self.addItem(item)
        self.gate_items.append(item)

        def done():
            a, b = item.getRegion()
            ng = dict(g, xf=[xf], min=[a if a > -0.04 else None], max=[b if b < 1.04 else None])
            self.gate_edited.emit(path, ng)
        item.sigRegionChangeFinished.connect(done)
        self._label(path, stats, (max(lo, 0) + min(hi, 1)) / 2, 0.92)

    def _add_gate(self, path, g, swap, stats):
        ctx = self.ctx
        xf_x, xf_y = ctx["xf_x"], ctx["xf_y"]
        gx, gy = (g["xf"][1], g["xf"][0]) if swap else (g["xf"][0], g["xf"][1])
        native = tx.same(gx, xf_x) and tx.same(gy, xf_y)
        t = g["type"]
        roi = None
        if t == "rect":
            gg = reexpress_rect(g, [xf_y, xf_x] if swap else [xf_x, xf_y])
            lo, hi = list(gg["min"]), list(gg["max"])
            if swap:
                lo, hi = lo[::-1], hi[::-1]
            open_ = [lo[0] is None, lo[1] is None, hi[0] is None, hi[1] is None]
            x0 = -0.02 if lo[0] is None else lo[0]
            y0 = -0.02 if lo[1] is None else lo[1]
            x1 = 1.02 if hi[0] is None else hi[0]
            y1 = 1.02 if hi[1] is None else hi[1]
            roi = pg.RectROI((x0, y0), (x1 - x0, y1 - y0), pen=GATE_PEN, hoverPen=GATE_HOVER,
                             invertible=True)
            for h in ([0, 0], [1, 0], [0, 1]):
                roi.addScaleHandle(h, [1 - h[0], 1 - h[1]])

            def done(r=roi):
                pos, size = r.pos(), r.size()
                X0, Y0, X1, Y1 = pos.x(), pos.y(), pos.x() + size.x(), pos.y() + size.y()
                X0, X1 = min(X0, X1), max(X0, X1)
                Y0, Y1 = min(Y0, Y1), max(Y0, Y1)
                mn = [None if X0 <= -0.015 else X0, None if Y0 <= -0.015 else Y0]
                mx = [None if X1 >= 1.015 else X1, None if Y1 >= 1.015 else Y1]
                if swap:
                    mn, mx = mn[::-1], mx[::-1]
                ng = dict(g, xf=[xf_y, xf_x] if swap else [xf_x, xf_y], min=mn, max=mx)
                self.gate_edited.emit(path, ng)
            cx, cy = (max(x0, 0) + min(x1, 1)) / 2, (max(y0, 0) + min(y1, 1)) / 2
        elif native and t == "poly":
            v = np.asarray(g["vertices"], float)
            if swap:
                v = v[:, ::-1]
            roi = pg.PolyLineROI(v.tolist(), closed=True, pen=GATE_PEN, hoverPen=GATE_HOVER)

            def done(r=roi):
                pts = [r.mapToParent(p) for p in r.getState()["points"]]
                verts = [[p.x(), p.y()] for p in pts]
                if swap:
                    verts = [[b, a] for a, b in verts]
                self.gate_edited.emit(path, dict(g, vertices=verts))
            cx, cy = v[:, 0].mean(), v[:, 1].mean()
        elif native and t == "ellipse":
            (cx, cy), (a, b), ang = g["center"], g["axes"], g.get("angle", 0.0)
            if swap:
                cx, cy = cy, cx
                ang = 90.0 - ang
            th = math.radians(ang)
            # ROI position is its local (0,0) corner, rotated about itself
            px = cx - (a * math.cos(th) - b * math.sin(th))
            py = cy - (a * math.sin(th) + b * math.cos(th))
            roi = pg.EllipseROI((px, py), (2 * a, 2 * b), angle=ang, pen=GATE_PEN, hoverPen=GATE_HOVER)

            def done(r=roi):
                size = r.size()
                c = r.mapToParent(QtCore.QPointF(size.x() / 2, size.y() / 2))
                A, B, ANG = abs(size.x()) / 2, abs(size.y()) / 2, r.angle()
                C = [c.x(), c.y()]
                if swap:
                    C = C[::-1]
                    ANG = 90.0 - ANG
                self.gate_edited.emit(path, dict(g, center=C, axes=[A, B], angle=ANG))
        if roi is not None:
            roi.sigRegionChangeFinished.connect(done)
            roi.setAcceptedMouseButtons(QtCore.Qt.LeftButton | QtCore.Qt.RightButton)
            roi.sigClicked.connect(lambda r, ev, p=path: self._roi_clicked(p, ev))
            self.addItem(roi)
            self.gate_items.append(roi)
        else:
            # drawn on other axes (e.g. a FlowJo polygon on linear, viewed on biex): true outline, read-only
            pts = gate_outline(g, xf_x, xf_y, swap=swap)
            c = pg.PlotCurveItem(pts[:, 0], pts[:, 1], pen=READONLY_PEN)
            c.setToolTip("Gate drawn on different axis scales. Switch the axes to match it, "
                         "or right-click the gate in the tree to convert it, to edit.")
            self.addItem(c)
            self.gate_items.append(c)
            inside = pts[(pts[:, 0] >= 0) & (pts[:, 0] <= 1) & (pts[:, 1] >= 0) & (pts[:, 1] <= 1)]
            cx, cy = (inside.mean(0) if len(inside) else (0.5, 0.5))
        self._label(path, stats, cx, cy)

    def _roi_clicked(self, path, ev):
        if ev.button() == QtCore.Qt.RightButton:
            self.gate_menu.emit(path, ev.screenPos().toPoint())
        elif ev.double():
            self.gate_open.emit(path)

    # ------------------------------------------------------------------ drawing
    def set_tool(self, tool):
        self.vb.set_tool(tool)

    def _on_drawn(self, tool, geom):
        if self.ctx is None:
            return
        self.gate_created.emit(tool, geom)

    def export_png(self, path):
        from pyqtgraph.exporters import ImageExporter
        ex = ImageExporter(self.getPlotItem())
        ex.parameters()["width"] = 1400
        ex.export(path)


def density_levels(H, smooth=True):
    """Colour levels 0..255 (0 = empty). Smoothed where events are dense; every occupied bin
    stays visible, and lone events stay small dots instead of smoothed blobs."""
    S = _smooth2d(H) if smooth else H
    img = np.log1p(S)
    mx = img.max() if img.size and img.max() > 0 else 1
    show = (H > 0) | (S > 0.35)
    return np.where(show, 1 + 254 * img / mx, 0)


def _smooth2d(H, sigma=None):
    from scipy.ndimage import gaussian_filter
    if sigma is None:
        sigma = 1.6 * H.shape[0] / 256
    return gaussian_filter(H, sigma=sigma, mode="nearest")
