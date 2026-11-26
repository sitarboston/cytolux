"""Gate-perturbation uncertainty.

The claim this feature makes is strong: that it can tell a frequency you may quote from
one that is an artifact of where a line landed. These tests hold it to that. The two
that matter most are the pair near the bottom, where the same statistic is measured on
a population sitting in open space and on one whose boundary runs through a continuum,
and the intervals have to come back different by a wide margin.
"""
import numpy as np
import pytest

from cytolux.engine import Workspace
from cytolux.uncertainty import (DEFAULT_SIGMA, PopUncertainty, Spread, fragility_report,
                                 gate_uncertainty, perturb_gate)

from helpers import (HIGH, LIN, LOW, T, TIGHT, FakeSample, attach, islands, rect,
                     smear, thresh)


# Both fixtures report about ten percent positive. The gates differ only in where the
# threshold sits, because that is what the two datasets force; the statistic, the gate
# shape and the number of events are the same. Anything left over in the intervals is
# the data.

@pytest.fixture
def island_ws():
    ws = Workspace()
    ws.add_pop("root", "High", thresh(0.50))          # the gap between the two clusters
    attach(ws, FakeSample("islands.fcs", islands()))
    return ws


@pytest.fixture
def smear_ws():
    ws = Workspace()
    ws.add_pop("root", "Positive", thresh(0.90))      # the top tenth of a continuum
    attach(ws, FakeSample("smear.fcs", smear()))
    return ws


def test_the_two_fixtures_report_the_same_frequency(island_ws, smear_ws):
    """The premise of the comparison below, asserted rather than assumed."""
    a = island_ws.stats(island_ws.samples[0])["/High"][1]
    b = smear_ws.stats(smear_ws.samples[0])["/Positive"][1]
    assert a == pytest.approx(10.0, abs=0.5)
    assert b == pytest.approx(10.0, abs=0.5)


# --- perturbing one gate ------------------------------------------------------------

def test_perturb_moves_a_rectangle_and_leaves_the_original_alone():
    g = rect(0.3, 0.7)
    before = (list(g["min"]), list(g["max"]))
    out = perturb_gate(g, np.random.default_rng(0), 0.01)
    assert (list(g["min"]), list(g["max"])) == before, "the input gate was mutated"
    assert out["min"] != g["min"] and out["max"] != g["max"]
    assert out["dims"] == g["dims"]


def test_perturb_keeps_an_open_sided_rectangle_open():
    """A one-sided gate has no second edge to move, and must not grow one."""
    g = rect(0.3, 0.7)
    g["min"] = [0.3, None]
    g["max"] = [None, 0.7]
    out = perturb_gate(g, np.random.default_rng(0), 0.01)
    assert out["min"][1] is None
    assert out["max"][0] is None
    assert out["min"][0] != 0.3


def test_perturb_displaces_a_boundary_by_about_sigma():
    rng = np.random.default_rng(0)
    g = rect(0.3, 0.7)
    moved = [perturb_gate(g, rng, 0.02)["min"][0] - 0.3 for _ in range(4000)]
    assert np.mean(moved) == pytest.approx(0.0, abs=0.002)
    assert np.std(moved) == pytest.approx(0.02, rel=0.08)


def test_perturb_of_zero_sigma_changes_nothing():
    g = rect(0.3, 0.7)
    out = perturb_gate(g, np.random.default_rng(0), 0.0)
    assert out["min"] == g["min"] and out["max"] == g["max"]


def test_perturb_polygon_keeps_its_vertex_count_and_moves_the_whole_shape():
    v = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    g = {"type": "poly", "dims": ["A", "B"], "xf": [dict(LIN), dict(LIN)], "vertices": v}
    out = perturb_gate(g, np.random.default_rng(0), 0.01)
    assert g["vertices"] == v, "the input gate was mutated"
    assert len(out["vertices"]) == 4
    moved = np.asarray(out["vertices"]) - np.asarray(v)
    assert np.abs(moved).max() < 0.1
    assert np.abs(moved).min() > 0, "no vertex moved at all"


