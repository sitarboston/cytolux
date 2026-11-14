"""Overlaid histograms: the plot you reach for when the question is "did it shift?".

A dot plot answers where cells sit. It is poor at answering whether one condition
moved a marker relative to another, because two dot plots side by side make the eye
do the comparing. Laying the distributions over each other on one axis puts the
comparison in the picture, which is why every CD27/CD28 differentiation figure and
every "did the dose do anything" CD69 figure is drawn this way.

This module is headless: it turns populations into curves and the numbers that go
in the legend. Nothing here knows about Qt.
"""
import math

import numpy as np

from . import transforms as tx

BINS = 512
TARGET_PER_BIN = 24          # events per bin before smoothing
MIN_BINS, MAX_BINS = 64, 512

# Okabe-Ito, which stays distinguishable under the common colour-vision deficiencies.
# A figure whose conditions are told apart only by red against green is a figure one
# reader in twelve cannot read.
PALETTE = [(0, 114, 178), (213, 94, 0), (0, 158, 115), (204, 121, 167),
           (230, 159, 0), (86, 180, 233), (120, 94, 160), (100, 100, 100)]

NORMS = ("mode", "area", "count")
NORM_LABEL = {"mode": "% of max", "area": "Density", "count": "Count"}
MODE_FULL = 100.0            # "% of max" has to run to 100, not to 1


def colour(i):
    """Okabe-Ito, then the same eight shifted lighter and darker.

    Past eight curves the palette has to repeat something. It repeats the hue and
    changes the value, so two curves of the same hue are still told apart, and the
    first eight - the common case - get the palette unaltered.
    """
    base = PALETTE[i % len(PALETTE)]
    cycle = i // len(PALETTE)
    if cycle == 0:
        return base
    f = (0.55, 1.45, 0.75, 1.25)[(cycle - 1) % 4]
    return cap(tuple(int(max(0, min(255, round(c * f)))) for c in base))


MAX_LUMA = 165.0     # anything paler than this disappears against the cream


def cap(rgb):
    """Darken a colour until it can be read on the page it is drawn on.

    Lightening a hue is the cheap way to get more of it, and it quietly produces
    curve labels nobody can read against a cream background. Hue is kept, value is
    pulled back to where the text holds.
    """
    r, g, b = rgb
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    if luma <= MAX_LUMA or luma == 0:
        return (r, g, b)
    k = MAX_LUMA / luma
    return tuple(int(round(c * k)) for c in (r, g, b))


class Series:
    """One curve, with the numbers a reader needs to believe it.

    `n` matters: a curve drawn from 60 events and one drawn from 60,000 look equally
    smooth once normalised, and only one of them means anything.
    """

    __slots__ = ("label", "x", "y", "n", "median", "mean", "raw_peak", "colour")

    def __init__(self, label, x, y, n, median, mean, raw_peak, colour=(0, 0, 0)):
        self.label, self.x, self.y = label, x, y
        self.n, self.median, self.mean, self.raw_peak = n, median, mean, raw_peak
        self.colour = colour

    @property
    def thin(self):
        """Too few events to draw a distribution from, by the usual flow rule of thumb."""
        return self.n < 100

    def legend_text(self):
        if not self.n:
            return "%s  (no events)" % self.label
        out = "%s  n=%s  median %s" % (self.label, f"{self.n:,}", _fmt(self.median))
        return out + "  (thin)" if self.thin else out


def _fmt(v):
    if v is None or not np.isfinite(v):
        return "-"
    a = abs(v)
    if a >= 10000:
        return "%.3g" % v
    if a >= 100:
        return "%.0f" % v
    return "%.4g" % v


