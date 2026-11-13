"""Axis transforms. Every transform maps raw values onto a 0..1 display scale
(the same idea as FlowJo's 0..256 display units), and every one is exactly invertible.

A transform is a plain dict so it can be saved in a workspace:
    {"kind": "linear", "T": 1048576}
    {"kind": "log",    "T": 1048576, "decades": 5}
    {"kind": "biex",   "T": 1048576, "W": 0.5, "M": 5.1, "A": 0}
"""
import math
import numpy as np
import flowkit as fk

_logicle_cache = {}
_wspbiex_cache = {}
WSP_SCALE = 4096.0   # FlowKit's WSPBiexTransform maps onto 0..4096


def _wspbiex(spec):
    key = (spec["T"], spec["W"], spec["P"], spec.get("N", 0.0))
    if key not in _wspbiex_cache:
        _wspbiex_cache[key] = fk.transforms.WSPBiexTransform(
            negative=spec.get("N", 0.0), width=spec["W"], positive=spec["P"], max_value=spec["T"])
    return _wspbiex_cache[key]


def wspbiex(T, width=-10.0, positive=4.41854, negative=0.0):
    """FlowJo 10's own biexponential, as written in a .wsp (width is a negative raw value)."""
    return {"kind": "wspbiex", "T": float(T), "W": float(width),
            "P": float(positive), "N": float(negative)}


def _logicle(spec):
    key = (spec["T"], spec["W"], spec["M"], spec.get("A", 0))
    if key not in _logicle_cache:
        _logicle_cache[key] = fk.transforms.LogicleTransform(
            param_t=spec["T"], param_w=spec["W"], param_m=spec["M"], param_a=spec.get("A", 0))
    return _logicle_cache[key]


def linear(T):
    return {"kind": "linear", "T": float(T)}


def log(T, decades=None):
    T = float(T)
    if decades is None:
        decades = max(1.0, round(math.log10(T)) - 1)
    return {"kind": "log", "T": T, "decades": float(decades)}


def biex(T, W=0.5, M=None, A=0.0):
    T = float(T)
    if M is None:
        M = 4.5 + math.log10(T / 262144.0)
    return {"kind": "biex", "T": T, "W": float(W), "M": float(M), "A": float(A)}


def apply(spec, x):
    x = np.asarray(x, dtype=float)
    k = spec["kind"]
    if k == "linear":
        return x / spec["T"]
    if k == "log":
        lo = math.log10(spec["T"]) - spec["decades"]
        return (np.log10(np.maximum(x, 1e-300)) - lo) / spec["decades"]
    if k == "biex":
        shape = x.shape
        return np.asarray(_logicle(spec).apply(x.reshape(-1))).reshape(shape)
    if k == "wspbiex":
        shape = x.shape
        return np.asarray(_wspbiex(spec).apply(x.reshape(-1))).reshape(shape) / WSP_SCALE
    raise ValueError(k)


def inverse(spec, y):
    y = np.asarray(y, dtype=float)
    k = spec["kind"]
    if k == "linear":
        return y * spec["T"]
    if k == "log":
        lo = math.log10(spec["T"]) - spec["decades"]
        return 10.0 ** (y * spec["decades"] + lo)
    if k == "biex":
        shape = y.shape
        return np.asarray(_logicle(spec).inverse(y.reshape(-1))).reshape(shape)
    if k == "wspbiex":
        shape = y.shape
        return np.asarray(_wspbiex(spec).inverse(
            np.clip(y.reshape(-1), 0.0, 1.0) * WSP_SCALE)).reshape(shape)
    raise ValueError(k)


def convert(value, src, dst):
    """Re-express a coordinate given in one transform's display space in another's."""
    if value is None:
        return None
    if src == dst:
        return value
    return float(apply(dst, inverse(src, value)))


def same(a, b):
    if a["kind"] != b["kind"]:
        return False
    return all(abs(a.get(k, 0) - b.get(k, 0)) < 1e-9 * max(1, abs(a.get(k, 0))) for k in a if k != "kind")


def _fmt(v):
    a = abs(v)
    if a == 0:
        return "0"
    if a >= 1e6:
        s = f"{v / 1e6:g}M"
    elif a >= 1e3:
        s = f"{v / 1e3:g}K"
    else:
        s = f"{v:g}"
    return s


def ticks(spec):
    """Return (major [(pos, label)], minor [pos]) in display units for an axis."""
    k = spec["kind"]
    T = spec["T"]
    major, minor = [], []
    if k == "linear":
        step = 10 ** math.floor(math.log10(T / 5))
        for m in (1, 2, 5):
            if T / (step * m) <= 6:
                step *= m
                break
        v = 0.0
        while v <= T * 1.0001:
            major.append((v / T, _fmt(v)))
            v += step
        return major, minor
    hi = int(math.floor(math.log10(T)))
    lo = int(math.ceil(math.log10(T) - spec["decades"])) if k == "log" else 1
    if k in ("biex", "wspbiex"):
        major.append((float(apply(spec, 0.0)), "0"))
        # negative decades that are still on scale
        for e in range(1, hi + 1):
            p = float(apply(spec, -(10.0 ** e)))
            if p >= 0:
                major.append((p, f"-10^{e}"))
                for m in range(2, 10):
                    q = float(apply(spec, -m * 10.0 ** e))
                    if q >= 0:
                        minor.append(q)
    for e in range(lo, hi + 1):
        p = float(apply(spec, 10.0 ** e))
        if 0 <= p <= 1.0001:
            major.append((p, f"10^{e}"))
        for m in range(2, 10):
            q = float(apply(spec, m * 10.0 ** e))
            if 0 <= q <= 1.0001:
                minor.append(q)
    if k in ("biex", "wspbiex"):
        # drop labels that would crowd the zero region
        major.sort()
        kept = []
        for p, lab in major:
            if kept and p - kept[-1][0] < 0.035:
                continue
            kept.append((p, lab))
        major = kept
    return major, minor
