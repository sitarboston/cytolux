"""Cross-platform behaviour: the three builds have to behave like the same program.

Everything here was a real defect found on 2026-11-18. The Ask panel opened as a
99 px sliver, the window could not be made narrower than 1362 px, the macOS delete
key went to the wrong action, and a double-clicked .fcs file opened an empty window
on every platform that registers the file type.
"""
import os

import pytest

pytest.importorskip("PySide6")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DATA = os.path.join(REPO, "testdata")


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def win(app):
    from cytolux.app import MainWindow
    w = MainWindow()
    w.show()
    app.processEvents()
    yield w
    w.dirty = False
    w.close()


def shortcuts(w, text):
    from PySide6 import QtGui
    for a in w.findChildren(QtGui.QAction):
        if a.text() == text:
            return [k.toString() for k in a.shortcuts()]
    raise AssertionError("no action named %r" % text)


# ------------------------------------------------------------------ the Ask panel
def test_the_ask_panel_opens_wide_enough_to_read(win, app):
    """It opened at its 99 px minimum, one word per line, on all three platforms."""
    from PySide6 import QtCore
    from cytolux.app import ASK_DOCK_WIDTH

    win.setGeometry(0, 0, 1400, 900)
    app.processEvents()
    win.act_ask.trigger()
    app.processEvents()
    assert win._assist_dock.isVisible()
    assert win.dockWidgetArea(win._assist_dock) == QtCore.Qt.RightDockWidgetArea
    assert win._assist_dock.width() >= min(ASK_DOCK_WIDTH, 300)


def test_the_ask_panel_answers_and_says_so_when_it_cannot(win, app):
    from cytolux.assistant import NO_MATCH

    win.act_ask.trigger()
    app.processEvents()
    win._assist_box.setText("how do I export to excel")
    app.processEvents()
    assert "Excel" in win._assist_out.toPlainText()
    win._assist_box.setText("zzzzqqq")
    app.processEvents()
    assert NO_MATCH.split(".")[0] in win._assist_out.toPlainText()


def test_pressing_ask_from_inside_the_panel_means_put_it_away(win, app, monkeypatch):
    """And pressing it from anywhere else means go to the search box."""
    from PySide6 import QtWidgets

    win.act_ask.trigger(); app.processEvents()
    assert win._assist_dock.isVisible()

    monkeypatch.setattr(QtWidgets.QApplication, "focusWidget",
                        staticmethod(lambda: win._assist_box))
    assert win._ask_should_close()
    monkeypatch.setattr(QtWidgets.QApplication, "focusWidget",
                        staticmethod(lambda: win._assist_out))
    assert win._ask_should_close(), "reading an answer counts as being in the panel"
    monkeypatch.setattr(QtWidgets.QApplication, "focusWidget",
                        staticmethod(lambda: win.sample_list))
    assert not win._ask_should_close()
    monkeypatch.setattr(QtWidgets.QApplication, "focusWidget", staticmethod(lambda: None))
    assert not win._ask_should_close()

    win._assist_dock.hide()
    assert not win._ask_should_close(), "a hidden panel is never closed again"


def test_the_ask_button_puts_the_panel_away_again(win, app):
    """The whole path, where the environment will give a widget keyboard focus. A
    bare X server with no window manager, which is what CI runs, often will not."""
    win.act_ask.trigger(); app.processEvents()
    win._assist_box.setFocus(); app.processEvents()
    if not win._assist_box.hasFocus():
        pytest.skip("this display cannot give a widget keyboard focus")
    win.act_ask.trigger(); app.processEvents()
    assert not win._assist_dock.isVisible()
    win.act_ask.trigger(); app.processEvents()
    assert win._assist_dock.isVisible()


# ------------------------------------------------------- the window's minimum width
def test_the_window_fits_a_small_laptop(win):
    """A control row of eight buttons held the central widget at 1362 px, so the
    window could not be made small enough for a 1366x768 screen."""
    assert win.centralWidget().minimumSizeHint().width() < 900


