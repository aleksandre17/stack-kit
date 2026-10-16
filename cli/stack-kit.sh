#!/usr/bin/env bash
# stack-kit CLI launcher: everything is the Python CLI's (cli/stack_kit.py -> lib/cli), the same verbs
# in a terminal and in CI (ADR-001 amendment 13). This file only finds Python and passes the
# command line through, unchanged.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
py="$(command -v python3 || command -v python || true)"
[[ -n "$py" ]] || { echo "ERROR: Python 3 is required" >&2; exit 9; }
export PYTHONUTF8=1
exec "$py" -B "$here/stack_kit.py" "$@"
