#!/bin/bash
# Migrate flat backend deploy dirs -> structured runtime/ (server-side via SSH)
#
# Usage:
#   bash kits/stack-kit/toolkit/deploy/migrate-backend-layout.sh [--dry-run] [--dev|--prod]
#
# Requires: api module .env.deploy (DEPLOY_LAYOUT=structured), ops/config/deploy.env

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export STACK_KIT_KIT_ROOT="$PKG_ROOT"

# shellcheck source=../../lib/project.sh
source "$PKG_ROOT/lib/project.sh"
# shellcheck source=../../lib/env.sh
source "$PKG_ROOT/lib/env.sh"
# shellcheck source=../../lib/ssh.sh
source "$PKG_ROOT/lib/ssh.sh"
stack_kit_ssh_maybe_alias

STACK_KIT_PROJECT_ROOT="$(stack_kit_find_project_root "$(pwd)" 2>/dev/null || echo "$(cd "$PKG_ROOT/../../.." && pwd)")"
export STACK_KIT_PROJECT_ROOT
if [[ -n "$(_stack_kit_resolve target 2>/dev/null)" ]]; then
  echo "  REFUSED: layout migration and cleanup are for a host without deploy targets; a declared target's" >&2
  echo "  layout is its own -- see: stack-kit targets --plan / --verify" >&2
  exit 1
fi

OPS_MODULE_ID="$(stack_kit_module_id_for_role api)"
[[ -n "$OPS_MODULE_ID" ]] || OPS_MODULE_ID="$(stack_kit_module_id_for_deploy_kind runtime)"
[[ -n "$OPS_MODULE_ID" ]] || { echo "  ERROR: no api module, and no module whose driver deploys as runtime" >&2; exit 1; }
OPS_SECRETS_MODULE="$(stack_kit_secrets_module_name "$OPS_MODULE_ID")"
SECRETS_DIR="$(stack_kit_secrets_dir_for_module "$OPS_MODULE_ID")"
SERVER="$(stack_kit_env_value "$OPS_SECRETS_MODULE" DEPLOY_SERVER "$(stack_kit_deploy_env_value DEPLOY_SERVER "")")"
PROJECT="$(stack_kit_env_value "$OPS_SECRETS_MODULE" DEPLOY_PROJECT "")"
[[ -n "$PROJECT" ]] || PROJECT="$(stack_kit_project_slug)"
DEPLOY_PATH_BASE="$(stack_kit_env_value "$OPS_SECRETS_MODULE" DEPLOY_PATH "")"
[[ -n "$DEPLOY_PATH_BASE" ]] || DEPLOY_PATH_BASE="$(stack_kit_default_remote_deploy_base "$OPS_SECRETS_MODULE")"
DEPLOY_PATH_BASE="${DEPLOY_PATH_BASE%/}"
LAYOUT="$(stack_kit_env_value "$OPS_SECRETS_MODULE" DEPLOY_LAYOUT "flat")"
RENAME_PAIRS="$(PYTHONPATH="${PKG_ROOT}" stack_kit_python "$PKG_ROOT/lib/migrate_layout_names.py" --pairs-api 2>/dev/null || true)"
SOURCE_DIRS="$(PYTHONPATH="${PKG_ROOT}" stack_kit_python "$PKG_ROOT/lib/migrate_layout_names.py" --sources-api 2>/dev/null || true)"

DRY_RUN=0
ENVIRONMENT="prod"
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --dev) ENVIRONMENT="dev" ;;
    --prod) ENVIRONMENT="prod" ;;
  esac
done

COMPOSE_FILE="docker-compose.${ENVIRONMENT}.yml"

if [[ "$LAYOUT" != "structured" ]]; then
  echo "  ERROR: DEPLOY_LAYOUT must be structured in ${SECRETS_DIR}/.env.deploy" >&2
  exit 1
fi
[[ -n "$SERVER" ]] || { echo "  ERROR: DEPLOY_SERVER not set" >&2; exit 1; }

echo ""
echo "  Backend layout migration (flat -> runtime/)"
echo "  Server: $SERVER"
echo "  Base:   $DEPLOY_PATH_BASE"
if [[ -n "$SOURCE_DIRS" ]]; then
  echo "  Scope:  $SOURCE_DIRS"
fi
if [[ -n "$RENAME_PAIRS" ]]; then
  echo "  Renames: $RENAME_PAIRS"
fi
echo "  Mode:   $(if [[ $DRY_RUN -eq 1 ]]; then echo 'dry-run'; else echo 'apply'; fi)"
echo ""

stack_kit_ssh "$SERVER" "bash -s" -- "$DEPLOY_PATH_BASE" "$COMPOSE_FILE" "$DRY_RUN" "$RENAME_PAIRS" "$SOURCE_DIRS" <<'REMOTE'
set -euo pipefail
BASE="$1"
COMPOSE_FILE="$2"
DRY="$3"
RENAME_PAIRS="${4:-}"
SOURCE_DIRS="${5:-}"

resolve_dest() {
  local name="$1"
  local p old new
  if [[ -z "$RENAME_PAIRS" ]]; then
    echo "$name"
    return
  fi
  IFS=',' read -ra _pairs <<< "$RENAME_PAIRS"
  for p in "${_pairs[@]}"; do
    [[ -z "$p" ]] && continue
    old="${p%%:*}"
    new="${p#*:}"
    if [[ "$name" == "$old" && -n "$new" ]]; then
      echo "$new"
      return
    fi
  done
  echo "$name"
}

is_scoped() {
  local name="$1" d
  [[ -n "$SOURCE_DIRS" ]] || return 1
  IFS=',' read -ra _dirs <<< "$SOURCE_DIRS"
  for d in "${_dirs[@]}"; do
    [[ -z "$d" ]] && continue
    [[ "$name" == "$d" ]] && return 0
  done
  return 1
}

for old in "$BASE"/*; do
  [[ -d "$old" ]] || continue
  name="$(basename "$old")"
  [[ "$name" == "runtime" || "$name" == "workspace" ]] && continue
  is_scoped "$name" || continue
  [[ -f "$old/$COMPOSE_FILE" || -f "$old/app.jar" || -f "$old/Dockerfile" ]] || continue
  dest_name="$(resolve_dest "$name")"
  new="$BASE/runtime/$dest_name"
  if [[ -d "$new" ]]; then
    echo "  [skip] $name - runtime already exists: $new"
    continue
  fi
  if [[ "$DRY" == "1" ]]; then
    echo "  [dry-run] mv $old -> $new"
  else
    mkdir -p "$BASE/runtime"
    mv "$old" "$new"
    echo "  [OK] mv $old -> $new"
  fi
done
REMOTE

echo ""
echo "  Done. Verify: stack-kit be manage <service> status --$ENVIRONMENT"
echo ""
