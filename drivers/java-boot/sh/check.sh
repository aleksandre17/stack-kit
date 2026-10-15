#!/bin/bash
# ============================================================
#  Pre-flight Checks — validates all prerequisites before deploy
#
#  Usage:
#    stack-kit be check                        check all services
#    stack-kit be check api                    check api only
#    stack-kit be check api frontend           check api on frontend target
#    stack-kit be check --no-build             skip build-related checks
#
#  Exit codes:
#    0 — all checks passed (warnings allowed)
#    1 — one or more errors found
# ============================================================

# shellcheck source=_init.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_init.sh"
ERRORS=0
WARNINGS=0

# ── Parse args ──
SERVICE="all"
SKIP_BUILD=0
for arg in "$@"; do
    arg="${arg//$'\r'/}"
    case "$arg" in
        --no-build) SKIP_BUILD=1 ;;
        all)        SERVICE="all" ;;
        backend|frontend) ;;
        *)          SERVICE="$arg" ;;
    esac
done

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
DEPLOY_LIB="$(stack_kit_kit_deploy_lib)"
# shellcheck source=../../toolkit/deploy/common.sh
source "$DEPLOY_LIB/common.sh"
module_load_registry

module_port_env_key() {
    local key
    key="$(PYTHONPATH="${STACK_KIT_KIT_ROOT}" stack_kit_python "$STACK_KIT_KIT_ROOT/lib/config_gen.py" --port-env "$STACK_KIT_MODULE_ID" 2>/dev/null || true)"
    [[ -n "$key" ]] || key="API_PORT"
    echo "$key"
}

MODULE_PORT_ENV="$(module_port_env_key)"
deploy_path_load_config
DEPLOY_SUMMARY="$(deploy_path_summary)"
if [[ -n "$SERVER" && -z "$SERVER_BASE" && -z "$DEPLOY_PATH_BASE" ]]; then
    warn "DEPLOY_SERVER_BASE unset — set in ops/config/deploy.env for predictable remote paths"
fi

