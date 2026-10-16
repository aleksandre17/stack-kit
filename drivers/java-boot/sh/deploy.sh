#!/bin/bash
# Backend SSH deploy — orchestrator (kits/stack-kit/toolkit/deploy/)
#
# Usage:
#   stack-kit be deploy [service] [--dev|--prod] [--no-build] [--skip-checks] [backend|frontend]

# shellcheck source=../_init.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_init.sh"

DEPLOY_LIB="$(stack_kit_kit_deploy_lib)"
# shellcheck source=../../toolkit/deploy/common.sh
source "$DEPLOY_LIB/common.sh"

if [[ "${1:-}" == "watch" ]]; then
  shift
  # shellcheck source=../../toolkit/deploy/gradle-build.sh
  source "$DEPLOY_LIB/gradle-build.sh"
  # shellcheck source=../../toolkit/deploy/jar-prepare.sh
  source "$DEPLOY_LIB/jar-prepare.sh"
  # shellcheck source=../../toolkit/deploy/upload.sh
  source "$DEPLOY_LIB/upload.sh"
  # shellcheck source=../../toolkit/deploy/gradle-modules.sh
  source "$DEPLOY_LIB/gradle-modules.sh"
  # shellcheck source=../../toolkit/deploy/deploy-watch.sh
  source "$DEPLOY_LIB/deploy-watch.sh"
  deploy_watch_main "$@"
  exit $?
fi
# shellcheck source=../../toolkit/deploy/gradle-build.sh
source "$DEPLOY_LIB/gradle-build.sh"
# shellcheck source=../../toolkit/deploy/jar-prepare.sh
source "$DEPLOY_LIB/jar-prepare.sh"
# shellcheck source=../../toolkit/deploy/upload.sh
source "$DEPLOY_LIB/upload.sh"
# shellcheck source=../../toolkit/deploy/server-compose.sh
source "$DEPLOY_LIB/server-compose.sh"
# shellcheck source=../../toolkit/deploy/docker-up.sh
source "$DEPLOY_LIB/docker-up.sh"
# shellcheck source=../../toolkit/deploy/gradle-modules.sh
source "$DEPLOY_LIB/gradle-modules.sh"

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
    backend|frontend) ;;
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

if [ "$SKIP_BUILD" = "0" ] && [ $# -eq 0 ]; then
  read -rp "  Gradle build? [Y/n]: " bc
  [[ "$bc" =~ ^[Nn] ]] && SKIP_BUILD=1
fi

if [ "$SKIP_BUILD" = "0" ]; then
  if [ $# -eq 0 ]; then deploy_resolve_gradle_modules 1
  else deploy_resolve_gradle_modules 0
  fi
fi

if [ "$SKIP_CHECKS" = "0" ]; then
  check_args="$SERVICE"
  [ "$SKIP_BUILD" = "1" ] && check_args="$check_args --no-build"
  bash "$(dirname "$0")/check.sh" $check_args || exit 1
fi

deploy_require_provenance "$ENVIRONMENT" || exit 1
stack_kit_remote_preflight $([[ "$SERVICE" == "all" ]] || echo "$SERVICE") || exit 1
DEPLOY_VERSION="$(date +%Y%m%d-%H%M%S)"
echo ""
echo "  Deploy [$SERVICE] → $DEPLOY_SUMMARY [$ENVIRONMENT]"
if [ "$SKIP_BUILD" = "0" ] && [ -n "${GRADLE_PROPS:-}" ]; then
  echo "  Gradle: $GRADLE_PROPS"
fi
for s in "${SERVICES[@]}"; do
  [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue
  echo "    $s → task $(module_gradle_boot_task "$s")  dir $(module_project_dir "$s")  server $(remote_path_for_service "$s")"
done
echo ""

deploy_step_build || exit 1
deploy_step_prepare_jars
deploy_step_upload
deploy_step_server_compose
deploy_step_docker_up "$@"

echo ""
for s in "${SERVICES[@]}"; do
  [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue
  echo "  DONE $s — logs: $(remote_path_for_service "$s")/logs/"
done
echo "  Manage:  stack-kit mod $STACK_KIT_MODULE_ID manage $SERVICE status --$ENVIRONMENT"
echo ""