def test_perturb_polygon_scales_a_small_gate_no_harder_than_a_large_one():
    """The dilation is per unit of boundary displacement, not per unit of size, or a
    tight gate would be shaken to pieces while a loose one barely stirred."""
    def spread(scale):
        v = (np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]]) * scale + 0.5)
        g = {"type": "poly", "dims": ["A", "B"], "xf": [dict(LIN), dict(LIN)],
             "vertices": v.tolist()}
        rng = np.random.default_rng(3)
        radii = []
        for _ in range(600):
            w = np.asarray(perturb_gate(g, rng, 0.01)["vertices"])
            radii.append(np.hypot(*(w - w.mean(axis=0)).T).mean())
        return np.std(radii)
    small, large = spread(0.02), spread(0.40)
    assert small == pytest.approx(large, rel=0.25)


def test_perturb_ellipse_never_produces_a_negative_radius():
    g = {"type": "ellipse", "dims": ["A", "B"], "xf": [dict(LIN), dict(LIN)],
         "center": [0.5, 0.5], "axes": [0.001, 0.001], "angle": 20.0}
    rng = np.random.default_rng(0)
    for _ in range(2000):
        out = perturb_gate(g, rng, 0.05)
        assert out["axes"][0] > 0 and out["axes"][1] > 0
    assert out["angle"] == 20.0


def test_perturb_rejects_a_gate_type_it_does_not_know():
    with pytest.raises(ValueError):
        perturb_gate({"type": "quadrant", "dims": ["A"], "xf": [dict(LIN)]},
                     np.random.default_rng(0), 0.01)


# --- the reported number is still the reported number -------------------------------

def test_the_value_is_the_unperturbed_statistic(island_ws):
    u = gate_uncertainty(island_ws, island_ws.samples[0], n=30)
    s = island_ws.stats(island_ws.samples[0])
    for path, pu in u.items():
        assert pu.count.value == pytest.approx(s[path][0])
        assert pu.parent_pct.value == pytest.approx(s[path][1])
        assert pu.total_pct.value == pytest.approx(s[path][2])


def test_the_workspace_is_untouched(island_ws):
    s = island_ws.samples[0]
    pops_before = [dict(p) for p in island_ws.pops]
    stats_before = island_ws.stats(s)
    version_before = island_ws.version
    gate_uncertainty(island_ws, s, n=30)
    assert island_ws.pops == pops_before
    assert island_ws.overrides == {}
    assert island_ws.version == version_before
    assert island_ws.stats(s) == stats_before


def test_root_has_no_uncertainty(island_ws):
    u = gate_uncertainty(island_ws, island_ws.samples[0], n=20)
    r = u["root"]
    assert r.count.lo == r.count.hi == r.count.value
    assert r.parent_pct.value == 100.0 and r.parent_pct.half_width == 0.0


def test_every_population_is_reported(island_ws):
    island_ws.add_pop("/High", "Child", rect(0.0, 2.0))
    u = gate_uncertainty(island_ws, island_ws.samples[0], n=20)
    assert set(u) == {"root", "/High", "/High/Child"}
    assert all(isinstance(v, PopUncertainty) for v in u.values())


def test_a_workspace_with_no_gates_still_answers():
    ws = Workspace()
    attach(ws, FakeSample("bare.fcs", islands(n=500)))
    u = gate_uncertainty(ws, ws.samples[0], n=5)
    assert set(u) == {"root"}


# --- reproducibility ----------------------------------------------------------------

def test_the_same_seed_gives_the_same_interval(smear_ws):
    s = smear_ws.samples[0]
    a = gate_uncertainty(smear_ws, s, n=40, seed=7)["/Positive"].parent_pct
    b = gate_uncertainty(smear_ws, s, n=40, seed=7)["/Positive"].parent_pct
    assert (a.lo, a.hi, a.median) == (b.lo, b.hi, b.median)


