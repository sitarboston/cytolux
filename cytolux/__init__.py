"""Cytolux: a desktop flow cytometry viewer and gating application."""

# The one place the version is written. pyproject.toml reads it from here via
# setuptools' dynamic attr, so the two can no longer drift: the v0.3.0 build
# introduced itself as 0.2.0 because the number was written down twice.
# Reading it from importlib.metadata instead does not work in a PyInstaller
# bundle, which carries no dist-info.
__version__ = "0.3.2"
