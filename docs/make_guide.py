"""Build docs/Cytolux_Step_by_Step.docx from the screenshots made by tests/make_guide_shots.py.
Usage: python docs/make_guide.py"""
import os

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "shots")
OUT = os.path.join(HERE, "Cytolux_Step_by_Step.docx")
NAVY = RGBColor(0x1D, 0x2B, 0x4F)

doc = Document()
sec = doc.sections[0]
for side in ("left_margin", "right_margin"):
    setattr(sec, side, Inches(0.8))
sec.top_margin = sec.bottom_margin = Inches(0.7)
st = doc.styles["Normal"]
st.font.name = "Calibri"
st.font.size = Pt(10.5)
for name, size in (("Heading 1", 16), ("Heading 2", 12.5), ("Title", 26)):
    s = doc.styles[name]
    s.font.name = "Calibri"
    s.font.size = Pt(size)
    s.font.color.rgb = NAVY


def p(text="", bold_lead=None, style=None, space_after=4):
    para = doc.add_paragraph(style=style)
    if bold_lead:
        r = para.add_run(bold_lead)
        r.bold = True
    _runs(para, text)
    para.paragraph_format.space_after = Pt(space_after)
    return para


def _runs(para, text):
    """**bold** spans inside text."""
    parts = text.split("**")
    for i, part in enumerate(parts):
        if part:
            r = para.add_run(part)
            r.bold = i % 2 == 1


def bullet(text):
    para = doc.add_paragraph(style="List Bullet")
    _runs(para, text)
    para.paragraph_format.space_after = Pt(2)
    return para


def step(n, title, lines):
    h = doc.add_paragraph()
    r = h.add_run(f"Step {n}.  {title}")
    r.bold = True
    r.font.size = Pt(11.5)
    r.font.color.rgb = NAVY
    h.paragraph_format.space_before = Pt(10)
    h.paragraph_format.space_after = Pt(3)
    h.paragraph_format.keep_with_next = True
    for ln in lines:
        bullet(ln)


def shot(name, caption, width=6.4):
    path = os.path.join(SHOTS, name + ".png")
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.keep_with_next = True
    para.add_run().add_picture(path, width=Inches(width))
    c = doc.add_paragraph()
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = c.add_run(caption)
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    c.paragraph_format.space_after = Pt(8)


def shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear")
    sh.set(qn("w:color"), "auto")
    sh.set(qn("w:fill"), hexcolor)
    tcPr.append(sh)


def table(rows, widths, header=True):
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = t.cell(i, j)
            cell.width = Inches(widths[j])
            cell.text = ""
            para = cell.paragraphs[0]
            _runs(para, val)
            for r in para.runs:
                r.font.size = Pt(9.5)
                if header and i == 0:
                    r.bold = True
            if header and i == 0:
                shade(cell, "DCE6F1")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


# ------------------------------------------------------------------------------------ cover
doc.add_paragraph(style="Title").add_run("Cytolux: step by step")
p("How to gate an experiment, add statistics, export to Excel, and re-run the same analysis on new "
  "data. Cytolux runs on this computer only; nothing is uploaded anywhere.", space_after=8)

p("**Start the app:** Cytolux in the applications menu, the Cytolux icon on the Desktop, or "
  "in a terminal: ~/cytolux/cytolux.sh. Press **F1** inside the app for a one-page reminder.")
p("**Follow along with real data:** the screenshots use public CAR-T data from Good et al., "
  "Nature Medicine 2022 (Figure 6 cohort, BD LSRII). Two practice folders are ready:")
bullet("~/flowcyt_data/flowgate_demo/**Run1_controls** : 18 control tubes (CAR19 product and "
       "healthy PBMC, full stain and FMOs). Used in Part A.")
bullet("~/flowcyt_data/flowgate_demo/**Run2_patients** : 31 patient samples stained with the same "
       "panel. Used in Part B as the \"new data\".")
p("The finished example files from this guide (workspace, template and both Excel exports) are in "
  "~/cytolux/docs/shots/ if you want to compare.", space_after=6)

doc.add_heading("The idea in one paragraph", level=2)
p("You gate once, carefully, on one experiment. Cytolux keeps one gate tree for every sample in "
  "the workspace, so each gate you draw applies to all of them at once. You then choose the numbers "
  "you want (counts, percentages, medians), export them, and save the whole recipe as a "
  "**gating template**. Next time, you point the template at a new folder of FCS files and get "
  "the same gates and the same table in a minute; you only look through the samples and nudge any "
  "gate that does not fit.")

