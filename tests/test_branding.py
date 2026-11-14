"""The mark.

An application's icon is the one piece of it everybody sees before anything else,
and the one thing a default PyInstaller build silently gets wrong. These tests hold
the icon to being present, being ours, and surviving the sizes a desktop asks for.
"""
import os
import re

import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore, QtGui

import cytolux
from cytolux.app import app_icon

ICONS = os.path.join(os.path.dirname(cytolux.__file__), "icons")
WANTED = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_the_mark_is_a_valid_drawing(app):
    from PySide6 import QtSvg
    r = QtSvg.QSvgRenderer(os.path.join(ICONS, "cytolux.svg"))
    assert r.isValid()
    assert r.viewBoxF().width() == r.viewBoxF().height(), "the tile is not square"


def test_every_size_the_desktop_asks_for_exists():
    have = set()
    for f in os.listdir(os.path.join(ICONS, "app")):
        m = re.fullmatch(r"cytolux-(\d+)\.png", f)
        if m:
            have.add(int(m.group(1)))
    assert set(WANTED) <= have, "missing %s" % sorted(set(WANTED) - have)


def test_the_rendered_sizes_are_what_they_claim(app):
    for s in WANTED:
        img = QtGui.QImage(os.path.join(ICONS, "app", "cytolux-%d.png" % s))
        assert not img.isNull()
        assert (img.width(), img.height()) == (s, s)


def test_the_icon_still_reads_at_sixteen_pixels(app):
    """A mark that goes to mush in the taskbar is not a mark. At 16 px it must still
    have both ink and background: not a solid block, not an empty one."""
    img = QtGui.QImage(os.path.join(ICONS, "app", "cytolux-16.png")).convertToFormat(
        QtGui.QImage.Format_ARGB32)
    lums = [QtGui.QColor(img.pixel(x, y)).lightness()
            for x in range(16) for y in range(16)]
    assert max(lums) - min(lums) > 120, "the small icon has no contrast left in it"
    bright = sum(1 for v in lums if v > 150)
    assert 8 < bright < 200, "the small icon is a solid block, light or dark"


def test_the_windows_and_mac_icons_are_built():
    for name in ("cytolux.ico", "cytolux.icns"):
        p = os.path.join(ICONS, name)
        assert os.path.exists(p), "%s is missing, so that platform ships a default icon" % name
        assert os.path.getsize(p) > 2000


def test_the_app_icon_carries_more_than_one_size(app):
    ic = app_icon()
    assert not ic.isNull()
    assert len(ic.availableSizes()) >= len(WANTED) - 1
    assert ic.pixmap(QtCore.QSize(16, 16)).size() == QtCore.QSize(16, 16)
    assert ic.pixmap(QtCore.QSize(256, 256)).size() == QtCore.QSize(256, 256)


def test_the_window_wears_it(app):
    from cytolux.app import MainWindow
    w = MainWindow()
    try:
        assert not w.windowIcon().isNull(), "the window has no icon"
    finally:
        w.dirty = False
        w.close()


def test_the_builds_are_told_about_the_icons():
    """PyInstaller ships its own icon unless told otherwise, and nobody notices until
    the .exe is on someone else's desktop."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(cytolux.__file__)))
    wf = os.path.join(root, ".github", "workflows", "build.yml")
    if not os.path.exists(wf):
        pytest.skip("no workflow in this checkout")
    text = open(wf).read()
    assert "--icon" in text
    assert "cytolux.ico" in text and "cytolux.icns" in text


def test_the_lockup_exists_for_documents(app):
    from PySide6 import QtSvg
    r = QtSvg.QSvgRenderer(os.path.join(ICONS, "cytolux-lockup.svg"))
    assert r.isValid()
    assert r.viewBoxF().width() > r.viewBoxF().height(), "the lockup is not horizontal"
