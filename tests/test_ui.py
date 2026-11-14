"""Window-level behaviour: the engine being right is not enough if the UI never calls it."""
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
    from cytolux.app import MainWindow
    w = MainWindow()
    yield w
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