table([
    ["File", "What it holds", "When to use it"],
    ["**.fgw** workspace", "Your FCS file list, compensation, gates, per-sample adjustments, "
     "statistics, annotations, axis scales", "Reopen one experiment exactly as you left it"],
    ["**.fgt** template", "Gates, statistics, axis scales and channel names; no samples",
     "Run the same analysis on new data"],
    ["**.xlsx** export", "Your statistics table plus every gate's counts", "Graphing, Prism, reports"],
], [1.25, 3.3, 2.3])

# ------------------------------------------------------------------------------------ part A
doc.add_heading("Part A. Analyze an experiment for the first time", level=1)

step(1, "Open the FCS files", [
    "**File → Open FCS folder** (Ctrl+O) and pick the folder. Every .fcs file in it is loaded.",
    "Samples are listed top left. The gate tree is below it. The plot is on the right.",
    "Move between samples with **Page Up / Page Down**, or click one in the list.",
])
shot("A1_opened", "After opening Run1_controls: all events, FSC-A against SSC-A.")

step(2, "Check compensation", [
    "By default Cytolux uses the spillover matrix the cytometer wrote into each file (FlowJo calls "
    "this \"acquisition-defined\"). Compensated channels are shown with a **Comp-** prefix, as in FlowJo.",
    "**Compensation → View / edit matrix** shows it; edit a value and press OK to apply it to every sample.",
    "If you made a matrix elsewhere, **Compensation → Load matrix from CSV** (channel names as the header row).",
    "Worth knowing: the public files used here carry an identity matrix (the authors compensated in "
    "Cytobank and did not deposit it), which is why some plots show diagonal smears. Your own files "
    "from the Attune or a Cytek will normally have a real matrix in them.",
])

step(3, "Give the channels sensible names (optional)", [
    "**Edit → Rename channels** lets you change the marker name shown on the axes and in the table, "
    "for example when a detector was mislabelled at acquisition (YL1 shown as \"CAR CD20\" but actually EGFR).",
    "The names are saved in the workspace and in the template.",
])

step(4, "Choose the axes and their scales", [
    "Use the **Y** and **X** drop-downs above the plot. Choose **[Histogram]** as Y for a one-parameter plot.",
    "Next to each axis choose **Linear**, **Log** or **Biex**. Scatter channels are linear by default and "
    "fluorescence channels biex. **W** sets how much room biex gives to the region around zero; Cytolux "
    "picks a starting value from the data.",
    "**Display** switches between pseudocolor and dots.",
])
shot("A2_ssc_log", "SSC-A switched to Log, which spreads out the low side-scatter of these files.")

step(5, "Draw the first gate", [
    "Pick a tool in the toolbar or press its number: **1** Select, **2** Rectangle, **3** Polygon, "
    "**4** Ellipse, **5** Quadrant, **6** Range.",
    "Polygon: click the corners, then double-click (or press Enter, or click the first point) to close it.",
    "Rectangle and Ellipse: drag. Quadrant: click where the lines should cross. Range: drag across a histogram.",
    "Type a name for the population and press OK. The gate shows its name and % of parent.",
    "To adjust it, press **1** (Select) and drag the gate or its handles. Numbers update when you let go.",
])
shot("A3_cells", "\"Cells\": a polygon that leaves out debris on the left and saturated events at the FSC ceiling.")

step(6, "Go into the gate and keep going", [
    "Click the population in the gate tree (or double-click the gate on the plot). The plot now shows only "
    "the events inside it, and any gate you draw is placed under it.",
    "Set new axes and draw the next gate. **Backspace** goes back up to the parent.",
    "Right-click any gate in the tree to rename or delete it.",
])
shot("A4_singlets", "Inside Cells: FSC-A against FSC-H, with a \"Single cells\" polygon along the diagonal.")
shot("A5_live", "Inside Single cells: a rectangle on the low side of the live/dead dye (LD) gives \"Live\".")
shot("A6_quadrant", "Inside Live: one click with the Quadrant tool on CAR against CD3 makes four populations, "
                    "named from the markers.")

step(7, "Check every sample", [
    "The **All samples** tab draws every sample on the current axes with the gates on top. Look for any "
    "sample where a gate cuts through a population.",
    "Click a thumbnail to open that sample on the Gating tab.",
    "To move a gate for **every** sample, just drag it.",
    "To move it for **one** sample only, right-click the gate → **Edits apply to this sample only**, then "
    "drag. That gate shows in italics for that sample. Right-click → **Use the group gate again** undoes it.",
])
shot("A7_all_samples", "All samples tab, Live population on CAR against CD3: the CAR FMO and healthy "
                       "tubes sit left of the CAR line, as they should.")

