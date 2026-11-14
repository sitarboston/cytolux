"""The Overlay tab. Mostly about what gets laid over what, which is the only
control here anyone can get wrong."""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore, QtGui

from cytolux import overlay as ov
from cytolux import transforms as tx
from cytolux.engine import EventData, Workspace

from helpers import FakeSample, thresh

T = 262144.0


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def win(app):
    from cytolux.app import MainWindow
    w = MainWindow()
    w.resize(1000, 700)
    rng = np.random.default_rng(0)
    for i, name in enumerate(("plate_A1.fcs", "plate_A2.fcs", "plate_A3.fcs")):
        cols = {"CD69": np.clip(rng.normal(0.35 + 0.1 * i, 0.06, 5000), 0, 1) * T,
                "FSC-A": np.clip(rng.normal(0.5, 0.1, 5000), 0, 1) * T}
        s = FakeSample(name, cols)
        w.ws.samples.append(s)
        w.ws._events[s.name] = EventData(s, None)
        w.sample_list.addItem(s.name)
    w.ws.add_pop("root", "CD69+", thresh(0.45, dim="CD69"))
    w.cur_sample = w.ws.samples[0]
    w.cur_pop = "root"
    w.sample_list.setCurrentRow(0)
    w.overlay.refresh_channels()
    yield w
    w.dirty = False
    w.close()


def _pick(ov_tab, channel="CD69"):
    i = ov_tab.cb_channel.findData(channel)
    assert i >= 0, "the channel is not in the list"
    ov_tab.cb_channel.setCurrentIndex(i)


def test_the_tab_is_there_and_named(win):
    names = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    assert "Overlay" in names
    assert win.tabs.tabToolTip(names.index("Overlay"))


def test_drawing_nothing_says_what_to_do_rather_than_crashing(app):
    from cytolux.app import MainWindow
    w = MainWindow()
    w.overlay.draw()
    assert w.overlay.note.text()
    assert not w.overlay.series
    w.dirty = False
    w.close()


def test_selected_samples_become_curves(win):
    _pick(win.overlay)
    sel = win.sample_list.selectionModel()
    sel.clearSelection()
    for r in (0, 2):
        sel.select(win.sample_list.model().index(r, 0), QtCore.QItemSelectionModel.Select)
    win.overlay.cb_source.setCurrentIndex(0)
    win.overlay.draw()
    assert [s.label for s in win.overlay.series] == ["A1 · All events", "A3 · All events"]


def test_every_sample_draws_the_whole_plate(win):
    _pick(win.overlay)
    win.overlay.cb_source.setCurrentIndex(1)
    win.overlay.draw()
    assert len(win.overlay.series) == 3


def test_one_sample_many_gates(win):
    _pick(win.overlay)
    win.overlay.cb_source.setCurrentIndex(2)
    win.overlay.draw()
    labels = [s.label for s in win.overlay.series]
    assert labels[0].endswith("All events") and any("CD69+" in t for t in labels)


def test_with_nothing_selected_it_falls_back_to_the_open_sample(win):
    _pick(win.overlay)
    win.sample_list.selectionModel().clearSelection()
    win.overlay.cb_source.setCurrentIndex(0)
    win.overlay.draw()
    assert len(win.overlay.series) == 1


def test_the_axis_follows_the_channel_transform(win):
    _pick(win.overlay)
    win.ws.set_xform("CD69", tx.biex(T))
    win.overlay.cb_source.setCurrentIndex(1)
    win.overlay.draw()
    assert win.overlay.ax_x.spec["kind"] == "biex"
    win.ws.set_xform("CD69", tx.linear(T))
    win.overlay.draw()
    assert win.overlay.ax_x.spec["kind"] == "linear"


def test_changing_normalisation_redraws_what_is_on_screen(win):
    _pick(win.overlay)
    win.overlay.cb_source.setCurrentIndex(1)
    win.overlay.draw()
    assert max(s.y.max() for s in win.overlay.series) == pytest.approx(100.0)
    win.overlay.cb_norm.setCurrentIndex(2)          # raw count
    assert win.overlay.plot.getPlotItem().getAxis("left").labelText == "Count"


def test_the_legend_keeps_off_the_data(win):
    """Right-heavy curves put the key on the left, and the other way round."""
    _pick(win.overlay)
    win.overlay.cb_source.setCurrentIndex(1)
    win.overlay.draw()
    right_heavy = win.overlay._busy_side()
    assert right_heavy in ("left", "right")
    flipped = []
    for s in win.overlay.series:                    # mirror every curve
        s.y = s.y[::-1].copy()
    assert win.overlay._busy_side() != right_heavy, "the key would sit on the data"


def test_the_table_matches_the_curves(win):
    _pick(win.overlay)
    win.overlay.cb_source.setCurrentIndex(1)
    win.overlay.draw()
    rows = win.overlay.table()
    assert rows[0] == ("Curve", "n", "Median", "Mean")
    assert len(rows) == len(win.overlay.series) + 1
    assert rows[1][1] == str(win.overlay.series[0].n)


def test_export_writes_a_real_image(win, tmp_path):
    _pick(win.overlay)
    win.overlay.cb_source.setCurrentIndex(1)
    win.overlay.draw()
    out = win.overlay.export(str(tmp_path / "ov.png"), width=800)
    img = QtGui.QImage(out)
    assert not img.isNull() and img.width() == 800


def test_export_puts_the_figure_on_white_and_the_tab_back_on_cream(win, tmp_path):
    from cytolux import theme
    _pick(win.overlay)
    win.overlay.cb_source.setCurrentIndex(1)
    win.overlay.draw()
    out = win.overlay.export(str(tmp_path / "ov.png"), width=600)
    img = QtGui.QImage(out)
    assert QtGui.QColor(img.pixel(3, 3)) == QtGui.QColor(theme.FIGURE)
    assert win.overlay.plot.backgroundBrush().color() == QtGui.QColor(theme.CANVAS)


def test_a_long_plate_is_capped_and_says_so(win):
    from cytolux.engine import EventData
    rng = np.random.default_rng(1)
    for i in range(40):
        s = FakeSample("extra_%02d.fcs" % i,
                       {"CD69": np.clip(rng.normal(0.5, 0.05, 400), 0, 1) * T})
        win.ws.samples.append(s)
        win.ws._events[s.name] = EventData(s, None)
    _pick(win.overlay)
    win.overlay.cb_source.setCurrentIndex(1)
    win.overlay.draw()
    from cytolux.overlay_ui import MAX_CURVES
    assert len(win.overlay.series) == MAX_CURVES
    assert "first %d" % MAX_CURVES in win.overlay.note.text()
