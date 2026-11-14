"""Quadrant crosshairs.

Quadrants are not one object anywhere: not in Cytolux's file, not in FlowJo's. They are
four ordinary rectangles that happen to share a corner. Everything here follows from
that. They have to be recognised after the fact, so a crosshair works on gates imported
from a FlowJo workspace and not only on ones drawn today; and they have to move as one,
or the four corners drift apart and the partition stops being a partition.
"""
import numpy as np
import pytest

from cytolux import transforms as tx
from cytolux.engine import (Workspace, find_quads, quad_from_center, quad_signs)

from helpers import FakeSample, attach, smear

T = 262144.0
LIN = tx.linear(T)
XF = [dict(LIN), dict(LIN)]


def q(sx, sy, cx=0.5, cy=0.5, dims=("A", "B")):
    return quad_from_center(dims, XF, cx, cy, sx, sy)


# --- reading a rectangle ------------------------------------------------------------

@pytest.mark.parametrize("sx,sy", [("+", "+"), ("+", "-"), ("-", "+"), ("-", "-")])
def test_a_quadrant_reports_its_own_corner_and_signs(sx, sy):
    signs, corner = quad_signs(q(sx, sy, 0.3, 0.7))
    assert signs == (sx, sy)
    assert corner == pytest.approx((0.3, 0.7))


def test_a_closed_rectangle_is_not_a_quadrant():
    g = {"type": "rect", "dims": ["A", "B"], "xf": XF, "min": [0.2, 0.2], "max": [0.8, 0.8]}
    assert quad_signs(g) is None


def test_an_unbounded_rectangle_is_not_a_quadrant():
    g = {"type": "rect", "dims": ["A", "B"], "xf": XF, "min": [None, 0.2], "max": [None, None]}
    assert quad_signs(g) is None


def test_a_polygon_or_a_histogram_gate_is_not_a_quadrant():
    assert quad_signs({"type": "poly", "dims": ["A", "B"], "xf": XF, "vertices": []}) is None
    assert quad_signs({"type": "rect", "dims": ["A"], "xf": XF[:1],
                       "min": [0.5], "max": [None]}) is None


def test_quad_from_center_opens_the_right_two_sides():
    g = q("+", "-", 0.4, 0.6)
    assert g["min"] == [0.4, None]
    assert g["max"] == [None, 0.6]
    assert g["dims"] == ["A", "B"]


# --- finding families ---------------------------------------------------------------

def family(cx=0.5, cy=0.5, parent="root", dims=("A", "B")):
    return [{"path": "/%s%s" % s, "parent": parent, "gate": q(s[0], s[1], cx, cy, dims)}
            for s in (("-", "+"), ("+", "+"), ("+", "-"), ("-", "-"))]


def test_four_rectangles_sharing_a_corner_are_found():
    pops = family(0.3, 0.7)
    found = find_quads(pops, lambda p: p["gate"])
    assert len(found) == 1
    (cx, cy), members = found[0]
    assert (cx, cy) == pytest.approx((0.3, 0.7))
    assert set(members) == {("-", "+"), ("+", "+"), ("+", "-"), ("-", "-")}


def test_three_quadrants_are_not_a_family():
    assert find_quads(family()[:3], lambda p: p["gate"]) == []


def test_quadrants_at_different_corners_are_not_a_family():
    pops = family(0.3, 0.7)
    pops[0]["gate"] = q("-", "+", 0.9, 0.1)
    assert find_quads(pops, lambda p: p["gate"]) == []


def test_two_of_the_same_sign_are_not_a_family():
    pops = family()
    pops[0]["gate"] = q("+", "+")
    assert find_quads(pops, lambda p: p["gate"]) == []


def test_quadrants_under_different_parents_are_not_one_family():
    pops = family(parent="/P1")[:2] + family(parent="/P2")[2:]
    for i, p in enumerate(pops):
        p["path"] = "/p%d" % i
    assert find_quads(pops, lambda p: p["gate"]) == []


def test_quadrants_on_different_axes_are_not_one_family():
    pops = family()[:2] + family(dims=("C", "D"))[2:]
    for i, p in enumerate(pops):
        p["path"] = "/p%d" % i
    assert find_quads(pops, lambda p: p["gate"]) == []


