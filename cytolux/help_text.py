"""One source of truth for in-app help.

TIPS feeds hover tooltips. TOPICS feeds the built-in assistant, so a question
about a feature and the tooltip on that feature can never drift apart.
"""

# Keyed by the exact menu action text, so a renamed action fails the test
# rather than silently losing its tooltip.
MENU_TIPS = {
    "Open FCS folder…":
        "Open every .fcs file in a folder as a new analysis. Replaces what is currently open.",
    "Add FCS files…":
        "Add more .fcs files to the analysis you already have open. They inherit the existing gates.",
    "Open workspace…":
        "Reopen a saved .fgw analysis: its samples, gates, axes and statistics.",
    "Save workspace":
        "Save samples, gates, axes, statistics and annotations to the current .fgw file.",
    "Save workspace as…":
        "Save the analysis to a new .fgw file, leaving the original untouched.",
    "Import FlowJo workspace (.wsp)…":
        "Read a FlowJo 10 workspace and rebuild its gate tree here. Gates keep the axes FlowJo "
        "drew them on. Use Help, Check against FlowJo counts afterwards to confirm the numbers agree.",
    "Save gating template…":
        "Save just the gate tree and axis settings, with no samples, as a .fgt template you can "
        "apply to future runs of the same panel.",
    "Apply gating template to these samples…":
        "Apply a saved .fgt gate tree to the samples already open. Check every gate level before "
        "trusting the numbers: voltages and staining drift between runs.",
    "New analysis: FCS folder + gating template…":
        "Start a fresh analysis in one step: pick a folder of .fcs files and a .fgt template.",
    "Export statistics to Excel…":
        "Write the statistics table to .xlsx, with sheets for your table, the definitions, every "
        "gate count, and the settings used.",
    "Export plot as image…":
        "Save the plot currently on screen as a .png.",
    "Quit":
        "Close Cytolux. You are asked first if the workspace has unsaved changes.",
    "Use the matrix stored in the files (FlowJo: acquisition-defined)":
        "Compensate using the spillover matrix the cytometer wrote into each .fcs file. This is "
        "what FlowJo calls acquisition-defined, and it is the right default.",
    "No compensation":
        "Show raw uncompensated values. Useful for checking single-stain controls, misleading for "
        "anything else.",
    "Load matrix from CSV…":
        "Use a spillover matrix from a .csv instead of the one in the files. First row and column "
        "are channel names.",
    "View / edit matrix…":
        "Inspect the active spillover matrix and adjust coefficients by hand. Diagonal smears "
        "between two colours mean compensation is wrong.",
    "Undo": "Step back one edit. Gates, renames, deletions and per-sample adjustments are all undoable.",
    "Redo": "Step forward again after an undo.",
    "Rename channels (marker names)…":
        "Give channels readable marker names, so axes read CD3 rather than Comp-V710-A.",
    "Delete selected gate":
        "Delete the selected population and every gate underneath it. This cannot be undone.",
    "Annotate samples (donor, dose…)…":
        "Add your own columns, such as Donor or Dose, to each sample. They travel into the "
        "statistics export so the table is analysis-ready.",
    "Add statistic…":
        "Add a column to the statistics table: frequency of parent, count, median, geometric mean, "
        "percentile and others, for any population and channel.",
    "Measure confidence for this sample":
        "Move every gate by about as much as a careful hand would, re-gate this file, and report "
        "how far each frequency travelled. Separates a number you can quote from one that is an "
        "artifact of where the line landed.",
    "Find the weakest gates in this workspace…":
        "The same measurement across every sample, sorted weakest first, so the gate that cannot "
        "carry the weight being put on it turns up before the numbers reach a figure.",
    "Quick guide":
        "A one-page reminder of the workflow and every keyboard shortcut.",
    "Check against FlowJo counts":
        "Compare every population count with the count FlowJo saved in the imported workspace, and "
        "flag any that differ by more than your tolerance. This is how you prove the gating agrees.",
}

