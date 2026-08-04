#!/usr/bin/env bash
# Local CI gate — mirrors .github/workflows/ci.yml job "test" (single local Python).
# Also runs the "build" package check (uv build + twine), excluding PyPI publish.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "==> uv sync --frozen --group dev"
uv sync --frozen --group dev

echo "==> ruff check"
uv run ruff check .

echo "==> ruff format --check"
uv run ruff format --check .

echo "==> basedpyright"
uv run basedpyright --warnings acdd tests

echo "==> pytest"
uv run python -m pytest

echo "==> build + twine check"
rm -rf build dist *.egg-info acdd/*.egg-info
uv build
uv run --with twine python -m twine check dist/*

echo "ACDD CI gate OK"
