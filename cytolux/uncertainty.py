"""How much of a gated percentage is real, and how much is where the line was drawn.

A frequency comes out of a flow package as a single number, printed to two decimal
places, carrying the same air of fact as the event count it came from. The count is a
fact. The frequency is a count divided by a boundary somebody drew with a mouse. Draw
it again tomorrow and the number moves. How far it moves is the question this module
answers, and no commercial package answers it.

The method is deliberate: take the gating tree as given, displace every boundary in it
by about as much as a careful hand would, re-gate the file from the root, and watch
where each population's frequency goes. Repeat a couple of hundred times and report the
spread. A lymphocyte gate in open space barely moves. A CD25 positive boundary sitting
in the middle of a continuum moves a lot. Both print 12.43 in FlowJo.

The displacement is in display space, where every axis runs 0 to 1 whatever its
transform, so one `sigma` means the same thing on a biexponential CD3 axis as on a
linear FSC axis: the fraction of the plot's width by which the boundary is uncertain.
The default, 0.01, is a hand that places a line to within one percent of the axis.

Three properties worth knowing about before reading the numbers:

* Every gate in the tree is displaced at once, and the tree is recomputed from the
  root. A child's interval therefore already contains its parent's uncertainty, which
  is how gating actually behaves. Deep populations have wider intervals than shallow
  ones, and that is not an artifact.
* Boundaries move independently. Real hands have correlated habits, so this is a
  simplification, and it is the conservative direction: independent errors spread a
  little wider than correlated ones.
* A gate thinner than `sigma` will sometimes close completely and return no events.
  That is left in rather than guarded against, because it is true: the gate is finer
  than the precision of the hand that drew it, and the enormous interval says so.
"""

import copy
import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from . import transforms as tx
from .engine import build_masks

DEFAULT_N = 200
DEFAULT_SIGMA = 0.01
DEFAULT_LEVEL = 95.0

# Where a frequency stops being solid. Conventions, not findings, and a user is meant
# to be able to argue with them.
#
# The grade is driven by the interval relative to the number itself, because that is
# what decides whether a difference between two arms survives. Judging it on
# percentage points alone would call a 0.1 percent population with an interval of
# [0.02, 0.18] solid, when the gate is really saying somewhere between a fiftieth and
# a fifth of a percent: a nine-fold range.
#
# Two absolute bounds sit on either side of that. Below NEGLIGIBLE_PP the number
# cannot move enough to matter whatever its size, which also rescues populations at or
# near zero, where a relative width means nothing. Above FRAGILE_PP it moves too much
# to matter whatever its size: a parent population at 60 percent give or take 6 is
# only 10 percent relative, and still far too loose to build an argument on.
FIRM_REL = 0.05
FRAGILE_REL = 0.25
NEGLIGIBLE_PP = 0.05
FRAGILE_PP = 5.0


def grade_of(half_width, value):
    """One word for how much weight a number will carry.

    "firm" to quote as it stands, "soft" to quote with the interval beside it,
    "fragile" to go back and fix something before quoting it at all. "unknown" means
    there was nothing to measure, usually a population whose parent was empty.
    """
    hw = half_width
    if np.isnan(hw):
        return "unknown"
    if hw <= NEGLIGIBLE_PP:
        return "firm"
    rel = hw / value if value else float("nan")
    rel_known = not np.isnan(rel)
    if hw >= FRAGILE_PP or (rel_known and rel >= FRAGILE_REL):
        return "fragile"
    if rel_known and rel <= FIRM_REL:
        return "firm"
    return "soft"


@dataclass(frozen=True)
class Spread:
    """One number, and the range it covered while the gates were being jittered.

    `value` is the ordinary unperturbed result, the one the statistics table shows.
    `lo` and `hi` bound the middle `level` percent of the replicates. `median` is the
    replicates' own centre, which drifts away from `value` when a boundary sits on a
    steep part of the distribution; a large gap between the two is itself a warning.
    """
    value: float
    lo: float
    hi: float
    median: float

    @property
    def half_width(self):
        return 0.5 * (self.hi - self.lo)

    @property
    def relative(self):
        """Half interval as a fraction of the value, or nan where the value is zero."""
        return self.half_width / self.value if self.value else float("nan")

    @property
    def bias(self):
        """How far the replicates' centre sits from the reported number."""
        return self.median - self.value

    @property
    def grade(self):
        return grade_of(self.half_width, self.value)

    def text(self, places=2):
        return "%.*f [%.*f, %.*f]" % (places, self.value, places, self.lo, places, self.hi)


