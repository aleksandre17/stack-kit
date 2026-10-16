#!/bin/bash
# Shared helpers for backend deploy — source from deploy.sh after _init.sh

deploy_log() { echo "$1"; }

# shellcheck source=provenance.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/provenance.sh"

# shellcheck source=modules.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/modules.sh"
# shellcheck source=deploy-path.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deploy-path.sh"

is_subproject() {
  local s="$1"
  [[ -n "$(module_gradle_name "$s")" ]]
}

container_name_for() {
  local s="$1"
  local name
  name=$(awk "/^  ${s}:/{f=1;next} f && /^  [^ ]/{f=0} f && /container_name:/{gsub(/.*container_name:[[:space:]]*/,\"\"); gsub(/[\"']/,\"\"); print; exit}" "$PROJECT_DIR/$COMPOSE_FILE")
  echo "${name:-$s}"
}

discover_services() {
  mapfile -t SERVICES < <(
    awk '/^services:/{f=1;next} f && /^[^ ]/{f=0} f && /^  [a-zA-Z0-9_-]+:/{gsub(/[ :]/,""); print}' \
      "$PROJECT_DIR/$COMPOSE_FILE" 2>/dev/null
  )
  module_load_registry
  local filtered=() s
  for s in "${SERVICES[@]}"; do
    if [[ -f "$OPS_MODULES_FILE" ]] && ! is_deployable_service "$s"; then
      deploy_log "  [skip] $s (library / not deployable)"
      continue
    fi
    filtered+=("$s")
  done
  [[ ${#filtered[@]} -gt 0 ]] && SERVICES=("${filtered[@]}")
}

# Map a module shorthand (<moduleId>) → compose service key (<slug>-<moduleId>).
resolve_deploy_service_arg() {
  local raw="$1" s
  [[ -z "$raw" || "$raw" == "all" ]] && { echo "$raw"; return 0; }
  for s in "${SERVICES[@]}"; do
    [[ "$s" == "$raw" ]] && { echo "$raw"; return 0; }
  done
  for s in "${SERVICES[@]}"; do
    [[ "$s" == *"-$raw" ]] && { echo "$s"; return 0; }
  done
  return 1
}

apply_deploy_service_arg() {
  local resolved
  SERVICE="${SERVICE//$'\r'/}"
  [[ -z "$SERVICE" || "$SERVICE" == "all" ]] && return 0
  if resolved="$(resolve_deploy_service_arg "$SERVICE")"; then
    [[ "$resolved" != "$SERVICE" ]] && deploy_log "  Service: $SERVICE → $resolved"
    SERVICE="$resolved"
    return 0
  fi
  deploy_log "  ERROR: Unknown service '$SERVICE'"
  deploy_log "  Available: ${SERVICES[*]} all"
  exit 1
}