def test_a_different_seed_gives_a_different_interval(smear_ws):
    s = smear_ws.samples[0]
    a = gate_uncertainty(smear_ws, s, n=40, seed=7)["/Positive"].parent_pct
    b = gate_uncertainty(smear_ws, s, n=40, seed=8)["/Positive"].parent_pct
    assert (a.lo, a.hi) != (b.lo, b.hi)
    assert a.lo == pytest.approx(b.lo, abs=1.0), "two seeds should still broadly agree"


def test_one_replicate_is_refused(island_ws):
    with pytest.raises(ValueError):
        gate_uncertainty(island_ws, island_ws.samples[0], n=1)


# --- the core claim -----------------------------------------------------------------

def test_a_gate_in_empty_space_is_firm(island_ws):
    """The boundary sits in the gap between two clusters. Moving it changes nothing."""
    pu = gate_uncertainty(island_ws, island_ws.samples[0], n=200)["/High"]
    assert pu.parent_pct.half_width < 0.1
    assert pu.grade == "firm"


def test_a_gate_through_a_continuum_is_not_firm(smear_ws):
    """The same gate, on data with no gap to hide the boundary in."""
    pu = gate_uncertainty(smear_ws, smear_ws.samples[0], n=200)["/Positive"]
    assert pu.parent_pct.half_width > 1.0
    assert pu.grade in ("soft", "fragile")


def test_the_continuum_gate_is_far_wider_than_the_empty_space_gate(island_ws, smear_ws):
    """The whole feature in one assertion: the same statistic, the same gate shape, the
    same ten percent on the screen, and the uncertainty differs by more than an order of
    magnitude because of what the boundary is standing on."""
    firm = gate_uncertainty(island_ws, island_ws.samples[0], n=200)["/High"]
    soft = gate_uncertainty(smear_ws, smear_ws.samples[0], n=200)["/Positive"]
    assert soft.parent_pct.half_width > 10 * firm.parent_pct.half_width


def test_a_wider_hand_gives_a_wider_interval(smear_ws):
    s = smear_ws.samples[0]
    tight = gate_uncertainty(smear_ws, s, n=150, sigma=0.005)["/Positive"]
    loose = gate_uncertainty(smear_ws, s, n=150, sigma=0.040)["/Positive"]
    assert loose.parent_pct.half_width > 3 * tight.parent_pct.half_width


def test_a_lower_confidence_level_gives_a_narrower_interval(smear_ws):
    s = smear_ws.samples[0]
    wide = gate_uncertainty(smear_ws, s, n=300, level=95.0)["/Positive"]
    narrow = gate_uncertainty(smear_ws, s, n=300, level=50.0)["/Positive"]
    assert narrow.parent_pct.half_width < wide.parent_pct.half_width
    assert narrow.parent_pct.lo > wide.parent_pct.lo


def test_the_interval_brackets_the_reported_value(smear_ws):
    p = gate_uncertainty(smear_ws, smear_ws.samples[0], n=300)["/Positive"].parent_pct
    assert p.lo <= p.value <= p.hi


# --- propagation down the tree ------------------------------------------------------

def test_a_child_carries_its_parent_s_uncertainty(smear_ws):
    """A child gate loose enough to keep everything its parent gives it must inherit
    the parent's spread exactly, as a fraction of the file. That is the propagation
    working: the child's own boundary contributes nothing, the parent's is all of it."""
    smear_ws.add_pop("/Positive", "Everything", rect(-5.0, 5.0))
    u = gate_uncertainty(smear_ws, smear_ws.samples[0], n=100)
    parent, child = u["/Positive"].total_pct, u["/Positive/Everything"].total_pct
    assert child.lo == pytest.approx(parent.lo)
    assert child.hi == pytest.approx(parent.hi)
    assert u["/Positive/Everything"].parent_pct.half_width == pytest.approx(0.0)


