"""Import a FlowJo 10 workspace (.wsp): gate geometry and hierarchy per sample.

FlowJo stores rectangle and polygon coordinates in raw (compensated, untransformed) units, and
ellipses in display units (0..256 on linear axes). Both are converted into FlowGate gates on
linear axes scaled 0..1 (raw / $PnR, display / 256), which are the same shapes, exactly.
"""
import json
import math
import os
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter

from . import transforms as tx

GNS = "{http://www.isac-net.org/std/Gating-ML/v2.0/gating}"
DNS = "{http://www.isac-net.org/std/Gating-ML/v2.0/datatypes}"


def _dims(gate):
    return [d.find(DNS + "fcs-dimension").get(DNS + "name") for d in gate.findall(GNS + "dimension")]


def _coords(vertex):
    return [float(c.get(DNS + "value")) for c in vertex.findall(GNS + "coordinate")]


def parse_gate(gate):
    kind = gate.tag.replace(GNS, "")
    out = {"type": kind, "dims": _dims(gate)}
    if kind == "RectangleGate":
        out["min"], out["max"] = [], []
        for d in gate.findall(GNS + "dimension"):
            mn, mx = d.get(GNS + "min"), d.get(GNS + "max")
            out["min"].append(float(mn) if mn is not None else None)
            out["max"].append(float(mx) if mx is not None else None)
    elif kind == "PolygonGate":
        out["vertices"] = [_coords(v) for v in gate.findall(GNS + "vertex")]
    elif kind == "EllipsoidGate":
        out["foci"] = [_coords(v) for v in gate.find(GNS + "foci").findall(GNS + "vertex")]
        out["edge"] = [_coords(v) for v in gate.find(GNS + "edge").findall(GNS + "vertex")]
    out["eventsInside"] = gate.get(GNS + "eventsInside", "1") != "0"
    return out


def _walk(node, parent_path, acc):
    for sub in node.findall("Subpopulations"):
        for pop in sub.findall("Population"):
            name = pop.get("name")
            path = parent_path + "/" + name
            gate_el = pop.find("Gate")
            g = parse_gate(list(gate_el)[0]) if gate_el is not None and len(gate_el) else None
            acc.append({"path": path, "parent": parent_path or "root", "name": name,
                        "count": int(pop.get("count", "-1")), "gate": g})
            _walk(pop, path, acc)


def parse_wsp(path):
    """-> {fcs file name: {"total": n, "uri": path, "populations": [...]}}"""
    root = ET.parse(path).getroot()
    result = {}
    for s in root.iter("Sample"):
        ds = s.find("DataSet")
        uri = urllib.parse.unquote(ds.get("uri", ""))
        fname = uri.replace("file:", "").split("/")[-1]
        sn = s.find("SampleNode")
        pops = []
        _walk(sn, "", pops)
        result[fname] = {"total": int(sn.get("count", "-1")), "uri": uri.replace("file:", ""),
                         "populations": pops}
    return result


def to_flowgate_gate(fj, ranges):
    """FlowJo gate dict -> FlowGate gate dict. ranges: channel -> $PnR."""
    if fj is None:
        return None
    dims = fj["dims"]

    def T(d):
        rc = d[5:] if d.startswith("Comp-") else d
        return ranges.get(rc, 262144.0)

    xfs = [tx.linear(T(d)) for d in dims]
    t = fj["type"]
    if t == "RectangleGate":
        g = {"type": "rect", "dims": dims, "xf": xfs,
             "min": [None if v is None else v / T(d) for v, d in zip(fj["min"], dims)],
             "max": [None if v is None else v / T(d) for v, d in zip(fj["max"], dims)]}
    elif t == "PolygonGate":
        g = {"type": "poly", "dims": dims, "xf": xfs,
             "vertices": [[v[0] / T(dims[0]), v[1] / T(dims[1])] for v in fj["vertices"]]}
    elif t == "EllipsoidGate":
        f1, f2 = [[c / 256.0 for c in p] for p in fj["foci"]]
        e1, e2 = [[c / 256.0 for c in p] for p in fj["edge"][:2]]
        a = math.dist(e1, e2) / 2.0
        c = math.dist(f1, f2) / 2.0
        b = math.sqrt(max(a * a - c * c, 1e-12))
        g = {"type": "ellipse", "dims": dims, "xf": xfs,
             "center": [(f1[0] + f2[0]) / 2, (f1[1] + f2[1]) / 2], "axes": [a, b],
             "angle": math.degrees(math.atan2(f2[1] - f1[1], f2[0] - f1[0]))}
    else:
        return None
    if not fj.get("eventsInside", True):
        g["invert"] = True
    return g


def import_into(ws, wsp_path, ranges=None):
    """Load a .wsp into a Workspace that already holds the FCS files.
    The most common gate for each population becomes the group gate; samples whose gate
    differs get a per-sample override (as in FlowJo, where gates can be adjusted per sample).
    Returns (n_matched_samples, flowjo_counts {sample: {path: count}}, skipped gate types)."""
    data = parse_wsp(wsp_path)
    names = {s.name: s for s in ws.samples}
    if ranges is None:
        ranges = {}
        for s in ws.samples:
            for c, r in s.ranges.items():
                ranges.setdefault(c, r)
    per_sample, order, parents, fj_counts, skipped = {}, [], {}, {}, Counter()
    for fname, rec in data.items():
        if fname not in names:
            continue
        per_sample[fname] = {}
        fj_counts[fname] = {"root": rec["total"]}
        for p in rec["populations"]:
            g = to_flowgate_gate(p["gate"], ranges)
            if g is None:
                skipped[(p["gate"] or {}).get("type", "none")] += 1
                continue
            if p["path"] not in parents:
                order.append(p["path"])
                parents[p["path"]] = (p["parent"], p["name"])
            per_sample[fname][p["path"]] = g
            fj_counts[fname][p["path"]] = p["count"]
    for path in order:
        variants = Counter(json.dumps(per_sample[s][path], sort_keys=True)
                           for s in per_sample if path in per_sample[s])
        group = json.loads(variants.most_common(1)[0][0])
        parent, name = parents[path]
        if ws.pop(path) is None:
            ws.pops.append({"path": path, "name": name, "parent": parent, "gate": group})
        else:
            ws.pop(path)["gate"] = group
        gkey = json.dumps(group, sort_keys=True)
        for s, gates in per_sample.items():
            if path in gates and json.dumps(gates[path], sort_keys=True) != gkey:
                ws.overrides.setdefault(s, {})[path] = gates[path]
    # FlowJo shows these channels on linear axes; keep the user's view consistent with the gates
    ws.changed()
    return len(per_sample), fj_counts, dict(skipped)


def fcs_candidates(wsp_path):
    """FCS files referenced by the workspace, searched next to the .wsp if the original path moved."""
    data = parse_wsp(wsp_path)
    base = os.path.dirname(os.path.abspath(wsp_path))
    found = []
    index = {}
    for dirpath, _, files in os.walk(base):
        for f in files:
            if f.lower().endswith(".fcs"):
                index.setdefault(f, os.path.join(dirpath, f))
    for fname, rec in data.items():
        if os.path.exists(rec["uri"]):
            found.append(rec["uri"])
        elif fname in index:
            found.append(index[fname])
    return found, len(data)
