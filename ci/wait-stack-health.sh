#!/bin/bash
# Wait for all stack health targets (manifest stack.composeModules + stack-catalog)
set -euo pipefail

ROOT="${STACK_KIT_PROJECT_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
PKG="${STACK_KIT_KIT_ROOT:-$ROOT/kits/stack-kit}"
export STACK_KIT_PROJECT_ROOT="$ROOT"
export STACK_KIT_KIT_ROOT="$PKG"

MAX="${CI_HEALTH_TIMEOUT:-180}"
WAIT="${1:-$PKG/ci/wait-health.sh}"

if [[ ! -f "$WAIT" ]]; then
  echo "[ci] ERROR: wait script missing: $WAIT" >&2
  exit 1
fi

PY="python3"
if ! command -v python3 &>/dev/null; then
  PY="python"
fi

mapfile -t lines < <(
  cd "$PKG" && PYTHONPATH="$PKG" "$PY" lib/resolve_cli.py stack-health
)

if [[ ${#lines[@]} -eq 0 ]]; then
  echo "[ci] ERROR: no stack-health targets (check stack.composeModules / ci.healthModules)" >&2
  exit 1
fi

echo "[ci] Stack health matrix (${#lines[@]} targets, timeout ${MAX}s each)"
for line in "${lines[@]}"; do
  IFS=$'\t' read -r mod url expect <<< "$line"
  echo "[ci] -- $mod -> $url"
  bash "$WAIT" "$url" "$expect" "$MAX"
done
echo "[ci] Stack health matrix passed."
