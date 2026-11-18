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


class FlowLayout(QtWidgets.QLayout):
    """Lay widgets out left to right and wrap to the next line when they run out.

    Qt ships no such layout. A plain QHBoxLayout of eight buttons reports a minimum
    width equal to all eight, and QMainWindow honours it: the Statistics tab alone
    held the central widget at 1362 px, so the window could not be made small enough
    for a 1366x768 laptop and a newly opened dock was squeezed to 99 px. Wrapping
    costs a little height instead, and every control stays visible and clickable,
    which a horizontal scrollbar under a button row does not manage.
    """

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)

    # -- the five methods QLayout requires
    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def sizeHint(self):
        return self.minimumSize()

    # -- wrapping
    def expandingDirections(self):
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._lay(QtCore.QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._lay(rect, apply=True)

    def minimumSize(self):
        """One control wide. This is the whole point: the row stops dictating the
        window's minimum width, and wraps instead."""
        size = QtCore.QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())

    def _lay(self, rect, apply):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line = area.x(), area.y(), 0
        for it in self._items:
            w = it.sizeHint().width()
            h = it.sizeHint().height()
            if line and x + w > area.right() + 1:
                x = area.x()
                y += line + self.spacing()
                line = 0
            if apply:
                it.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), it.sizeHint()))
            x += w + self.spacing()
            line = max(line, h)
        return y + line - rect.y() + m.bottom()


def control_row(layout):
    """Re-pack a row of controls so it cannot dictate the window's minimum width.

    A horizontal row is re-laid in a FlowLayout, which wraps. Anything else, such as
    the two-row grid above the gating plot, keeps its arrangement inside a scroll
    area, because wrapping would scramble the Y and X rows into one another.
    """
    if not isinstance(layout, QtWidgets.QHBoxLayout):
        inner = QtWidgets.QWidget()
        inner.setLayout(layout)
        area = QtWidgets.QScrollArea()
        area.setWidget(inner)
        area.setWidgetResizable(True)
        area.setFrameShape(QtWidgets.QFrame.NoFrame)
        area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        area.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        h = inner.sizeHint().height()
        area.setFixedHeight(h + area.horizontalScrollBar().sizeHint().height())
        area.setMinimumWidth(120)
        return area

    holder = QtWidgets.QWidget()
    flow = FlowLayout(holder)
    flow.setContentsMargins(0, 0, 0, 0)
    # Move the widgets across and drop the spacers: a stretch that pushed two buttons
    # to the right edge would otherwise push them off the first wrapped line.
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            flow.addWidget(w)
    holder.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)
    return holder
