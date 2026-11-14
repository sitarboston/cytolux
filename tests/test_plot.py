"""Rendering and export. A gating app that produces blocky pictures is not finished.

The pixelation these tests guard against had one cause: the density grid was a fixed
256 bins stretched across however many pixels the plot happened to occupy, so on any
reasonably sized window the eye was reading the grid rather than the data.
"""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtGui

from cytolux import transforms as tx
from cytolux.engine import Workspace
from cytolux.plot import GatePlot, contour_levels

from helpers import FakeSample, attach, islands, rect, smear, thresh

T = 262144.0


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def plotted(app):
    ws = Workspace()
    # a two-dimensional gate, so the plot grows the drag handles a real gate has
    ws.add_pop("root", "High", rect(0.40, 1.20))
    s = attach(ws, FakeSample("one.fcs", islands(n=12000)))
    p = GatePlot()
    p.resize(600, 600)
    p.show()
    ctx = dict(ws=ws, sample=s, pop="root", x="A", y="B",
               xf_x=tx.linear(T), xf_y=tx.linear(T),
               gates=[("/High", ws.gate_for("/High", s.name))])
    p.show_population(ctx)
    yield p, ws, ctx
    p.close()


# --- the grid that was causing the blockiness ---------------------------------------

def test_the_density_grid_follows_the_plot_size(plotted):
    p, _, _ = plotted
    assert p.grid_bins() > 256, "still at the old fixed resolution"
    assert p.grid_bins() <= p.MAX_BINS


def test_the_grid_is_clamped_at_both_ends(plotted):
    p, _, ctx = plotted
    p.resize(40, 40)
    p.show_population(ctx)
    assert p.grid_bins() >= p.MIN_BINS, "a tiny plot must not drop below a usable grid"
    p.resize(4000, 4000)
    p.show_population(ctx)
    assert p.grid_bins() <= p.MAX_BINS, "a huge plot must not bin itself to a standstill"


def test_an_export_override_wins_over_the_screen_size(plotted):
    p, _, _ = plotted
    p.bins_override = 1500
    assert p.grid_bins() == 1500
    p.bins_override = None


# --- contour levels ------------------------------------------------------------------

def test_contour_levels_are_increasing_and_the_right_count():
    rng = np.random.default_rng(0)
    S = np.abs(rng.normal(size=(64, 64))) ** 3
    lv = contour_levels(S, 8)
    assert len(lv) <= 8 and len(lv) >= 5
    assert lv == sorted(lv)
    assert all(l > 0 for l in lv)


def test_contour_levels_enclose_rising_shares_of_the_events():
    """The point of equal-probability contours: each line encloses a known fraction of
    the cells, so the spacing of the lines is the shape of the distribution."""
    rng = np.random.default_rng(1)
    xy = rng.normal(32, 6, size=(40000, 2))
    S, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=64, range=[[0, 64], [0, 64]])
    lv = contour_levels(S, 6)
    shares = [S[S >= l].sum() / S.sum() for l in lv]
    assert shares == sorted(shares, reverse=True), "outer contours must enclose more"
    assert shares[0] > shares[-1]
    assert 0.0 < shares[-1] < shares[0] < 1.0


def test_contour_levels_of_empty_or_flat_data_are_empty():
    assert contour_levels(np.zeros((16, 16)), 8) == []
    assert contour_levels(np.array([[0.0]]), 8) == []


# --- the three display modes ---------------------------------------------------------

def test_contour_mode_draws_curves_and_clears_them_again(plotted):
    p, _, ctx = plotted
    p.mode = "contour"
    p.show_population(ctx)
    assert len(p.contour_items) > 0, "contour mode drew nothing"
    p.mode = "density"
    p.show_population(ctx)
    assert p.contour_items == [], "contours survived a switch back to pseudocolor"


def test_contour_mode_leaves_the_sparse_events_as_dots(plotted):
    """A rare population must not be smoothed out of existence by the contours."""
    p, _, ctx = plotted
    p.mode = "contour"
    p.show_population(ctx)
    assert len(p.scatter.getData()[0]) > 0


def test_every_mode_renders_without_error(plotted):
    p, _, ctx = plotted
    for mode in ("density", "contour", "dots"):
        p.mode = mode
        p.show_population(ctx)
    p.mode = "density"


# --- export --------------------------------------------------------------------------

def test_export_honours_the_requested_size_and_dpi(plotted, tmp_path):
    p, _, _ = plotted
    f = tmp_path / "fig.png"
    p.export_png(str(f), width=1200, dpi=600)
    img = QtGui.QImage(str(f))
    assert img.width() == 1200
    assert round(img.dotsPerMeterX() * 0.0254) == 600, "the PNG did not carry its dpi"


def test_export_rebins_the_density_at_the_export_size(plotted, tmp_path, monkeypatch):
    """Enlarging the canvas without rebinning only enlarges the blocks."""
    p, _, _ = plotted
    seen = []
    real = p.grid_bins
    monkeypatch.setattr(p, "grid_bins", lambda: seen.append(real()) or real())
    p.export_png(str(tmp_path / "f.png"), width=1600, dpi=300)
    assert max(seen) >= 1600, "exported from the on-screen grid: %r" % seen


def test_export_restores_the_screen_state(plotted, tmp_path):
    p, _, _ = plotted
    before_bins, before_fig = p.bins_override, p.figure_mode
    p.export_png(str(tmp_path / "f.png"), width=1200, dpi=300)
    assert (p.bins_override, p.figure_mode) == (before_bins, before_fig)
    assert all(h.isVisible() for h in p._handle_items()), "handles never came back"


