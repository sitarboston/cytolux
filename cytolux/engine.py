"""Gating engine: samples, compensation, gates, the population tree and statistics.
No GUI code here, so it can be tested on its own (see tests/validate_flowjo.py).

Gates are plain dicts, with coordinates in the display space of their own axis transforms
("xf"), so a gate drawn on a biex axis stays exactly the gate you drew:
    {"type": "rect",    "dims": [x, y] or [x], "xf": [...], "min": [...], "max": [...]}
    {"type": "poly",    "dims": [x, y], "xf": [...], "vertices": [[x, y], ...]}
    {"type": "ellipse", "dims": [x, y], "xf": [...], "center": [cx, cy], "axes": [a, b], "angle": deg}
plus optional "invert": True (events outside the shape).
"""
import copy
import json
import math
import os
from collections import OrderedDict

import numpy as np
import flowkit as fk

from . import transforms as tx

SCATTER_PREFIXES = ("FSC", "SSC", "Time", "TIME", "Event", "Width")


def is_scatter(ch):
    return ch.startswith(SCATTER_PREFIXES)


# ----------------------------------------------------------------------------- samples

class Sample:
    """One FCS file, read lazily; event data are dropped from memory by the Workspace cache."""

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.name = os.path.basename(path)
        fs = fk.Sample(self.path, ignore_offset_error=True)
        self.channels = list(fs.pnn_labels)
        self.markers = {c: (m or "") for c, m in zip(fs.pnn_labels, fs.pns_labels)}
        self.event_count = fs.event_count
        self.ranges = {}
        for i, c in enumerate(self.channels, start=1):
            r = fs.metadata.get(f"p{i}r")
            try:
                self.ranges[c] = float(r)
            except (TypeError, ValueError):
                self.ranges[c] = 262144.0
        self.spill_channels, self.spill = None, None
        sp = fs.metadata.get("spill") or fs.metadata.get("spillover")
        if sp:
            self.spill_channels, self.spill = parse_spill(sp, self.channels)
        self._fs = None

    def raw(self):
        fs = fk.Sample(self.path, ignore_offset_error=True)
        return fs.get_events(source="raw").astype(np.float64)


def parse_spill(text, channels):
    parts = [p.strip() for p in text.split(",")]
    n = int(parts[0])
    names = parts[1:1 + n]
    vals = np.array([float(v) for v in parts[1 + n:1 + n + n * n]]).reshape(n, n)
    # some instruments write $PnS or channel numbers; map numbers to names
    out = []
    for nm in names:
        if nm.isdigit() and 0 < int(nm) <= len(channels):
            out.append(channels[int(nm) - 1])
        else:
            out.append(nm)
    return out, vals


class EventData:
    """Raw + compensated columns for one sample. Compensated columns are named 'Comp-<ch>'
    exactly as FlowJo names them, so FlowJo gate dimensions resolve directly."""

    def __init__(self, sample, comp):
        raw = sample.raw()
        self.n = raw.shape[0]
        self.cols = {c: raw[:, i] for i, c in enumerate(sample.channels)}
        self.comp_channels = []
        if comp is not None:
            chans, mat = comp
            idx = [sample.channels.index(c) for c in chans if c in sample.channels]
            if len(idx) == len(chans):
                compd = raw[:, idx] @ np.linalg.inv(mat)
                for j, c in enumerate(chans):
                    self.cols["Comp-" + c] = compd[:, j]
                self.comp_channels = list(chans)

    def col(self, dim):
        if dim in self.cols:
            return self.cols[dim]
        if dim.startswith("Comp-") and dim[5:] in self.cols:   # scatter, or comp switched off
            return self.cols[dim[5:]]
        if "Comp-" + dim in self.cols:
            return self.cols["Comp-" + dim]
        raise KeyError(f"channel not found: {dim}")


# ----------------------------------------------------------------------------- gates

