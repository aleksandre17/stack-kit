#!/bin/bash
# P6-migrate — flat → structured deploy layout on remote server (backend runtime/ + frontend static/)
#
# Usage:
#   stack-kit layout migrate [--dry-run] [--dev|--prod] [--backend|--frontend|--all]
#
# Default: --all (backend + frontend when modules exist)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export STACK_KIT_KIT_ROOT="$PKG_ROOT"

# shellcheck source=../../lib/project.sh
source "$PKG_ROOT/lib/project.sh"

STACK_KIT_PROJECT_ROOT="$(stack_kit_find_project_root "$(pwd)" 2>/dev/null || echo "$(cd "$PKG_ROOT/../../.." && pwd)")"
export STACK_KIT_PROJECT_ROOT

RUN_BACKEND=0
RUN_FRONTEND=0
PASS_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --backend|--api) RUN_BACKEND=1 ;;
    --frontend|--ui) RUN_FRONTEND=1 ;;
    --all) RUN_BACKEND=1; RUN_FRONTEND=1 ;;
    *) PASS_ARGS+=("$arg") ;;
  esac
done

if [[ $RUN_BACKEND -eq 0 && $RUN_FRONTEND -eq 0 ]]; then
  RUN_BACKEND=1
  RUN_FRONTEND=1
fi

echo ""
echo "  stack-kit layout migrate (P6-migrate)"
echo "  Project: $STACK_KIT_PROJECT_ROOT"
echo ""

if [[ $RUN_BACKEND -eq 1 ]]; then
  mid="$(stack_kit_module_id_for_role api 2>/dev/null || true)"
  [[ -n "$mid" ]] || mid="$(stack_kit_module_id_for_type java-boot 2>/dev/null || true)"
  if [[ -n "$mid" ]]; then
    bash "$SCRIPT_DIR/migrate-backend-layout.sh" "${PASS_ARGS[@]}"
  else
    echo "  [skip] backend — no api/java-boot module"
  fi
fi

if [[ $RUN_FRONTEND -eq 1 ]]; then
  mid="$(stack_kit_module_id_for_role ui 2>/dev/null || true)"
  [[ -n "$mid" ]] || mid="$(stack_kit_module_id_for_type node-vite 2>/dev/null || true)"
  if [[ -n "$mid" ]]; then
    bash "$SCRIPT_DIR/migrate-frontend-layout.sh" "${PASS_ARGS[@]}"
  else
    echo "  [skip] frontend — no ui/node-vite module"
  fi
fi

echo ""
echo "  Next: stack-kit stack-deploy --prod  (new compose service names from manifest)"
echo ""
