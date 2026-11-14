"""Overlaid histograms.

Everything here is about one question: when two conditions are laid over each
other, does the picture say what the numbers say? A curve that looks shifted when
the medians are identical, or flat when they are not, is worse than no plot.
"""
import numpy as np
import pytest

from cytolux import overlay as ov
from cytolux import transforms as tx
from cytolux.engine import Workspace

from helpers import FakeSample, attach, thresh

T = 262144.0
LIN = tx.linear(T)


def pos(n, centre, spread=0.05, seed=0):
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(centre, spread, n), 0, 1) * T


@pytest.fixture
def ws():
    w = Workspace()
    for i, (name, centre) in enumerate([("low.fcs", 0.30), ("high.fcs", 0.60)]):
        cols = {"CD69": pos(6000, centre, seed=i), "FSC-A": pos(6000, 0.5, seed=9 + i)}
        attach(w, FakeSample(name, cols))
    return w


def pairs(ws):
    return [(s, "root") for s in ws.samples]


# --- the numbers under the curves ------------------------------------------


def test_a_shift_in_the_data_is_a_shift_in_the_curves(ws):
    a, b = ov.build(ws, pairs(ws), "CD69", xf=LIN)
    assert b.median > a.median
    assert float(b.x[np.argmax(b.y)]) > float(a.x[np.argmax(a.y)]), \
        "the medians moved but the peaks did not"


def test_the_median_is_reported_in_raw_units(ws):
    """A median in logicle units is not a number anyone can put in a paper."""
    a, _ = ov.build(ws, pairs(ws), "CD69", xf=tx.biex(T))
    raw = ws.events(ws.samples[0]).col("CD69")
    assert a.median == pytest.approx(float(np.median(raw)), rel=1e-9)
    assert a.median > 1000, "the median came back on the 0-1 display scale"


def test_every_curve_shares_one_transform(ws):
    """Curves drawn on different axes cannot be compared, which is the whole point."""
    ws.set_xform("CD69", tx.biex(T))
    out = ov.build(ws, pairs(ws), "CD69")
    assert len({len(s.x) for s in out}) == 1
    peaks = [float(s.x[np.argmax(s.y)]) for s in out]
    assert peaks[1] > peaks[0]


def test_a_sample_without_the_channel_is_skipped_not_drawn_empty(ws):
    other = attach(ws, FakeSample("odd.fcs", {"FSC-A": pos(500, 0.5)}))
    out = ov.build(ws, [(s, "root") for s in ws.samples], "CD69", xf=LIN)
    assert len(out) == 2
    assert all("odd" not in s.label for s in out)


def test_counts_follow_the_gate(ws):
    ws.add_pop("root", "CD69+", thresh(0.45, dim="CD69"))
    s = ws.samples[1]
    out = ov.build(ws, [(s, "root"), (s, "/CD69+")], "CD69", xf=LIN)
    whole, gated = out
    assert gated.n == int(ws.masks(s)["/CD69+"].sum())
    assert gated.n < whole.n
    assert gated.median > whole.median, "gating on the bright side did not raise the median"


# --- normalisation ----------------------------------------------------------


def test_modal_normalisation_peaks_at_a_hundred(ws):
    """The axis is labelled "% of max", so it has to reach 100."""
    for s in ov.build(ws, pairs(ws), "CD69", norm="mode", xf=LIN):
        assert s.y.max() == pytest.approx(100.0)


def test_a_smaller_population_draws_a_shorter_curve_on_a_count_axis(ws):
    """The bug this is here for: bins were chosen per curve, so the population with
    fewer events got wider bins, more events in each, and the taller curve."""
    ws.add_pop("root", "CD69 bright", thresh(0.68, dim="CD69"))
    s = ws.samples[1]
    whole, gated = ov.build(ws, [(s, "root"), (s, "/CD69 bright")], "CD69",
                            norm="count", xf=LIN)
    assert gated.n < whole.n
    assert gated.y.max() < whole.y.max()


def test_all_curves_share_one_bin_grid(ws):
    ws.add_pop("root", "CD69+", thresh(0.45, dim="CD69"))
    s = ws.samples[1]
    out = ov.build(ws, [(s, "root"), (s, "/CD69+")] + pairs(ws), "CD69", xf=LIN)
    first = out[0].x
    for c in out[1:]:
        assert np.array_equal(c.x, first), "%s is on a different grid" % c.label