def build_masks(ed, pops, gate_of, vals_of=None):
    """Walk a population list and return {path: boolean mask}, children ANDed into parents.

    `pops` must list parents before children, which add_pop guarantees. A population
    whose parent is missing is skipped; one whose gate names a channel this file does
    not have comes back empty rather than raising, so a panel that varies across a
    workspace still opens. `vals_of(p)` may supply the already-transformed columns for
    a population, which is what makes repeated re-gating of one file affordable.
    """
    m = {"root": np.ones(ed.n, dtype=bool)}
    for p in pops:
        parent = m.get(p["parent"])
        if parent is None:
            continue
        try:
            vals = None if vals_of is None else vals_of(p)
            m[p["path"]] = parent & gate_mask(ed, gate_of(p), vals=vals)
        except KeyError:                # channel missing in this file
            m[p["path"]] = np.zeros(ed.n, dtype=bool)
    return m


def gate_mask(ed, g, vals=None):
    dims, xfs = g["dims"], g["xf"]
    if vals is None:
        vals = [tx.apply(xf, ed.col(d)) for d, xf in zip(dims, xfs)]
    t = g["type"]
    if t == "rect":
        m = np.ones(ed.n, dtype=bool)
        for v, lo, hi in zip(vals, g["min"], g["max"]):
            if lo is not None:
                m &= v >= lo
            if hi is not None:
                m &= v < hi
    elif t == "poly":
        m = points_in_polygon(vals[0], vals[1], np.asarray(g["vertices"], dtype=float))
    elif t == "ellipse":
        cx, cy = g["center"]
        a, b = g["axes"]
        th = math.radians(g.get("angle", 0.0))
        dx, dy = vals[0] - cx, vals[1] - cy
        u = dx * math.cos(th) + dy * math.sin(th)
        w = -dx * math.sin(th) + dy * math.cos(th)
        m = (u / a) ** 2 + (w / b) ** 2 <= 1.0
    else:
        raise ValueError(t)
    return ~m if g.get("invert") else m


def points_in_polygon(x, y, v):
    """Even-odd ray casting, vectorised over events (same rule as FlowJo / Gating-ML)."""
    inside = np.zeros(x.shape, dtype=bool)
    n = len(v)
    j = n - 1
    for i in range(n):
        xi, yi = v[i]
        xj, yj = v[j]
        with np.errstate(divide="ignore", invalid="ignore"):
            cross = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi) + xi)
        inside ^= cross
        j = i
    return inside


def gate_outline(g, xf_x, xf_y, swap=False, n=64):
    """Gate outline as display-space points for axes with transforms xf_x / xf_y.
    Edges are densified, so a gate drawn on other axes is shown with its true curved shape."""
    t = g["type"]
    if t == "rect":
        lo, hi = g["min"], g["max"]
        x0 = -0.5 if lo[0] is None else lo[0]
        x1 = 1.5 if hi[0] is None else hi[0]
        if len(g["dims"]) == 1:
            return None
        y0 = -0.5 if lo[1] is None else lo[1]
        y1 = 1.5 if hi[1] is None else hi[1]
        pts = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]])
    elif t == "poly":
        v = np.asarray(g["vertices"], dtype=float)
        pts = np.vstack([v, v[:1]])
    else:
        cx, cy = g["center"]
        a, b = g["axes"]
        th = math.radians(g.get("angle", 0.0))
        s = np.linspace(0, 2 * math.pi, 129)
        u, w = a * np.cos(s), b * np.sin(s)
        pts = np.column_stack([cx + u * math.cos(th) - w * math.sin(th),
                               cy + u * math.sin(th) + w * math.cos(th)])
    # densify, then map gate space -> raw -> plot space
    dense = [pts[0]]
    for p, q in zip(pts[:-1], pts[1:]):
        for f in np.linspace(0, 1, n)[1:]:
            dense.append(p + (q - p) * f)
    dense = np.array(dense)
    gx, gy = g["xf"]
    X = tx.apply(xf_x, tx.inverse(gx, dense[:, 0]))
    Y = tx.apply(xf_y, tx.inverse(gy, dense[:, 1]))
    if swap:
        X, Y = Y, X
    return np.column_stack([X, Y])


def reexpress_rect(g, new_xfs):
    """Rectangles stay exact rectangles under any per-axis monotonic transform."""
    g2 = copy.deepcopy(g)
    for i, nxf in enumerate(new_xfs):
        g2["min"][i] = tx.convert(g["min"][i], g["xf"][i], nxf)
        g2["max"][i] = tx.convert(g["max"][i], g["xf"][i], nxf)
        g2["xf"][i] = nxf
    return g2


