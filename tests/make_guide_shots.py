"""Drive Cytolux through a full analysis of PUBLIC data (Good et al. 2022, Figure 6) and
save screenshots for the step-by-step guide. Usage: python -m tests.make_guide_shots <outdir>"""
import glob, json, os, sys
import numpy as np
from PySide6 import QtWidgets, QtCore
from cytolux.app import MainWindow
from cytolux import transforms as tx
from cytolux.stats_ui import AddStatDialog, AnnotateDialog, export_excel
from cytolux.engine import stats_table

out = sys.argv[1]; os.makedirs(out, exist_ok=True)
DEMO = os.path.expanduser("~/flowcyt_data/flowgate_demo")
app = QtWidgets.QApplication(sys.argv)
QtWidgets.QMessageBox.information = staticmethod(lambda *a, **k: None)
QtWidgets.QMessageBox.question = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Yes)
names = iter([])
QtWidgets.QInputDialog.getText = staticmethod(lambda *a, **k: (next(names), True))
w = MainWindow(); w.resize(1440, 900); w.show()

def shot(n, widget=None):
    for _ in range(3): app.processEvents()
    (widget or w).grab().save(os.path.join(out, n + ".png"))

def D(dim, v):   # raw value -> display coordinate on the current axis scale
    return float(tx.apply(w.ws.xform(dim, w.cur_sample), v))

# ---- Part A: first experiment
w._load_files(sorted(glob.glob(f"{DEMO}/Run1_controls/*.fcs")))
w.sample_list.setCurrentRow(0); shot("A1_opened")
w.ws.set_xform("SSC-A", tx.log(262144, 4)); w._sync_xf_widgets(); w.refresh(); shot("A2_ssc_log")
w.cb_xf_y.blockSignals(True)
names = iter(["Cells"])
w._gate_created("poly", [(D("FSC-A", 30000), D("SSC-A", 400)), (D("FSC-A", 30000), D("SSC-A", 20000)),
                         (D("FSC-A", 250000), D("SSC-A", 20000)), (D("FSC-A", 250000), D("SSC-A", 400))])
w.set_tool("poly"); shot("A3_cells")
w.set_tool("pointer")
w._select_pop("/Cells"); w._set_axes("FSC-A", "FSC-H"); w.refresh()
names = iter(["Single cells"])
w._gate_created("poly", [(D("FSC-A", 30000), D("FSC-H", 15000)), (D("FSC-A", 30000), D("FSC-H", 40000)),
                         (D("FSC-A", 250000), D("FSC-H", 250000)), (D("FSC-A", 250000), D("FSC-H", 140000))])
shot("A4_singlets")
w._select_pop("/Cells/Single cells"); w._set_axes("Comp-V525-A", "Comp-V710-A"); w.refresh()
names = iter(["Live"])
w._gate_created("rect", (D("Comp-V525-A", -300), D("Comp-V710-A", -300), D("Comp-V525-A", 2500), D("Comp-V710-A", 250000)))
shot("A5_live")
w._select_pop("/Cells/Single cells/Live"); w._set_axes("Comp-R670-A", "Comp-V710-A"); w.refresh()
w._gate_created("quad", (D("Comp-R670-A", 1500), D("Comp-V710-A", 4000)))
w.sample_list.setCurrentRow(0); w._select_pop("/Cells/Single cells/Live"); shot("A6_quadrant")
w.tabs.setCurrentIndex(1); shot("A7_all_samples"); w.tabs.setCurrentIndex(0)

# the overlay: every control tube on the CAR channel, laid over each other
w.tabs.setCurrentIndex(2)
w.overlay.refresh_channels()
w.overlay.cb_channel.setCurrentIndex(w.overlay.cb_channel.findData("Comp-R670-A"))
w.overlay.cb_source.setCurrentIndex(1)
w.overlay.draw()
shot("A7b_overlay")
w.tabs.setCurrentIndex(0)

# statistics
quad_cd3pos = [p["path"] for p in w.ws.pops if p["name"].endswith("CD3+")]
dlg = AddStatDialog(w.ws, w.cur_sample, w, preselect=quad_cd3pos, channel="Comp-R670-A")
dlg.stat.setCurrentText("Median"); dlg.show(); shot("A8_add_statistic", dlg)
w.ws.stat_defs += dlg.defs(); dlg.close()
w._add_standard_stats()
w.ws.stat_defs = [d for d in w.ws.stat_defs if d["stat"] != "Count" or d["pop"] == "/Cells/Single cells/Live"]
w.tabs.setCurrentIndex(2); w._refresh_table(); shot("A9_statistics")
ad = AnnotateDialog(w.ws, w); ad._wells()
ad.cols = []; ad.t.setColumnCount(0)
c1 = ad._add_col("Group"); c2 = ad._add_col("Tube")
for r, s in enumerate(w.ws.samples):
    ad.t.setItem(r, c1, QtWidgets.QTableWidgetItem("CAR19 product" if s.name.startswith("CAR19") else "Healthy PBMC"))
    tube = s.name.split("Control ")[1].split("_")[0][3:].strip()
    ad.t.setItem(r, c2, QtWidgets.QTableWidgetItem(tube))
ad.show(); shot("A10_annotate", ad); ad.store(); ad.close()
w._refresh_table(); shot("A11_statistics_annotated")
export_excel(w.ws, os.path.join(out, "Run1_statistics.xlsx"))
w.ws.save(os.path.join(out, "Run1_controls.fgw"))
from cytolux.engine import template_dict
json.dump(template_dict(w.ws), open(os.path.join(out, "CAR_T_panel_template.fgt"), "w"), indent=1)
w.tabs.setCurrentIndex(0); w.dirty = False

# ---- Part B: new data with the template
w.ws = type(w.ws)(); w._fill_samples()
w.ws.add_files(sorted(glob.glob(f"{DEMO}/Run2_patients/*.fcs")))
w.ws.pops = []
w.apply_template_file(os.path.join(out, "CAR_T_panel_template.fgt"))
w._select_pop("/Cells/Single cells/Live"); shot("B1_template_applied")
w.tabs.setCurrentIndex(1); shot("B2_all_samples")
w.tabs.setCurrentIndex(2); w._refresh_table(); shot("B3_statistics")
export_excel(w.ws, os.path.join(out, "Run2_statistics.xlsx"))
df = stats_table(w.ws); print(df.iloc[:5, :5].to_string()); print("patients:", len(df))
w.dirty = False
print("DONE")
