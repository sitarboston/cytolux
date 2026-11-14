"""Window-level behaviour: the engine being right is not enough if the UI never calls it."""
import numpy as np
import pytest

from cytolux import transforms as tx

pytest.importorskip("PySide6")
T = 262144.0


def rect(lo=0.2, hi=0.8):
    xf = tx.biex(T)
    return {"type": "rect", "dims": ["A", "B"], "xf": [dict(xf), dict(xf)],
            "min": [lo, lo], "max": [hi, hi]}


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def win(app):
    """A main window that cannot hang on the way out.

    closeEvent asks whether to save unsaved work, which is right in the application and
    fatal here: offscreen nobody can answer the prompt and the run blocks for ever at
    shutdown. Any test that edits anything would trip it.
    """
    from cytolux.app import MainWindow
    w = MainWindow()
    yield w
    w.dirty = False
    w.close()


def test_undo_and_redo_are_in_the_edit_menu(win):
    texts = []
    for top in win.menuBar().actions():
        if top.text().replace("&", "") == "Edit" and top.menu():
            texts = [a.text() for a in top.menu().actions()]
    assert any(t.startswith("Undo") for t in texts)
    assert any(t.startswith("Redo") for t in texts)


def test_undo_actions_are_disabled_with_nothing_to_undo(win):
    win._sync_undo_actions()
    assert not win.act_undo.isEnabled()
    assert not win.act_redo.isEnabled()


def test_the_menu_names_the_edit_you_will_undo(win):
    win.ws.add_pop("root", "Cells", rect())
    win.ws.changed(label="Draw rectangle gate")
    win._sync_undo_actions()
    assert win.act_undo.isEnabled()
    assert win.act_undo.text() == "Undo Draw rectangle gate"


def test_undo_through_the_window_actually_reverts(win):
    win.ws.add_pop("root", "Cells", rect())
    assert len(win.ws.pops) == 1
    win.do_undo()
    assert win.ws.pops == []
    assert win.act_redo.isEnabled()


def test_redo_through_the_window(win):
    win.ws.add_pop("root", "Cells", rect())
    win.do_undo()
    win.do_redo()
    assert [p["path"] for p in win.ws.pops] == ["/Cells"]


def test_undo_with_empty_history_says_so_rather_than_crashing(win):
    win.do_undo()
    win.do_redo()


def test_sample_filter_hides_non_matching_rows(win):
    from PySide6 import QtWidgets
    for name in ("A1 Control", "A2 Patient", "B1 Control", "B2 Patient"):
        win.sample_list.addItem(QtWidgets.QListWidgetItem(name))
    win.sample_filter.setText("patient")
    hidden = [win.sample_list.item(i).text()
              for i in range(win.sample_list.count()) if win.sample_list.item(i).isHidden()]
    assert sorted(hidden) == ["A1 Control", "B1 Control"]


def test_clearing_the_filter_shows_everything_again(win):
    from PySide6 import QtWidgets
    for name in ("A1 Control", "A2 Patient"):
        win.sample_list.addItem(QtWidgets.QListWidgetItem(name))
    win.sample_filter.setText("patient")
    win.sample_filter.setText("")
    assert not any(win.sample_list.item(i).isHidden()
                   for i in range(win.sample_list.count()))


def test_the_filter_is_case_insensitive(win):
    from PySide6 import QtWidgets
    win.sample_list.addItem(QtWidgets.QListWidgetItem("A1 CONTROL"))
    win.sample_filter.setText("control")
    assert not win.sample_list.item(0).isHidden()


def test_assistant_panel_opens_and_answers(win):
    win.show()
    win.show_assistant()
    win._assist_box.setText("how do I export to excel")
    html = win._assist_out.toHtml()
    assert "Excel" in html
    assert "File" in html



# --- the right-click route to a statistic, as in FlowJo -----------------------------

def _stat_submenu(win, path):
    """Build the right-click menu and hand back the Add-statistic submenu.

    The parent menu is given an owner. Without one, Python drops the last reference the
    moment this returns, Qt destroys the menu and every submenu under it, and the test
    is left holding a deleted C++ object.
    """
    from PySide6 import QtWidgets
    m = QtWidgets.QMenu(win)
    win._add_stat_submenu(m, path)
    return [a.menu() for a in m.actions() if a.menu()][0]