# ----------------------------------------------------------------------------- workspace

class Workspace:
    """Samples + compensation + one gating tree shared by all samples (FlowJo's 'group'),
    with optional per-sample gate overrides."""

    CACHE = 6   # event data for this many samples are kept in memory

    def __init__(self):
        self.samples = []            # list[Sample]
        self.comp_mode = "file"      # "file" | "none" | "custom"
        self.custom_comp = None      # (channels, matrix)
        self.pops = []               # [{"path","name","parent","gate"}], parents before children
        self.overrides = {}          # sample name -> {path: gate}
        self.xforms = {}             # channel -> transform dict
        self.labels = {}             # channel -> user label
        self.stat_defs = []          # [{"pop","stat","channel","arg","name"}]
        self.annot_cols = []         # sample annotation column names, e.g. Donor, Dose
        self.annotations = {}        # sample name -> {column: value}
        self.path = None
        self._events = OrderedDict()
        self._masks = {}             # sample name -> {path: mask}
        self.version = 0
        self.UNDO_DEPTH = 50
        self._undo = []              # [(snapshot, label)] oldest first
        self._redo = []
        self._prev = self.snapshot()

    # --- samples
    def add_files(self, paths):
        have = {s.path for s in self.samples}
        added = []
        for p in paths:
            ap = os.path.abspath(p)
            if ap in have:
                continue
            try:
                s = Sample(ap)
            except Exception as e:      # unreadable file: skip but report
                print("skip", p, e)
                continue
            self.samples.append(s)
            added.append(s)
        return added

    def sample(self, name):
        for s in self.samples:
            if s.name == name:
                return s
        return None

    def comp_for(self, s):
        if self.comp_mode == "none":
            return None
        if self.comp_mode == "custom" and self.custom_comp is not None:
            return self.custom_comp
        if s.spill is not None:
            return (s.spill_channels, s.spill)
        return None

    def events(self, s):
        if s.name in self._events:
            self._events.move_to_end(s.name)
            return self._events[s.name]
        ed = EventData(s, self.comp_for(s))
        self._events[s.name] = ed
        while len(self._events) > self.CACHE:
            self._events.popitem(last=False)
        return ed

    def display_channels(self, s):
        comp = self.comp_for(s)
        cc = set(comp[0]) if comp else set()
        out = []
        for c in s.channels:
            out.append("Comp-" + c if c in cc else c)
        return out

    def raw_channel(self, dim):
        return dim[5:] if dim.startswith("Comp-") else dim

    def marker(self, rc, s=None):
        """User label, else this sample's $PnS, else the first non-empty $PnS of any sample
        (some instruments leave marker names out of some files)."""
        if rc in self.labels:
            return self.labels[rc]
        if s is not None and s.markers.get(rc):
            return s.markers[rc]
        for o in self.samples:
            if o.markers.get(rc):
                return o.markers[rc]
        return ""

    def label(self, dim, s=None):
        lab = self.marker(self.raw_channel(dim))
        return f"{dim} :: {lab}" if lab else dim

    def xform(self, dim, s=None):
        rc = self.raw_channel(dim)
        if rc not in self.xforms:
            T = (s.ranges.get(rc) if s else None) or 262144.0
            if rc.lower().startswith("time"):
                self.xforms[rc] = tx.linear(T)
            elif is_scatter(rc):
                self.xforms[rc] = tx.linear(T)
            else:
                self.xforms[rc] = tx.biex(T, W=self._auto_width(dim, s, T))
        return self.xforms[rc]

    def _auto_width(self, dim, s, T):
        """Biex width from the data, as Parks et al. 2006 (the logicle paper) recommend:
        W = (M - log10(T / |r|)) / 2, r = 5th percentile of the negative values."""
        M = 4.5 + math.log10(T / 262144.0)
        try:
            v = self.events(s).col(dim) if s is not None else None
        except KeyError:
            v = None
        if v is None:
            return 0.5
        neg = v[v < 0]
        if len(neg) < max(50, 0.005 * len(v)):
            return 0.5
        r = abs(np.percentile(neg, 5))
        W = (M - math.log10(T / r)) / 2 if r > 0 else 0.5
        return float(min(max(W, 0.3), M / 2 - 0.05))

    def set_xform(self, dim, spec):
        self.xforms[self.raw_channel(dim)] = spec

    # --- gates
    def pop(self, path):
        for p in self.pops:
            if p["path"] == path:
                return p
        return None

    def children(self, path):
        return [p for p in self.pops if p["parent"] == path]

    def gate_for(self, path, sname):
        ov = self.overrides.get(sname, {})
        if path in ov:
            return ov[path]
        return self.pop(path)["gate"]

    def unique_path(self, parent, name):
        base = (parent if parent != "root" else "") + "/" + name
        path, i = base, 2
        while self.pop(path):
            path = f"{base} ({i})"
            i += 1
        return path

    def add_pop(self, parent, name, gate):
        path = self.unique_path(parent, name)
        p = {"path": path, "name": path.rsplit("/", 1)[1], "parent": parent, "gate": gate}
        # insert after the parent's last descendant, so parents precede children
        idx = len(self.pops)
        if parent != "root":
            for i, q in enumerate(self.pops):
                if q["path"] == parent or q["path"].startswith(parent + "/"):
                    idx = i + 1
        self.pops.insert(idx, p)
        self.changed(label="add %s" % p["name"])
        return p

    def set_gate(self, path, gate, sname=None):
        name = (self.pop(path) or {}).get("name", "gate")
        if sname is not None:
            self.overrides.setdefault(sname, {})[path] = gate
            self.changed(label="adjust %s for %s" % (name, sname))
        else:
            self.pop(path)["gate"] = gate
            self.changed(label="move %s" % name)

    def clear_override(self, path, sname):
        self.overrides.get(sname, {}).pop(path, None)
        self.changed(label="reset %s on %s" % (path.rsplit("/", 1)[-1], sname))

    def has_override(self, path, sname):
        return path in self.overrides.get(sname, {})

    def delete_pop(self, path):
        gone = {p["path"] for p in self.pops if p["path"] == path or p["path"].startswith(path + "/")}
        self.pops = [p for p in self.pops if p["path"] not in gone]
        for ov in self.overrides.values():
            for g in list(ov):
                if g in gone:
                    del ov[g]
        self.stat_defs = [d for d in self.stat_defs if d["pop"] not in gone and d.get("arg") not in gone]
        self.changed(label="delete %s" % path.rsplit("/", 1)[-1])

    def rename_pop(self, path, new_name):
        p = self.pop(path)
        new_path = self.unique_path(p["parent"], new_name)
        for q in self.pops:
            if q["path"] == path or q["path"].startswith(path + "/"):
                q["path"] = new_path + q["path"][len(path):]
            if q["parent"] == path or q["parent"].startswith(path + "/"):
                q["parent"] = new_path + q["parent"][len(path):]
        old_name = p["name"]
        p["name"] = new_path.rsplit("/", 1)[1]
        for ov in self.overrides.values():
            for k in list(ov):
                if k == path or k.startswith(path + "/"):
                    ov[new_path + k[len(path):]] = ov.pop(k)
        for d in self.stat_defs:
            for key in ("pop", "arg"):
                v = d.get(key)
                if isinstance(v, str) and (v == path or v.startswith(path + "/")):
                    d[key] = new_path + v[len(path):]
        self.changed(label="rename %s to %s" % (old_name, p["name"]))
        return new_path

    # --- undo
    # Only the analysis state is snapshotted: the loaded samples and their event
    # arrays are untouched, so a snapshot costs almost nothing and undo never
    # re-reads an FCS file.
    SNAPSHOT_FIELDS = ("pops", "overrides", "xforms", "labels", "stat_defs",
                       "annot_cols", "annotations", "comp_mode")

    def snapshot(self):
        return {f: copy.deepcopy(getattr(self, f)) for f in self.SNAPSHOT_FIELDS}

    def _restore(self, snap):
        for f, v in snap.items():
            setattr(self, f, copy.deepcopy(v))
        self._masks.clear()
        self.version += 1

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def undo_label(self):
        return self._undo[-1][1] if self._undo else None

    def redo_label(self):
        return self._redo[-1][1] if self._redo else None

    def undo(self):
        """Step back one edit. Returns the label of what was undone, or None."""
        if not self._undo:
            return None
        snap, label = self._undo.pop()
        self._redo.append((self.snapshot(), label))
        self._restore(snap)
        self._prev = snap
        return label

    def redo(self):
        if not self._redo:
            return None
        snap, label = self._redo.pop()
        self._undo.append((self.snapshot(), label))
        self._restore(snap)
        self._prev = snap
        return label

    def clear_undo(self):
        """Called after open/load: the file as opened is the baseline."""
        self._undo.clear()
        self._redo.clear()
        self._prev = self.snapshot()

    def changed(self, events=False, label=None):
        # push the state as it was *before* this edit
        self._undo.append((self._prev, label))
        if len(self._undo) > self.UNDO_DEPTH:
            self._undo.pop(0)
        self._redo.clear()
        self._prev = self.snapshot()
        self._masks.clear()
        if events:
            self._events.clear()
        self.version += 1

    def masks(self, s):
        if s.name in self._masks:
            return self._masks[s.name]
        m = build_masks(self.events(s), self.pops,
                        lambda p: self.gate_for(p["path"], s.name))
        self._masks[s.name] = m
        return m

    def stats(self, s):
        m = self.masks(s)
        n = int(m["root"].sum())
        out = {"root": (n, 100.0, 100.0)}
        for p in self.pops:
            if p["path"] not in m:
                continue
            c = int(m[p["path"]].sum())
            par = int(m[p["parent"]].sum()) if p["parent"] in m else n
            out[p["path"]] = (c, 100.0 * c / par if par else 0.0, 100.0 * c / n if n else 0.0)
        return out

    # --- save / load
    def to_dict(self):
        return {
            "format": "cytolux-workspace", "version": 1,
            "samples": [s.path for s in self.samples],
            "comp_mode": self.comp_mode,
            "custom_comp": None if self.custom_comp is None else
            {"channels": self.custom_comp[0], "matrix": np.asarray(self.custom_comp[1]).tolist()},
            "pops": self.pops, "overrides": self.overrides,
            "xforms": self.xforms, "labels": self.labels,
            "stat_defs": self.stat_defs, "annot_cols": self.annot_cols, "annotations": self.annotations,
        }

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=1)
        self.path = path

    @classmethod
    def load(cls, path, relocate=None):
        d = json.load(open(path))
        ws = cls()
        files = []
        for p in d["samples"]:
            if not os.path.exists(p):
                alt = os.path.join(os.path.dirname(os.path.abspath(path)), os.path.basename(p))
                if os.path.exists(alt):
                    p = alt
                elif relocate:
                    p = relocate(p)
            if p and os.path.exists(p):
                files.append(p)
        ws.add_files(files)
        ws.comp_mode = d.get("comp_mode", "file")
        cc = d.get("custom_comp")
        if cc:
            ws.custom_comp = (cc["channels"], np.array(cc["matrix"]))
        ws.pops = d.get("pops", [])
        ws.overrides = d.get("overrides", {})
        ws.xforms = d.get("xforms", {})
        ws.labels = d.get("labels", {})
        ws.stat_defs = d.get("stat_defs", [])
        ws.annot_cols = d.get("annot_cols", [])
        ws.annotations = d.get("annotations", {})
        ws.path = path
        ws.clear_undo()
        return ws