step(8, "Lay the samples over each other", [
    "The **Overlay** tab answers the question a grid of plots cannot: did this marker move?",
    "Pick the **channel**, then what to lay over what: the samples you selected in the list, the whole "
    "plate, or every gate inside the sample you have open.",
    "**Normalise to mode** is the default. Every curve peaks at the same height, so the shapes compare "
    "even when one population has ten times the cells of another. This is what FlowJo calls modal. "
    "**Normalise to area** draws a smaller population as a shorter curve; **Raw count** shows the sizes.",
    "**Stacked** offsets the curves up the page, which stays readable past about six samples. Overlaid is "
    "better for two or three.",
    "Each curve carries its own **n, median and mean** in the legend, in raw units: the same numbers the "
    "Statistics tab gives, so the picture and the table agree. A curve under 100 events is called out as "
    "thin, because a smooth curve drawn from sixty cells still looks convincing.",
    "**Export figure** writes the plot at 300 dpi on white, ready for a slide or a paper.",
])

step(9, "Choose your statistics", [
    "Open the **Statistics** tab. Each column is one number for every sample.",
    "**Count + % of parent for every gate** adds the usual set in one click.",
    "**Σ Add statistic** opens the dialog below: (1) pick one or more populations, (2) pick the statistic, "
    "(3) for intensity statistics pick one or more channels, then **Add**. One column is made for every "
    "population × channel you picked.",
    "Also available: right-click a population in the gate tree → **Add statistic for this population**. "
    "Intensity statistics also appear in the tree as blue Σ lines for the sample you are looking at.",
    "Double-click a column header to rename it. Select a column and use **Remove column**, **Move left** "
    "or **Move right** to tidy the table.",
])
shot("A8_add_statistic", "Adding the median CAR intensity for the two CD3+ quadrants.", width=5.0)
table([
    ["Statistic", "What it is"],
    ["Count", "Events in the population"],
    ["% of parent / % of total", "Percent of the gate above, or of all events in the file"],
    ["% of …", "Percent of any ancestor you choose (for example CAR+ as % of Live)"],
    ["Median", "Median intensity; the usual \"MFI\" (same as FlowJo's Median)"],
    ["Mean, Geometric mean, SD", "As in FlowJo (geometric mean uses positive events only)"],
    ["CV, Robust CV", "Spread in %; Robust CV is FlowJo's rCV and ignores outliers"],
    ["Percentile", "Intensity at a percentile you choose (for example the 99th, for an FMO cut-off)"],
], [2.0, 4.8])

step(10, "Describe the samples (optional, but saves time in Excel)", [
    "**Annotate samples** opens a small spreadsheet with one row per sample. **Add column** (Donor, Dose, "
    "Condition, Timepoint…) and type values in.",
    "Faster: copy a block from Excel, click the first cell and press **Ctrl+V**. Or **Import from "
    "CSV/Excel** with the FCS file name in the first column. **Fill 'Well' from file names** reads A1…H12 "
    "out of plate file names.",
    "These columns lead the statistics table and the export, so you can sort and graph by them.",
])
shot("A10_annotate", "Two annotation columns, Group and Tube.", width=5.4)
shot("A11_statistics_annotated", "The finished table: annotations first, then one column per statistic.")

step(11, "Export", [
    "**Export to Excel** (Ctrl+E) writes a workbook with four sheets: **Statistics** (your table, "
    "formatted), **Definitions** (what each column means and which gate and channel it uses), "
    "**All gates** (count, % of parent and % of total for every gate in every sample, in long format) and "
    "**About** (date, workspace, compensation used).",
    "Cytolux offers to open the file straight away.",
    "**Copy table** puts the same table on the clipboard, ready to paste into Prism or Excel.",
    "**File → Export plot as image** saves the current plot as a PNG.",
])

step(12, "Save, twice", [
    "**File → Save workspace** (Ctrl+S) saves this experiment as a .fgw file. Reopen it any time with "
    "File → Open workspace (or the Recent list) and everything is as you left it.",
    "**File → Save gating template** saves the recipe (gates, statistics, scales, channel names) as a "
    ".fgt file. Give it a name that says what panel it is for, for example "
    "\"CAR-T panel v1.fgt\". This is the file you will use on new data.",
])

# ------------------------------------------------------------------------------------ part B
doc.add_heading("Part B. Re-analyze new data with the same panel", level=1)
p("Use this every time a new run comes off the cytometer with the same panel and settings.")

