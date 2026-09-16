#!/bin/bash
# ============================================================
#  Service Manager — SSH Remote (node-api)
#
#  Runs locally (Git Bash / WSL); operations execute on the server via SSH against
#  the deployed runtime path. Stack-agnostic docker-compose control — same contract
#  as java-boot/sh/manage.sh (no JVM/JAR specifics; the image is built server-side).
#
#  Usage:
#    geostat <api> manage                      interactive menu
#    geostat <api> manage <svc> status --prod
#    geostat <api> manage <svc> logs --dev
#    geostat <api> manage all restart --prod
# ============================================================

# shellcheck source=../_init.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_init.sh"
# shellcheck source=../../toolkit/bash/compose-cli.sh
source "$GEOSTAT_KIT_ROOT/toolkit/bash/compose-cli.sh"

MANAGE_ENV="prod"
for arg in "$@"; do
  case "$arg" in
    --dev)  MANAGE_ENV="dev"  ;;
    --prod) MANAGE_ENV="prod" ;;
  esac
done

COMPOSE_FILE="docker-compose.${MANAGE_ENV}.yml"
ENV_FILE=".env.${MANAGE_ENV}"
geostat_compose_init
COMPOSE="${GEOSTAT_COMPOSE[*]} -f $COMPOSE_FILE --env-file ./$ENV_FILE"

DEPLOY_LIB="$(geostat_kit_deploy_lib)"
# shellcheck source=../../toolkit/deploy/common.sh
source "$DEPLOY_LIB/common.sh"
deploy_path_load_config
DEPLOY_SUMMARY="$(deploy_path_summary)"

# shellcheck source=../../toolkit/bash/manage-remote.sh
source "$GEOSTAT_KIT_ROOT/toolkit/bash/manage-remote.sh"

# ── Discover deployed services (compose keys that have a deploy compose on server) ──
mapfile -t _SVCS < <(
  awk '/^services:/{f=1;next} f && /^[^ ]/{f=0} f && /^  [a-zA-Z0-9_-]+:/{gsub(/[ :]/,""); print}' \
    "$PROJECT_DIR/$COMPOSE_FILE" 2>/dev/null
)
SERVICES=()
for _ms in "${_SVCS[@]}"; do
  if backend_find_deployed_path "$_ms" >/dev/null 2>&1; then
    SERVICES+=("$_ms")
  fi
done
if [ ${#SERVICES[@]} -eq 0 ]; then
  echo "  ERROR: No deployed services found (checked under ${DEPLOY_PATH_BASE:-$DEPLOY_SUMMARY})."
  echo "  Run: geostat mod $GEOSTAT_MODULE_ID deploy <service> --$MANAGE_ENV"
  exit 1
fi

VALID_ACTIONS="stop start restart logs status rm rebuild"
SVC="" ACTION=""
FORCE=""
pos=0
for arg in "$@"; do
  case "$arg" in
    --dev|--prod|-y|--force) [[ "$arg" == "-y" || "$arg" == "--force" ]] && FORCE="YES"; continue ;;
  esac
  if [[ " $VALID_ACTIONS " == *" $arg "* ]]; then ACTION="$arg"; continue; fi
  pos=$((pos+1))
  [ $pos -eq 1 ] && [ -z "$SVC" ] && SVC="$arg"
done

is_valid_service() {
  [ "$1" = "all" ] && return 0
  for s in "${SERVICES[@]}"; do [ "$s" = "$1" ] && return 0; done
  return 1
}

if [ -z "$SVC" ]; then
  echo ""
  echo "   Service Manager  [$DEPLOY_SUMMARY]"
  for i in "${!SERVICES[@]}"; do echo "     $((i+1))) ${SERVICES[$i]}"; done
  echo "     $((${#SERVICES[@]}+1))) all"
  read -rp "  Service: " choice
  if [ "$choice" = "$((${#SERVICES[@]}+1))" ]; then SVC="all"
  else SVC="${SERVICES[$((choice-1))]}"; fi
fi

if [ -z "$ACTION" ]; then
  echo ""
  echo "   Action for [$SVC]: 1)stop 2)start 3)restart 4)logs 5)status 6)rm 7)rebuild"
  read -rp "  Action [1-7]: " ac
  case $ac in
    1) ACTION="stop" ;; 2) ACTION="start" ;; 3) ACTION="restart" ;;
    4) ACTION="logs" ;; 5) ACTION="status" ;; 6) ACTION="rm" ;; 7) ACTION="rebuild" ;;
    *) echo "  Invalid."; exit 1 ;;
  esac
fi

if ! is_valid_service "$SVC"; then
  echo "  ERROR: Unknown service '$SVC'  (available: ${SERVICES[*]} all)"
  exit 1
fi

echo ""
echo "  [$SVC] $ACTION  ($DEPLOY_SUMMARY)"
echo "  ------------------------------------------"

ssh_svc() { local d; d="$(remote_path "$SVC")"; ssh "$SERVER" "cd \"$d\" && $COMPOSE $*"; }
ssh_all() { local s d; for s in "${SERVICES[@]}"; do d="$(remote_path "$s")"; ssh "$SERVER" "cd \"$d\" && $COMPOSE $*"; done; }

case "$ACTION" in
  stop)    if [ "$SVC" = "all" ]; then ssh_all stop; else ssh_svc stop; fi; echo "  [OK] Stopped." ;;
  start)   if [ "$SVC" = "all" ]; then ssh_all up -d; else ssh_svc up -d; fi; echo "  [OK] Started." ;;
  restart) if [ "$SVC" = "all" ]; then ssh_all restart; else ssh_svc restart; fi; echo "  [OK] Restarted." ;;
  logs)    if [ "$SVC" = "all" ]; then ssh_all logs --tail=200 -f; else ssh_svc logs --tail=200 -f; fi ;;
  status)  ssh "$SERVER" "docker ps --filter name=$PROJECT --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'" ;;
  rm)
    if [ "$SVC" = "all" ]; then ssh_all down; else ssh_svc stop; ssh_svc rm -f; fi
    echo "  [OK] Removed." ;;
  rebuild)
    if [ "$SVC" = "all" ]; then
      local_s=""; for s in "${SERVICES[@]}"; do d="$(remote_path "$s")"; ssh "$SERVER" "cd \"$d\" && $COMPOSE down && $COMPOSE build --no-cache && $COMPOSE up -d"; done
    else
      ssh_svc down; ssh_svc build --no-cache; ssh_svc up -d
    fi
    echo "  [OK] Rebuilt and started." ;;
  *) echo "  Unknown action: $ACTION"; exit 1 ;;
esac