@pytest.fixture
def win_with_data(win):
    from cytolux.engine import EventData
    import numpy as np
    rng = np.random.default_rng(0)
    cols = {c: rng.normal(5e4, 1e4, 4000) for c in ("FSC-A", "CD4", "CD8")}
    from helpers import FakeSample
    s = FakeSample("one.fcs", cols)
    win.ws.samples.append(s)
    win.ws._events[s.name] = EventData(s, None)
    # gate on channels this sample actually carries, or the population is empty and
    # every intensity statistic comes back as nan
    xf = tx.biex(T)
    win.ws.add_pop("root", "Cells", {"type": "rect", "dims": ["CD4", "CD8"],
                                     "xf": [dict(xf), dict(xf)],
                                     "min": [None, None], "max": [None, None]})
    win.cur_sample = s
    win.sample_list.addItem(s.name)
    win.sample_list.setCurrentRow(0)
    return win, s


def test_the_submenu_offers_the_frequency_statistics_directly(win_with_data):
    w, _ = win_with_data
    sub = _stat_submenu(w, "/Cells")
    plain = [a.text() for a in sub.actions() if not a.menu() and not a.isSeparator()]
    assert "Count" in plain and "% of parent" in plain and "% of total" in plain


def test_the_submenu_offers_the_intensity_statistics_per_channel(win_with_data):
    w, _ = win_with_data
    sub = _stat_submenu(w, "/Cells")
    nested = {a.text(): a.menu() for a in sub.actions() if a.menu()}
    assert set(w.QUICK_STATS) <= set(nested)
    assert all(len(m.actions()) > 0 for m in nested.values())


def test_the_dialog_is_still_reachable(win_with_data):
    w, _ = win_with_data
    sub = _stat_submenu(w, "/Cells")
    assert any("More" in a.text() for a in sub.actions())


def test_the_channels_on_the_axes_come_first_and_in_bold(win_with_data):
    """The marker you are looking at is nearly always the one you want the MFI of."""
    w, _ = win_with_data
    chans = w._stat_channels()
    assert chans, "no channels offered"
    on_axis = [c for c in chans if c[2]]
    assert on_axis == chans[:len(on_axis)], "axis channels were not first"
    sub = _stat_submenu(w, "/Cells")
    med = {a.text(): a.menu() for a in sub.actions() if a.menu()}["Median"]
    assert med.actions()[0].font().bold()


def test_picking_one_adds_exactly_one_column(win_with_data):
    w, _ = win_with_data
    assert w.ws.stat_defs == []
    w._quick_stat("/Cells", "Median", "CD4")
    assert w.ws.stat_defs == [{"pop": "/Cells", "stat": "Median", "channel": "CD4"}]


def test_a_frequency_statistic_carries_no_channel(win_with_data):
    w, _ = win_with_data
    w._quick_stat("/Cells", "% of parent")
    assert w.ws.stat_defs[0]["channel"] is None


def test_adding_the_same_column_twice_is_refused(win_with_data):
    w, _ = win_with_data
    w._quick_stat("/Cells", "Median", "CD4")
    w._quick_stat("/Cells", "Median", "CD4")
    assert len(w.ws.stat_defs) == 1


def test_the_same_statistic_on_another_channel_is_a_new_column(win_with_data):
    w, _ = win_with_data
    w._quick_stat("/Cells", "Median", "CD4")
    w._quick_stat("/Cells", "Median", "CD8")
    assert len(w.ws.stat_defs) == 2


def test_all_events_gets_the_submenu_too(win_with_data):
    w, _ = win_with_data
    sub = _stat_submenu(w, "root")
    assert [a.text() for a in sub.actions() if not a.menu() and not a.isSeparator()]
    w._quick_stat("root", "Count")
    assert w.ws.stat_defs[0]["pop"] == "root"


def test_a_quick_statistic_computes(win_with_data):
    from cytolux.engine import compute_stat
    w, s = win_with_data
    w._quick_stat("/Cells", "Median", "CD4")
    v = compute_stat(w.ws, s, w.ws.stat_defs[0])
    assert np.isfinite(v) and v > 0
