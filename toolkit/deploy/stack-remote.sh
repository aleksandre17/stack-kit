#!/bin/bash
# Full-stack remote deploy — steps from stack-kit.json stackDeploy (or defaults)
# Usage: stack-kit stack-deploy [--dev|--prod] [--no-build] [--skip-checks]

set -euo pipefail
PKG="$(cd "$(dirname "$0")/../.." && pwd)"
export STACK_KIT_KIT_ROOT="$PKG"

# shellcheck source=../../lib/project.sh
source "$PKG/lib/project.sh"

# The project is the declared root, else the one the working directory is in (the resolver's one
# discovery) -- never a guess from where the kit happens to be vendored.
STACK_KIT_PROJECT_ROOT="$(stack_kit_find_project_root)" || { echo "  ERROR: no project manifest here" >&2; exit 1; }
export STACK_KIT_PROJECT_ROOT
ROOT="$STACK_KIT_PROJECT_ROOT"

ENV_FLAG="--prod"
EXTRA=()
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[$i]}" in
    --dev)  ENV_FLAG="--dev" ;;
    --prod) ENV_FLAG="--prod" ;;
    --target) export STACK_KIT_TARGET="${args[$((i + 1))]:-}"; i=$((i + 1)) ;;
    *)      EXTRA+=("${args[$i]}") ;;
  esac
done
export STACK_KIT_ENVIRONMENT="${ENV_FLAG#--}"

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
