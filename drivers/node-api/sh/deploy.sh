#!/bin/bash
# node-api SSH deploy — orchestrator (kits/geostat-kit/toolkit/deploy/)
# Same lifecycle as java-boot/sh/deploy.sh; the build is pnpm (workspace) and the artifact
# is a server-built docker image (multi-stage Dockerfile), not a gradle JAR.
#
# Usage:
#   geostat <api-alias> deploy [service] [--dev|--prod] [--no-build] [--skip-checks]

# shellcheck source=../_init.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_init.sh"

DEPLOY_LIB="$(geostat_kit_deploy_lib)"
# Generic helpers reused as-is from the toolkit (path resolution, compose-gen):
# shellcheck source=../../toolkit/deploy/common.sh
source "$DEPLOY_LIB/common.sh"
# shellcheck source=../../toolkit/deploy/server-compose.sh
source "$DEPLOY_LIB/server-compose.sh"
# Node-stack step helpers (pnpm build / context upload / image up + rollback):
# shellcheck source=../../toolkit/deploy/pnpm-build.sh
source "$DEPLOY_LIB/pnpm-build.sh"
# shellcheck source=../../toolkit/deploy/node-upload.sh
source "$DEPLOY_LIB/node-upload.sh"
# shellcheck source=../../toolkit/deploy/node-docker-up.sh
source "$DEPLOY_LIB/node-docker-up.sh"

ENVIRONMENT="prod"
SERVICE=""
SKIP_BUILD=0
SKIP_CHECKS=0

for arg in "$@"; do
  arg="${arg//$'\r'/}"
  case "$arg" in
    --no-build)    SKIP_BUILD=1 ;;
    --skip-checks) SKIP_CHECKS=1 ;;
    --dev)         ENVIRONMENT="dev" ;;
    --prod)        ENVIRONMENT="prod" ;;
    all)           SERVICE="all" ;;
    *)             SERVICE="$arg" ;;
  esac
done

COMPOSE_FILE="docker-compose.${ENVIRONMENT}.yml"
ENV_FILE=".env.${ENVIRONMENT}"
cd "$PROJECT_DIR" || exit 1

discover_services
if [ ${#SERVICES[@]} -eq 0 ]; then
  echo "  ERROR: No services in $COMPOSE_FILE"
  exit 1
fi

apply_deploy_service_arg

deploy_path_load_config
DEPLOY_SUMMARY="$(deploy_path_summary)"

if [ -z "$SERVICE" ]; then
  echo ""
  echo "  Deployer  [$DEPLOY_SUMMARY] [$ENVIRONMENT]"
  echo ""
  local_i=1
  for s in "${SERVICES[@]}"; do echo "     $((local_i++))) $s"; done
  echo "     $local_i) all"
  read -rp "  Service: " choice
  if [ "$choice" = "$local_i" ]; then SERVICE="all"
  else SERVICE="${SERVICES[$((choice - 1))]}"; fi
fi
[ -z "$SERVICE" ] && SERVICE="all"

if [ "$SKIP_CHECKS" = "0" ]; then
  check_args="$SERVICE"
  [ "$SKIP_BUILD" = "1" ] && check_args="$check_args --no-build"
  bash "$(dirname "$0")/check.sh" $check_args || exit 1
fi

DEPLOY_VERSION="$(date +%Y%m%d-%H%M%S)"
echo ""
echo "  Deploy [$SERVICE] → $DEPLOY_SUMMARY [$ENVIRONMENT]"
echo "  pnpm: filter $NODE_PKG_FILTER  workspace $NODE_WORKSPACE_DIR"
for s in "${SERVICES[@]}"; do
  [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue
  echo "    $s → image $(container_name_for "$s")  server $(remote_path_for_service "$s")"
done
echo ""

deploy_step_build || exit 1
deploy_step_node_upload || exit 1
deploy_step_server_compose
deploy_step_node_docker_up "$@"

echo ""
for s in "${SERVICES[@]}"; do
  [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue
  echo "  DONE $s — logs: $(remote_path_for_service "$s")/logs/"
done
echo "  Manage:  geostat mod $GEOSTAT_MODULE_ID manage $SERVICE status --$ENVIRONMENT"
echo ""