def test_opening_data_does_not_widen_the_minimum(win, app):
    """The channel combo sizes to the longest marker name, which used to raise the
    whole window's minimum width as soon as a file was opened."""
    import glob

    before = win.centralWidget().minimumSizeHint().width()
    files = sorted(glob.glob(os.path.join(DATA, "*.fcs")))
    assert files, "testdata has no FCS files"
    win._load_files(files[:1])
    app.processEvents()
    assert win.centralWidget().minimumSizeHint().width() <= before


def test_the_toolbar_can_be_saved_in_the_window_state(win):
    """saveState() silently drops a toolbar with no objectName, and warns."""
    from PySide6 import QtWidgets

    bars = win.findChildren(QtWidgets.QToolBar)
    assert bars
    assert all(b.objectName() for b in bars)


def test_the_window_remembers_where_it_was(win, tmp_path):
    """Writes into a throwaway ini file: the suite must not move his real window."""
    from PySide6 import QtCore

    win.settings = QtCore.QSettings(str(tmp_path / "cytolux.ini"), QtCore.QSettings.IniFormat)
    win._save_layout()
    assert win.settings.value("geometry") is not None
    assert win.settings.value("winstate") is not None
    assert win._on_a_screen()


# ----------------------------------------------------------------- macOS shortcuts
def test_the_mac_delete_key_deletes_a_gate(app, monkeypatch):
    """On macOS the key labelled delete sends Backspace and Key_Delete is Fn+Delete.
    Backspace was bound to Parent, so the obvious key went up a level instead."""
    import cytolux.app as A

    monkeypatch.setattr(A, "MAC", True)
    w = A.MainWindow()
    try:
        assert "Backspace" in shortcuts(w, "Delete selected gate")
        assert "Backspace" not in shortcuts(w, "Parent")
        assert shortcuts(w, "Parent") == ["Ctrl+Up"]
    finally:
        w.dirty = False
        w.close()


def test_the_mac_build_has_keys_for_prev_and_next_sample(app, monkeypatch):
    """A Mac laptop has no PgUp or PgDown key."""
    import cytolux.app as A

    monkeypatch.setattr(A, "MAC", True)
    w = A.MainWindow()
    try:
        assert shortcuts(w, "Prev sample") == ["PgUp", "Ctrl+Alt+Left"]
        assert shortcuts(w, "Next sample") == ["PgDown", "Ctrl+Alt+Right"]
    finally:
        w.dirty = False
        w.close()


def test_no_two_actions_claim_the_same_key(app, monkeypatch):
    import cytolux.app as A
    from PySide6 import QtGui

    for mac in (False, True):
        monkeypatch.setattr(A, "MAC", mac)
        w = A.MainWindow()
        try:
            seen = {}
            for a in w.findChildren(QtGui.QAction):
                for k in a.shortcuts():
                    t = k.toString()
                    assert t, "unparsed shortcut on %r" % a.text()
                    if t in seen:
                        assert seen[t] == a.text(), \
                            "%s is claimed by %r and %r (MAC=%s)" % (t, seen[t], a.text(), mac)
                    seen[t] = a.text()
        finally:
            w.dirty = False
            w.close()


# ------------------------------------------------------- the file associations work
def test_a_double_clicked_fcs_file_is_loaded(tmp_path):
    """Windows registers .fcs and the Linux desktop file declares the MIME type, but
    only .fgw and directories were handled, so the app opened empty."""
    from cytolux.app import split_argv
    import glob

    files = sorted(glob.glob(os.path.join(DATA, "*.fcs")))
    ws, fcs = split_argv([files[0], files[1]])
    assert ws == []
    assert fcs == [files[0], files[1]]


def test_an_uppercase_fcs_file_is_loaded_too(tmp_path):
    """A Windows cytometer writes .FCS, and a case-sensitive filesystem will not
    match that against *.fcs."""
    from cytolux.app import split_argv

    p = tmp_path / "Sample.FCS"
    p.write_bytes(b"FCS3.1")
    ws, fcs = split_argv([str(p)])
    assert fcs == [str(p)]
    ws, fcs = split_argv([str(tmp_path)])
    assert fcs == [str(p)]