def test_a_child_is_never_bigger_than_its_parent_in_any_replicate(smear_ws):
    """If this fails the hierarchy has come apart somewhere in the rebuild."""
    smear_ws.add_pop("/Positive", "Inner", rect(0.5, 0.9))
    u = gate_uncertainty(smear_ws, smear_ws.samples[0], n=100)
    assert u["/Positive/Inner"].parent_pct.hi <= 100.0 + 1e-9
    assert u["/Positive/Inner"].total_pct.hi <= u["/Positive"].total_pct.hi + 1e-9


def test_deeper_gates_accumulate_spread():
    """Independent slop at four boundaries stacks up, measured relative to each
    population's own size. Four thresholds on a continuum, each keeping a third or so,
    so every level has a real boundary of its own to be uncertain about."""
    ws = Workspace()
    attach(ws, FakeSample("chain.fcs", smear(n=40000, seed=11)))
    ws.add_pop("root", "P1", thresh(0.70, "A"))
    ws.add_pop("/P1", "P2", thresh(0.70, "B"))
    ws.add_pop("/P1/P2", "P3", thresh(0.80, "A"))
    ws.add_pop("/P1/P2/P3", "P4", thresh(0.80, "B"))
    u = gate_uncertainty(ws, ws.samples[0], n=300)
    rel = [u[p].total_pct.relative for p in ("/P1", "/P1/P2", "/P1/P2/P3", "/P1/P2/P3/P4")]
    assert rel == sorted(rel), "relative spread shrank with depth: %r" % rel
    assert rel[-1] > 2 * rel[0]


def test_absolute_spread_may_shrink_with_depth_even_so():
    """Worth pinning down, because it looks wrong the first time you see it. A child is
    smaller than its parent, so its interval in percentage points can be narrower while
    the number is in fact less certain. Relative width is the figure to read."""
    ws = Workspace()
    attach(ws, FakeSample("narrow.fcs", smear(n=20000, seed=12)))
    ws.add_pop("root", "Parent", thresh(0.90, "A"))
    ws.add_pop("/Parent", "Child", thresh(0.90, "B"))
    u = gate_uncertainty(ws, ws.samples[0], n=300)
    parent, child = u["/Parent"].total_pct, u["/Parent/Child"].total_pct
    assert child.value < parent.value
    assert child.half_width < parent.half_width
    assert child.relative > parent.relative


# --- a channel the file does not have ----------------------------------------------

def test_a_missing_channel_is_reported_as_unknown_not_as_a_crash():
    ws = Workspace()
    ws.add_pop("root", "Ghost", rect(0.3, 0.7, dims=("Nope", "AlsoNope")))
    ws.add_pop("/Ghost", "Below", rect(0.3, 0.7))
    attach(ws, FakeSample("plain.fcs", islands(n=2000)))
    u = gate_uncertainty(ws, ws.samples[0], n=10)
    assert u["/Ghost"].count.value == 0
    assert u["/Ghost"].grade == "unknown", \
        "a gate that was never evaluated must not grade firm on its stable zero"
    assert u["/Ghost/Below"].grade == "unknown"
    assert np.isnan(u["/Ghost"].parent_pct.value)


def test_a_population_that_is_genuinely_empty_is_not_called_unknown():
    """The distinction the test above depends on. A real gate that happens to catch
    nothing is a measurement, and a confident one; a gate that could not be evaluated
    is not a measurement at all. Both show a count of zero."""
    ws = Workspace()
    ws.add_pop("root", "Empty", thresh(5.0))      # far above any event, but on a real channel
    attach(ws, FakeSample("plain.fcs", islands(n=2000)))
    pu = gate_uncertainty(ws, ws.samples[0], n=20)["/Empty"]
    assert pu.count.value == 0
    assert pu.parent_pct.value == 0.0
    assert pu.grade == "firm"


# --- the Spread value object --------------------------------------------------------

def test_spread_arithmetic():
    s = Spread(value=10.0, lo=9.0, hi=13.0, median=10.5)
    assert s.half_width == pytest.approx(2.0)
    assert s.relative == pytest.approx(0.2)
    assert s.bias == pytest.approx(0.5)
    assert s.text() == "10.00 [9.00, 13.00]"
    assert s.text(1) == "10.0 [9.0, 13.0]"


