# FlowGate

A desktop app for looking at and gating flow cytometry data (FCS 2.0/3.0/3.1). Local only.

**Start:** FlowGate in the applications menu, or `~/flowgate/flowgate.sh [workspace.fgw | fcs_folder]`.
Press F1 in the app for the quick guide.

- Pseudocolor, dot and histogram plots; Linear, Log and Biex (logicle) axes, biex width set from the data.
- Rectangle, polygon, ellipse, quadrant and range gates; drag to edit; gate tree with counts, % parent, % total.
- One gate tree for all samples, with per-sample adjustments where needed.
- Compensation from the FCS file (FlowJo "acquisition-defined"), a CSV matrix, or edited by hand.
- Import FlowJo 10 workspaces (.wsp); every count is checked against FlowJo's (Help menu).
- All-samples grid; statistics table; export to Excel and PNG; workspaces saved as .fgw (JSON).

Engine check against FlowJo: `python -m tests.validate_flowjo <fcs_folder> <workspace.wsp>`.
Environment: conda env `flowgate` (Python 3.12, PySide6, pyqtgraph, FlowKit).