def auto_bins(n):
    """Bin count for n events.

    A fixed 512 bins is the reason a histogram of four thousand events comes out as
    grass: at eight events a bin, counting noise alone is a third of the height. Bins
    are chosen for about two dozen events each, so the wiggle in the curve is the
    distribution and not the Poisson.
    """
    if n <= 0:
        return MIN_BINS
    want = max(1, int(n // TARGET_PER_BIN))
    b = 1 << int(round(math.log2(max(want, 1))))
    return int(min(MAX_BINS, max(MIN_BINS, b)))


def auto_smooth(n):
    """Smoothing passes. Fewer events, more smoothing - the bins are already wider,
    and what is left is the noise too coarse for the binning to have absorbed."""
    if n >= 50000:
        return 1
    if n >= 10000:
        return 2
    if n >= 1000:
        return 3
    return 4


def smooth_counts(h, passes=1):
    """A light binomial blur. Enough to stop 512 bins looking like grass, not enough
    to move a peak: the kernel is symmetric, so the mode stays where the data put it."""
    k = np.array([1, 4, 6, 4, 1], float)
    k /= k.sum()
    for _ in range(max(0, passes)):
        h = np.convolve(h, k, mode="same")
    return h


def histogram(values, xf, bins=None, smooth=None):
    """Counts per bin on the transformed axis, plus the raw median and mean.

    The median and mean are taken on raw values, not on the transformed ones: a
    median reported in logicle units is not a number anyone can put in a paper.
    """
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    n = v.size
    if bins is None:
        bins = auto_bins(n)
    if smooth is None:
        smooth = auto_smooth(n)
    edges = np.linspace(0.0, 1.0, bins + 1)
    if not n:
        return edges, np.zeros(bins), 0, np.nan, np.nan
    t = np.clip(tx.apply(xf, v), 0.0, 1.0)
    h, _ = np.histogram(t, bins=bins, range=(0.0, 1.0))
    return edges, smooth_counts(h.astype(float), smooth), n, float(np.median(v)), float(v.mean())


def normalise(h, kind, edges=None):
    """Scale a set of counts for display.

    mode  - every curve peaks at 1, which is FlowJo's "modal" and the right default:
            it compares shapes when the populations differ in size.
    area  - every curve integrates to 1, so a curve carrying half the cells is drawn
            half as tall. Honest about weight, harder to read when sizes differ wildly.
    count - raw counts, for when the sizes are the point.
    """
    if kind not in NORMS:
        raise ValueError("unknown normalisation %r" % (kind,))
    if kind == "count":
        return h
    if kind == "mode":
        peak = h.max()
        return h * (MODE_FULL / peak) if peak > 0 else h
    w = (edges[1] - edges[0]) if edges is not None and len(edges) > 1 else 1.0
    area = h.sum() * w
    return h / area if area > 0 else h


def steps(edges, y):
    """Edge arrays as a staircase, so a bin is drawn as the flat thing it is."""
    return np.repeat(edges, 2)[1:-1], np.repeat(y, 2)


def build(ws, pairs, channel, bins=None, norm="mode", smooth=None, xf=None):
    """Curves for [(sample, population path), ...] on one channel.

    Every curve uses one transform - the workspace's for this channel - because
    curves drawn on different axes cannot be laid over each other and compared, and
    one bin count, chosen from the largest population in the set. Letting each curve
    pick its own resolution looks harmless and is not: wider bins hold more events,
    so the smaller population would draw the taller curve on a count axis.

    A sample that does not carry the channel is skipped rather than drawn empty,
    which happens in a plate where a few wells ran a different panel.
    """
    if norm not in NORMS:
        raise ValueError("unknown normalisation %r" % (norm,))
    picked = []
    for s, pop in pairs:
        spec = ws.xform(channel, s) if xf is None else xf
        ed = ws.events(s)
        try:
            col = ed.col(channel)
        except KeyError:
            continue
        mask = ws.masks(s).get(pop)
        if mask is None:
            continue
        picked.append((s, pop, spec, col[mask]))
    sizes = [v.size for _, _, _, v in picked] or [0]
    if bins is None:
        bins = auto_bins(max(sizes))
    if smooth is None:
        # One bin grid and one amount of smoothing for the whole set. Smoothing from
        # the smallest population, so the weakest curve in the picture is readable and
        # no curve is flattened more than its neighbour.
        smooth = auto_smooth(min(sizes))
    out = []
    for i, (s, pop, spec, vals) in enumerate(picked):
        edges, h, n, med, mean = histogram(vals, spec, bins=bins, smooth=smooth)
        peak = float(h.max()) if h.size else 0.0
        y = normalise(h, norm, edges)
        x, yy = steps(edges, y)
        out.append(Series(_label(ws, s, pop), x, yy, n, med, mean, peak, colour(i)))
    return out


def _label(ws, s, pop):
    name = s.name
    if name.lower().endswith(".fcs"):
        name = name[:-4]
    leaf = "All events" if pop == "root" else pop.rsplit("/", 1)[-1]
    return "%s · %s" % (name, leaf)


def shorten(labels, keep=60):
    """Drop the prefix every label shares, then ellipsize the middle of what is left.

    Plate wells are named identically for forty characters and then differ in the last
    three, so a legend truncated from the right says the same thing eight times. The
    shared prefix is backed up to the last separator, because cutting mid-token turns
    well A1 into "1" and loses the row. What survives is cut in the middle rather than
    at either end: a quadrant is told apart by its opening ("Q2:") and a well by its
    close, and a one-ended trim throws away one or the other.
    """
    labels = list(labels)
    if not labels:
        return []
    pre = labels[0]
    for s in labels[1:]:
        while pre and not s.startswith(pre):
            pre = pre[:-1]
    cut = 0
    if len(set(labels)) > 1:
        at = max(pre.rfind(c) for c in "_ -:.·")
        if at >= 3:
            cut = at + 1
    out = []
    for s in labels:
        t = s[cut:].strip() or s
        out.append(t if len(t) <= keep else _middle(t, keep))
    return out


def _middle(text, keep):
    head = (keep - 1) * 6 // 10
    return text[:head] + "\u2026" + text[-(keep - 1 - head):]


def stack_offsets(n, spread=0.55):
    """Vertical offsets for a ridgeline. Overlapping by design: a stack with gaps is
    just small multiples in a column, and the point of the stack is the shared axis."""
    if n <= 1:
        return [0.0]
    return [i * spread for i in range(n)]