# Keyboard shortcuts, so the assistant can answer "what is the shortcut for X".
SHORTCUTS = {
    "Open FCS folder": "Ctrl+O",
    "Open workspace": "Ctrl+Shift+O",
    "Save workspace": "Ctrl+S",
    "Save workspace as": "Ctrl+Shift+S",
    "Import FlowJo workspace": "Ctrl+I",
    "New analysis from template": "Ctrl+N",
    "Export statistics to Excel": "Ctrl+E",
    "Add statistic": "Ctrl+T",
    "Quit": "Ctrl+Q",
    "Quick guide": "F1",
    "Measure confidence for this sample": "Ctrl+U",
    "Delete the selected gate": "Delete",
    "Go up to the parent population": "Backspace",
    "Previous sample": "PageUp",
    "Next sample": "PageDown",
    "Edit this sample only, on or off": "L",
    "Undo": "Ctrl+Z",
    "Redo": "Ctrl+Shift+Z",
    "Select, Rectangle, Polygon, Ellipse, Quadrant, Range tools": "1 to 6",
    "Cancel drawing and go back to Select": "Esc",
    "Close a polygon": "Enter",
}

TAB_TIPS = {
    "Gating": "Draw and edit gates on the current sample.",
    "All samples": "Every sample on the same two axes, as a grid. Click any plot to open that sample.",
    "Overlay": "Histograms of several samples, or several gates, laid over each other on one channel. The plot for “did it shift?”.",
    "Statistics": "The numbers from your gates for every sample, ready to export to Excel.",
}

WIDGET_TIPS = {
    "sample_list": "Every open sample. Click to view it; PageUp and PageDown step through.",
    "tree": "The gate hierarchy, with the count, % of parent and % of total for the current sample. "
            "Italic means this sample has its own adjusted copy of that gate.",
    "cb_x": "Channel on the X axis.",
    "ask": "Ask how to do something, in your own words. Searches the built-in guide; "
           "nothing leaves this machine.  [Ctrl+/]",
    "cb_y": "Channel on the Y axis. Choose [Histogram] to plot a single channel.",
    "cb_xf_x": "How the X axis is scaled. Biex keeps negative events visible near zero.",
    "cb_xf_y": "How the Y axis is scaled. Biex keeps negative events visible near zero.",
    "cb_mode": "Pseudocolor shades by event density. Contour draws black equal-probability lines, the convention in published figures, and stays sharp at any export size. Dots draws one point per event.",
    "uncertainty_run":
        "Run the measurement on this sample. Nothing here recomputes on its own, because two "
        "hundred re-gatings on every mouse release would make gating unusable.",
    "uncertainty_sigma":
        "How precisely you place a boundary, as a percentage of the axis. One percent is a careful "
        "hand on a familiar panel. Raise it to ask what a sloppier day would cost. The same "
        "fraction applies on a biexponential axis as on a linear one.",
    "uncertainty_reps":
        "How many times to re-gate the file. More runs give a steadier interval and take "
        "proportionally longer. Two hundred is plenty to read a grade off; use more if the "
        "interval itself is going into a figure.",
    "uncertainty_level":
        "How much of the spread the interval covers. 95 % is the usual choice and means what a "
        "confidence interval means everywhere else.",
    "uncertainty_only_bad":
        "Hide the populations that held still, leaving only the ones worth looking at.",
    "sample_filter": "Type part of a sample name to narrow the list. Useful on a full plate.",
    "prev_sample": "Go to the previous sample [PageUp]",
    "next_sample": "Go to the next sample [PageDown]",
}