# ----------------------------------------------------------------------------- statistics

STATS = {
    # name: (needs channel, description)
    "Count": (False, "Number of events in the population"),
    "% of parent": (False, "Percent of the parent population"),
    "% of total": (False, "Percent of all events in the file"),
    "% of": (False, "Percent of a chosen ancestor population"),
    "Median": (True, "Median intensity (what FlowJo calls Median; the usual 'MFI')"),
    "Mean": (True, "Arithmetic mean intensity"),
    "Geometric mean": (True, "Geometric mean (positive events only, as FlowJo)"),
    "SD": (True, "Standard deviation"),
    "CV": (True, "Coefficient of variation, % (SD / mean)"),
    "Robust CV": (True, "FlowJo's rCV, %: half the 15.87th to 84.13th percentile spread / median"),
    "Percentile": (True, "Intensity at a chosen percentile"),
}
PERCENT_STATS = {"% of parent", "% of total", "% of", "CV", "Robust CV"}


def stat_name(d, ws=None, s=None):
    if d.get("name"):
        return d["name"]
    pop = "All events" if d["pop"] == "root" else d["pop"].rsplit("/", 1)[1]
    st = d["stat"]
    if st == "% of":
        anc = "All events" if d.get("arg") in (None, "root") else d["arg"].rsplit("/", 1)[1]
        st = f"% of {anc}"
    elif st == "Percentile":
        st = f"{d.get('arg', 50):g}th percentile"
    if STATS[d["stat"]][0]:
        ch = d["channel"]
        lab = ws.label(ch, s).split(" :: ")[-1] if ws is not None else ch
        return f"{pop} | {st} {lab}"
    return f"{pop} | {st}"


