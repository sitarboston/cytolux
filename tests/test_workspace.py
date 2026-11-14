"""Population tree and workspace persistence, exercised without any FCS files."""
import json

import pytest

from cytolux import transforms as tx
from cytolux.engine import Workspace, apply_template, template_dict

T = 262144.0


def rect(lo=0.2, hi=0.8):
    xf = tx.biex(T)
    return {"type": "rect", "dims": ["A", "B"], "xf": [dict(xf), dict(xf)],
            "min": [lo, lo], "max": [hi, hi]}


@pytest.fixture
def ws():
    w = Workspace()
    w.add_pop("root", "Cells", rect())
    w.add_pop("/Cells", "Single cells", rect())
    w.add_pop("/Cells/Single cells", "Live", rect())
    w.add_pop("/Cells/Single cells/Live", "CD3+", rect())
    return w


def test_paths_are_built_from_the_parent(ws):
    assert [p["path"] for p in ws.pops] == [
        "/Cells", "/Cells/Single cells", "/Cells/Single cells/Live",
        "/Cells/Single cells/Live/CD3+"]


def test_parents_always_precede_children(ws):
    seen = set()
    for p in ws.pops:
        if p["parent"] != "root":
            assert p["parent"] in seen, "%s came before its parent" % p["path"]
        seen.add(p["path"])


def test_a_sibling_inserts_directly_after_its_parents_subtree(ws):
    ws.add_pop("/Cells", "Debris", rect())
    paths = [p["path"] for p in ws.pops]
    assert paths.index("/Cells/Debris") > paths.index("/Cells/Single cells/Live/CD3+")


def test_duplicate_names_are_made_unique(ws):
    ws.add_pop("/Cells", "Single cells", rect())
    ws.add_pop("/Cells", "Single cells", rect())
    assert [p["path"] for p in ws.pops if p["parent"] == "/Cells"] == [
        "/Cells/Single cells", "/Cells/Single cells (2)", "/Cells/Single cells (3)"]


def test_children_lists_only_direct_children(ws):
    assert [p["path"] for p in ws.children("/Cells")] == ["/Cells/Single cells"]


def test_delete_takes_the_whole_subtree(ws):
    ws.delete_pop("/Cells/Single cells")
    assert [p["path"] for p in ws.pops] == ["/Cells"]


def test_delete_drops_overrides_and_stats_for_the_subtree(ws):
    ws.overrides["s1"] = {"/Cells/Single cells/Live": rect()}
    ws.stat_defs = [{"pop": "/Cells/Single cells/Live", "stat": "freq"},
                    {"pop": "/Cells", "stat": "freq"}]
    ws.delete_pop("/Cells/Single cells")
    assert ws.overrides["s1"] == {}
    assert [d["pop"] for d in ws.stat_defs] == ["/Cells"]


def test_rename_rewrites_every_descendant(ws):
    ws.rename_pop("/Cells/Single cells", "Singlets")
    assert [p["path"] for p in ws.pops] == [
        "/Cells", "/Cells/Singlets", "/Cells/Singlets/Live", "/Cells/Singlets/Live/CD3+"]
    assert all(p["parent"] in ("root", "/Cells", "/Cells/Singlets", "/Cells/Singlets/Live")
               for p in ws.pops)


def test_rename_rewrites_overrides_and_stat_defs(ws):
    ws.overrides["s1"] = {"/Cells/Single cells/Live": rect()}
    ws.stat_defs = [{"pop": "/Cells/Single cells/Live", "stat": "freq", "arg": None}]
    ws.rename_pop("/Cells/Single cells", "Singlets")
    assert "/Cells/Singlets/Live" in ws.overrides["s1"]
    assert ws.stat_defs[0]["pop"] == "/Cells/Singlets/Live"


def test_rename_does_not_collide_with_a_sibling(ws):
    ws.add_pop("/Cells", "Debris", rect())
    new = ws.rename_pop("/Cells/Debris", "Single cells")
    assert new == "/Cells/Single cells (2)"


def test_override_set_and_clear(ws):
    assert not ws.has_override("/Cells", "s1")
    ws.set_gate("/Cells", rect(0.1, 0.9), sname="s1")
    assert ws.has_override("/Cells", "s1")
    ws.clear_override("/Cells", "s1")
    assert not ws.has_override("/Cells", "s1")


def test_setting_a_gate_without_a_sample_changes_it_for_everyone(ws):
    ws.set_gate("/Cells", rect(0.15, 0.85))
    assert ws.pop("/Cells")["gate"]["min"][0] == pytest.approx(0.15)
    assert ws.overrides == {}


def test_version_advances_on_every_edit(ws):
    v = ws.version
    ws.add_pop("/Cells", "Debris", rect())
    assert ws.version > v


def test_save_load_round_trip(tmp_path, ws):
    ws.xforms["A"] = tx.biex(T)
    ws.labels["A"] = "CD3"
    ws.annot_cols = ["Donor"]
    ws.annotations = {"s1": {"Donor": "D1"}}
    p = tmp_path / "w.fgw"
    ws.save(str(p))
    back = Workspace.load(str(p))
    assert [q["path"] for q in back.pops] == [q["path"] for q in ws.pops]
    assert back.labels == ws.labels
    assert back.annot_cols == ws.annot_cols
    assert back.annotations == ws.annotations
    assert tx.same(back.xforms["A"], ws.xforms["A"])


def test_saved_file_is_tagged_cytolux(tmp_path, ws):
    p = tmp_path / "w.fgw"
    ws.save(str(p))
    assert json.load(open(p))["format"] == "cytolux-workspace"


def test_workspaces_written_by_the_old_build_still_open(tmp_path, ws):
    """Files saved before the rename carry format 'flowgate-workspace'. They must still load."""
    p = tmp_path / "old.fgw"
    ws.save(str(p))
    d = json.load(open(p))
    d["format"] = "flowgate-workspace"
    p.write_text(json.dumps(d))
    back = Workspace.load(str(p))
    assert [q["path"] for q in back.pops] == [q["path"] for q in ws.pops]


def test_missing_sample_files_are_dropped_not_fatal(tmp_path, ws):
    p = tmp_path / "w.fgw"
    ws.save(str(p))
    d = json.load(open(p))
    d["samples"] = ["/no/such/file.fcs"]
    p.write_text(json.dumps(d))
    back = Workspace.load(str(p))
    assert back.samples == []
    assert len(back.pops) == 4


def test_template_round_trip(ws):
    ws.xforms["A"] = tx.biex(T)
    d = template_dict(ws)
    fresh = Workspace()
    apply_template(fresh, d)
    assert [p["path"] for p in fresh.pops] == [p["path"] for p in ws.pops]


def test_template_is_tagged_cytolux(ws):
    assert template_dict(ws)["format"] == "cytolux-template"
