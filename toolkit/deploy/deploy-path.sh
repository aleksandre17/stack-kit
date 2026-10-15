#!/bin/bash
# Backend deploy path resolution (structured runtime/ + workspace/)
# Requires: OPS_SECRETS_MODULE, SERVER_BASE, PROJECT (from _common.sh)
# Optional: COMPOSE_FILE, PROJECT_DIR for container_name_for (modules.sh)

deploy_path_load_config() {
  local deploy_base_module
  deploy_base_module="$(stack_kit_read_manifest_field stack.deployBaseSecretsModule backend)"
  DEPLOY_PATH_BASE="${DEPLOY_PATH_BASE:-$(stack_kit_env_value "$OPS_SECRETS_MODULE" DEPLOY_PATH "")}"
  if [[ -z "$DEPLOY_PATH_BASE" && -n "${OPS_SECRETS_MODULE:-}" && "$OPS_SECRETS_MODULE" != "$deploy_base_module" ]]; then
    DEPLOY_PATH_BASE="$(stack_kit_env_value "$deploy_base_module" DEPLOY_PATH "")"
  fi
  if [[ -z "$DEPLOY_PATH_BASE" && -n "${OPS_SECRETS_MODULE:-}" ]]; then
    DEPLOY_PATH_BASE="$(stack_kit_default_remote_deploy_base "$OPS_SECRETS_MODULE")"
  fi
  DEPLOY_PATH_BASE="${DEPLOY_PATH_BASE%/}"
  DEPLOY_LAYOUT="${DEPLOY_LAYOUT:-$(stack_kit_env_value "$OPS_SECRETS_MODULE" DEPLOY_LAYOUT "")}"
  [[ -n "$DEPLOY_LAYOUT" ]] || DEPLOY_LAYOUT="flat"
  DEPLOY_PATH_MODE="${DEPLOY_PATH_MODE:-$(stack_kit_env_value "$OPS_SECRETS_MODULE" DEPLOY_PATH_MODE "base")}"
  case "$DEPLOY_LAYOUT" in
    structured | flat | legacy) ;;
    *) DEPLOY_LAYOUT="structured" ;;
  esac
  case "$DEPLOY_PATH_MODE" in
    base | full) ;;
    *) DEPLOY_PATH_MODE="base" ;;
  esac
}

# resolve_backend_deploy_path <container_name> [runtime|workspace]
resolve_backend_deploy_path() {
  local container="$1" kind="${2:-runtime}"
  deploy_path_load_config
  [[ -n "$DEPLOY_PATH_BASE" ]] || {
    echo "ERROR: DEPLOY_PATH or DEPLOY_SERVER_BASE required in secrets" >&2
    return 1
  }

  if [[ "$DEPLOY_PATH_MODE" == "full" ]]; then
    if [[ "$DEPLOY_PATH_BASE" == */"$container" ]]; then
      echo "$DEPLOY_PATH_BASE"
    else
      echo "$DEPLOY_PATH_BASE"
    fi
    return 0
  fi

  if [[ "$DEPLOY_LAYOUT" == "structured" ]]; then
    if [[ "$kind" == "workspace" ]]; then
      echo "$DEPLOY_PATH_BASE/workspace/$container"
    else
      echo "$DEPLOY_PATH_BASE/runtime/$container"
    fi
    return 0
  fi

  if [[ "$DEPLOY_PATH_BASE" == */"$container" ]]; then
    echo "$DEPLOY_PATH_BASE"
  else
    echo "$DEPLOY_PATH_BASE/$container"
  fi
}

# Full remote path for a compose service (JAR deploy uses runtime/)
remote_path_for_service() {
  local s="$1" cname
  cname="$(container_name_for "$s")"
  resolve_backend_deploy_path "$cname" "runtime"
}

# Legacy name: returns full deploy path (not just container segment)
remote_dir_for_service() {
  remote_path_for_service "$1"
}

# Ordered candidates for server discovery / migration
backend_deploy_path_candidates() {
  local container="$1"
  deploy_path_load_config
  [[ -n "$DEPLOY_PATH_BASE" ]] || return 0
  echo "$DEPLOY_PATH_BASE/runtime/$container"
  echo "$DEPLOY_PATH_BASE/workspace/$container"
  echo "$DEPLOY_PATH_BASE/$container"
}

# First candidate on server that has the env-specific compose file (for manage)
backend_find_deployed_path() {
  local compose_svc="$1" cname candidate
  cname="$(container_name_for "$compose_svc")"
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] || continue
    if ssh -n "$SERVER" "test -f '$candidate/$COMPOSE_FILE'" 2>/dev/null; then
      echo "$candidate"
      return 0
    fi
  done < <(backend_deploy_path_candidates "$cname")
  return 1
}

# Log-friendly summary of where JAR deploy lands (structured: backend/runtime/<container>/)
deploy_path_summary() {
  deploy_path_load_config
  if [[ -z "$DEPLOY_PATH_BASE" ]]; then
    echo "${SERVER_BASE}/${PROJECT}/backend/runtime/<container>/ (set DEPLOY_PATH in ops/config)"
    return 0
  fi
  if [[ "$DEPLOY_LAYOUT" == "structured" ]]; then
    echo "${DEPLOY_PATH_BASE}/runtime/<container>/"
    return 0
  fi
  echo "${DEPLOY_PATH_BASE}/<container>/"
}