def compute_stat(ws, s, d):
    m = ws.masks(s)
    if d["pop"] not in m:
        return float("nan")
    mask = m[d["pop"]]
    n = int(mask.sum())
    st = d["stat"]
    if st == "Count":
        return n
    if st == "% of parent":
        par = ws.pop(d["pop"])["parent"] if d["pop"] != "root" else "root"
        den = int(m[par].sum())
        return 100.0 * n / den if den else float("nan")
    if st == "% of total":
        den = int(m["root"].sum())
        return 100.0 * n / den if den else float("nan")
    if st == "% of":
        anc = d.get("arg") or "root"
        if anc not in m:
            return float("nan")
        den = int(m[anc].sum())
        return 100.0 * n / den if den else float("nan")
    if n == 0:
        return float("nan")
    try:
        v = ws.events(s).col(d["channel"])[mask]
    except KeyError:
        return float("nan")
    if st == "Median":
        return float(np.median(v))
    if st == "Mean":
        return float(np.mean(v))
    if st == "Geometric mean":
        p = v[v > 0]
        return float(np.exp(np.mean(np.log(p)))) if len(p) else float("nan")
    if st == "SD":
        return float(np.std(v, ddof=1)) if n > 1 else float("nan")
    if st == "CV":
        mu = np.mean(v)
        return float(100 * np.std(v, ddof=1) / mu) if n > 1 and mu != 0 else float("nan")
    if st == "Robust CV":
        med = np.median(v)
        lo, hi = np.percentile(v, [15.87, 84.13])
        return float(100 * 0.5 * (hi - lo) / med) if med != 0 else float("nan")
    if st == "Percentile":
        return float(np.percentile(v, d.get("arg", 50)))
    raise ValueError(st)


