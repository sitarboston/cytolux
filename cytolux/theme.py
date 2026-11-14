"""A warm, quiet interface: cream paper rather than a sheet of white.

Two rules sit behind the choices here, and they pull in opposite directions.

The first is that a screen full of pure white is tiring, and a flow cytometry window is
mostly background. Cream reads as paper, which is what the thing is.

The second is that the plot canvas is not decoration, it is the measurement. Texture
belongs on the window chrome, never behind the data: a faint mottle under a density
plot competes with the lowest contour and makes sparse events ambiguous, which is
exactly where the eye is already working hardest. So the canvas is flat, and a figure
exported for publication goes back to plain white, because that is what journals take.
"""
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

PAPER = "#F4EFE2"        # window background, the warmest tone
PANEL = "#FAF6EB"        # docks, toolbars, lists
CANVAS = "#F8F3E5"       # the plot itself: clearly cream, still light enough for data
FIGURE = "#FFFFFF"       # what an exported figure uses, whatever the screen shows
INK = "#2B2721"
MUTED = "#6B6355"
LINE = "#DDD3BE"
SELECT = "#DEC9A0"
HILITE = "#8A6D3B"

TILE = 64
TEXTURE_STRENGTH = 2.2   # peak RGB deviation; above about 4 it starts to look dirty


def texture_pixmap(seed=11):
    """A small tile of very faint warm noise, for the window background.

    Deliberately weak. The point is to stop a large flat area reading as a blank screen,
    not to be noticed. Two units of RGB is under a tenth of the contrast step the eye
    resolves on a mid tone, so it registers as paper rather than as a pattern.
    """
    rng = np.random.default_rng(seed)
    base = np.array([244, 239, 226], dtype=float)
    noise = rng.normal(0.0, TEXTURE_STRENGTH, size=(TILE, TILE, 1))
    grain = rng.normal(0.0, TEXTURE_STRENGTH * 0.4, size=(TILE, TILE, 3))
    arr = np.clip(base + noise + grain, 0, 255).astype(np.uint8)
    arr = np.ascontiguousarray(arr)
    img = QtGui.QImage(arr.data, TILE, TILE, 3 * TILE, QtGui.QImage.Format_RGB888)
    return QtGui.QPixmap.fromImage(img.copy())


def palette():
    p = QtGui.QPalette()
    ink, muted = QtGui.QColor(INK), QtGui.QColor(MUTED)
    p.setBrush(QtGui.QPalette.Window, QtGui.QBrush(texture_pixmap()))
    p.setColor(QtGui.QPalette.WindowText, ink)
    p.setColor(QtGui.QPalette.Base, QtGui.QColor(PANEL))
    p.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(PAPER))
    p.setColor(QtGui.QPalette.Text, ink)
    p.setColor(QtGui.QPalette.Button, QtGui.QColor(PANEL))
    p.setColor(QtGui.QPalette.ButtonText, ink)
    p.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(PANEL))
    p.setColor(QtGui.QPalette.ToolTipText, ink)
    p.setColor(QtGui.QPalette.Highlight, QtGui.QColor(SELECT))
    p.setColor(QtGui.QPalette.HighlightedText, ink)
    p.setColor(QtGui.QPalette.Link, QtGui.QColor(HILITE))
    p.setColor(QtGui.QPalette.PlaceholderText, muted)
    for role in (QtGui.QPalette.WindowText, QtGui.QPalette.Text, QtGui.QPalette.ButtonText):
        p.setColor(QtGui.QPalette.Disabled, role, QtGui.QColor("#A59D8C"))
    return p


STYLESHEET = """
QToolBar, QStatusBar, QMenuBar {{ background: {panel}; border: 0; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {select}; color: {ink}; }}
QMenu {{ background: {panel}; border: 1px solid {line}; }}
QToolTip {{ background: {panel}; color: {ink}; border: 1px solid {line}; padding: 4px; }}
QDockWidget::title {{ background: {panel}; padding: 5px; border-bottom: 1px solid {line}; }}
QTreeWidget, QListWidget, QTableWidget, QTableView, QLineEdit, QTextBrowser,
QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {panel}; border: 1px solid {line}; border-radius: 3px;
    selection-background-color: {select}; selection-color: {ink};
}}
QHeaderView::section {{
    background: {paper}; color: {muted}; border: 0;
    border-right: 1px solid {line}; border-bottom: 1px solid {line}; padding: 4px 6px;
}}
QTabBar::tab {{ background: {paper}; color: {muted}; padding: 6px 14px;
                border: 1px solid {line}; border-bottom: 0; }}
QTabBar::tab:selected {{ background: {panel}; color: {ink}; }}
QPushButton {{ background: {panel}; border: 1px solid {line}; border-radius: 3px;
               padding: 5px 12px; }}
QPushButton:hover {{ background: {select}; }}
QPushButton:disabled {{ color: #A59D8C; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: {paper}; border: 0; }}
QScrollBar::handle {{ background: {line}; border-radius: 4px; min-height: 24px; }}
QSplitter::handle {{ background: {line}; }}
"""


def stylesheet():
    return STYLESHEET.format(paper=PAPER, panel=PANEL, ink=INK, muted=MUTED,
                             line=LINE, select=SELECT)


def apply(app):
    """Dress the whole application. Call once, before the main window is built."""
    app.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
    app.setPalette(palette())
    app.setStyleSheet(stylesheet())