# Short task-oriented answers for the built-in assistant. Kept here, next to the
# tooltips, so the two cannot disagree.
TOPICS = [
    ("import a FlowJo workspace, reuse FlowJo gates, open a .wsp",
     "File, Import FlowJo workspace (.wsp). The gate tree comes across on the axes FlowJo drew it "
     "on. Then run Help, Check against FlowJo counts to confirm every population agrees."),
    ("compensation, spillover, diagonal smear between two colours",
     "The Compensation menu. The default uses the matrix stored in each .fcs file, which is "
     "FlowJo's acquisition-defined. You can load a .csv matrix instead or edit coefficients by "
     "hand. A diagonal smear between two colours almost always means compensation is wrong."),
    ("reuse gates on a new run, gating template, apply the same gates",
     "Save the tree with File, Save gating template, then File, New analysis: FCS folder + gating "
     "template for the next run. Templates assume the same panel and similar voltages, so check "
     "every gate level before exporting."),
    ("export numbers, Excel, statistics table",
     "Add columns with Edit, Add statistic, then File, Export statistics to Excel. The workbook "
     "also carries the definitions, every gate count and the settings used."),
    ("gate applies to one sample only, per-sample gate, adjust one sample",
     "The 'Edit: this sample' button in the toolbar, shortcut L. On, dragging a gate changes only "
     "the current sample and the tree shows it in italic. Off, dragging changes every sample."),
    ("negative values, events pile up at the axis, log axis hides cells",
     "Switch the axis to Biex. A log axis cannot show zero or negative events, so they pile onto "
     "the edge. Biex gives the region around zero its own space; the W box sets how much."),
    ("draw a gate, rectangle, polygon, ellipse, quadrant, histogram range",
     "Pick a tool from the toolbar, keys 1 to 6. Polygon: click the corners and close with "
     "double-click, Enter, or by clicking the first point. Quadrant: click the crossing point. "
     "Range works on a histogram, so set Y to [Histogram] first."),
    ("overlay histograms, compare samples on one marker, did it shift, stacked, "
     "offset, ridgeline, modal normalisation, half offset",
     "The Overlay tab. Pick a channel, then choose what to lay over what: the samples you "
     "selected in the list, the whole plate, or every gate inside the current sample. "
     "Normalise to mode is the default and is what FlowJo calls modal: every curve peaks at "
     "the same height, so shapes compare even when the populations differ in size. Stacked "
     "offsets the curves up the page, which stays readable past about six."),
    ("MFI shifted but I cannot see it, prove a marker moved, compare medians",
     "Draw the two populations on the Overlay tab: the legend carries n, the median and the "
     "mean for each curve, in raw units. Medians there and an MFI column on the Statistics "
     "tab are the same number, so the picture and the table will agree."),
    ("rename a channel, marker names, axis says Comp-V710-A",
     "Edit, Rename channels, to map detectors onto marker names so the axes read CD3 rather than "
     "Comp-V710-A."),
    ("add donor or dose columns, sample metadata, annotate",
     "Edit, Annotate samples. The columns you add travel into the Excel export alongside the "
     "statistics."),
    ("see every sample at once, overview, plate",
     "The All samples tab shows every sample on the current two axes. Click any plot to jump to "
     "that sample."),
    ("a gate counts zero on every sample",
     "The channel that gate uses is missing from these files, or the template came from a "
     "different panel. Check the axis names against the channels in the file."),
    ("undo a mistake, go back, I deleted a gate by accident",
     "Ctrl+Z steps back and Ctrl+Shift+Z steps forward again. Drawing, moving, renaming and "
     "deleting gates are all undoable, including a deleted population and everything under it. "
     "The Edit menu names the exact edit you are about to undo."),
    ("find one sample, too many samples, filter the list, 96 wells",
     "Type into the Filter samples box above the sample list to narrow it. The All samples tab "
     "is the other way: it shows every sample at once, and clicking a plot opens that sample."),
    ("keyboard shortcut, hotkey, key binding",
     "Press F1 for the full list. The ones worth memorising: Ctrl+S saves, Ctrl+E exports to "
     "Excel, Ctrl+T adds a statistic, keys 1 to 6 pick a gate tool, Backspace goes up to the "
     "parent population, and PageUp and PageDown step through samples."),
    ("set a positive cutoff, where to put the gate, FMO",
     "Look at the FMO or unstained control on the All samples tab before trusting a positive gate. "
     "The Percentile statistic on an FMO, the 99th for example, gives an objective cut-off."),
    ("how certain is this percentage, error bars on a frequency, confidence interval, how much "
     "can my gate move the number",
     "Confidence, Measure confidence for this sample. Every boundary in the tree is moved by about "
     "as much as a careful hand would place it, the file is re-gated from the root, and the spread "
     "of each frequency is reported. Green means quote the number as it stands, amber means quote "
     "the interval with it, red means fix something first."),
    ("which of my gates is weakest, which number should I not trust, check the gating before "
     "publishing",
     "Confidence, Find the weakest gates in this workspace. It runs the same measurement on every "
     "sample and sorts worst first, so you do not have to guess which gate to check. The Limited "
     "by column says whether to redraw the gate or acquire more events."),
    ("my population has very few events, is thirty cells enough, rare population, small count",
     "The confidence report separates the two reasons a frequency is shaky. Gate error means the "
     "boundary is in the wrong place and redrawing it would help. Counting error means too few "
     "cells landed in the population and only acquiring more would help. A tiny population with a "
     "perfect gate still grades fragile, because thirty is thirty."),
    ("what do firm soft and fragile mean, what is the grade column",
     "Three words for how much weight a number will carry. firm: the interval is inside 5 % of "
     "the frequency, or under 0.05 percentage points, so quote it. fragile: the interval reaches "
     "25 % of the frequency, or 5 percentage points, so fix something first. soft: in between, so "
     "quote the interval beside it. They are conventions rather than findings, and the hand "
     "steadiness setting moves all of them."),
]
