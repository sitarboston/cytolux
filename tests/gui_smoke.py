"""Headless GUI run-through on a real dataset. Usage: python -m tests.gui_smoke <fcs_dir> <wsp> <outdir>"""
import glob, os, sys
from PySide6 import QtWidgets, QtCore
from flowgate.app import MainWindow
from flowgate import wsp

fcs, wspp, out = sys.argv[1:4]
app = QtWidgets.QApplication(sys.argv)
QtWidgets.QMessageBox.information = staticmethod(lambda *a, **k: None)
QtWidgets.QMessageBox.question = staticmethod(  # yes to "add stats then export?", no to "open it now?"
    lambda *a, **k: QtWidgets.QMessageBox.Yes if "No statistics" in a[2] else QtWidgets.QMessageBox.No)
QtWidgets.QInputDialog.getText = staticmethod(lambda *a, **k: ("TestGate", True))
w = MainWindow(); w.resize(1500, 950); w.show()
w.ws.add_files(sorted(glob.glob(os.path.join(fcs, "*.fcs"))))
n, w.fj_counts, sk = wsp.import_into(w.ws, wspp)
w._fill_samples()
# pick a gated sample
w.sample_list.setCurrentRow([s.name for s in w.ws.samples].index(next(iter(w.fj_counts))))
app.processEvents()
def shot(name):
    app.processEvents(); w.grab().save(os.path.join(out, name + ".png"))
shot("01_root")
for p in ["/Lymphocytes", "/Lymphocytes/Single Cells", "/Lymphocytes/Single Cells/live",
          "/Lymphocytes/Single Cells/live/CD4+CD8+"]:
    w._select_pop(p); app.processEvents()
    shot("02_" + p.rsplit("/", 1)[1].replace(" ", "_").replace("+", "p"))
print("tree items ok; plot gates:", len(w.plot.gate_items))
# switch y axis transform to biex on live/CD4CD8 level (polygon becomes read-only outline)
w._select_pop("/Lymphocytes/Single Cells/live")
w.cb_xf_x.setCurrentIndex(2); w.cb_xf_y.setCurrentIndex(2); app.processEvents(); shot("03_biex_outline")
# draw new gates programmatically
w._select_pop("/Lymphocytes/Single Cells/live/CD4+CD8+")
w._set_axes("Comp-YL1-A", "Comp-RL1-A"); app.processEvents()
w._gate_created("rect", (0.6, 0.2, 0.95, 0.9)); app.processEvents()
w._gate_created("ellipse", (0.2, 0.2, 0.4, 0.5)); app.processEvents()
w._gate_created("poly", [(0.1, 0.6), (0.3, 0.9), (0.5, 0.7)]); app.processEvents()
w._gate_created("quad", (0.5, 0.5)); app.processEvents()
shot("04_new_gates")
w._set_axes("Comp-YL1-A", None); app.processEvents()
w._gate_created("range", (0.55, 0, 0.95, 1)); app.processEvents(); shot("05_histogram")
# edit: move the rect gate via the engine path the ROI uses
path = [p["path"] for p in w.ws.pops if p["name"] == "TestGate"][0]
g = dict(w.ws.pop(path)["gate"]); before = w.ws.stats(w.cur_sample)[path][0]
g["min"] = [0.5, 0.2]; w._gate_edited(path, g); after = w.ws.stats(w.cur_sample)[path][0]
print("edit rect count", before, "->", after)
# per-sample override
w._toggle_override(path, True); print("override:", w.ws.has_override(path, w.cur_sample.name))
# overview and stats
w._set_axes("FSC-A", "SSC-A"); w._select_pop("root"); w.tabs.setCurrentIndex(1); app.processEvents(); shot("06_overview")
w.tabs.setCurrentIndex(2); app.processEvents(); shot("07_stats")
w.tabs.setCurrentIndex(0)
# save / reload / export
wf = os.path.join(out, "test.fgw"); w.ws.save(wf)
from flowgate.engine import Workspace
ws2 = Workspace.load(wf)
s = ws2.sample(w.cur_sample.name)
assert ws2.stats(s) == w.ws.stats(w.ws.sample(s.name)), "reload mismatch"
print("save/reload identical;", len(ws2.pops), "pops")
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(out, "stats.xlsx"), ""))
w.export_stats(); print("excel", os.path.getsize(os.path.join(out, "stats.xlsx")))
w.plot.export_png(os.path.join(out, "plot_export.png"))
w._rename(path) ; print("renamed ok")
w.dirty = False
print("DONE")
