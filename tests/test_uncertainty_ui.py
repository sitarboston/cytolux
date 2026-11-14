"""The confidence panel. The engine being right does not help if the window never asks it."""
import numpy as np
import pytest

pytest.importorskip("PySide6")

from cytolux.engine import Workspace
from cytolux.uncertainty_ui import GRADE_BG, GRADE_NOTE, FragilityDialog, UncertaintyDock

from helpers import FakeSample, attach, smear, thresh


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def ws():
    w = Workspace()
    w.add_pop("root", "Positive", thresh(0.90))
    w.add_pop("/Positive", "Inner", thresh(0.95, "B"))
    attach(w, FakeSample("one.fcs", smear(n=8000, seed=3)))
    return w


# --- the per-sample dock ------------------------------------------------------------

def test_the_dock_opens_blank_and_says_why(app, ws):
    d = UncertaintyDock(ws)
    d.set_sample(ws.samples[0])
    assert d.table.rowCount() == 0
    assert "Measure confidence" in d.note.text()


def test_measuring_fills_a_row_for_every_population(app, ws):
    d = UncertaintyDock(ws)
    d.set_sample(ws.samples[0])
    d.reps.setValue(30)
    d.run()
    assert d.table.rowCount() == len(ws.pops)
    assert d.table.item(0, 0).text().strip() == "Positive"
    assert float(d.table.item(0, 1).text()) == pytest.approx(10.0, abs=1.0)


def test_the_interval_column_brackets_the_frequency(app, ws):
    d = UncertaintyDock(ws)
    d.set_sample(ws.samples[0])
    d.reps.setValue(50)
    d.run()
    value = float(d.table.item(0, 1).text())
    lo, hi = [float(x) for x in d.table.item(0, 2).text().split(" to ")]
    assert lo <= value <= hi
    assert float(d.table.item(0, 3).text()) == pytest.approx(0.5 * (hi - lo), abs=0.01)


def test_every_row_is_coloured_by_its_grade(app, ws):
    d = UncertaintyDock(ws)
    d.set_sample(ws.samples[0])
    d.reps.setValue(30)
    d.run()
    for r in range(d.table.rowCount()):
        grade = d.table.item(r, 5).text()
        assert grade in GRADE_BG
        assert d.table.item(r, 0).background().color() == GRADE_BG[grade]
        assert d.table.item(r, 5).toolTip() == GRADE_NOTE[grade]


def test_moving_a_gate_blanks_the_numbers_rather_than_leaving_them_stale(app, ws):
    """The important one. A number that silently followed a moved gate would be worse
    than a blank panel, because it would still look measured."""
    d = UncertaintyDock(ws)
    d.set_sample(ws.samples[0])
    d.reps.setValue(30)
    d.run()
    assert d.table.rowCount() > 0
    d.set_stale()
    assert d.table.rowCount() == 0
    assert "Measure confidence" in d.note.text()


def test_changing_sample_blanks_the_numbers(app, ws):
    s2 = attach(ws, FakeSample("two.fcs", smear(n=8000, seed=9)))
    d = UncertaintyDock(ws)
    d.set_sample(ws.samples[0])
    d.reps.setValue(30)
    d.run()
    d.set_sample(s2)
    assert d.table.rowCount() == 0
    assert "two.fcs" in d.head.text()


def test_the_dock_refuses_politely_with_no_gates(app):
    bare = Workspace()
    s = attach(bare, FakeSample("bare.fcs", smear(n=500)))
    d = UncertaintyDock(bare)
    d.set_sample(s)
    d.run()
    assert "gate" in d.note.text().lower()
    assert d.table.rowCount() == 0


def test_the_hand_setting_is_a_percentage_of_the_axis(app, ws):
    d = UncertaintyDock(ws)
    assert d.sigma.value() == pytest.approx(1.0)
    assert d.sigma.suffix().strip() == "%"


def test_a_wider_hand_widens_the_reported_interval(app, ws):
    d = UncertaintyDock(ws)
    d.set_sample(ws.samples[0])
    d.reps.setValue(100)
    d.sigma.setValue(0.5)
    d.run()
    tight = float(d.table.item(0, 3).text())
    d.sigma.setValue(4.0)
    d.run()
    assert float(d.table.item(0, 3).text()) > 2 * tight


