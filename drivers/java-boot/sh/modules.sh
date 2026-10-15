#!/bin/bash
# List deploy modules (backend/ops.modules + compose services)
# Usage: stack-kit be modules

# shellcheck source=../_init.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_init.sh"

DEPLOY_LIB="$(stack_kit_kit_deploy_lib)"
# shellcheck source=../../toolkit/deploy/common.sh
source "$DEPLOY_LIB/common.sh"

COMPOSE_FILE="docker-compose.prod.yml"
cd "$PROJECT_DIR" || exit 1
discover_services

echo ""
echo "  Backend modules  [$PROJECT_DIR]"
echo "  Registry: $OPS_MODULES_FILE"
echo ""
printf "  %-28s %-10s %-12s %s\n" "COMPOSE_SERVICE" "TYPE" "GRADLE" "DOCKERFILE"
printf "  %-28s %-10s %-12s %s\n" "----------------" "----" "------" "----------"

local_i=0
for s in "${SERVICES[@]}"; do
  gn="$(module_gradle_name "$s")"
  tp="$(module_type_for "$s")"
  df="$(module_dockerfile "$s")"
  df="${df#$PROJECT_DIR/}"
  printf "  %-28s %-10s %-12s %s\n" "$s" "$tp" "${gn:-root}" "$df"
  local_i=$((local_i + 1))
done

if [ ${#MODULE_LIB_GRADLE[@]} -gt 0 ]; then
  echo ""
  echo "  Libraries (not deployed alone):"
  for gn in "${MODULE_LIB_GRADLE[@]}"; do
    echo "    :$gn"
  done
fi

echo ""
echo "  Deploy examples:"
for s in "${SERVICES[@]}"; do
  echo "    stack-kit be deploy $s --prod"
done
echo "    stack-kit be deploy all --prod"
echo ""
