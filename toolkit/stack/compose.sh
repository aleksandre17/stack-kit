#!/bin/bash
# Full stack compose runner (manifest: stack.composeDir)
set -euo pipefail
PKG="$(cd "$(dirname "$0")/../.." && pwd)"
ROOT="$(cd "$PKG/../.." && pwd)"
export STACK_KIT_PROJECT_ROOT="$ROOT"
# shellcheck source=../../lib/env.sh
source "$PKG/lib/env.sh"

COMPOSE_REL="$(stack_kit_read_manifest_field stack.composeDir ops/compose/stack)"
COMPOSE_DIR="$ROOT/$COMPOSE_REL"

PROD=0
REMAIN=()
for arg in "$@"; do
  case "$arg" in
    -Prod|--prod) PROD=1 ;;
    *) REMAIN+=("$arg") ;;
  esac
done

if [[ "$PROD" -eq 1 ]]; then
  PROFILE=prod
  COMPOSE_FILE=docker-compose.prod.yml
else
  PROFILE=dev
  COMPOSE_FILE=docker-compose.yml
fi

ENV_ARGS=()
while IFS= read -r f; do
  [[ -n "$f" ]] && ENV_ARGS+=(--env-file "$f")
done < <(stack_kit_stack_env_files "$PROFILE")

cd "$COMPOSE_DIR"
STACK_NAME="$(stack_kit_deploy_env_value COMPOSE_PROJECT_NAME "$(basename "$ROOT")")"
echo ""
echo "  $STACK_NAME stack ($PROFILE)"
PY="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
if [[ -n "$PY" ]]; then
  while IFS= read -r line; do
    [[ -n "$line" ]] && echo "  $line"
  done < <("$PY" "$PKG/lib/modules_cli.py" stack-endpoints)
fi
echo ""

exec docker compose "${ENV_ARGS[@]}" -f "$COMPOSE_FILE" "${REMAIN[@]}"
