#!/bin/bash
# Project CI: compose smoke — paths from stack-kit.json (api role module)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PKG="$ROOT/kits/stack-kit"
export STACK_KIT_PROJECT_ROOT="$ROOT"
export STACK_KIT_KIT_ROOT="$PKG"

# shellcheck source=../../../lib/project.sh
source "$PKG/lib/project.sh"
# shellcheck source=../../../lib/env.sh
source "$PKG/lib/env.sh"

API_MOD="$(stack_kit_module_id_for_role api)"
[[ -n "$API_MOD" ]] || { echo "[ci] ERROR: no api module" >&2; exit 1; }

BE="$(stack_kit_module_path "$API_MOD")"
SECRETS_API="$(stack_kit_secrets_dir_for_module "$API_MOD")"
API_PORT="${API_PORT:-8090}"
WORKER_PORT="${WORKER_PORT:-8091}"

bash "$PKG/ci/prepare-integration-env.sh"
python3 "$PKG/compose/build.py"

cd "$BE"
export API_PORT WORKER_PORT
ENV_ARGS=(--env-file "$SECRETS_API/.env.dev")
# This machine's compose invocation: the runtime catalog's (the entry flagged `local`), never spelled here.
mapfile -t COMPOSE < <(stack_kit_python "$PKG/lib/resolve_cli.py" compose-command | tr -d $'\r')

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.dev.yml}"
echo "[ci] ${COMPOSE[*]} up (module=$API_MOD)..."
"${COMPOSE[@]}" "${ENV_ARGS[@]}" -f "$COMPOSE_FILE" up -d --build

bash "$PKG/ci/wait-health.sh" "http://127.0.0.1:${API_PORT}/health" "UP" 120

# The services are listed or the run fails: a list that could not be read must not skip the worker's check.
services="$("${COMPOSE[@]}" "${ENV_ARGS[@]}" -f "$COMPOSE_FILE" ps --format json)" || { echo "integration: the stack's services could not be listed" >&2; exit 1; }
if grep -q worker <<<"$services"; then
  bash "$PKG/ci/wait-health.sh" "http://127.0.0.1:${WORKER_PORT}/actuator/health" "UP" 120
fi

echo "[ci] ${COMPOSE[*]} down..."
"${COMPOSE[@]}" "${ENV_ARGS[@]}" -f "$COMPOSE_FILE" down -v
echo "[ci] Integration stack passed."
