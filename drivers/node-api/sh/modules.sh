#!/bin/bash
# List node-api compose services for this module.
# Usage: geostat <api> modules

# shellcheck source=../_init.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_init.sh"

DEPLOY_LIB="$(geostat_kit_deploy_lib)"
# shellcheck source=../../toolkit/deploy/common.sh
source "$DEPLOY_LIB/common.sh"

COMPOSE_FILE="docker-compose.prod.yml"
cd "$PROJECT_DIR" || exit 1
discover_services

echo ""
echo "  node-api module  [$PROJECT_DIR]"
echo "  pnpm filter: $NODE_PKG_FILTER   workspace: $NODE_WORKSPACE_DIR"
echo ""
printf "  %-28s %-12s %s\n" "COMPOSE_SERVICE" "CONTAINER" "DOCKERFILE"
printf "  %-28s %-12s %s\n" "----------------" "---------" "----------"
for s in "${SERVICES[@]}"; do
  df="$(module_dockerfile "$s")"; df="${df#"$PROJECT_DIR"/}"
  printf "  %-28s %-12s %s\n" "$s" "$(container_name_for "$s")" "$df"
done

echo ""
echo "  Deploy examples:"
for s in "${SERVICES[@]}"; do echo "    geostat mod $GEOSTAT_MODULE_ID deploy $s --prod"; done
echo "    geostat mod $GEOSTAT_MODULE_ID deploy all --prod"
echo ""
