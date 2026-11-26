# Working on Cytolux

`master` is what the last green CI run built. Nothing lands on it directly.

## One change, one branch

    git switch master && git pull
    git switch -c <kind>/<short-name>     # feat/, fix/, ci/, docs/, test/
    # work, commit in small steps
    git push -u origin HEAD
    gh pr create

Merge only when the `test` and all three `build` jobs are green, then delete the
branch. Squash when the branch history is noise; keep it when the steps matter.

Run once per clone, so git refuses a direct push to `master`:

    tools/install_hooks.sh

GitHub's own branch protection needs a paid plan on a private repository, so the
hook is the guard. `git push --no-verify` gets past it; don't.

## Before you push

    QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q

If you touched the gating engine, also run the FlowJo check on a real workspace:

    python -m tests.validate_flowjo <fcs_folder> <workspace.wsp>

and put its `exact counts` line in the pull request.

## Dependencies

CI installs against `constraints.txt`. To move a library, change its pin on a
branch of its own and let CI run the suite on all three platforms.

## Releases

Bump `__version__` in `cytolux/__init__.py`, add the section to `CHANGELOG.md`,
merge, then tag `master`:

    git tag -a vX.Y.Z -m "Cytolux X.Y.Z" && git push origin vX.Y.Z

The tag build publishes the three installers as a GitHub release.

## AI assistance

Commits written with an AI coding agent keep the agent's `Co-Authored-By` line.
Don't strip it.
