#!/bin/bash
# ============================================================
#  Service Manager — SSH Remote
#
#  Runs on local machine (Git Bash / WSL).
#  All operations execute on the remote server via SSH.
#
#  Usage:
#    stack-kit be manage                          interactive menu
#    stack-kit be manage api stop                 stop api (backend)
#    stack-kit be manage api stop frontend        stop api (frontend)
#    stack-kit be manage all nuke -y              nuke all (no confirm)
#    stack-kit be manage api logs errors          show error.log
#    stack-kit be manage all logs files           list all log files
# ============================================================

# shellcheck source=../_init.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_init.sh"
# shellcheck source=../../toolkit/bash/compose-cli.sh
source "$STACK_KIT_KIT_ROOT/toolkit/bash/compose-cli.sh"

# ── Parse TARGET / ENV from args ──
MANAGE_ENV="prod"
for arg in "$@"; do
    case "$arg" in
        --dev)    MANAGE_ENV="dev"  ;;
        --prod)   MANAGE_ENV="prod" ;;
    esac
done

COMPOSE_FILE="docker-compose.${MANAGE_ENV}.yml"
ENV_FILE=".env.${MANAGE_ENV}"
stack_kit_compose_init
COMPOSE="${STACK_KIT_COMPOSE[*]} -f $COMPOSE_FILE --env-file ./$ENV_FILE"

DEPLOY_LIB="$(stack_kit_kit_deploy_lib)"
# shellcheck source=../../toolkit/deploy/common.sh
source "$DEPLOY_LIB/common.sh"
deploy_path_load_config
DEPLOY_SUMMARY="$(deploy_path_summary)"

_manage_remote_dir() {
  local s="$1" name
  name=$(container_name_for "$s")
  echo "${name:-$s}"
}

# shellcheck source=../../toolkit/bash/manage-remote.sh
source "$STACK_KIT_KIT_ROOT/toolkit/bash/manage-remote.sh"
# shellcheck source=../../toolkit/bash/manage-logs.sh
source "$STACK_KIT_KIT_ROOT/toolkit/bash/manage-logs.sh"

# ── Discover services: local compose keys with deploy compose on server ──
mapfile -t _MANAGE_COMPOSE_SVCS < <(
    awk '/^services:/{f=1;next} f && /^[^ ]/{f=0} f && /^  [a-zA-Z0-9_-]+:/{gsub(/[ :]/,""); print}' \
        "$PROJECT_DIR/$COMPOSE_FILE" 2>/dev/null
)
SERVICES=()
for _ms in "${_MANAGE_COMPOSE_SVCS[@]}"; do
    if backend_find_deployed_path "$_ms" >/dev/null 2>&1; then
        SERVICES+=("$_ms")
    fi
done
if [ ${#SERVICES[@]} -eq 0 ]; then
    deploy_path_load_config
    echo "  ERROR: No deployed services found (checked under ${DEPLOY_PATH_BASE:-$DEPLOY_SUMMARY})."
    echo "  Run: stack-kit be deploy <service> --$MANAGE_ENV"
    exit 1
fi

# ── Parse positional args (skip target/flags) ──
VALID_ACTIONS="stop start restart logs status rm nuke rebuild"
SVC="" ACTION="" ARG3=""
LOG_LEVEL=""
pos=0
for arg in "$@"; do
    case "$arg" in
        backend|frontend|--dev|--prod|-y|--force) continue ;;
    esac
    if [[ " $VALID_ACTIONS " == *" $arg "* ]]; then
        ACTION="$arg"
        continue
    fi
    if manage_log_is_source "$arg" 2>/dev/null; then
        ARG3="$arg"
        continue
    fi
    case "$arg" in
        ERROR|WARN|INFO) LOG_LEVEL="$arg" ;;
        ALL) LOG_LEVEL="" ;;
    esac
    pos=$((pos+1))
    case $pos in
        1) [ -z "$SVC" ] && SVC="$arg" ;;
        2) [ -z "$ACTION" ] && ACTION="$arg" ;;
        3) [ -z "$ARG3" ] && ARG3="$arg" ;;
    esac
done

FORCE=""
for arg in "$@"; do
    case "$arg" in -y|--force) FORCE="YES" ;; esac
done

# ── Validate service ──
is_valid_service() {
    [ "$1" = "all" ] && return 0
    for s in "${SERVICES[@]}"; do [ "$s" = "$1" ] && return 0; done
    return 1
}

resolve_manage_service_arg() {
    local raw="$1" s
    [ "$raw" = "all" ] && { echo "$raw"; return 0; }
    for s in "${SERVICES[@]}"; do
        [ "$s" = "$raw" ] && { echo "$raw"; return 0; }
    done
    for s in "${SERVICES[@]}"; do
        [[ "$s" == *"-$raw" ]] && { echo "$s"; return 0; }
    done
    return 1
}

# ── Level 1: Service selection ──
if [ -z "$SVC" ]; then
    echo ""
    echo "  =========================================="
    echo "   Service Manager  [$DEPLOY_SUMMARY]"
    echo "  =========================================="
    echo ""
    echo "   Services:"
    for i in "${!SERVICES[@]}"; do
        echo "     $((i+1))) ${SERVICES[$i]}"
    done
    echo "     $((${#SERVICES[@]}+1))) all"
    echo ""
    read -rp "  Service [1-$((${#SERVICES[@]}+1))]: " choice
    if [ "$choice" = "$((${#SERVICES[@]}+1))" ]; then
        SVC="all"
    elif [ "$choice" -ge 1 ] 2>/dev/null && [ "$choice" -le "${#SERVICES[@]}" ]; then
        SVC="${SERVICES[$((choice-1))]}"
    else
        echo "  Invalid."; exit 1
    fi