step(1, "Start a new analysis from the template", [
    "**File → New analysis: FCS folder + gating template** (Ctrl+N).",
    "First choose the **template** (.fgt). A saved workspace (.fgw) also works; its gates are used.",
    "Then choose the **folder with the new FCS files**.",
    "Cytolux loads the files and puts the whole gate tree and the statistics on them. If the new files "
    "lack a channel the template uses, it tells you which, so you can check the panel.",
])
shot("B1_template_applied", "The 31 patient files with the template applied: same gates, numbers already filled in.")

step(2, "Look through the samples and adjust", [
    "Open the **All samples** tab and check each gate level (click a population in the tree on the Gating "
    "tab first; All samples shows the same level and axes).",
    "Patient samples vary more than controls. Fix a gate for the whole run by dragging it, or for one "
    "sample with right-click → **Edits apply to this sample only**.",
])
shot("B2_all_samples", "Patient samples on CAR against CD3. Here you would check that the CD3 and CAR "
                       "lines still sit in the troughs.")

step(3, "Annotate, export, save", [
    "The **Statistics** tab already has the same columns as last time.",
    "**Annotate samples** (paste the sample sheet from Excel), then **Export to Excel**.",
    "**Save workspace** for this run (for example \"Run2_patients.fgw\").",
    "If you improved the gates in a way that should apply to future runs, save the template again under "
    "a new version name (\"CAR-T panel v2.fgt\") so old analyses stay reproducible.",
])
shot("B3_statistics", "Statistics for the new run, ready to export.")

doc.add_heading("Other ways to add data", level=2)
bullet("**Add samples to an existing experiment:** open its workspace, then File → Add FCS files. The "
       "new files get the same gates.")
bullet("**Template onto files you have already opened:** File → Apply gating template to these samples.")
bullet("**Remove a sample:** right-click it in the sample list → Remove (Ctrl/Shift-click to pick several).")

# ------------------------------------------------------------------------------------ part C
doc.add_heading("Part C. Starting from a FlowJo analysis", level=1)
bullet("**File → Import FlowJo workspace (.wsp)** brings in FlowJo's gate tree. If the FCS files are "
       "not open yet, Cytolux looks for them next to the .wsp and asks for the folder if needed.")
bullet("**Help → Check against FlowJo counts** compares every population count with the count FlowJo "
       "saved and flags any population that differs by more than the tolerance you set.")
bullet("Then **Save gating template**, and FlowJo's gates can be used on new runs as in Part B.")
bullet("FlowJo polygons were drawn on linear axes. If you view them on biex axes they appear as a "
       "dashed outline that cannot be dragged: switch the axes back to linear to edit, or right-click → "
       "Convert gate to the current axis scales.")
p("A ready-made demo workspace ships with the public example data under data/public/.")

# ------------------------------------------------------------------------------------ part D
doc.add_heading("Shortcuts", level=1)
table([
    ["Key", "Action", "Key", "Action"],
    ["1 to 6", "Select, Rectangle, Polygon, Ellipse, Quadrant, Range", "Ctrl+O", "Open FCS folder"],
    ["Esc", "Cancel drawing, back to Select", "Ctrl+N", "New analysis from template"],
    ["Enter", "Close a polygon", "Ctrl+S", "Save workspace"],
    ["Backspace", "Go up to the parent population", "Ctrl+T", "Add statistic"],
    ["Page Up / Down", "Previous / next sample", "Ctrl+E", "Export to Excel"],
    ["Delete", "Delete the selected gate", "F1", "Quick guide"],
], [1.1, 2.4, 0.9, 2.4])

doc.add_heading("Good practice and fixes", level=1)
bullet("**Template reuse assumes the same panel and similar instrument settings.** If voltages or the "
       "panel changed, apply the template anyway but check every gate level before exporting.")
bullet("**Always look at the FMO or unstained controls** on the All samples tab before trusting a positive "
       "gate. The Percentile statistic on an FMO (for example the 99th) gives an objective cut-off.")
bullet("**A gate counts 0 in every sample:** the channel it uses is missing from these files, or the "
       "template came from a different panel.")
bullet("**Diagonal smears between two colors:** compensation is missing or wrong (Step 2).")
bullet("**Workspace files moved:** a .fgw stores where the FCS files were. If they moved, Cytolux asks "
       "for the new folder when you open it.")
bullet("**Large files:** Cytolux keeps a few samples in memory at a time, so a 96-well plate is fine. "
       "The All samples tab takes a few seconds to draw a full plate.")

doc.save(OUT)
print(OUT)
