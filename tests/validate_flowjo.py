"""Check Cytolux's gating engine against FlowJo: import a .wsp, re-gate the raw FCS files,
compare every population count with the count FlowJo saved in the workspace.
Usage: python -m tests.validate_flowjo <fcs_folder> <workspace.wsp>"""
import glob, os, sys, time
from cytolux.engine import Workspace
from cytolux import wsp

fcs_dir, wsp_path = sys.argv[1], sys.argv[2]
t0 = time.time()
ws = Workspace()
ws.add_files(sorted(glob.glob(os.path.join(fcs_dir, "*.fcs"))))
n, fj, skipped = wsp.import_into(ws, wsp_path)
print(f"{len(ws.samples)} files, {n} gated in FlowJo, {len(ws.pops)} populations, "
      f"{sum(len(v) for v in ws.overrides.values())} per-sample overrides, skipped {skipped}")
worst = {}
exact = total = 0
for sname, counts in fj.items():
    st = ws.stats(ws.sample(sname))
    root = st["root"][0]
    for path, c in counts.items():
        mine = st[path][0]
        par = ws.pop(path)["parent"] if path != "root" else None
        total += 1
        exact += mine == c
        pp_fj = 100 * c / counts[par] if par and counts.get(par) else 0
        pp_me = 100 * mine / st[par][0] if par and st[par][0] else 0
        d = abs(pp_fj - pp_me)
        w = worst.get(path, (0, 0))
        worst[path] = (max(w[0], abs(mine - c)), max(w[1], d))
print(f"exact counts: {exact}/{total}")
for p, (dc, dp) in worst.items():
    print(f"  {p:55s} max |count diff| {dc:5d}   max |%parent diff| {dp:.4f} pp")
print(f"{time.time()-t0:.1f}s")
