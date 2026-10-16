#!/bin/bash
# Backend remote dev — Windows edit → Linux workspace + Gradle bootRun
#
# Usage:
#   stack-kit be dev bootstrap [service] [--no-build]
#   stack-kit be dev sync [service]
#   stack-kit be dev watch [service] [--debounce-ms 1500] [--no-restart]
#   stack-kit be dev restart [service]
#   stack-kit be dev help

# shellcheck source=../_init.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_init.sh"

SUB="${1:-help}"
shift || true

SERVICE=""
NO_BUILD=0
NO_INITIAL_SYNC=0
DEBOUNCE_MS=1500
# Default: rsync only (Spring DevTools restarts bootRun in container)
NO_RESTART=1

for arg in "$@"; do
  case "$arg" in
    --no-build) NO_BUILD=1 ;;
    --no-initial-sync) NO_INITIAL_SYNC=1 ;;
    --restart) NO_RESTART=0 ;;
    --no-restart) NO_RESTART=1 ;;
    --debounce-ms=*) DEBOUNCE_MS="${arg#*=}" ;;
    --debounce-ms) shift; DEBOUNCE_MS="${1:-1500}" ;;
    help|-h|--help) SUB="help" ;;
    bootstrap|sync|watch|restart) SUB="$arg" ;;
    *)
      if [[ -z "$SERVICE" ]]; then SERVICE="$arg"; fi
      ;;
  esac
done

DEPLOY_LIB="$(stack_kit_kit_deploy_lib)"
# shellcheck source=../../toolkit/deploy/common.sh
source "$DEPLOY_LIB/common.sh"
# shellcheck source=../../toolkit/deploy/dev-remote.sh
source "$DEPLOY_LIB/dev-remote.sh"

COMPOSE_FILE="docker-compose.dev.yml"
cd "$PROJECT_DIR" || exit 1
module_load_registry
discover_services

if [[ "$SUB" == "help" || "$SUB" == "-h" || "$SUB" == "--help" ]]; then
  echo ""
  echo "  be dev — remote backend dev (Gradle bootRun on Linux, NO JAR deploy)"
  echo ""
  echo "  bootstrap   rsync backend/ + .env.dev + compose up (--build)"
  echo "  sync        rsync only"
  echo "  watch       poll saves → rsync (DevTools restart in container; use --restart to force compose restart)"
  echo "  restart     docker compose restart on server"
  echo ""
  echo "  Requires: ${SECRETS_DIR:-ops/config/<secretsModule>}/.env.deploy (DEPLOY_LAYOUT=structured), rsync"
  echo "  NOT the same as: be deploy (JAR → runtime/)"
  echo ""
  echo "  Example:"
  echo "    stack-kit be dev bootstrap <compose-api-service>"
  echo "    stack-kit be dev watch"
  echo ""
  exit 0
fi

dev_assert_structured_layout || exit 1
[[ -n "$SERVER" ]] || { echo "  ERROR: DEPLOY_SERVER required"; exit 1; }

if [[ -z "$SERVICE" ]]; then
  if [[ ${#SERVICES[@]} -eq 1 ]]; then
    SERVICE="${SERVICES[0]}"
  else
    echo ""
    echo "  Select service for dev:"
    local_i=1
    for s in "${SERVICES[@]}"; do
      echo "     $((local_i++))) $s"
    done
    read -rp "  Service: " choice
    SERVICE="${SERVICES[$((choice - 1))]}"
  fi
fi

is_deployable_service "$SERVICE" || {
  echo "  ERROR: '$SERVICE' is not a deployable boot module"
  exit 1
}

RP="$(dev_workspace_path_for "$SERVICE")"
CTR="$(container_name_for "$SERVICE")"
echo ""
echo "  be dev $SUB — $SERVICE ($CTR)"
echo "  Server: $SERVER"
echo "  Path:   $RP"
echo ""

case "$SUB" in
  bootstrap)
    stack_kit_remote_preflight || exit 1
    echo "  [1/4] rsync source"
    dev_rsync_to_workspace "$SERVICE" || exit 1
    ssh -n "$SERVER" "chmod +x '$RP/gradlew' 2>/dev/null || true"
    echo "  [2/4] env + compose file"
    dev_publish_workspace_env "$SERVICE" || exit 1
    dev_write_workspace_compose "$SERVICE" || exit 1
    echo "  [3/4] docker compose up"
    build_flag=""
    [[ "$NO_BUILD" -eq 0 ]] && build_flag="--build"
    dev_compose_up "$SERVICE" "$build_flag" || exit 1
    echo "  [4/4] manifest"
    dev_write_workspace_manifest "$SERVICE"
    port_var="$(dev_port_var_for "$SERVICE")"
    def_port="$(dev_default_port_for "$SERVICE")"
    echo "  [OK] bootRun on server — check logs: stack-kit be manage $SERVICE logs --dev"
    echo "  API URL from ${SECRETS_DIR:-<secrets>}/.env.dev (\$$port_var default $def_port)"
    ;;

  sync)
    dev_rsync_to_workspace "$SERVICE" || exit 1
    echo "  [OK] synced (restart if JVM needs reload: be dev restart)"
    ;;

  restart)
    dev_compose_restart "$SERVICE" || exit 1
    echo "  [OK] restarted"
    ;;

  watch)
    [[ "$NO_INITIAL_SYNC" -eq 0 ]] && dev_rsync_to_workspace "$SERVICE" || true
    restart_flag=1
    [[ "$NO_RESTART" -eq 1 ]] && restart_flag=0
    dev_watch_poll "$SERVICE" "$DEBOUNCE_MS" "$restart_flag"
    ;;

  *)
    echo "  ERROR: unknown subcommand: $SUB"
    exit 1
    ;;
esac
