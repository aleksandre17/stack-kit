#!/usr/bin/env bash
# Dev modes verification — package + consumer (bash/Git Bash)
set -euo pipefail
PKG="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="${STACK_KIT_PROJECT_ROOT:-$(cd "$PKG/../.." && pwd)}"
export STACK_KIT_KIT_ROOT="$PKG"
export STACK_KIT_PROJECT_ROOT="$ROOT"
export PYTHONPATH="$PKG${PYTHONPATH:+:$PYTHONPATH}"

SKIP_DOCKER=0
SKIP_INTEGRATION=0
for a in "$@"; do
  case "$a" in
    --skip-docker) SKIP_DOCKER=1 ;;
    --skip-integration) SKIP_INTEGRATION=1 ;;
  esac
done

pass=0
fail=0

ok() { echo "  [PASS] $1"; pass=$((pass + 1)); }
bad() { echo "  [FAIL] $1 — ${2:-}" >&2; fail=$((fail + 1)); }

echo ""
echo "=== stack-kit dev-modes verify ==="
echo "  root: $ROOT"
echo "  kit:  $PKG"

echo "--- pytest ---"
cd "$PKG"
if python3 -m pytest tests -q --tb=no; then ok "pytest"; else bad "pytest"; fi

echo "--- validate ---"
if python3 "$PKG/lib/validate_manifest.py"; then ok "validate"; else bad "validate"; fi

echo "--- docs + vscode ---"
[[ -f "$PKG/docs/DEV-MODES.md" ]] && ok "DEV-MODES.md" || bad "DEV-MODES.md"
[[ -f "$ROOT/.vscode/launch.json" ]] && ok "launch.json" || bad "launch.json"
[[ -f "$ROOT/.vscode/tasks.json" ]] && ok "tasks.json" || bad "tasks.json"

echo "--- mode 3 smoke ---"
bash "$PKG/scripts/module-ops-smoke.sh" && ok "module-ops-smoke" || bad "module-ops-smoke"

echo "--- mode 2 docker (optional) ---"
if [[ "$SKIP_DOCKER" -eq 1 ]]; then
  ok "docker (skipped)"
else
  if command -v docker &>/dev/null && docker info &>/dev/null; then
    ok "docker daemon"
    if [[ -f "$ROOT/tools/stack-kit.ps1" ]]; then
      powershell -ExecutionPolicy Bypass -File "$ROOT/tools/stack-kit.ps1" fe check && ok "fe check" || bad "fe check"
      powershell -ExecutionPolicy Bypass -File "$ROOT/tools/stack-kit.ps1" be check && ok "be check" || bad "be check"
    fi
  else
    bad "docker daemon" "not running or not installed"
  fi
fi

echo "--- integration stack (optional) ---"
if [[ "$SKIP_INTEGRATION" -eq 1 ]]; then
  ok "integration-stack (skipped)"
elif [[ -f "$ROOT/ops/ci/integration-stack.sh" ]] && command -v docker &>/dev/null && docker info &>/dev/null; then
  if bash "$ROOT/ops/ci/integration-stack.sh"; then ok "integration-stack"; else bad "integration-stack"; fi
else
  ok "integration-stack (skipped — no docker or script)"
fi

echo ""
echo "=== Summary: $pass passed, $fail failed ==="
[[ "$fail" -eq 0 ]] || exit 1
echo "  E2E note: mode 1 (npm dev / bootRun) not auto-started."
exit 0