def test_a_figure_export_hides_the_editing_handles(plotted, tmp_path):
    """The square drag handles belong to editing. In a figure they are furniture."""
    p, _, _ = plotted
    assert list(p._handle_items()), "the fixture has no handles to hide"
    states = []
    real = p._handle_items
    p.export_png(str(tmp_path / "f.png"), width=800, dpi=300, figure=True)
    # captured indirectly: during the export they were hidden, afterwards visible again
    assert all(h.isVisible() for h in real())


def test_a_figure_export_drops_the_detector_prefix(plotted):
    p, ws, _ = plotted
    ws.labels["A"] = "CD4-PE-Cy7-A"
    full = ws.label("A", None)
    p.figure_mode = False
    assert p._axis_label(ws, "A", None) == full
    p.figure_mode = True
    assert p._axis_label(ws, "A", None) == "CD4-PE-Cy7-A"
    assert " :: " not in p._axis_label(ws, "A", None)
    p.figure_mode = False


def test_a_screen_export_keeps_everything(plotted, tmp_path):
    p, _, _ = plotted
    p.export_png(str(tmp_path / "s.png"), width=700, dpi=0, figure=False)
    img = QtGui.QImage(str(tmp_path / "s.png"))
    assert img.width() == 700


# --- contour bandwidth ---------------------------------------------------------------

def test_the_contour_bandwidth_widens_as_events_get_scarcer(plotted):
    """A fixed bandwidth traced counting noise on small populations: dozens of little
    closed rings that look like structure and are not."""
    p, _, _ = plotted
    assert p._contour_sigma(3000) > p._contour_sigma(100000)
    assert p._contour_sigma(3000) / p._contour_sigma(3000 * 64) == pytest.approx(2.0, rel=1e-6)


def test_a_sparse_population_gets_smooth_contours_not_noise(app):
    """The regression guard. Three thousand events used to produce dozens of separate
    blobs above the outermost contour; it should be a handful of real regions."""
    from scipy import ndimage
    from cytolux.plot import contour_levels, _smooth2d
    rng = np.random.default_rng(5)
    n = 3000
    xy = np.clip(rng.normal(0.5, 0.12, size=(n, 2)), 0, 1)
    p = GatePlot()
    H, _, _ = np.histogram2d(xy[:, 0], xy[:, 1], bins=p.CONTOUR_BINS, range=[[0, 1], [0, 1]])
    S = _smooth2d(H, sigma=max(1.0, p._contour_sigma(n) * p.CONTOUR_BINS))
    lv = contour_levels(S, 8)
    assert lv, "no contours at all"
    assert ndimage.label(S >= lv[0])[1] <= 3, "the outermost contour broke into noise"
    p.close()


# --- the quadrant crosshair ----------------------------------------------------------

@pytest.fixture
def quad_plotted(app):
    from cytolux.engine import quad_from_center
    ws = Workspace()
    xf = [dict(tx.linear(T)), dict(tx.linear(T))]
    for sx, sy in (("-", "+"), ("+", "+"), ("+", "-"), ("-", "-")):
        ws.add_pop("root", "Q%s%s" % (sx, sy),
                   quad_from_center(("A", "B"), xf, 0.5, 0.5, sx, sy))
    s = attach(ws, FakeSample("q.fcs", smear(n=9000, seed=2)))
    p = GatePlot()
    p.resize(500, 500)
    p.show()
    ctx = dict(ws=ws, sample=s, pop="root", x="A", y="B",
               xf_x=tx.linear(T), xf_y=tx.linear(T),
               gates=[(q["path"], ws.gate_for(q["path"], s.name)) for q in ws.pops])
    p.show_population(ctx)
    yield p, ws, ctx
    p.close()


def test_a_quadrant_family_is_drawn_as_one_crosshair(quad_plotted):
    import pyqtgraph as pg
    p, _, _ = quad_plotted
    lines = [i for i in p.gate_items if isinstance(i, pg.InfiniteLine)]
    assert len(lines) == 2, "expected two crosshair arms, got %d" % len(lines)
    assert not any(hasattr(i, "handles") and i.handles for i in p.gate_items), \
        "the four rectangles were drawn as well, each with its own handles"


def test_the_crosshair_carries_a_percentage_in_each_corner(quad_plotted):
    import pyqtgraph as pg
    p, ws, _ = quad_plotted
    labels = [i for i in p.gate_items if isinstance(i, pg.TextItem)]
    assert len(labels) == 4
    pcts = [float(t.toPlainText().split("\n")[1].rstrip("%")) for t in labels]
    assert sum(pcts) == pytest.approx(100.0, abs=0.05), "the quadrants do not add up"


def test_dragging_an_arm_reports_the_new_centre(quad_plotted):
    import pyqtgraph as pg
    p, _, _ = quad_plotted
    seen = []
    p.quad_moved.connect(lambda m, x, y: seen.append((x, y)))
    vline = [i for i in p.gate_items if isinstance(i, pg.InfiniteLine) and i.angle == 90][0]
    vline.setValue(0.27)
    vline.sigPositionChangeFinished.emit(vline)
    assert len(seen) == 1
    assert seen[0][0] == pytest.approx(0.27)
    assert seen[0][1] == pytest.approx(0.5), "the other arm moved too"


def test_an_ordinary_gate_still_gets_its_own_handles(plotted):
    p, _, _ = plotted
    assert list(p._handle_items()), "a lone rectangle lost its drag handles"