def test_a_workspace_argument_still_opens_a_workspace(tmp_path):
    from cytolux.app import split_argv

    p = tmp_path / "run.fgw"
    p.write_text("{}")
    ws, fcs = split_argv([str(p)])
    assert ws == [str(p)]
    assert fcs == []


def test_an_argument_that_is_neither_is_ignored(tmp_path):
    from cytolux.app import split_argv

    junk = tmp_path / "notes.txt"
    junk.write_text("hello")
    assert split_argv([str(junk), "--verbose", str(tmp_path / "gone.fcs")]) == ([], [])


# ------------------------------------------------------------ the macOS .app bundle
def test_the_mac_bundle_declares_the_file_types_it_opens():
    """The Windows installer registers .fgw and .fcs. Without this the same
    double-click on a Mac does nothing, because the .app had no document types."""
    src = open(os.path.join(REPO, "packaging", "make_dmg.sh"), encoding="utf-8").read()
    assert "CFBundleDocumentTypes" in src
    assert '"fgw"' in src and '"fcs"' in src
    # Editing the bundle after codesign invalidates the signature.
    assert src.index("CFBundleDocumentTypes") < src.index("Ad-hoc signing")


def test_the_mac_bundle_has_a_stable_identifier():
    src = open(os.path.join(REPO, ".github", "workflows", "build.yml"), encoding="utf-8").read()
    assert "--osx-bundle-identifier com.samyabhaduri.cytolux" in src


def test_a_test_run_cannot_overwrite_the_real_preferences(tmp_path, monkeypatch):
    """The suite builds windows on a small offscreen screen and closes them, which
    saves a layout. Without the override that layout became his next real launch."""
    from cytolux.app import settings

    monkeypatch.setenv("CYTOLUX_SETTINGS", str(tmp_path / "scratch.ini"))
    assert settings().fileName() == str(tmp_path / "scratch.ini")
    monkeypatch.delenv("CYTOLUX_SETTINGS")
    assert "Cytolux" in settings().fileName()


# ------------------------------------------------------------ the wrapping rows
def test_a_control_row_wraps_instead_of_scrolling(app):
    """Eight buttons on one line forced the window wide. They wrap now, and every
    one stays visible: a horizontal scrollbar would have hidden Copy table and
    Export to Excel, which are the two most used."""
    from PySide6 import QtWidgets
    from cytolux import theme

    row = QtWidgets.QHBoxLayout()
    buttons = [QtWidgets.QPushButton("Button number %d" % i) for i in range(8)]
    for b in buttons:
        row.addWidget(b)
    row.addStretch(1)
    holder = theme.control_row(row)
    holder.resize(300, holder.layout().heightForWidth(300))
    holder.show()
    app.processEvents()

    assert isinstance(holder.layout(), theme.FlowLayout)
    assert holder.layout().count() == 8, "a widget was dropped on the way across"
    assert holder.minimumSizeHint().width() < 300, "the row still dictates the width"
    # Wrapped, not clipped: every button has a real position inside the holder.
    assert all(b.geometry().width() > 0 for b in buttons)
    assert len({b.y() for b in buttons}) > 1, "nothing wrapped at 300 px"
    holder.deleteLater()


def test_a_grid_of_controls_keeps_its_rows(app):
    """The gating bar is a two-row grid: Y on one line, X on the next. Wrapping it
    would interleave them, so it is scrolled rather than wrapped."""
    from PySide6 import QtWidgets
    from cytolux import theme

    grid = QtWidgets.QGridLayout()
    grid.addWidget(QtWidgets.QLabel("Y"), 0, 0)
    grid.addWidget(QtWidgets.QLabel("X"), 1, 0)
    holder = theme.control_row(grid)
    assert isinstance(holder, QtWidgets.QScrollArea)
    assert holder.minimumWidth() <= 120
    holder.deleteLater()
