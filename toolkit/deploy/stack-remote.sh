#!/bin/bash
# Full-stack remote deploy — steps from stack-kit.json stackDeploy (or defaults)
# Usage: stack-kit stack-deploy [--dev|--prod] [--no-build] [--skip-checks]

set -euo pipefail
PKG="$(cd "$(dirname "$0")/../.." && pwd)"
ROOT="$(cd "$PKG/../.." && pwd)"
export STACK_KIT_KIT_ROOT="$PKG"

# shellcheck source=../../lib/project.sh
source "$PKG/lib/project.sh"

STACK_KIT_PROJECT_ROOT="$(stack_kit_find_project_root "$ROOT" 2>/dev/null || echo "$ROOT")"
export STACK_KIT_PROJECT_ROOT

ENV_FLAG="--prod"
EXTRA=()
for arg in "$@"; do
  case "$arg" in
    --dev)  ENV_FLAG="--dev" ;;
    --prod) ENV_FLAG="--prod" ;;
    *)      EXTRA+=("$arg") ;;
  esac
done

ENV_NAME="prod"
[[ "$ENV_FLAG" == "--dev" ]] && ENV_NAME="dev"

echo ""
echo "  Stack remote deploy [$ENV_FLAG]"
echo ""

PWSH="$(command -v pwsh 2>/dev/null || command -v powershell.exe 2>/dev/null || true)"
[[ -n "$PWSH" ]] || { echo "  ERROR: PowerShell (pwsh or powershell.exe) is required to run module steps" >&2; exit 1; }

step=0

# Each step's argv is its driver's release rung, `{environment}` substituted; a flag below reaches
# a step only when that rung `forwards` it (drivers/registry.json). No driver is named here.
mapfile -t LINES < <(PYTHONPATH="$PKG" stack_kit_python "$PKG/lib/resolve_cli.py" stack-steps "$ENV_NAME" "${EXTRA[@]}")
total="${#LINES[@]}"

for line in "${LINES[@]}"; do
  line="${line//$'\r'/}"
  step=$((step + 1))
  IFS=$'\t' read -r module_id subcmd args_rest <<< "$line"
  args_rest="${args_rest//$'\r'/}"
  args=()
  if [[ -n "${args_rest:-}" ]]; then
    # shellcheck disable=SC2206
    args=($args_rest)
  fi
  echo "  $step/$total  module=$module_id  $subcmd ${args[*]}"
  echo ""
  # shellcheck disable=SC2086
  "$PWSH" -ExecutionPolicy Bypass -NoProfile -File \
    "$PKG/cli/stack-kit.ps1" mod "$module_id" "$subcmd" "${args[@]}"
  echo ""
done

echo "  Stack deploy finished."
echo ""