@dataclass(frozen=True)
class PopUncertainty:
    """What happened to one population across the replicates.

    Carries the two counts as well, because gate placement is only half of why a
    frequency is uncertain. The other half is how many cells were counted, and the two
    call for opposite responses: a shaky boundary means go back and redraw it, too few
    events means go back and acquire more. A report that blends them into one interval
    tells you a number is soft without telling you what to do about it, so they are
    kept apart here and compared in `limited_by`.
    """
    path: str
    count: Spread
    parent_pct: Spread
    total_pct: Spread
    parent_n: int = 0
    total_n: int = 0
    level: float = DEFAULT_LEVEL

    @property
    def name(self):
        return "All events" if self.path == "root" else self.path.rsplit("/", 1)[1]

    @property
    def gate_grade(self):
        """How the number stands up to the boundary being moved, and nothing else."""
        return self.parent_pct.grade

    @property
    def grade(self):
        """How the number stands up to everything: the boundary and the event count.

        This is the one to read. A population can be perfectly gated and still not
        worth quoting because only thirty cells landed in it, and `gate_grade` alone
        would call that firm.
        """
        return grade_of(self.combined_half_width, self.parent_pct.value)

    @property
    def combined_half_width(self):
        """Gate and counting error together, added in quadrature as independent terms.

        They are independent in the sense that matters: where the line was put has
        nothing to do with how many cells went through the cytometer. Combining them
        this way assumes both are roughly symmetric, which holds except for populations
        pressed against zero, where the interval should be read as indicative.
        """
        g, c = self.parent_pct.half_width, self.counting_half_width
        if np.isnan(g):
            return c
        if np.isnan(c):
            return g
        return math.hypot(g, c)

    @property
    def combined(self):
        """The interval to put in a figure: the value with everything accounted for."""
        hw = self.combined_half_width
        v = self.parent_pct.value
        return Spread(v, v - hw, v + hw, self.parent_pct.median)

    @property
    def counting_half_width(self):
        """Half interval in percentage points from counting statistics alone.

        The binomial standard error of this population's share of its parent, widened
        to the same confidence level as the gate interval so the two are comparable.
        This is the floor no amount of careful gating gets below.
        """
        n = self.parent_n
        if not n:
            return float("nan")
        p = self.count.value / n
        if p < 0.0 or p > 1.0:
            return float("nan")
        z = NormalDist().inv_cdf(0.5 + self.level / 200.0)
        return 100.0 * z * math.sqrt(max(p * (1.0 - p), 0.0) / n)

    @property
    def counting_relative(self):
        v = self.parent_pct.value
        return self.counting_half_width / v if v else float("nan")

    @property
    def limited_by(self):
        """"gate" or "counting": which of the two is the bigger part of the doubt.

        The useful question once a frequency comes back soft. "gate" means the boundary
        is doing more damage than the sample size and redrawing it would help; "counting"
        means the gate is about as good as it can be at this event count, and only more
        cells will tighten the number.
        """
        g, c = self.parent_pct.half_width, self.counting_half_width
        if math.isnan(g) or math.isnan(c):
            return "unknown"
        return "gate" if g >= c else "counting"


def perturb_gate(g, rng, sigma=DEFAULT_SIGMA):
    """A copy of `g` with its boundary displaced by about `sigma` of the axis.

    Each gate type is moved in the way a hand actually moves it. A rectangle's edges
    slide independently, which covers both a shifted gate and a wider or narrower one.
    A polygon travels as a rigid shape and then breathes in or out about its centroid,
    because people reposition and resize polygons, they do not nudge single vertices.
    An ellipse moves by its centre and its two radii. The dilation terms are scaled so
    that the boundary itself moves by about `sigma` whatever the gate's size, which
    keeps a small gate from being shaken apart.
    """
    g = copy.deepcopy(g)
    t = g["type"]
    if t == "rect":
        for key in ("min", "max"):
            g[key] = [None if b is None else float(b + rng.normal(0.0, sigma))
                      for b in g[key]]
    elif t == "poly":
        v = np.asarray(g["vertices"], dtype=float)
        c = v.mean(axis=0)
        radius = float(np.hypot(*(v - c).T).mean())
        v = v + rng.normal(0.0, sigma, size=2)
        if radius > 0:
            v = c + (v - c) * (1.0 + rng.normal(0.0, sigma) / radius)
        g["vertices"] = v.tolist()
    elif t == "ellipse":
        cx, cy = g["center"]
        a, b = g["axes"]
        g["center"] = [float(cx + rng.normal(0.0, sigma)),
                       float(cy + rng.normal(0.0, sigma))]
        g["axes"] = [max(float(a + rng.normal(0.0, sigma)), 1e-9),
                     max(float(b + rng.normal(0.0, sigma)), 1e-9)]
    else:
        raise ValueError(t)
    return g


def _transformed_columns(ws, s, gates):
    """The display-space columns each population needs, computed once for all replicates.

    This is what makes two hundred replicates cheap. Jittering a boundary never changes
    which channel or which transform a gate reads, so the expensive part, pushing a few
    hundred thousand events through a biexponential, is done one time. None marks a
    population whose channel this file does not carry.
    """
    ed = ws.events(s)
    out = {}
    for path, g in gates.items():
        try:
            out[path] = [tx.apply(xf, ed.col(d)) for d, xf in zip(g["dims"], g["xf"])]
        except KeyError:
            out[path] = None
    return out