def test_spread_relative_is_undefined_at_zero():
    assert np.isnan(Spread(0.0, 0.0, 0.4, 0.1).relative)


@pytest.mark.parametrize("value,lo,hi,expected", [
    (50.0, 49.9, 50.1, "firm"),        # half width under half a point
    (50.0, 49.0, 51.0, "firm"),        # 2% of the value
    (2.0, 1.78, 2.22, "soft"),         # 11% of the value, small though the width is
    (2.0, 1.40, 2.60, "fragile"),      # 30% of the value
    (40.0, 33.0, 47.0, "fragile"),     # seven points wide, whatever the value
    (0.10, 0.02, 0.18, "fragile"),     # a rare population over a nine-fold range
    (0.0, 0.0, 0.3, "soft"),           # reported as nothing, but the gate could admit 0.3
    (0.0, 0.0, 0.02, "firm"),          # nothing there, and nothing that could move it
])
def test_grades(value, lo, hi, expected):
    assert Spread(value, lo, hi, 0.5 * (lo + hi)).grade == expected


def test_grade_of_an_immeasurable_number_is_unknown():
    nan = float("nan")
    assert Spread(nan, nan, nan, nan).grade == "unknown"


# --- the workspace-wide report ------------------------------------------------------

def test_fragility_report_shape(smear_ws):
    smear_ws.add_pop("/Positive", "Inner", rect(0.5, 0.9))
    attach(smear_ws, FakeSample("smear2.fcs", smear(seed=5)))
    df = fragility_report(smear_ws, n=30)
    assert len(df) == 2 * 2
    assert set(df["Sample"]) == {"smear.fcs", "smear2.fcs"}


def test_fragility_report_puts_the_shakiest_gate_first(island_ws):
    """A workspace with one gate in open space and one on a continuum. The report has
    to surface the second without being told which is which."""
    island_ws.add_pop("root", "Dubious", thresh(LOW))        # straight through a cluster
    df = fragility_report(island_ws, n=200)
    assert df.iloc[0]["Population"] == "Dubious"
    assert df.iloc[-1]["Population"] == "High"
    assert df.iloc[0]["Half width"] > df.iloc[-1]["Half width"]


def test_fragility_report_excludes_all_events_unless_asked(smear_ws):
    assert "All events" not in set(fragility_report(smear_ws, n=10)["Population"])
    with_root = fragility_report(smear_ws, n=10, include_root=True)
    assert "All events" in set(with_root["Population"])


def test_fragility_report_gives_each_sample_its_own_stream(smear_ws):
    """Adding a sample must not change the answer for the samples already there, or no
    number in a report would be stable while the experiment was still being loaded."""
    first = fragility_report(smear_ws, n=40)
    attach(smear_ws, FakeSample("smear2.fcs", smear(seed=5)))
    second = fragility_report(smear_ws, n=40)
    was = first[first["Sample"] == "smear.fcs"].iloc[0]
    now = second[second["Sample"] == "smear.fcs"].iloc[0]
    assert was["Low"] == pytest.approx(now["Low"])
    assert was["High"] == pytest.approx(now["High"])


def test_fragility_report_of_an_empty_workspace_is_an_empty_frame():
    ws = Workspace()
    attach(ws, FakeSample("bare.fcs", islands(n=200)))
    assert len(fragility_report(ws, n=5)) == 0


def test_default_sigma_is_one_percent_of_the_axis():
    assert DEFAULT_SIGMA == 0.01


# --- telling a shaky gate apart from too few cells ----------------------------------

def test_counting_error_matches_the_binomial_standard_error():
    pu = PopUncertainty(path="/P", count=Spread(100.0, 0, 0, 0),
                        parent_pct=Spread(10.0, 0, 0, 0), total_pct=Spread(10.0, 0, 0, 0),
                        parent_n=1000, total_n=1000, level=95.0)
    expected = 100 * 1.959963985 * np.sqrt(0.1 * 0.9 / 1000)
    assert pu.counting_half_width == pytest.approx(expected, rel=1e-6)
    assert pu.counting_relative == pytest.approx(expected / 10.0, rel=1e-6)


