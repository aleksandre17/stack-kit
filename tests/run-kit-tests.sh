#!/usr/bin/env bash
# Run stack-kit package tests (no SSH/Docker required)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PKG="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PKG"
export PYTHONPATH="${PKG}${PYTHONPATH:+:$PYTHONPATH}"
if ! python3 -m pytest --version >/dev/null 2>&1; then
  python3 -m pip install -q pytest
fi
python3 -m pytest tests/ -v --tb=short "$@"
