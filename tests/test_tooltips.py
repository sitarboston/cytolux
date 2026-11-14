"""Every control the user can hover must explain itself.

These also guard the help text: rename a menu action without updating
help_text.MENU_TIPS and this fails, rather than the tooltip quietly vanishing.
"""
import pytest

from cytolux.help_text import MENU_TIPS, TAB_TIPS, TOPICS, WIDGET_TIPS

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def win(qapp_module):
    from cytolux.app import MainWindow
    w = MainWindow()
    yield w
    w.close()


@pytest.fixture(scope="module")
def qapp_module():
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app


def menu_actions(win):
    """Every leaf action in the menu bar, with the menu it lives in."""
    out = []
    for top in win.menuBar().actions():
        menu = top.menu()
        if menu is None:
            continue
        for a in menu.actions():
            if a.isSeparator() or a.menu() is not None:
                continue
            out.append((top.text(), a))
    return out


def test_the_menu_bar_was_actually_found(win):
    assert len(menu_actions(win)) >= 20, "menu walk found almost nothing; the test is not looking in the right place"


def test_every_menu_action_has_a_tooltip(win):
    missing = [f"{m} > {a.text()}" for m, a in menu_actions(win) if not a.toolTip().strip()]
    assert not missing, "menu actions with no tooltip: %s" % missing


def test_every_menu_action_has_a_status_tip(win):
    missing = [f"{m} > {a.text()}" for m, a in menu_actions(win) if not a.statusTip().strip()]
    assert not missing, "menu actions with no status tip: %s" % missing


def test_tooltips_are_sentences_not_echoes_of_the_label(win):
    """A tooltip that just repeats the button text helps nobody."""
    lazy = []
    for m, a in menu_actions(win):
        tip = a.toolTip().split("  [")[0].strip()
        if tip.lower().rstrip(".") == a.text().lower().rstrip("….").strip():
            lazy.append(f"{m} > {a.text()}")
    assert not lazy, "tooltips that only repeat the label: %s" % lazy


def test_menus_actually_show_their_tooltips(win):
    """Qt hides tooltips in a QMenu unless setToolTipsVisible(True)."""
    off = [t.text() for t in win.menuBar().actions()
           if t.menu() is not None and not t.menu().toolTipsVisible()]
    assert not off, "menus that will not show tooltips: %s" % off


def test_every_tab_has_a_tooltip(win):
    missing = [win.tabs.tabText(i) for i in range(win.tabs.count())
               if not win.tabs.tabToolTip(i).strip()]
    assert not missing, "tabs with no tooltip: %s" % missing


def test_every_toolbar_action_has_a_tooltip(win):
    from PySide6 import QtWidgets
    missing = []
    for tb in win.findChildren(QtWidgets.QToolBar):
        for a in tb.actions():
            if a.isSeparator():
                continue
            if not a.toolTip().strip():
                missing.append(a.text())
    assert not missing, "toolbar buttons with no tooltip: %s" % missing


def test_help_text_has_no_entries_for_actions_that_no_longer_exist(win):
    """Catches a menu action renamed without updating help_text."""
    live = {a.text() for _, a in menu_actions(win)}
    stale = [t for t in MENU_TIPS if t not in live]
    assert not stale, "MENU_TIPS entries matching no menu action: %s" % stale


def test_tab_tips_match_the_real_tabs(win):
    live = {win.tabs.tabText(i) for i in range(win.tabs.count())}
    assert set(TAB_TIPS) == live


def test_widget_tips_are_all_used():
    import inspect
    from cytolux import app as appmod
    src = inspect.getsource(appmod)
    unused = [k for k in WIDGET_TIPS if '"%s"' % k not in src]
    assert not unused, "WIDGET_TIPS keys never referenced in app.py: %s" % unused


@pytest.mark.parametrize("keys,answer", TOPICS, ids=[t[0][:28] for t in TOPICS])
def test_assistant_topics_are_well_formed(keys, answer):
    assert len(keys) > 5 and len(answer) > 40
    assert answer[0].isupper() and answer.rstrip().endswith((".", "!"))
