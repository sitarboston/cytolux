"""Transforms must be exactly invertible, monotonic, and stable across save/load."""
import math

import numpy as np
import pytest

from cytolux import transforms as tx

T = 262144.0
SPECS = [
    tx.linear(T),
    tx.log(T),
    tx.log(T, decades=4),
    tx.biex(T),
    tx.biex(T, W=1.0),
    tx.wspbiex(T),
]
IDS = ["linear", "log5", "log4", "biex", "biex-w1", "wspbiex"]


@pytest.mark.parametrize("spec", SPECS, ids=IDS)
def test_round_trip(spec):
    raw = np.array([1.0, 10.0, 100.0, 1e3, 1e4, 1e5, 2e5])
    back = tx.inverse(spec, tx.apply(spec, raw))
    assert np.allclose(back, raw, rtol=1e-4, atol=1e-3)


def test_logicle_round_trips_far_negatives():
    """logicle keeps off-scale negatives as negative display values, so they invert exactly."""
    spec = tx.biex(T)
    raw = np.array([-5000.0, -500.0, -50.0, 0.0, 50.0, 500.0, 5000.0])
    back = tx.inverse(spec, tx.apply(spec, raw))
    assert np.allclose(back, raw, rtol=1e-3, atol=1.0)


def test_wspbiex_round_trips_within_scale():
    """FlowJo's own biex only represents down to its bottom of scale, so test inside it."""
    spec = tx.wspbiex(T)
    floor = float(tx.inverse(spec, 0.0))
    raw = np.array([floor * 0.5, -50.0, 0.0, 50.0, 500.0, 5000.0])
    back = tx.inverse(spec, tx.apply(spec, raw))
    assert np.allclose(back, raw, rtol=1e-3, atol=1.0)


def test_wspbiex_clamps_below_bottom_of_scale():
    """Pinned behaviour, not a defect: FlowJo's biex collapses everything below its floor
    onto display 0, so those events are indistinguishable. A gate whose lower edge sits at
    display 0 therefore catches every event below the floor, exactly as FlowJo shows it.
    If FlowKit ever changes this, that is a FlowJo-agreement change and CI should say so."""
    spec = tx.wspbiex(T)
    floor = float(tx.inverse(spec, 0.0))
    assert floor == pytest.approx(-132.287, abs=0.01)
    for raw in (-5000.0, -500.0, -200.0):
        assert float(tx.apply(spec, raw)) == pytest.approx(0.0, abs=1e-9)
    assert float(tx.apply(spec, -100.0)) > 0.0


@pytest.mark.parametrize("spec", SPECS, ids=IDS)
def test_monotonic(spec):
    raw = np.linspace(1.0, T, 500)
    disp = tx.apply(spec, raw)
    assert np.all(np.diff(disp) > 0), "transform must be strictly increasing"


def test_linear_endpoints():
    spec = tx.linear(T)
    assert tx.apply(spec, 0.0) == pytest.approx(0.0)
    assert tx.apply(spec, T) == pytest.approx(1.0)
    assert tx.apply(spec, T / 2) == pytest.approx(0.5)


def test_log_top_of_scale():
    spec = tx.log(T, decades=5)
    assert float(tx.apply(spec, T)) == pytest.approx(1.0, abs=1e-9)


def test_biex_default_M_tracks_T():
    assert tx.biex(262144.0)["M"] == pytest.approx(4.5)
    assert tx.biex(26214.4)["M"] == pytest.approx(3.5)


def test_convert_is_identity_for_same_spec():
    spec = tx.biex(T)
    assert tx.convert(0.37, spec, spec) == 0.37


def test_convert_preserves_the_raw_value():
    """Re-expressing a display coordinate in another axis must not move the event."""
    src, dst = tx.biex(T), tx.log(T)
    raw = 1234.0
    v_src = float(tx.apply(src, raw))
    v_dst = tx.convert(v_src, src, dst)
    assert float(tx.inverse(dst, v_dst)) == pytest.approx(raw, rel=1e-4)


def test_convert_none_passes_through():
    assert tx.convert(None, tx.linear(T), tx.log(T)) is None


def test_same():
    assert tx.same(tx.linear(T), tx.linear(T))
    assert not tx.same(tx.linear(T), tx.log(T))
    assert not tx.same(tx.biex(T, W=0.5), tx.biex(T, W=1.0))


@pytest.mark.parametrize("spec", SPECS, ids=IDS)
def test_ticks_are_on_scale(spec):
    major, minor = tx.ticks(spec)
    assert major, "every axis needs at least one labelled tick"
    for pos, label in major:
        assert -0.01 <= pos <= 1.01, (label, pos)
        assert isinstance(label, str) and label
    for pos in minor:
        assert -0.01 <= pos <= 1.01


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        tx.apply({"kind": "nope", "T": T}, 1.0)
    with pytest.raises(ValueError):
        tx.inverse({"kind": "nope", "T": T}, 0.5)
