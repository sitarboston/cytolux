#!/bin/sh
# Point this clone at the versioned hooks in tools/hooks. Run once per clone.
set -e
cd "$(git rev-parse --show-toplevel)"
chmod +x tools/hooks/*
git config core.hooksPath tools/hooks
echo "hooks installed from tools/hooks"
