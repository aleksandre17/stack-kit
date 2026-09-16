#!/bin/bash
# node-api remote dev — Windows edit → Linux workspace + `pnpm dev` (tsx watch) in a container.
# Mirror of java-boot/sh/dev.sh; the run command is pnpm (not gradle bootRun).
#
# Usage:
#   geostat <api> dev bootstrap [service] [--no-build]
#   geostat <api> dev sync [service]
#   geostat <api> dev watch [service] [--debounce-ms 1500] [--restart]
#   geostat <api> dev restart [service]
#   geostat <api> dev help

# shellcheck source=../_init.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_init.sh"

SUB="${1:-help}"
shift || true

SERVICE=""
NO_BUILD=0
NO_INITIAL_SYNC=0
DEBOUNCE_MS=1500
NO_RESTART=1   # default: rsync only (tsx watch reloads in container)

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
    *) [[ -z "$SERVICE" ]] && SERVICE="$arg" ;;
  esac
done

DEPLOY_LIB="$(geostat_kit_deploy_lib)"
# shellcheck source=../../toolkit/deploy/common.sh
source "$DEPLOY_LIB/common.sh"
# Generic dev helpers (rsync, paths, compose up/restart) …
# shellcheck source=../../toolkit/deploy/dev-remote.sh
source "$DEPLOY_LIB/dev-remote.sh"
# … then node overrides (workspace compose + node watch globs):
# shellcheck source=../../toolkit/deploy/node-dev-remote.sh
source "$DEPLOY_LIB/node-dev-remote.sh"

COMPOSE_FILE="docker-compose.dev.yml"
cd "$PROJECT_DIR" || exit 1
discover_services

if [[ "$SUB" == "help" || "$SUB" == "-h" || "$SUB" == "--help" ]]; then
  echo ""
  echo "  <api> dev — remote node dev (pnpm/tsx watch on Linux, NO image deploy)"
  echo ""
  echo "  bootstrap   rsync source + .env.dev + compose up (--build)"
  echo "  sync        rsync only"
  echo "  watch       poll saves → rsync (tsx watch reloads; --restart to force compose restart)"
  echo "  restart     docker compose restart on server"
  echo ""
  echo "  Requires: ${SECRETS_DIR:-ops/config/<secretsModule>}/.env.deploy (DEPLOY_LAYOUT=structured), rsync"
  echo "  NOT the same as: deploy (image → runtime/)"
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
    for s in "${SERVICES[@]}"; do echo "     $((local_i++))) $s"; done
    read -rp "  Service: " choice
    SERVICE="${SERVICES[$((choice - 1))]}"
  fi
fi

RP="$(dev_workspace_path_for "$SERVICE")"
CTR="$(container_name_for "$SERVICE")"
echo ""
echo "  <api> dev $SUB — $SERVICE ($CTR)"
echo "  Server: $SERVER"
echo "  Path:   $RP"
echo ""

case "$SUB" in
  bootstrap)
    echo "  [1/4] rsync source"
    dev_rsync_to_workspace "$SERVICE" || exit 1
    echo "  [2/4] env + compose file"
    dev_publish_workspace_env "$SERVICE" || exit 1
    dev_write_workspace_compose "$SERVICE" || exit 1
    echo "  [3/4] docker compose up"
    build_flag=""
    [[ "$NO_BUILD" -eq 0 ]] && build_flag="--build"
    dev_compose_up "$SERVICE" "$build_flag" || exit 1
    echo "  [4/4] manifest"
    dev_write_workspace_manifest "$SERVICE"
    echo "  [OK] pnpm dev on server — logs: geostat mod $GEOSTAT_MODULE_ID manage $SERVICE logs --dev"
    ;;
  sync)
    dev_rsync_to_workspace "$SERVICE" || exit 1
    echo "  [OK] synced (tsx watch reloads; or: dev restart)"
    ;;
  restart)
    dev_compose_restart "$SERVICE" || exit 1
    echo "  [OK] restarted"
    ;;
  watch)
    [[ "$NO_INITIAL_SYNC" -eq 0 ]] && dev_rsync_to_workspace "$SERVICE" || true
    restart_flag=0
    [[ "$NO_RESTART" -eq 0 ]] && restart_flag=1
    dev_watch_poll "$SERVICE" "$DEBOUNCE_MS" "$restart_flag"
    ;;
  *)
    echo "  ERROR: unknown subcommand: $SUB"
    exit 1
    ;;
esac