def test_two_separate_families_are_both_found():
    pops = family(0.2, 0.2, parent="/P1") + family(0.8, 0.8, parent="/P2")
    for i, p in enumerate(pops):
        p["path"] = "/p%d" % i
    assert len(find_quads(pops, lambda p: p["gate"])) == 2


def test_ordinary_gates_alongside_a_family_do_not_disturb_it():
    pops = family() + [{"path": "/other", "parent": "root",
                        "gate": {"type": "rect", "dims": ["A", "B"], "xf": XF,
                                 "min": [0.1, 0.1], "max": [0.4, 0.4]}}]
    assert len(find_quads(pops, lambda p: p["gate"])) == 1


# --- moving one ----------------------------------------------------------------------

@pytest.fixture
def quad_ws():
    ws = Workspace()
    for sx, sy in (("-", "+"), ("+", "+"), ("+", "-"), ("-", "-")):
        ws.add_pop("root", "Q%s%s" % (sx, sy), q(sx, sy, 0.5, 0.5))
    attach(ws, FakeSample("q.fcs", smear(n=20000, seed=3)))
    ws.clear_undo()
    return ws


def counts(ws):
    s = ws.samples[0]
    st = ws.stats(s)
    return {p["path"]: st[p["path"]][0] for p in ws.pops}


def test_the_four_quadrants_partition_the_parent(quad_ws):
    c = counts(quad_ws)
    assert sum(c.values()) == quad_ws.stats(quad_ws.samples[0])["root"][0]


def test_moving_the_crosshair_moves_all_four(quad_ws):
    before = counts(quad_ws)
    (_, _), members = quad_ws.quads()[0]
    quad_ws.move_quad(members, 0.25, 0.75)
    after = counts(quad_ws)
    assert all(before[p] != after[p] for p in before), "a quadrant was left behind"


def test_moving_the_crosshair_keeps_the_partition_complete(quad_ws):
    total = quad_ws.stats(quad_ws.samples[0])["root"][0]
    (_, _), members = quad_ws.quads()[0]
    for cx, cy in ((0.25, 0.75), (0.9, 0.1), (0.5, 0.5)):
        quad_ws.move_quad(members, cx, cy)
        assert sum(counts(quad_ws).values()) == total, "events were lost or double counted"


def test_one_drag_is_one_undo(quad_ws):
    before = counts(quad_ws)
    (_, _), members = quad_ws.quads()[0]
    n = len(quad_ws._undo)
    quad_ws.move_quad(members, 0.3, 0.3)
    assert len(quad_ws._undo) == n + 1, "four gates moved, four presses of Ctrl+Z to undo"
    assert quad_ws.undo() == "move quadrant"
    assert counts(quad_ws) == before


def test_moving_it_for_one_sample_only(quad_ws):
    other = attach(quad_ws, FakeSample("q2.fcs", smear(n=20000, seed=4)))
    s = quad_ws.samples[0]
    before_other = {p["path"]: quad_ws.stats(other)[p["path"]][0] for p in quad_ws.pops}
    (_, _), members = quad_ws.quads()[0]
    quad_ws.move_quad(members, 0.2, 0.8, sname=s.name)
    assert all(quad_ws.has_override(p, s.name) for p in members.values())
    assert {p["path"]: quad_ws.stats(other)[p["path"]][0]
            for p in quad_ws.pops} == before_other, "the other sample moved too"


def test_the_family_is_still_found_after_being_moved(quad_ws):
    (_, _), members = quad_ws.quads()[0]
    quad_ws.move_quad(members, 0.33, 0.66)
    found = quad_ws.quads()
    assert len(found) == 1
    assert found[0][0] == pytest.approx((0.33, 0.66))


# --- the corner label ----------------------------------------------------------------

def test_a_flowjo_quadrant_name_is_shortened_to_its_corner_label():
    from cytolux.plot import _quad_name
    long = "/L/live/Q2: CD69-Brilliant Violet 605-A+ , CD25-Brilliant Violet 421-A+"
    assert _quad_name(long) == "Q2"
    assert _quad_name("/L/CD4+ CD8-") == "CD4+ CD8-"
    assert len(_quad_name("/L/" + "x" * 40)) <= 18
