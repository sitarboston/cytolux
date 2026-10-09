"""Build a panel chart: which detector carries which marker, on which laser, in a set of FCS files.

Everything here is read from the FCS headers themselves ($PnN, $PnS, $PnV, $PnR, laser and
filter keywords), so it describes what the cytometer actually recorded, not what a protocol said.

Usage:
    python -m flowgate.tools.panel_chart <folder-or-fcs> [more folders...] -o out_prefix
Writes <out_prefix>.xlsx (one sheet per experiment plus a combined sheet) and prints the chart.
"""
import argparse
import glob
import os
import re
import sys
from collections import Counter, OrderedDict

import pandas as pd
import flowkit as fk

# Laser lines by channel-name prefix.
# Attune NxT uses BL/YL/RL/VL; BD (LSRFortessa, LSRII) uses one letter per laser.
ATTUNE = {"BL": ("Blue", "488 nm"), "YL": ("Yellow-green", "561 nm"),
          "RL": ("Red", "638 nm"), "VL": ("Violet", "405 nm"),
          "UV": ("Ultraviolet", "355 nm")}
BD = {"B": ("Blue", "488 nm"), "V": ("Violet", "405 nm"), "R": ("Red", "640 nm"),
      "G": ("Green", "561 nm"), "U": ("Ultraviolet", "355 nm"), "Y": ("Yellow-green", "561 nm")}
SCATTER = ("FSC", "SSC", "Time", "Event")


def laser_of(chan):
    """-> (laser name, wavelength, detector number) from a channel name such as YL1-A or V450-A."""
    base = chan.split("-")[0]
    if chan.startswith(SCATTER):
        return ("", "", "")
    m = re.match(r"^([A-Z]{2})(\d+)$", base)
    if m and m.group(1) in ATTUNE:
        return ATTUNE[m.group(1)] + (m.group(2),)
    m = re.match(r"^([BVRGUY])(\d{3})$", base)          # BD style: V450 = violet laser, 450/50 filter
    if m and m.group(1) in BD:
        return BD[m.group(1)] + (m.group(2) + " nm filter",)
    m = re.match(r"^([BVRGUY])(\d+)$", base)
    if m and m.group(1) in BD:
        return BD[m.group(1)] + (m.group(2),)
    return ("", "", "")


# Fluorochrome names that often appear inside the marker string, longest first so that
# "APC-Cy7" is found before "APC".
DYES = ["Alexa Fluor 700", "Alexa Fluor 647", "Alexa Fluor 488", "Brilliant Violet 785",
        "Brilliant Violet 711", "Brilliant Violet 650", "Brilliant Violet 605",
        "Brilliant Violet 570", "Brilliant Violet 510", "Brilliant Violet 421",
        "eFluor 450", "eFluor 506", "Fixable Aqua", "Live Dead", "Zombie",
        "PerCP-Cy5.5", "PerCP-eFluor710", "PerCP", "APC-Cy7", "APC-Fire750", "APC-R700",
        "APC-eFluor780", "APC", "PE-Cy7", "PE-Cy5", "PE-Dazzle", "PE-CF594", "R-PE", "PE",
        "FITC", "BV785", "BV711", "BV650", "BV605", "BV570", "BV510", "BV421", "BUV395",
        "BUV737", "PB", "Pacific Blue", "AF700", "AF647", "AF488", "GFP", "mCherry"]


def split_marker(pns):
    """'CAR CD20-R-PE-A' -> ('CAR CD20', 'R-PE'). Returns (antigen, fluorochrome)."""
    s = (pns or "").strip()
    if not s:
        return "", ""
    s = re.sub(r"-[AHW]$", "", s).strip()
    for d in DYES:
        for pat in (d, d.replace(" ", "")):
            i = s.lower().rfind(pat.lower())
            if i >= 0:
                antigen = s[:i].rstrip(" -_")
                return (antigen or s), s[i:i + len(pat)]
    # any Brilliant Violet / Brilliant Blue / BV / BUV number not in the list above
    m = re.search(r"(Brilliant (?:Violet|Blue|Ultra Violet)\s*\d+|B[UV]V?\d{3})\s*$", s, re.I)
    if m:
        return s[:m.start()].rstrip(" -_") or s, m.group(1)
    return s, ""


