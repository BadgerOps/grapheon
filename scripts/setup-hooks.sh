#!/usr/bin/env bash
#
# Install Graphēon pre-commit hooks.
#
# Usage:  ./scripts/setup-hooks.sh
#
# This tells git to look for hooks in .githooks/ (committed to the repo)
# instead of .git/hooks/ (local-only). Every contributor who runs this
# script once will automatically get the same hooks on future pulls.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Setting git hooksPath → .githooks/"
git -C "$REPO_ROOT" config core.hooksPath .githooks

chmod +x "$REPO_ROOT/.githooks/"*

echo "Done — pre-commit hook is now active."
echo ""
echo "Checks that run before each commit:"
echo "  1. ruff check backend"
echo "  2. python -m pytest"
echo "  3. python scripts/validate_versions.py"
echo "  4. npm run build (only when frontend/ files are staged)"
