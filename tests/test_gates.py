"""Gate geometry. These are the numbers every reported percentage rests on."""
import numpy as np
import pytest

from cytolux import transforms as tx
from cytolux.engine import gate_outline, points_in_polygon, reexpress_rect

T = 262144.0
SQUARE = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]


def test_polygon_square():
    x = np.array([0.5, 0.1, 0.9, -0.5, 1.5, 0.5])
    y = np.array([0.5, 0.1, 0.9, 0.5, 0.5, -0.5])
    got = points_in_polygon(x, y, SQUARE)
    assert list(got) == [True, True, True, False, False, False]


def test_polygon_is_even_odd_for_concave_shapes():
    """A C-shape: the notch must read as outside (the Gating-ML / FlowJo rule)."""
    c = [[0, 0], [3, 0], [3, 1], [1, 1], [1, 2], [3, 2], [3, 3], [0, 3]]
    x = np.array([0.5, 2.0, 2.0, 2.0])
    y = np.array([1.5, 0.5, 1.5, 2.5])
    assert list(points_in_polygon(x, y, c)) == [True, True, False, True]


def test_polygon_empty_input():
    got = points_in_polygon(np.array([]), np.array([]), SQUARE)
    assert got.shape == (0,)
    assert got.dtype == bool


def test_polygon_triangle_area_is_about_right():
    """Statistical check: a half-unit triangle should catch about half the uniform points."""
    rng = np.random.default_rng(0)
    x, y = rng.random(20000), rng.random(20000)
    tri = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
    frac = points_in_polygon(x, y, tri).mean()
    assert frac == pytest.approx(0.5, abs=0.02)


def test_reexpress_rect_is_lossless_round_trip():
    """Changing a rectangle's axis and changing it back must return the same gate."""
    src = [tx.biex(T), tx.biex(T)]
    dst = [tx.log(T), tx.log(T)]
    g = {"type": "rect", "dims": ["A", "B"], "xf": [dict(src[0]), dict(src[1])],
         "min": [0.3, 0.4], "max": [0.8, 0.9]}
    there = reexpress_rect(g, dst)
    back = reexpress_rect(there, src)
    assert back["min"][0] == pytest.approx(g["min"][0], rel=1e-6)
    assert back["min"][1] == pytest.approx(g["min"][1], rel=1e-6)
    assert back["max"][0] == pytest.approx(g["max"][0], rel=1e-6)
    assert back["max"][1] == pytest.approx(g["max"][1], rel=1e-6)


def test_reexpress_rect_keeps_the_same_raw_boundary():
    """The gate must sit on the same events, whatever axis it is drawn on."""
    src = [tx.biex(T), tx.biex(T)]
    dst = [tx.linear(T), tx.linear(T)]
    g = {"type": "rect", "dims": ["A", "B"], "xf": [dict(src[0]), dict(src[1])],
         "min": [0.3, 0.4], "max": [0.8, 0.9]}
    raw_lo = float(tx.inverse(src[0], g["min"][0]))
    g2 = reexpress_rect(g, dst)
    assert float(tx.inverse(dst[0], g2["min"][0])) == pytest.approx(raw_lo, rel=1e-6)


def test_reexpress_rect_does_not_mutate_the_original():
    src = [tx.biex(T), tx.biex(T)]
    g = {"type": "rect", "dims": ["A", "B"], "xf": [dict(src[0]), dict(src[1])],
         "min": [0.3, 0.4], "max": [0.8, 0.9]}
    before = (list(g["min"]), list(g["max"]), g["xf"][0]["kind"])
    reexpress_rect(g, [tx.log(T), tx.log(T)])
    assert (list(g["min"]), list(g["max"]), g["xf"][0]["kind"]) == before


def test_reexpress_rect_handles_open_edges():
    """None means 'no bound on this side' and must stay None."""
    src = [tx.biex(T), tx.biex(T)]
    g = {"type": "rect", "dims": ["A", "B"], "xf": [dict(src[0]), dict(src[1])],
         "min": [0.3, None], "max": [None, 0.9]}
    g2 = reexpress_rect(g, [tx.log(T), tx.log(T)])
    assert g2["min"][1] is None
    assert g2["max"][0] is None


@pytest.mark.parametrize("gate", [
    {"type": "rect", "dims": ["A", "B"], "min": [0.2, 0.2], "max": [0.8, 0.8]},
    {"type": "poly", "dims": ["A", "B"], "vertices": [[0.2, 0.2], [0.8, 0.3], [0.5, 0.9]]},
    {"type": "ellipse", "dims": ["A", "B"], "center": [0.5, 0.5], "axes": [0.2, 0.1], "angle": 30.0},
], ids=["rect", "poly", "ellipse"])
def test_gate_outline_is_a_closed_finite_loop(gate):
    xf = tx.biex(T)
    gate = dict(gate, xf=[dict(xf), dict(xf)])
    pts = gate_outline(gate, xf, xf)
    assert pts.ndim == 2 and pts.shape[1] == 2
    assert len(pts) > 4
    assert np.all(np.isfinite(pts))
    assert pts[0] == pytest.approx(pts[-1], abs=1e-6)


def test_gate_outline_swap_mirrors_the_axes():
    xf = tx.biex(T)
    g = {"type": "rect", "dims": ["A", "B"], "xf": [dict(xf), dict(xf)],
         "min": [0.2, 0.4], "max": [0.8, 0.9]}
    a = gate_outline(g, xf, xf, swap=False)
    b = gate_outline(g, xf, xf, swap=True)
    assert np.allclose(a[:, 0], b[:, 1])
    assert np.allclose(a[:, 1], b[:, 0])


def test_gate_outline_one_dimensional_rect_has_no_outline():
    xf = tx.biex(T)
    g = {"type": "rect", "dims": ["A"], "xf": [dict(xf)], "min": [0.2], "max": [0.8]}
    assert gate_outline(g, xf, xf) is None
