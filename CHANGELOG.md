# Changelog

Versions follow `cytolux/__init__.py`. v0.3.1 onwards have GitHub releases; the
earlier versions are tagged `flowgate-0.1` and `flowgate-0.2` at the commits that
introduced them, and were never packaged.

## Unreleased

## 0.3.2, 2026-11-26

- MIT licence, CITATION.cff, and a screenshot of the Confidence panel at the top of
  the README.
- The combined confidence interval is clamped to 0 to 100%. A 99.64% singlet gate
  had shown "98.11 to 101.16".
- CI uploads installers only for `v*` tags and installs against `constraints.txt`.
  Every untagged build from 2026-11-18 on had failed at the upload step after the
  account's artifact quota filled.
- Branch and pull-request workflow, `CONTRIBUTING.md`, a pre-push hook that refuses
  direct pushes to `master`, and this file.
- The three builds behave the same on Windows, macOS and Linux: macOS Delete and
  Backspace, settings isolated from test runs, a window that fits a small laptop.
  The Ask panel toggle no longer depends on the display granting focus.
- Three public-domain FCS files in `testdata/`, from the axi-cel cohort of Good et al.,
  Nature Medicine 2022, so a fresh clone has data to open.

## 0.3.1, 2026-11-14

- The binaries report their own version. The 0.3.0 build introduced itself as
  0.2.0 because the number was kept in two files; `cytolux/__init__.py` is now the
  only one.

## 0.3.0, 2026-11-14 (untagged)

- Renamed from FlowGate to Cytolux.
- Installers for Windows (Inno Setup), macOS (DMG, Apple silicon) and Linux
  (AppImage, built on Ubuntu 22.04 for older glibc), each smoke-tested in CI.
- Confidence intervals on every gated frequency (Ctrl+U), a confidence panel, and a
  sweep that ranks the weakest gates in a workspace.
- Overlays of several samples on one plot; draggable quadrants; contours that skip
  sparse noise; MFI from a gate in two clicks; publication export of plots.
- Undo and redo, a sample filter, a tooltip on every control, offline help search.
- Packaged with `pyproject.toml`, a pytest suite, and CI on all three platforms.

## 0.2, 2026-10-09 (FlowGate)

- Statistics builder, sample annotations, Excel export, gating templates, the
  step-by-step guide.
- FlowJo gates imported on FlowJo's own display axes; panel chart tool.
- Gate edits apply to the current sample only, as in FlowJo (2026-10-17).

## 0.1, 2026-10-09 (FlowGate)

- Desktop viewer and gating app for FCS 2.0, 3.0 and 3.1.