fi

# ── Level 2: Action selection ──
if [ -z "$ACTION" ]; then
    echo ""
    echo "   Action for [$SVC]:"
    echo "     1) stop       5) status"
    echo "     2) start      6) rm"
    echo "     3) restart    7) nuke"
    echo "     4) logs       8) rebuild"
    echo ""
    read -rp "  Action [1-8]: " ac
    case $ac in
        1) ACTION="stop"    ;; 2) ACTION="start"   ;;
        3) ACTION="restart" ;; 4) ACTION="logs"    ;;
        5) ACTION="status"  ;; 6) ACTION="rm"      ;;
        7) ACTION="nuke"    ;; 8) ACTION="rebuild" ;;
        *) echo "  Invalid."; exit 1 ;;
    esac
fi

if ! is_valid_service "$SVC"; then
    resolved=""
    if resolved="$(resolve_manage_service_arg "$SVC" 2>/dev/null)"; then
        [[ "$resolved" != "$SVC" ]] && echo "  Service: $SVC → $resolved"
        SVC="$resolved"
    fi
fi

if ! is_valid_service "$SVC"; then
    echo "  ERROR: Unknown service '$SVC'"
    echo "  Available: ${SERVICES[*]} all"
    exit 1
fi

echo ""
echo "  [$SVC] $ACTION  ($DEPLOY_SUMMARY)"
echo "  ------------------------------------------"

# ── SSH helpers ──
ssh_svc()  {
    local d
    d="$(remote_path "$SVC")"
    ssh "$SERVER" "cd \"$d\" && $COMPOSE $*"
}
ssh_all()  {
    local s d
    for s in "${SERVICES[@]}"; do
        d="$(remote_path "$s")"
        ssh "$SERVER" "cd \"$d\" && $COMPOSE $*"
    done
}

# ── Actions ──
case "$ACTION" in

    stop)
        if [ "$SVC" = "all" ]; then ssh_all stop
        else ssh_svc stop; fi
        echo "  [OK] Stopped."
        ;;

    start)
        if [ "$SVC" = "all" ]; then ssh_all up -d
        else ssh_svc up -d; fi
        echo "  [OK] Started."
        ;;

    restart)
        if [ "$SVC" = "all" ]; then ssh_all restart
        else ssh_svc restart; fi
        echo "  [OK] Restarted."
        ;;

    logs)
        if [[ -z "$ARG3" ]] || ! manage_log_is_source "$ARG3"; then
            manage_logs_interactive_source
            manage_logs_interactive_level
        else
            LOG_LEVEL="${LOG_LEVEL:-}"
            if [[ "$ARG3" != "files" && "$ARG3" != "docker" && -z "$LOG_LEVEL" ]]; then
                manage_logs_interactive_level
            fi
        fi
        manage_logs_dispatch
        ;;

    status)
        ssh "$SERVER" "docker ps --filter name=$PROJECT --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'; echo; docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' \$(docker ps -q --filter name=$PROJECT) 2>/dev/null || true"
        ;;

    rm)
        if [ "$SVC" = "all" ]; then
            ssh_all down
        else
            ssh_svc stop
            ssh_svc rm -f
        fi
        echo "  [OK] Removed."
        ;;

    nuke)
        echo ""
        echo "  WARNING: Removes container(s), volumes, images, files and logs!"
        if [ "$FORCE" != "YES" ]; then
            read -rp "  Type YES to confirm: " confirm
            [ "$confirm" != "YES" ] && echo "  Cancelled." && exit 0
        fi
        if [ "$SVC" = "all" ]; then
            local s d
            for s in "${SERVICES[@]}"; do
                d="$(remote_path "$s")"
                ssh "$SERVER" "bash -c 'cd \"$d\" && $COMPOSE down -v --rmi local 2>/dev/null; true'"
            done
            manage_prune_deployed_images
            for s in "${SERVICES[@]}"; do
                d="$(remote_path "$s")"
                ssh "$SERVER" "docker run --rm -v \"$d:/target\" alpine find /target -mindepth 1 -delete 2>/dev/null || true"
                ssh "$SERVER" "rm -rf \"$d\""
            done
        else
            d="$(remote_path "$SVC")"
            ssh "$SERVER" "bash -c 'cd \"$d\" && $COMPOSE down -v --rmi local 2>/dev/null; true'"
            ssh "$SERVER" "docker run --rm -v \"$d:/target\" alpine find /target -mindepth 1 -delete 2>/dev/null || true"
            ssh "$SERVER" "rm -rf \"$d\""
        fi
        echo "  [OK] Nuked."
        ;;

    rebuild)
        local s d
        if [ "$SVC" = "all" ]; then
            for s in "${SERVICES[@]}"; do
                d="$(remote_path "$s")"
                ssh "$SERVER" "cd \"$d\" && $COMPOSE down && $COMPOSE build --no-cache && $COMPOSE up -d"
            done
        else
            ssh_svc down
            ssh_svc build --no-cache
            ssh_svc up -d
        fi
        echo "  [OK] Rebuilt and started."
        ;;

    *)
        echo "  Unknown action: $ACTION"
        exit 1
        ;;
esac