def stats_table(ws, samples=None):
    """DataFrame: one row per sample; annotation columns, then one column per statistic."""
    import pandas as pd
    samples = samples or ws.samples
    rows = []
    for s in samples:
        r = {"Sample": s.name}
        for c in ws.annot_cols:
            r[c] = ws.annotations.get(s.name, {}).get(c, "")
        for d in ws.stat_defs:
            r[stat_name(d, ws, s)] = compute_stat(ws, s, d)
        rows.append(r)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- templates

def template_dict(ws):
    return {"format": "cytolux-template", "version": 1, "pops": ws.pops, "xforms": ws.xforms,
            "labels": ws.labels, "stat_defs": ws.stat_defs, "comp_mode": ws.comp_mode,
            "custom_comp": None if ws.custom_comp is None else
            {"channels": ws.custom_comp[0], "matrix": np.asarray(ws.custom_comp[1]).tolist()}}


def apply_template(ws, d):
    """Put a saved gating tree (and its statistics, axis scales, channel names) onto the
    samples in ws. Returns a list of channels the template uses that the samples lack."""
    ws.pops = copy.deepcopy(d["pops"])
    ws.overrides = {}
    ws.xforms.update(d.get("xforms", {}))
    ws.labels.update(d.get("labels", {}))
    ws.stat_defs = copy.deepcopy(d.get("stat_defs", []))
    if d.get("comp_mode"):
        ws.comp_mode = d["comp_mode"]
    cc = d.get("custom_comp")
    if cc:
        ws.custom_comp = (cc["channels"], np.array(cc["matrix"]))
    ws.changed(events=True)
    have = set()
    for s in ws.samples:
        have |= set(s.channels)
    missing = sorted({ws.raw_channel(dim) for p in ws.pops for dim in p["gate"]["dims"]} - have)
    return missing