def test_the_note_names_the_weakest_population_and_what_to_do(app, ws):
    d = UncertaintyDock(ws)
    d.set_sample(ws.samples[0])
    d.reps.setValue(100)
    d.sigma.setValue(3.0)          # shaky enough to produce something fragile
    d.run()
    note = d.note.text()
    assert "weakest" in note
    assert "redrawing that gate" in note or "more events" in note


# --- the workspace-wide dialog ------------------------------------------------------

def test_the_dialog_runs_and_fills_a_table(app, ws):
    s2 = attach(ws, FakeSample("two.fcs", smear(n=8000, seed=9)))
    dlg = FragilityDialog(ws)
    dlg.reps.setValue(30)
    dlg.run()
    assert dlg.table.rowCount() == 2 * len(ws.pops)
    assert "Grade" in [dlg.table.horizontalHeaderItem(c).text()
                       for c in range(dlg.table.columnCount())]
    assert "rows" in dlg.summary.text()


def test_the_dialog_headers_explain_themselves(app, ws):
    dlg = FragilityDialog(ws)
    dlg.reps.setValue(20)
    dlg.run()
    tips = [dlg.table.horizontalHeaderItem(c).toolTip()
            for c in range(dlg.table.columnCount())]
    assert sum(bool(t) for t in tips) >= 8, "most columns should explain themselves"


def test_hiding_firm_rows_shortens_the_table(app, ws):
    dlg = FragilityDialog(ws)
    dlg.reps.setValue(60)
    dlg.sigma.setValue(0.2)        # gentle, so most rows come back firm
    dlg.run()
    full = dlg.table.rowCount()
    dlg.only_bad.setChecked(True)
    assert dlg.table.rowCount() <= full
    assert len(dlg.df) == full, "the underlying report is not filtered, only the view"


def test_export_is_disabled_until_there_is_something_to_export(app, ws):
    dlg = FragilityDialog(ws)
    assert not dlg.xl_btn.isEnabled()
    assert not dlg.copy_btn.isEnabled()
    dlg.reps.setValue(20)
    dlg.run()
    assert dlg.xl_btn.isEnabled()
    assert dlg.copy_btn.isEnabled()


def test_copy_puts_the_whole_report_on_the_clipboard(app, ws):
    from PySide6 import QtWidgets
    dlg = FragilityDialog(ws)
    dlg.reps.setValue(20)
    dlg.run()
    dlg._copy()
    text = QtWidgets.QApplication.clipboard().text()
    assert "Grade" in text and "Limited by" in text
    assert len(text.strip().split("\n")) == len(dlg.df) + 1


def test_the_excel_export_carries_its_own_method(app, ws, tmp_path):
    """An interval is meaningless without the assumption that produced it, and the
    spreadsheet outlives the conversation where it was explained."""
    import pandas as pd
    from cytolux.uncertainty_ui import export_confidence
    from cytolux.uncertainty import fragility_report
    df = fragility_report(ws, n=20)
    out = tmp_path / "confidence.xlsx"
    export_confidence(ws, df, str(out), sigma=0.01, n=20, level=95.0)
    assert out.exists()
    book = pd.read_excel(out, sheet_name=None)
    assert set(book) == {"Confidence", "Method"}
    assert len(book["Confidence"]) == len(df)
    method = dict(zip(book["Method"]["Item"], book["Method"]["Value"]))
    assert "1.00 % of each axis" in method["Hand steadiness (sigma)"]
    assert method["Runs per sample"] == 20
    assert "quadrature" in method["Interval"]
    assert "Cytolux" in method["Software"]


# --- the main window ----------------------------------------------------------------

@pytest.fixture
def win(app):
    """A main window that cannot hang on the way out.

    closeEvent asks whether to save unsaved work, which is right in the application and
    fatal in a test: offscreen there is nobody to answer the prompt and the run blocks
    forever at shutdown. Any test that edits the workspace would trip it, so the flag is
    cleared here rather than remembered in each test.
    """
    from cytolux.app import MainWindow
    w = MainWindow()
    yield w
    w.dirty = False
    w.close()