def read_panel(path):
    s = fk.Sample(path, ignore_offset_error=True)
    rows = []
    for i, (pnn, pns) in enumerate(zip(s.pnn_labels, s.pns_labels), start=1):
        laser, wl, det = laser_of(pnn)
        antigen, dye = split_marker(pns)
        rows.append({"Detector": pnn, "Laser": laser, "Excitation": wl, "Channel no.": det,
                     "Marker (as recorded)": (pns or "").strip(), "Antigen": antigen,
                     "Fluorochrome": dye,
                     "Voltage": s.metadata.get(f"p{i}v", ""),
                     "Range": s.metadata.get(f"p{i}r", "")})
    meta = {"Cytometer": s.metadata.get("cyt", ""), "Date": s.metadata.get("date", ""),
            "Events": s.event_count, "Spillover in file": bool(s.metadata.get("spill") or
                                                               s.metadata.get("spillover")),
            "Software": s.metadata.get("creator", "") or s.metadata.get("sys", "")}
    return rows, meta


def panel_for_folder(folder, max_files=400):
    files = sorted(glob.glob(os.path.join(folder, "**", "*.fcs"), recursive=True))
    files = [f for f in files if not os.path.basename(f).startswith("._")][:max_files]
    if not files:
        return None, None, []
    base, meta = read_panel(files[0])
    # check every file agrees, and note any that differ
    key0 = tuple((r["Detector"], r["Marker (as recorded)"]) for r in base)
    differing = []
    seen_markers = {r["Detector"]: Counter() for r in base}
    for f in files:
        rows, _ = read_panel(f)
        for r in rows:
            if r["Detector"] in seen_markers and r["Marker (as recorded)"]:
                seen_markers[r["Detector"]][r["Marker (as recorded)"]] += 1
        if tuple((r["Detector"], r["Marker (as recorded)"]) for r in rows) != key0:
            differing.append(os.path.basename(f))
    for r in base:
        c = seen_markers.get(r["Detector"], Counter())
        if c:
            r["Marker (as recorded)"] = c.most_common(1)[0][0]
            antigen, dye = split_marker(r["Marker (as recorded)"])
            r["Antigen"], r["Fluorochrome"] = antigen, dye
            if len(c) > 1:
                r["Note"] = "also recorded as: " + "; ".join(f"{k} ({v}x)" for k, v in c.most_common()[1:])
    meta["Files"] = len(files)
    return base, meta, differing


def to_frame(rows):
    cols = ["Detector", "Laser", "Excitation", "Antigen", "Fluorochrome",
            "Marker (as recorded)", "Voltage", "Note"]
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df:
            df[c] = ""
    df = df[cols].fillna("")
    return df


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("-o", "--out", default="panel_chart")
    args = ap.parse_args(argv)
    sheets = OrderedDict()
    for p in args.paths:
        name = os.path.basename(os.path.normpath(p))
        parent = os.path.basename(os.path.dirname(os.path.normpath(p)))
        if name.lower().startswith(("24h", "day", "fcs")) or name[:31] in sheets:
            name = f"{parent[:14]} {name}"            # keep sheet names unique and readable
        rows, meta, differing = panel_for_folder(p) if os.path.isdir(p) else (read_panel(p)[0], read_panel(p)[1], [])
        if not rows:
            print(f"(no FCS files in {p})")
            continue
        df = to_frame(rows)
        sheets[name[:31]] = (df, meta, differing)
        print(f"\n=== {name}  —  {meta.get('Cytometer','?')}, {meta.get('Files', 1)} files, "
              f"spillover in file: {'yes' if meta['Spillover in file'] else 'no'}")
        fl = df[df["Laser"] != ""]
        print(fl.drop(columns=["Note"]).to_string(index=False))
        if differing:
            print(f"  note: {len(differing)} file(s) carry different labels, e.g. {differing[:3]}")
    out = args.out if args.out.endswith(".xlsx") else args.out + ".xlsx"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        for name, (df, meta, differing) in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False, startrow=len(meta) + 2)
            sh = xw.sheets[name]
            for i, (k, v) in enumerate(meta.items(), start=1):
                sh.cell(i, 1, k).font = sh.cell(i, 1).font.copy(bold=True)
                sh.cell(i, 2, str(v))
            for j, width in enumerate([14, 14, 12, 22, 20, 30, 10, 40], start=1):
                sh.column_dimensions[chr(64 + j)].width = width
            for c in sh[len(meta) + 3]:
                c.font = c.font.copy(bold=True)
    print(f"\nWritten: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
