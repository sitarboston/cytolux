"""The author's name, where it belongs.

Two promises pull against each other here. The attribution has to be permanent:
in the window, and inside every file the program writes, surviving a copy that
arrives with no explanation. And it must never be stamped across a figure, because
a plot with a name written over the data is one no journal will print, which would
make the credit cost its author the work it was meant to credit. The name rides in
the metadata; the picture stays clean.
"""
import os

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtGui

from cytolux import brand
from cytolux import transforms as tx
from cytolux.engine import Workspace

from helpers import FakeSample, attach, islands, rect

T = 262144.0


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_the_creator_is_named_in_one_place_only():
    assert brand.CREATOR == "Samyabrata Bhaduri, PhD"
    assert brand.CREATOR in brand.CREDIT
    assert brand.CREATOR in brand.software_tag()
    assert brand.CREATOR in brand.COPYRIGHT


def test_the_window_carries_the_credit_permanently(app):
    from cytolux.app import MainWindow
    w = MainWindow()
    try:
        assert brand.CREATOR in w.credit.text()
        bar = w.statusBar()
        # a transient status message must not displace it
        bar.showMessage("Loaded 96 files", 1000)
        assert brand.CREATOR in w.credit.text()
        assert w.credit.isVisibleTo(w)
    finally:
        w.dirty = False
        w.close()


def test_there_is_no_switch_to_turn_it_off(app):
    """Permanent means permanent: no menu entry and no setting removes it."""
    from cytolux.app import MainWindow
    w = MainWindow()
    try:
        texts = []
        for top in w.menuBar().actions():
            if top.menu():
                texts += [a.text().lower() for a in top.menu().actions()]
        assert not [t for t in texts if "credit" in t or "attribution" in t or "watermark" in t]
    finally:
        w.dirty = False
        w.close()


def test_about_names_the_creator_and_the_version(app):
    from cytolux import __version__
    from cytolux.app import MainWindow
    w = MainWindow()
    try:
        found = [a for top in w.menuBar().actions() if top.menu()
                 for a in top.menu().actions() if a.text() == "About Cytolux"]
        assert found, "there is no About entry"
        assert brand.CREATOR in brand.LONG_CREDIT
        assert __version__ in brand.LONG_CREDIT
    finally:
        w.dirty = False
        w.close()


# --- what the written files say --------------------------------------------


def test_an_exported_figure_carries_the_author_in_its_metadata(app, tmp_path):
    from cytolux.plot import GatePlot
    ws = Workspace()
    ws.add_pop("root", "High", rect(0.40, 1.20))
    s = attach(ws, FakeSample("one.fcs", islands(n=4000)))
    p = GatePlot()
    p.resize(420, 420)
    p.show_population(dict(ws=ws, sample=s, pop="root", x="A", y="B",
                           xf_x=tx.linear(T), xf_y=tx.linear(T),
                           gates=[("/High", ws.gate_for("/High", s.name))]))
    out = p.export_png(str(tmp_path / "fig.png"), width=700, dpi=300)
    p.close()
    img = QtGui.QImage(out)
    assert not img.isNull()
    assert img.text("Author") == brand.CREATOR
    assert "Cytolux" in img.text("Software")
    assert img.text("Copyright") == brand.COPYRIGHT


def test_the_figure_itself_is_not_defaced(app, tmp_path):
    """No visible stamp: the exported image must be only the plot."""
    from cytolux.plot import GatePlot
    ws = Workspace()
    s = attach(ws, FakeSample("one.fcs", islands(n=3000)))
    p = GatePlot()
    p.resize(400, 400)
    p.show_population(dict(ws=ws, sample=s, pop="root", x="A", y="B",
                           xf_x=tx.linear(T), xf_y=tx.linear(T), gates=[]))
    plain = p.export_png(str(tmp_path / "a.png"), width=600, dpi=0, figure=True)
    img = QtGui.QImage(plain).convertToFormat(QtGui.QImage.Format_ARGB32)
    p.close()
    # the four corners of a figure export are paper, not ink
    for x, y in ((4, 4), (img.width() - 5, 4), (4, img.height() - 5),
                 (img.width() - 5, img.height() - 5)):
        c = QtGui.QColor(img.pixel(x, y))
        assert c.lightness() > 230, "something is printed in the corner of the figure"


def test_a_saved_workspace_records_who_wrote_it(tmp_path):
    import json
    ws = Workspace()
    attach(ws, FakeSample("one.fcs", islands(n=500)))
    path = str(tmp_path / "w.fgw")
    ws.save(path)
    d = json.load(open(path))
    assert d["author"] == brand.CREATOR
    assert "Cytolux" in d["created_with"]


def test_an_exported_workbook_is_signed(tmp_path):
    pytest.importorskip("openpyxl")
    from openpyxl import load_workbook

    from cytolux.stats_ui import export_excel
    ws = Workspace()
    attach(ws, FakeSample("one.fcs", islands(n=800)))
    ws.add_pop("root", "High", rect(0.40, 1.20))
    out = str(tmp_path / "stats.xlsx")
    export_excel(ws, out)
    wb = load_workbook(out)
    assert wb.properties.creator == brand.CREATOR
    about = wb["About"]
    cells = [str(c.value) for row in about.iter_rows() for c in row]
    assert brand.CREATOR in cells