def test_area_normalisation_integrates_to_one(ws):
    for s in ov.build(ws, pairs(ws), "CD69", norm="area", xf=LIN):
        edges = np.linspace(0, 1, (len(s.y) // 2) + 1)
        area = float(s.y[::2].sum()) * (edges[1] - edges[0])
        assert area == pytest.approx(1.0, rel=1e-6)


def test_raw_counts_add_up_to_the_events(ws):
    s = ov.build(ws, pairs(ws), "CD69", norm="count", xf=LIN)[0]
    assert float(s.y[::2].sum()) == pytest.approx(s.n, rel=0.02)


def test_an_unknown_normalisation_is_refused(ws):
    with pytest.raises(ValueError):
        ov.build(ws, pairs(ws), "CD69", norm="percentile", xf=LIN)


# --- resolution -------------------------------------------------------------


def test_bins_scale_with_the_events():
    assert ov.auto_bins(400) < ov.auto_bins(40000)
    for n in (200, 2000, 20000, 200000):
        assert ov.MIN_BINS <= ov.auto_bins(n) <= ov.MAX_BINS


def test_a_small_population_is_not_drawn_as_grass():
    """The failure this guards: 512 fixed bins over 3,000 events is Poisson noise,
    and it reads as structure that is not in the data."""
    rng = np.random.default_rng(3)
    v = np.clip(rng.normal(0.5, 0.08, 3000), 0, 1) * T
    _, h, n, _, _ = ov.histogram(v, LIN)
    peaks = int(((h[1:-1] > h[:-2]) & (h[1:-1] > h[2:])).sum())
    assert peaks <= 4, "a single gaussian came out with %d local maxima" % peaks


def test_smoothing_does_not_move_the_peak():
    rng = np.random.default_rng(4)
    v = np.clip(rng.normal(0.62, 0.05, 20000), 0, 1) * T
    edges, soft, _, _, _ = ov.histogram(v, LIN, bins=512, smooth=4)
    peak = (int(np.argmax(soft)) + 0.5) / 512.0
    # the raw argmax is the noisiest bin, not the peak, so the truth is the data's own
    assert peak == pytest.approx(0.62, abs=0.01), "smoothing walked the mode off 0.62"


def test_a_thin_population_is_flagged(ws):
    few = attach(ws, FakeSample("few.fcs", {"CD69": pos(40, 0.5, seed=7)}))
    s = ov.build(ws, [(few, "root")], "CD69", xf=LIN)[0]
    assert s.thin and "thin" in s.legend_text()


def test_an_empty_population_says_so(ws):
    ws.add_pop("root", "Impossible", thresh(0.999, dim="CD69"))
    s = ov.build(ws, [(ws.samples[0], "/Impossible")], "CD69", xf=LIN)[0]
    assert s.n == 0 and "no events" in s.legend_text()


# --- the legend -------------------------------------------------------------


def test_labels_keep_the_well_that_tells_them_apart():
    """The bug this is here for: trimming the shared prefix mid-token turned well
    A1 into "1" and threw away the row."""
    names = ["Act Plate 24hr_Experiment_Group_%s · live" % w
             for w in ("A1", "A10", "B1", "B12")]
    out = ov.shorten(names)
    assert out == ["A1 · live", "A10 · live", "B1 · live", "B12 · live"]


def test_long_labels_stay_distinct_at_both_ends():
    q = ["Q%d: CD69-Brilliant Violet 605-A%s , CD25-Brilliant Violet 421-A%s"
         % (i, a, b) for i, (a, b) in enumerate((("-", "+"), ("+", "+"), ("+", "-")), 1)]
    out = ov.shorten(q)
    assert len(set(out)) == 3, "two quadrants ended up with the same legend entry"
    assert all(t.startswith("Q") for t in out)


def test_a_single_label_is_left_alone():
    assert ov.shorten(["one · live"]) == ["one · live"]


def test_colours_stay_distinct_past_the_palette():
    assert len({ov.colour(i) for i in range(24)}) == 24


def test_no_curve_colour_is_too_pale_to_read():
    for i in range(32):
        r, g, b = ov.colour(i)
        assert 0.299 * r + 0.587 * g + 0.114 * b <= ov.MAX_LUMA + 1