def test_counting_error_shrinks_with_the_square_root_of_the_count():
    def hw(n):
        return PopUncertainty(path="/P", count=Spread(0.1 * n, 0, 0, 0),
                              parent_pct=Spread(10.0, 0, 0, 0),
                              total_pct=Spread(10.0, 0, 0, 0), parent_n=n).counting_half_width
    assert hw(1000) == pytest.approx(hw(100) / np.sqrt(10), rel=1e-6)


def test_counting_error_of_a_pure_population_is_zero():
    pu = PopUncertainty(path="/P", count=Spread(500.0, 0, 0, 0),
                        parent_pct=Spread(100.0, 0, 0, 0), total_pct=Spread(100.0, 0, 0, 0),
                        parent_n=500)
    assert pu.counting_half_width == pytest.approx(0.0)


def test_counting_error_is_undefined_without_a_parent():
    pu = PopUncertainty(path="/P", count=Spread(0.0, 0, 0, 0),
                        parent_pct=Spread(float("nan"), 0, 0, 0),
                        total_pct=Spread(float("nan"), 0, 0, 0), parent_n=0)
    assert np.isnan(pu.counting_half_width)
    assert pu.limited_by == "unknown"


def _pu(gate_hw, parent_n, pct):
    return PopUncertainty(
        path="/P", count=Spread(pct / 100.0 * parent_n, 0, 0, 0),
        parent_pct=Spread(pct, pct - gate_hw, pct + gate_hw, pct),
        total_pct=Spread(pct, pct - gate_hw, pct + gate_hw, pct), parent_n=parent_n)


def test_limited_by_names_the_gate_when_the_boundary_is_the_problem():
    """Plenty of events, boundary on a continuum: redrawing the gate is the fix."""
    pu = _pu(gate_hw=3.0, parent_n=200000, pct=10.0)
    assert pu.counting_half_width < 1.0
    assert pu.limited_by == "gate"


def test_limited_by_names_counting_when_the_population_is_too_rare():
    """A handful of events: the boundary is not what is wrong, the sample size is."""
    pu = _pu(gate_hw=0.05, parent_n=300, pct=10.0)
    assert pu.counting_half_width > 0.05
    assert pu.limited_by == "counting"


def test_a_perfectly_gated_rare_population_is_still_not_quotable():
    """The case that makes the combined grade necessary. A tight cluster of thirty
    cells, with the boundary sitting in open space well away from it: the gate is
    beyond reproach and the number is still worthless, because thirty is thirty."""
    ws = Workspace()
    attach(ws, FakeSample("rare.fcs", islands(n=20000, seed=4, frac_high=0.0015)))
    ws.add_pop("root", "Rare", thresh(0.50))
    pu = gate_uncertainty(ws, ws.samples[0], n=200)["/Rare"]
    assert pu.count.value == pytest.approx(30, abs=5)
    assert pu.gate_grade == "firm", "the boundary is in empty space"
    assert pu.limited_by == "counting"
    assert pu.grade == "fragile", "and yet the number cannot be quoted"


def test_a_rare_population_in_a_continuum_is_limited_by_the_gate(smear_ws):
    """The mirror case. The same handful of events, but the boundary is standing on
    the distribution rather than beside it, and now the gate is the larger problem."""
    smear_ws.add_pop("root", "Rare", thresh(0.9985))
    pu = gate_uncertainty(smear_ws, smear_ws.samples[0], n=200)["/Rare"]
    assert pu.count.value < 100
    assert pu.limited_by == "gate"
    assert pu.grade == "fragile"


