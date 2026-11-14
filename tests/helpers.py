"""Synthetic samples for tests that need event data without an FCS file on disk.

Two shapes of data, and between them they are the whole argument for the uncertainty
feature. `islands` has two tight clusters with empty space between them, so a boundary
drawn in the gap can be moved and the count does not change. `smear` is one broad
continuum, so any boundary inside it sits on events and moving it trades them across.
"""
import numpy as np

from cytolux import transforms as tx
from cytolux.engine import EventData

T = 262144.0
LIN = tx.linear(T)
LOW, HIGH, TIGHT = 0.08, 0.95, 0.004      # display-space cluster centres and width


class FakeSample:
    """A sample backed by arrays instead of a file, so the tests own their event data."""

    def __init__(self, name, cols):
        self.name = name
        self.path = "/nonexistent/" + name
        self.channels = list(cols)
        self._raw = np.column_stack([np.asarray(cols[c], dtype=float) for c in self.channels])
        self.markers = {c: "" for c in self.channels}
        self.ranges = {c: T for c in self.channels}
        self.spill_channels = None
        self.spill = None
        self.event_count = self._raw.shape[0]

    def raw(self):
        return self._raw


def attach(ws, sample):
    """Put a synthetic sample into a workspace, event cache and all."""
    ws.samples.append(sample)
    ws._events[sample.name] = EventData(sample, None)
    return sample


def islands(n=20000, seed=1, frac_high=0.10):
    """A tenth of the events in a tight cluster high, the rest in a tight cluster low."""
    rng = np.random.default_rng(seed)
    hi = int(round(n * frac_high))
    xy = np.vstack([rng.normal(LOW * T, TIGHT * T, (n - hi, 2)),
                    rng.normal(HIGH * T, TIGHT * T, (hi, 2))])
    return {"A": xy[:, 0], "B": xy[:, 1]}


def smear(n=20000, seed=2):
    rng = np.random.default_rng(seed)
    return {"A": rng.uniform(0.0, T, n), "B": rng.uniform(0.0, T, n)}


def rect(lo, hi, dims=("A", "B")):
    n = len(dims)
    return {"type": "rect", "dims": list(dims), "xf": [dict(LIN) for _ in range(n)],
            "min": [lo] * n, "max": [hi] * n}


def thresh(lo, dim="A"):
    """A one-sided threshold on a single marker, which is how a positive population is
    actually gated, and the case where boundary placement matters most."""
    return {"type": "rect", "dims": [dim], "xf": [dict(LIN)], "min": [lo], "max": [None]}
