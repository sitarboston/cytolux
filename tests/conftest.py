"""Keep the suite out of his real preferences.

MainWindow saves its geometry and dock layout on close, which is what the application
should do and what a test run must not do: the windows here are built on a small
offscreen screen, so a run would leave his next launch narrow with the Ask panel
collapsed. QSettings.setPath cannot redirect the native format on macOS or Windows,
so the application reads an environment variable instead, and it is set here at
import time, before the first window exists.
"""
import os
import tempfile

os.environ["CYTOLUX_SETTINGS"] = os.path.join(
    tempfile.mkdtemp(prefix="cytolux-tests-"), "cytolux.ini")