def test_the_confidence_menu_exists_with_both_actions(win):
    texts = []
    for top in win.menuBar().actions():
        if top.text().replace("&", "") == "Confidence" and top.menu():
            texts = [a.text() for a in top.menu().actions()]
    assert len(texts) == 2, "no Confidence menu found: %r" % texts
    assert any("this sample" in t for t in texts)
    assert any("weakest" in t for t in texts)


def test_both_confidence_actions_explain_themselves_on_hover(win):
    for top in win.menuBar().actions():
        if top.text().replace("&", "") == "Confidence" and top.menu():
            for a in top.menu().actions():
                assert len(a.toolTip()) > 40, "no tooltip on %r" % a.text()


def test_the_measure_action_is_on_control_u(win):
    for top in win.menuBar().actions():
        if top.text().replace("&", "") == "Confidence" and top.menu():
            a = top.menu().actions()[0]
            assert a.shortcut().toString() == "Ctrl+U"


def test_editing_a_gate_marks_the_open_panel_stale(win, monkeypatch):
    """_mark is the window's catch-all for 'something changed'. The panel has to be
    wired to it, or an interval could outlive the gate it was measured on."""
    s = attach(win.ws, FakeSample("w.fcs", smear(n=4000, seed=2)))
    win.ws.add_pop("root", "P", thresh(0.90))
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.information",
                        lambda *a, **k: None)
    win.cur_sample = s
    win.show_confidence()
    panel = win._conf_panel
    panel.reps.setValue(20)
    panel.run()
    assert panel.table.rowCount() == 1
    win._mark()
    assert panel.table.rowCount() == 0, "the panel kept numbers for a changed gating tree"


def test_closing_with_unsaved_work_asks_first(win, monkeypatch):
    """Guards the behaviour that made the fixture above necessary. A window with edits
    in it must not go quietly, and the test suite must not be what discovers that."""
    asked = []
    monkeypatch.setattr("cytolux.app.MainWindow._maybe_save",
                        lambda self: asked.append(self.dirty) or True)
    win.dirty = True
    win.close()
    assert asked == [True]


# --- long names ---------------------------------------------------------------------

def test_shared_prefix_finds_what_the_names_have_in_common():
    from cytolux.uncertainty_ui import shared_prefix
    plate = ["Plate 2 Day 7_Group_A%d.fcs" % i for i in range(1, 13)]
    assert shared_prefix(plate) == "Plate 2 Day 7_Group_"
    assert shared_prefix(["one.fcs"]) == "", "a single name shares nothing with anything"
    assert shared_prefix([]) == ""
    assert shared_prefix(["alpha.fcs", "beta.fcs"]) == "", "nothing in common, nothing to cut"


def test_shared_prefix_stops_at_a_word_boundary():
    """Cutting mid-word would leave unreadable stubs like 'roup_A3'."""
    from cytolux.uncertainty_ui import shared_prefix
    assert shared_prefix(["donor_A1.fcs", "donor_A2.fcs"]) == "donor_"


def test_trim_front_keeps_the_end_that_identifies_the_row():
    from cytolux.uncertainty_ui import trim_front
    assert trim_front("plate_A/well_03.fcs", "plate_A/") == "well_03.fcs"
    long = "x" * 60 + "WELL_H12"
    assert trim_front(long, "").endswith("WELL_H12")
    assert trim_front(long, "").startswith("…")
    assert trim_front("short.fcs", "") == "short.fcs"


def test_the_table_shows_what_tells_the_samples_apart(app):
    """The point of all of the above: a plate's rows must not all read identically."""
    w = Workspace()
    w.add_pop("root", "Positive", thresh(0.90))
    for i in range(1, 5):
        attach(w, FakeSample("Plate 2 Day 7_Experiment_Group_A%d.fcs" % i,
                             smear(n=3000, seed=i)))
    dlg = FragilityDialog(w)
    dlg.reps.setValue(20)
    dlg.run()
    shown = {dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())}
    assert len(shown) == 4, "sample names were trimmed down to the same string: %r" % shown
    assert all("Experiment_Group" not in t for t in shown), "the common part survived"
    full = {dlg.table.item(r, 0).toolTip() for r in range(dlg.table.rowCount())}
    assert all(t.endswith(".fcs") for t in full), "the tooltip must keep the real name"
