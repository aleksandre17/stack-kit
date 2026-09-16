#!/bin/bash
# ============================================================
#  Pre-flight Checks (node-api) — parity with java-boot/sh/check.sh scope,
#  node-stack specifics (package.json / pnpm / Dockerfile / DATABASE_URL).
#
#  Usage:
#    geostat <api> check                 check all services
#    geostat <api> check <svc>           check one service
#    geostat <api> check --no-build      skip build-related checks
#  Exit: 0 = passed (warnings allowed), 1 = errors found
# ============================================================

# shellcheck source=../_init.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_init.sh"
ERRORS=0
WARNINGS=0

SERVICE="all"
SKIP_BUILD=0
for arg in "$@"; do
  arg="${arg//$'\r'/}"
  case "$arg" in
    --no-build) SKIP_BUILD=1 ;;
    all)        SERVICE="all" ;;
    *)          SERVICE="$arg" ;;
  esac
done

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
DEPLOY_LIB="$(geostat_kit_deploy_lib)"
# shellcheck source=../../toolkit/deploy/common.sh
source "$DEPLOY_LIB/common.sh"
deploy_path_load_config
DEPLOY_SUMMARY="$(deploy_path_summary)"

ok()   { printf "    [OK]   %s\n" "$1"; }
warn() { printf "    [WARN] %s\n" "$1"; WARNINGS=$((WARNINGS+1)); }
fail() { printf "    [FAIL] %s\n" "$1"; ERRORS=$((ERRORS+1)); }
section() { echo ""; printf "  %s\n" "$1"; }

echo ""
echo "  Pre-flight Checks (node-api)  [$SERVICE → $DEPLOY_SUMMARY]"

# ── Local project files ──
section "Local — Project Files"
[ -f "$PROJECT_DIR/docker-compose.prod.yml" ] && ok "docker-compose.prod.yml found" || fail "docker-compose.prod.yml missing"
[ -f "$SECRETS_DIR/.env.prod" ] && ok "${SECRETS_DIR}/.env.prod found" || fail "${SECRETS_DIR}/.env.prod missing (see ${SECRETS_DIR}/.env.example)"
[ -f "$PROJECT_DIR/package.json" ] && ok "package.json found (pnpm filter: $NODE_PKG_FILTER)" || fail "package.json missing"
[ -f "$NODE_WORKSPACE_DIR/pnpm-workspace.yaml" ] && ok "pnpm workspace: $NODE_WORKSPACE_DIR" || warn "pnpm-workspace.yaml not found at $NODE_WORKSPACE_DIR"
if [ "$SKIP_BUILD" = "0" ]; then
  command -v pnpm >/dev/null 2>&1 && ok "pnpm on PATH ($(pnpm --version 2>/dev/null))" || warn "pnpm not on PATH (server image build still compiles)"
fi

# ── Discover services + per-service Dockerfile ──
mapfile -t SERVICES < <(
  awk '/^services:/{f=1;next} f && /^[^ ]/{f=0} f && /^  [a-zA-Z0-9_-]+:/{gsub(/[ :]/,""); print}' \
    "$PROJECT_DIR/docker-compose.prod.yml" 2>/dev/null
)
[ ${#SERVICES[@]} -eq 0 ] && fail "No services found in docker-compose.prod.yml"

section "Local — Per-Service"
for s in "${SERVICES[@]}"; do
  [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue
  df="$(module_dockerfile "$s")"
  [ -f "$df" ] && ok "$(basename "$df") found ($(basename "$(dirname "$df")")/)" || fail "Dockerfile missing (expected $df)"
done

# ── .env.prod required vars (env.ts contract) ──
section "Local — Environment Variables (.env.prod)"
if [ -f "$SECRETS_DIR/.env.prod" ]; then
  check_var() {
    local var="$1" required="$2" val
    val=$(grep -E "^${var}=" "$SECRETS_DIR/.env.prod" | cut -d= -f2- | tr -d '"' | tr -d "'")
    if [ -z "$val" ]; then
      [ "$required" = "required" ] && fail "$var is not set" || warn "$var is empty (optional)"
    elif echo "$val" | grep -qiE "^(CHANGE_ME|YOUR_|example|dev-secret)"; then
      fail "$var still has placeholder value"
    else
      ok "$var set"
    fi
  }
  check_var "DATABASE_URL"   "required"
  check_var "JWT_SECRET"     "required"
  check_var "ADMIN_USERNAME" "required"
  check_var "ADMIN_PASSWORD" "required"
  check_var "EMBED_SECRET"   "optional"
  check_var "PORT"           "optional"
fi

# ── Server connectivity ──
section "Server — $SERVER"
if [ -z "$SERVER" ]; then
  warn "DEPLOY_SERVER unset (needed for remote deploy)"
elif ssh -n -o ConnectTimeout=5 -o BatchMode=yes "$SERVER" "echo ok" >/dev/null 2>&1; then
  ok "SSH connection OK"
  ssh -n "$SERVER" "command -v docker >/dev/null 2>&1 && echo ok" 2>/dev/null | grep -q ok && ok "docker present" || fail "docker not installed on server"
else
  fail "SSH connection failed — check server/key"
fi

echo ""
if [ "$ERRORS" -eq 0 ]; then
  echo "  Ready to deploy (warnings: $WARNINGS)"
else
  echo "  ERRORS: $ERRORS  WARNINGS: $WARNINGS — fix errors before deploying"
fi
echo ""
[ "$ERRORS" -gt 0 ] && exit 1 || exit 0
