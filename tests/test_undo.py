"""Undo is the usability gap FlowJo never closed. It has to be exactly right."""
import pytest

from cytolux import transforms as tx
from cytolux.engine import Workspace

T = 262144.0


def rect(lo=0.2, hi=0.8):
    xf = tx.biex(T)
    return {"type": "rect", "dims": ["A", "B"], "xf": [dict(xf), dict(xf)],
            "min": [lo, lo], "max": [hi, hi]}


@pytest.fixture
def ws():
    w = Workspace()
    w.add_pop("root", "Cells", rect(), )
    w.add_pop("/Cells", "Single cells", rect())
    return w


def paths(w):
    return [p["path"] for p in w.pops]


def test_a_new_workspace_has_nothing_to_undo():
    w = Workspace()
    assert not w.can_undo and not w.can_redo
    assert w.undo() is None and w.redo() is None


def test_undo_removes_the_last_gate(ws):
    before = paths(ws)
    ws.add_pop("/Cells/Single cells", "Live", rect())
    assert len(paths(ws)) == 3
    ws.undo()
    assert paths(ws) == before


def test_redo_puts_it_back(ws):
    ws.add_pop("/Cells/Single cells", "Live", rect())
    after = paths(ws)
    ws.undo()
    ws.redo()
    assert paths(ws) == after


def test_undo_all_the_way_to_empty():
    w = Workspace()
    w.add_pop("root", "A", rect())
    w.add_pop("root", "B", rect())
    w.add_pop("root", "C", rect())
    while w.can_undo:
        w.undo()
    assert w.pops == []


def test_undo_restores_a_deleted_subtree(ws):
    ws.add_pop("/Cells/Single cells", "Live", rect())
    full = paths(ws)
    ws.delete_pop("/Cells")
    assert ws.pops == []
    ws.undo()
    assert paths(ws) == full


def test_undo_reverses_a_rename(ws):
    ws.rename_pop("/Cells/Single cells", "Singlets")
    assert "/Cells/Singlets" in paths(ws)
    ws.undo()
    assert "/Cells/Single cells" in paths(ws)


def test_undo_reverses_a_moved_gate(ws):
    ws.set_gate("/Cells", rect(0.05, 0.95))
    assert ws.pop("/Cells")["gate"]["min"][0] == pytest.approx(0.05)
    ws.undo()
    assert ws.pop("/Cells")["gate"]["min"][0] == pytest.approx(0.2)


def test_undo_reverses_a_per_sample_override(ws):
    ws.set_gate("/Cells", rect(0.1, 0.9), sname="s1")
    assert ws.has_override("/Cells", "s1")
    ws.undo()
    assert not ws.has_override("/Cells", "s1")


def test_a_new_edit_clears_the_redo_branch(ws):
    ws.add_pop("root", "A", rect())
    ws.undo()
    assert ws.can_redo
    ws.add_pop("root", "B", rect())
    assert not ws.can_redo, "editing after undo must drop the abandoned branch"


def test_labels_say_what_will_be_undone():
    w = Workspace()
    w.add_pop("root", "Cells", rect())
    w.changed(label="Draw rectangle gate")
    assert w.undo_label() == "Draw rectangle gate"
    assert w.undo() == "Draw rectangle gate"
    assert w.redo_label() == "Draw rectangle gate"


def test_undo_does_not_disturb_loaded_samples(ws):
    """Snapshots cover the analysis only: undo must never re-read an FCS file."""
    sentinel = ["sample-object"]
    ws.samples = sentinel
    ws.add_pop("root", "X", rect())
    ws.undo()
    assert ws.samples is sentinel


def test_version_advances_on_undo_so_the_view_repaints(ws):
    ws.add_pop("root", "X", rect())
    v = ws.version
    ws.undo()
    assert ws.version > v


def test_history_is_capped(ws):
    ws.UNDO_DEPTH = 5
    for i in range(20):
        ws.add_pop("root", "P%d" % i, rect())
    assert len(ws._undo) <= 5


def test_snapshots_are_deep_copies(ws):
    """A later mutation must not reach back into a stored snapshot."""
    ws.add_pop("root", "X", rect())
    ws.pop("/X")["gate"]["min"][0] = 0.99
    ws.undo()
    ws.redo()
    assert ws.pop("/X")["gate"]["min"][0] == pytest.approx(0.99)


def test_opening_a_file_starts_a_clean_history(tmp_path, ws):
    p = tmp_path / "w.fgw"
    ws.save(str(p))
    back = Workspace.load(str(p))
    assert not back.can_undo, "the file as opened is the baseline, not an edit to undo"