def test_the_report_carries_both_kinds_of_doubt(smear_ws):
    df = fragility_report(smear_ws, n=30)
    assert list(df.columns) == ["Sample", "Population", "Grade", "Limited by", "Count",
                                "% of parent", "Low", "High", "Half width", "Relative",
                                "Gate half width", "Counting half width", "Bias", "Path"]
    assert list(df.columns).index("Grade") < list(df.columns).index("Count"), \
        "the verdict must be visible without scrolling"
    assert set(df["Limited by"]) <= {"gate", "counting", "unknown"}


def test_the_combined_interval_is_wider_than_either_part(smear_ws):
    pu = gate_uncertainty(smear_ws, smear_ws.samples[0], n=200)["/Positive"]
    comb = pu.combined
    assert comb.half_width > pu.parent_pct.half_width
    assert comb.half_width > pu.counting_half_width
    assert comb.half_width == pytest.approx(
        np.hypot(pu.parent_pct.half_width, pu.counting_half_width))
    assert comb.value == pu.parent_pct.value


def test_the_combined_interval_falls_back_when_one_part_is_undefined():
    pu = PopUncertainty(path="/P", count=Spread(10.0, 0, 0, 0),
                        parent_pct=Spread(5.0, 4.0, 6.0, 5.0),
                        total_pct=Spread(5.0, 4.0, 6.0, 5.0), parent_n=0)
    assert np.isnan(pu.counting_half_width)
    assert pu.combined_half_width == pytest.approx(1.0)


def test_fragility_report_reports_progress_and_can_be_stopped(smear_ws):
    attach(smear_ws, FakeSample("smear2.fcs", smear(seed=5)))
    attach(smear_ws, FakeSample("smear3.fcs", smear(seed=6)))
    seen = []

    def progress(done, total):
        seen.append((done, total))
        return done >= 2            # stop before the third sample

    df = fragility_report(smear_ws, n=10, progress=progress)
    assert seen == [(0, 3), (1, 3), (2, 3)]
    assert set(df["Sample"]) == {"smear.fcs", "smear2.fcs"}, "partial work was discarded"


def test_counting_error_is_undefined_when_the_frequency_is():
    """Guards the subtler half of the missing-channel case. A count of zero gives a
    binomial standard error of exactly zero, which is the most confident answer there
    is, and would have overridden the gate's own 'I could not measure this'."""
    pu = PopUncertainty(path="/P", count=Spread(0.0, 0, 0, 0),
                        parent_pct=Spread(float("nan"), float("nan"), float("nan"),
                                          float("nan")),
                        total_pct=Spread(float("nan"), 0, 0, 0), parent_n=5000)
    assert np.isnan(pu.counting_half_width)
    assert np.isnan(pu.combined_half_width)
    assert pu.grade == "unknown"


@pytest.mark.parametrize("value", [99.64, 0.3])
def test_the_combined_interval_stays_inside_zero_to_a_hundred(value):
    """A 99.64% singlet gate once showed "98.11 to 101.16": the quadrature half-width
    is symmetric, and nothing stopped it running past either end of a percentage."""
    pu = PopUncertainty(path="/P", count=Spread(100.0, 0, 0, 0),
                        parent_pct=Spread(value, value - 1.5, value + 1.5, value),
                        total_pct=Spread(value, value, value, value),
                        parent_n=2000, total_n=2000)
    c = pu.combined
    assert 0.0 <= c.lo <= c.value <= c.hi <= 100.0
    assert pu.combined_half_width > 1.0


def test_clamping_the_interval_does_not_shrink_the_reported_half_width():
    """The ± column and the exported "Half width" read combined_half_width, the
    uncertainty itself. The clamped interval is narrower, and reporting its width
    would make a number pressed against 100% look more certain than it is."""
    pu = PopUncertainty(path="/P", count=Spread(100.0, 0, 0, 0),
                        parent_pct=Spread(99.64, 98.0, 101.0, 99.64),
                        total_pct=Spread(99.64, 99.64, 99.64, 99.64),
                        parent_n=2000, total_n=2000)
    assert pu.combined.hi == 100.0
    assert pu.combined.half_width < pu.combined_half_width
