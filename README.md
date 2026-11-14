# Cytolux

A desktop app for looking at and gating flow cytometry data (FCS 2.0/3.0/3.1). Local only.

**Start:** Cytolux in the applications menu, or `~/cytolux/cytolux.sh [workspace.fgw | fcs_folder]`.
Press F1 in the app for the quick guide.

- Pseudocolor, dot and histogram plots; Linear, Log and Biex (logicle) axes, biex width set from the data.
- Rectangle, polygon, ellipse, quadrant and range gates; drag to edit; gate tree with counts, % parent, % total.
- One gate tree for all samples, with per-sample adjustments where needed.
- Compensation from the FCS file (FlowJo "acquisition-defined"), a CSV matrix, or edited by hand.
- Import FlowJo 10 workspaces (.wsp); every count is checked against FlowJo's (Help menu).
- All-samples grid; statistics table; export to Excel and PNG; workspaces saved as .fgw (JSON).
- Undo and redo (Ctrl+Z), a sample filter, a tooltip on every control, and an offline help search (Ctrl+/).
- **Confidence intervals on every frequency (Ctrl+U).** A gated percentage is a count divided by a
  line somebody drew with a mouse. Cytolux displaces every boundary in the tree by about as much as a
  careful hand would, re-gates the file from the root, and reports where each percentage went. It
  separates the two reasons a number is shaky, because they call for opposite fixes: a boundary on a
  continuum means redraw the gate, too few events means go and acquire more. Confidence → Find the
  weakest gates sweeps the whole workspace and sorts worst first. No commercial flow package does this.

Engine check against FlowJo: `python -m tests.validate_flowjo <fcs_folder> <workspace.wsp>`.
Requires Python 3.12 with PySide6, pyqtgraph, FlowKit, numpy, scipy and pandas.
