"""The cream. A gating app is something you stare at for an afternoon, and a flat
white window under a dense plot is the thing that makes the afternoon feel long.

These tests hold three promises: the chrome is warm rather than white, the warmth
is consistent across the window, and a figure you export is still on white paper,
because a journal does not want your interface colour in its figure.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6 import QtGui

from cytolux import theme


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def warmth(hexcode):
    """How far a colour leans to the warm side: red minus blue, in 0-255."""
    c = QtGui.QColor(hexcode)
    return c.red() - c.blue()


CHROME = ("PAPER", "PANEL", "CANVAS")


@pytest.mark.parametrize("name", CHROME)
def test_the_chrome_is_cream_and_not_white(name):
    v = getattr(theme, name)
    c = QtGui.QColor(v)
    assert c.isValid(), "%s = %r is not a colour" % (name, v)
    assert warmth(v) >= 8, "%s (%s) reads as white, not cream" % (name, v)
    assert c.lightness() > 215, "%s (%s) is too dark to work behind text" % (name, v)


def test_the_canvas_is_in_the_same_family_as_the_panels():
    """A plot area a shade off from its surround looks like a bug, not a design."""
    assert abs(warmth(theme.CANVAS) - warmth(theme.PANEL)) < 10


def test_exported_figures_stay_on_white_paper():
    assert QtGui.QColor(theme.FIGURE) == QtGui.QColor("#FFFFFF")


def test_ink_on_cream_is_readable():
    """WCAG asks 4.5:1 for body text. Cream chrome is no excuse to lose contrast."""
    def rel_lum(hexcode):
        c = QtGui.QColor(hexcode)
        chans = []
        for v in (c.redF(), c.greenF(), c.blueF()):
            chans.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
        r, g, b = chans
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    for bg in CHROME:
        lo, hi = sorted((rel_lum(theme.INK), rel_lum(getattr(theme, bg))))
        assert (hi + 0.05) / (lo + 0.05) >= 4.5, "ink on %s is too faint" % bg


def test_the_texture_tile_is_faint_and_repeatable(app):
    """Texture is meant to be felt, not seen. A loud tile shows its seams."""
    pm = theme.texture_pixmap()
    assert pm.width() == theme.TILE and pm.height() == theme.TILE
    img = pm.toImage()
    vals = [QtGui.QColor(img.pixel(x, y)).lightness()
            for x in range(0, theme.TILE, 4) for y in range(0, theme.TILE, 4)]
    assert max(vals) - min(vals) <= 14, "the noise is strong enough to see as speckle"
    again = theme.texture_pixmap().toImage()
    assert img == again, "the tile is random each call, so the window would shimmer"


def test_the_palette_paints_the_window_with_the_texture(app):
    pal = theme.palette()
    brush = pal.brush(QtGui.QPalette.Window)
    assert not brush.texture().isNull(), "the window is a flat fill, with no texture"
    assert pal.color(QtGui.QPalette.WindowText) == QtGui.QColor(theme.INK)


def test_applying_the_theme_leaves_the_app_styled(app):
    before = app.styleSheet()
    try:
        theme.apply(app)
        assert "QToolBar" in app.styleSheet(), "the stylesheet never reached the app"
        assert app.palette().color(QtGui.QPalette.Base).isValid()
    finally:
        app.setStyleSheet(before)
