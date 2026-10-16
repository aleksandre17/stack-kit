#!/bin/bash
# Remove this consumer's flat/structured deploy dirs on remote server (scoped — no other projects).
# Does NOT stop or remove Docker containers (legacy names may keep running).
#
# Usage:
#   stack-kit layout cleanup [--dry-run] [--dev|--prod] [--backend|--frontend|--all]
#   stack-kit layout cleanup --legacy-segments   # safe: empty stack-kit/{retrieval,ingestion}/ only

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

RUN_BACKEND=0
RUN_FRONTEND=0
RUN_LEGACY_SEGMENTS=0
DRY_RUN=0
ENVIRONMENT="prod"

for arg in "$@"; do
  case "$arg" in
    --backend|--api) RUN_BACKEND=1 ;;
    --frontend|--ui) RUN_FRONTEND=1 ;;
    --all) RUN_BACKEND=1; RUN_FRONTEND=1 ;;
    --legacy-segments) RUN_LEGACY_SEGMENTS=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --dev) ENVIRONMENT="dev" ;;
    --prod) ENVIRONMENT="prod" ;;
  esac
done

if [[ $RUN_BACKEND -eq 0 && $RUN_FRONTEND -eq 0 && $RUN_LEGACY_SEGMENTS -eq 0 ]]; then
  RUN_BACKEND=1
  RUN_FRONTEND=1
fi

echo ""
echo "  stack-kit layout cleanup (scoped — this consumer only)"
echo "  Project: $STACK_KIT_PROJECT_ROOT"
echo "  Mode:    $(if [[ $DRY_RUN -eq 1 ]]; then echo 'dry-run'; else echo 'apply'; fi)"
echo ""

run_cleanup() {
  local role="$1" module_id kind subdir
  module_id="$(stack_kit_module_id_for_role "$role" 2>/dev/null || true)"
  if [[ -z "$module_id" ]]; then
    # No module of the role: the one whose driver deploys as this layout's kind (deployKind).
    if [[ "$role" == "api" ]]; then
      module_id="$(stack_kit_module_id_for_deploy_kind runtime 2>/dev/null || true)"
    else
      module_id="$(stack_kit_module_id_for_deploy_kind static 2>/dev/null || true)"
    fi
  fi
  [[ -n "$module_id" ]] || { echo "  [skip] $role — no module"; return 0; }

  local secrets_module server base sources pairs
  secrets_module="$(stack_kit_secrets_module_name "$module_id")"
  server="$(stack_kit_env_value "$secrets_module" DEPLOY_SERVER "$(stack_kit_deploy_env_value DEPLOY_SERVER "")")"
  base="$(stack_kit_env_value "$secrets_module" DEPLOY_PATH "")"
  [[ -n "$base" ]] || base="$(stack_kit_default_remote_deploy_base "$secrets_module")"
  base="${base%/}"
  [[ -n "$server" ]] || { echo "  ERROR: DEPLOY_SERVER not set" >&2; exit 1; }

  if [[ "$role" == "api" ]]; then
    kind="runtime"
    subdir="$role ($module_id)"
    sources="$(PYTHONPATH="${PKG_ROOT}" stack_kit_python "$PKG_ROOT/lib/migrate_layout_names.py" --sources-api 2>/dev/null || true)"
    pairs="$(PYTHONPATH="${PKG_ROOT}" stack_kit_python "$PKG_ROOT/lib/migrate_layout_names.py" --pairs-api 2>/dev/null || true)"
  else
    kind="static"
    subdir="$role ($module_id)"
    sources="$(PYTHONPATH="${PKG_ROOT}" stack_kit_python "$PKG_ROOT/lib/migrate_layout_names.py" --sources-ui 2>/dev/null || true)"
    pairs="$(PYTHONPATH="${PKG_ROOT}" stack_kit_python "$PKG_ROOT/lib/migrate_layout_names.py" --pairs-ui 2>/dev/null || true)"
  fi

  echo "  $subdir cleanup"
  echo "  Server: $server"
  echo "  Base:   $base"
  echo "  Scope:  $sources"
  [[ -n "$pairs" ]] && echo "  Renames(ref): $pairs"
  echo ""

  stack_kit_ssh "$server" "bash -s" -- "$base" "$kind" "$DRY_RUN" "$sources" "$pairs" <<'REMOTE'
set -euo pipefail
BASE="$1"
KIND="$2"
DRY="$3"
SOURCE_DIRS="$4"
RENAME_PAIRS="${5:-}"

resolve_dest() {
  local name="$1" p old new
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

names_for() {
  local name="$1" dest
  dest="$(resolve_dest "$name")"
  printf '%s\n' "$name"
  if [[ "$dest" != "$name" ]]; then
    printf '%s\n' "$dest"
  fi
}

remove_dir() {
  local d="$1"
  [[ -d "$d" ]] || return 0
  if [[ "$DRY" == "1" ]]; then
    echo "  [dry-run] rm -rf $d"
  else
    rm -rf "$d"
    echo "  [OK] deleted: $d"
  fi
}

IFS=',' read -ra _scope <<< "$SOURCE_DIRS"
for src in "${_scope[@]}"; do
  [[ -z "$src" ]] && continue
  while IFS= read -r n; do
    [[ -z "$n" ]] && continue
    remove_dir "$BASE/$n"
    remove_dir "$BASE/$KIND/$n"
  done < <(names_for "$src")
done
REMOTE
  echo ""
}

[[ $RUN_BACKEND -eq 1 ]] && run_cleanup api
[[ $RUN_FRONTEND -eq 1 ]] && run_cleanup ui

# Legacy deploy.sh mkdir artifacts: empty stack-kit/{retrieval,ingestion,...} (not D-10 layout)
if [[ $RUN_LEGACY_SEGMENTS -eq 1 ]]; then
  server="$(stack_kit_deploy_env_value DEPLOY_SERVER "")"
  proj="$(stack_kit_project_slug)"
  root_base="$(stack_kit_server_base)/$proj"
  if [[ -n "$server" ]]; then
    echo "  legacy segment cleanup (empty dirs only)"
    for seg in retrieval ingestion; do
      if [[ "$DRY_RUN" -eq 1 ]]; then
        stack_kit_ssh "$server" "if [ -d '${root_base}/${seg}' ] && [ -z \"\$(ls -A '${root_base}/${seg}' 2>/dev/null)\" ]; then echo '  [dry-run] rmdir ${root_base}/${seg}'; fi" || true
      else
        stack_kit_ssh "$server" "if [ -d '${root_base}/${seg}' ] && [ -z \"\$(ls -A '${root_base}/${seg}' 2>/dev/null)\" ]; then rmdir '${root_base}/${seg}' && echo '  [OK] removed empty ${root_base}/${seg}'; fi" || true
      fi
    done
    echo ""
  fi
fi

echo "  Done."
echo ""