# ── Helpers ──
ok()   { printf "    \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "    \033[33m⚠\033[0m %s\n" "$1"; WARNINGS=$((WARNINGS+1)); }
fail() { printf "    \033[31m✗\033[0m %s\n" "$1"; ERRORS=$((ERRORS+1)); }
section() {
    echo ""
    printf "  \033[1m%s\033[0m\n" "$1"
    printf "  %s\n" "$(printf '─%.0s' $(seq 1 45))"
}

echo ""
echo "  ══════════════════════════════════════════════"
printf "   \033[1mPre-flight Checks\033[0m  [%s → %s]\n" "$SERVICE" "$DEPLOY_SUMMARY"
echo "  ══════════════════════════════════════════════"

# ════════════════════════════════════════════════
#  LOCAL CHECKS
# ════════════════════════════════════════════════
section "Local — Project Files"

# docker-compose.prod.yml
if [ -f "$PROJECT_DIR/docker-compose.prod.yml" ]; then
    ok "docker-compose.prod.yml found"
else
    fail "docker-compose.prod.yml missing"
fi

# .env.prod (module secrets dir)
if [ -f "$SECRETS_DIR/.env.prod" ]; then
    ok "${SECRETS_DIR}/.env.prod found"
else
    fail "${SECRETS_DIR}/.env.prod missing  (see ${SECRETS_DIR}/.env.example)"
fi

# gradlew (module dir or shared apps/backend wrapper for includeBuild modules)
gradlew_dir="$PROJECT_DIR"
if [[ ! -f "$PROJECT_DIR/gradlew" && ! -f "$PROJECT_DIR/gradlew.bat" ]]; then
    if [[ -f "$MONOREPO/apps/backend/gradlew" || -f "$MONOREPO/apps/backend/gradlew.bat" ]]; then
        gradlew_dir="$MONOREPO/apps/backend"
    fi
fi
if [ "$SKIP_BUILD" = "0" ]; then
    if [ -f "$gradlew_dir/gradlew" ] || [ -f "$gradlew_dir/gradlew.bat" ]; then
        ok "gradlew found"
    else
        fail "gradlew missing — cannot build"
    fi
fi

# ── Discover services ──
mapfile -t SERVICES < <(
    awk '/^services:/{f=1;next} f && /^[^ ]/{f=0} f && /^  [a-zA-Z0-9_-]+:/{gsub(/[ :]/,""); print}' \
    "$PROJECT_DIR/docker-compose.prod.yml" 2>/dev/null
)
if [ ${#SERVICES[@]} -eq 0 ]; then
    fail "No services found in docker-compose.prod.yml"
fi

# ── Per-service local checks ──
section "Local — Per-Service"

for s in "${SERVICES[@]}"; do
    [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue

    # Dockerfile (runtime, uploaded by deploy)
    df="$(module_dockerfile "$s")"
    if [ -f "$df" ]; then
        ok "$(basename "$df") found ($(basename "$(dirname "$df")")/)"
    else
        fail "Dockerfile missing (expected $df)"
    fi

    mod_dir="$(module_project_dir "$s")"
    # build.gradle.kts
    if [ -f "$mod_dir/build.gradle.kts" ]; then
        ok "build.gradle.kts found"
    else
        warn "build.gradle.kts missing"
    fi

    # app.jar (only relevant if --no-build)
    if [ "$SKIP_BUILD" = "1" ]; then
        jar=$(ls "$mod_dir/build/libs/"*-boot.jar 2>/dev/null | head -1)
        [ -z "$jar" ] && jar=$(ls "$mod_dir/build/libs/"*.jar 2>/dev/null | grep -iv plain | head -1)
        if [ -n "$jar" ]; then
            ok "app.jar ready  ($(du -h "$jar" | cut -f1))"
        else
            fail "no built jar found  (run without --no-build)"
        fi
    fi
done

# ── .env.prod content validation ──
section "Local — Environment Variables (.env.prod)"

if [ -f "$SECRETS_DIR/.env.prod" ]; then
    check_var() {
        local var="$1" required="$2"
        local val
        val=$(grep -E "^${var}=" "$SECRETS_DIR/.env.prod" | cut -d= -f2- | tr -d '"' | tr -d "'")
        if [ -z "$val" ]; then
            [ "$required" = "required" ] && fail "$var is not set" || warn "$var is empty (optional)"
        elif echo "$val" | grep -qiE "^(CHANGE_ME|YOUR_|example)"; then
            fail "$var still has placeholder value: $val"
        else
            ok "$var  ✓"
        fi
    }

    # Required port — manifest-driven (API_PORT, RETRIEVAL_PORT, INGESTION_PORT, …)
    check_var "$MODULE_PORT_ENV" "required"

    # A module's own integrations are the project's to name: modules.<id>.check.requiredEnv and
    # modules.<id>.check.optionalEnv in the manifest. The kit names none of them (ADR-001).
    while read -r var; do
        [[ -n "$var" ]] && check_var "$var" "required"
    done < <(stack_kit_read_manifest_list "modules.${STACK_KIT_MODULE_ID}.check.requiredEnv")
    while read -r var; do
        [[ -n "$var" ]] && check_var "$var" "optional"
    done < <(stack_kit_read_manifest_list "modules.${STACK_KIT_MODULE_ID}.check.optionalEnv")
fi

# ════════════════════════════════════════════════
#  SERVER CHECKS
# ════════════════════════════════════════════════
section "Server — $SERVER"

# SSH connectivity
if ssh -n -o ConnectTimeout=5 -o BatchMode=yes "$SERVER" "echo ok" >/dev/null 2>&1; then
    ok "SSH connection OK"
else
    fail "SSH connection failed — check server/key"
    echo ""
    echo "  ══════════════════════════════════════════════"
    printf "   \033[31mERRORS: %d\033[0m  \033[33mWARNINGS: %d\033[0m\n" "$ERRORS" "$WARNINGS"
    echo "  ══════════════════════════════════════════════"
    echo ""
    exit 1
fi

# Run all server checks in one SSH call
server_results=$(ssh -n "$SERVER" bash << 'SSHEOF'
results=""

# docker
if command -v docker >/dev/null 2>&1; then
    results+="ok:docker $(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')\n"
else
    results+="fail:docker not installed\n"
fi

# docker-compose
if command -v docker-compose >/dev/null 2>&1; then
    results+="ok:docker-compose $(docker-compose --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')\n"
elif docker compose version >/dev/null 2>&1; then
    results+="ok:docker compose (plugin) available\n"
else
    results+="fail:docker-compose not installed\n"
fi

# disk space (warn if < 2GB free)
free_kb=$(df / | awk 'NR==2{print $4}')
free_gb=$(echo "$free_kb" | awk '{printf "%.1f", $1/1024/1024}')
if [ "$free_kb" -lt 2097152 ]; then
    results+="warn:disk space low (${free_gb}GB free)\n"
else
    results+="ok:disk space OK (${free_gb}GB free)\n"
fi

printf "%b" "$results"
SSHEOF
)

while IFS= read -r line; do
    level="${line%%:*}"
    msg="${line#*:}"
    case "$level" in
        ok)   ok "$msg" ;;
        warn) warn "$msg" ;;
        fail) fail "$msg" ;;
    esac
done <<< "$server_results"

# Server deploy base
if ssh -n "$SERVER" "[ -d '${DEPLOY_PATH_BASE:-$REMOTE}' ] && echo ok || echo missing" 2>/dev/null | grep -q "ok"; then
    ok "Deploy base ${DEPLOY_PATH_BASE:-$REMOTE} exists (layout: $DEPLOY_LAYOUT)"
else
    warn "Deploy base ${DEPLOY_PATH_BASE:-$REMOTE} not found — will be created on deploy"
fi

# Docker network
if ssh -n "$SERVER" "docker network inspect ${PROJECT}-net >/dev/null 2>&1 && echo ok || echo missing" 2>/dev/null | grep -q "ok"; then
    ok "Docker network ${PROJECT}-net exists"
else
    warn "Docker network ${PROJECT}-net missing — will be created on deploy"
fi

# ── Per-service server checks ──
for s in "${SERVICES[@]}"; do
    [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue
    section "Server — $s"

    rp="$(remote_path_for_service "$s")"
    ctr="$(container_name_for "$s")"

    # Service runtime dir
    if ssh -n "$SERVER" "[ -d '$rp' ] && echo ok || echo missing" 2>/dev/null | grep -q "ok"; then
        ok "$ctr runtime at $rp"

        if ssh -n "$SERVER" "[ -f '$rp/docker-compose.prod.yml' ] && echo ok || echo missing" 2>/dev/null | grep -q "ok"; then
            ok "$ctr/docker-compose.prod.yml present"
        else
            warn "$ctr/docker-compose.prod.yml missing — will be generated on deploy"
        fi

        container_status=$(ssh -n "$SERVER" "docker ps --filter name=$ctr --format '{{.Status}}' 2>/dev/null")
        if [ -n "$container_status" ]; then
            ok "Container $ctr: $container_status"
        else
            warn "Container $ctr not running"
        fi
    else
        warn "$ctr runtime not on server ($rp) — will be created on deploy"
    fi
done

# ════════════════════════════════════════════════
#  SUMMARY
# ════════════════════════════════════════════════
echo ""
echo "  ══════════════════════════════════════════════"
if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    printf "   \033[32m✓ All checks passed\033[0m\n"
elif [ "$ERRORS" -eq 0 ]; then
    printf "   \033[32m✓ Ready to deploy\033[0m  \033[33m(warnings: %d)\033[0m\n" "$WARNINGS"
else
    printf "   \033[31m✗ ERRORS: %d\033[0m  \033[33mWARNINGS: %d\033[0m  — fix errors before deploying\033[0m\n" "$ERRORS" "$WARNINGS"
fi
echo "  ══════════════════════════════════════════════"
echo ""

[ "$ERRORS" -gt 0 ] && exit 1 || exit 0