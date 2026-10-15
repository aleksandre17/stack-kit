#!/usr/bin/env bash
# Prepare minimal ops/config for CI — manifest-driven (no hardcoded backend/frontend paths)
set -euo pipefail
PKG="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${PKG}${PYTHONPATH:+:$PYTHONPATH}"
if [[ -z "${STACK_KIT_PROJECT_ROOT:-}" ]]; then
  export STACK_KIT_PROJECT_ROOT="$(cd "$PKG/../.." && pwd)"
fi
exec python3 "$PKG/lib/ci_prepare.py"