def gate_uncertainty(ws, s, n=DEFAULT_N, sigma=DEFAULT_SIGMA, level=DEFAULT_LEVEL,
                     seed=0):
    """Re-gate `s` `n` times with every boundary displaced, and report what moved.

    Returns {path: PopUncertainty}, including "root", whose count is fixed and whose
    intervals are therefore degenerate. The workspace is not touched: the perturbed
    gates live only inside this call, so the cached masks and the numbers on screen are
    exactly as they were. A fixed `seed` makes the whole thing reproducible, which
    matters if an interval is going into a report.
    """
    if n < 2:
        raise ValueError("need at least two replicates to have a spread")
    ed = ws.events(s)
    pops = list(ws.pops)
    gates = {p["path"]: ws.gate_for(p["path"], s.name) for p in pops}
    vals = _transformed_columns(ws, s, gates)
    paths = ["root"] + [p["path"] for p in pops]
    index = {path: i for i, path in enumerate(paths)}
    parent_of = {p["path"]: p["parent"] for p in pops}

    counts = np.zeros((n, len(paths)), dtype=np.int64)
    rng = np.random.default_rng(seed)
    for r in range(n):
        jittered = {path: perturb_gate(g, rng, sigma) for path, g in gates.items()}
        m = build_masks(ed, pops, lambda p: jittered[p["path"]],
                        vals_of=lambda p: vals[p["path"]])
        for path, i in index.items():
            if path in m:
                counts[r, i] = int(m[path].sum())

    # the unperturbed numbers, straight from the workspace, so the reported value
    # always agrees with the statistics table
    base_stats = ws.stats(s)
    half = (100.0 - level) / 2.0
    out = {}
    for path in paths:
        c = counts[:, index[path]]
        par = counts[:, index.get(parent_of.get(path, "root"), 0)]
        root = counts[:, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            pp = np.where(par > 0, 100.0 * c / np.maximum(par, 1), np.nan)
            tp = np.where(root > 0, 100.0 * c / np.maximum(root, 1), np.nan)
        b = base_stats.get(path, (0, float("nan"), float("nan")))
        par_path = parent_of.get(path, "root")
        out[path] = PopUncertainty(
            path=path,
            count=_spread(float(b[0]), c.astype(float), half),
            parent_pct=_spread(float(b[1]), pp, half),
            total_pct=_spread(float(b[2]), tp, half),
            parent_n=int(base_stats.get(par_path, (0,))[0]),
            total_n=int(base_stats.get("root", (0,))[0]),
            level=float(level),
        )
    return out


def _spread(value, draws, half):
    draws = np.asarray(draws, dtype=float)
    good = draws[~np.isnan(draws)]
    if not len(good):
        nan = float("nan")
        return Spread(value, nan, nan, nan)
    lo, med, hi = np.percentile(good, [half, 50.0, 100.0 - half])
    return Spread(value, float(lo), float(hi), float(med))


def fragility_report(ws, samples=None, n=DEFAULT_N, sigma=DEFAULT_SIGMA,
                     level=DEFAULT_LEVEL, seed=0, include_root=False, progress=None):
    """One row per sample and population: the frequency, its interval, and its grade.

    This is the view that earns the feature. Run it on a finished workspace and the
    gates that cannot carry the weight being put on them sort to the top, before the
    numbers reach a figure. Each sample gets its own stream of random numbers, derived
    from `seed` and the sample's position, so adding a sample never changes an existing
    sample's answer.

    `progress(done, total)` is called before each sample and may return True to stop
    early, which returns the samples finished so far rather than nothing: a long run on
    a big workspace is worth keeping when the user has seen enough.

    Read "Limited by" before acting on a row. A fragile row limited by counting is not
    a badly drawn gate, it is a population too rare to have been measured at this event
    count, and redrawing the boundary will not save it.
    """
    import pandas as pd
    samples = samples or ws.samples
    rows = []
    for k, s in enumerate(samples):
        if progress is not None and progress(k, len(samples)):
            break
        u = gate_uncertainty(ws, s, n=n, sigma=sigma, level=level, seed=seed + 7919 * k)
        for path, pu in u.items():
            if path == "root" and not include_root:
                continue
            comb = pu.combined
            # Verdict first. The grade and what to do about it are what the reader
            # came for; the full gating path is reference and goes last, or it pushes
            # everything that matters off the right-hand edge of the window.
            rows.append({
                "Sample": s.name,
                "Population": pu.name,
                "Grade": pu.grade,
                "Limited by": pu.limited_by,
                "Count": pu.count.value,
                "% of parent": pu.parent_pct.value,
                "Low": comb.lo,
                "High": comb.hi,
                "Half width": comb.half_width,
                "Relative": comb.relative,
                "Gate half width": pu.parent_pct.half_width,
                "Counting half width": pu.counting_half_width,
                "Bias": pu.parent_pct.bias,
                "Path": path,
            })
    df = pd.DataFrame(rows)
    if len(df):
        order = {"fragile": 0, "soft": 1, "unknown": 2, "firm": 3}
        df = (df.assign(_o=df["Grade"].map(order))
                .sort_values(["_o", "Half width"], ascending=[True, False])
                .drop(columns="_o").reset_index(drop=True))
    return df
