#!/bin/bash
# Docker Compose — env from secrets/<module> (.env.dev | .env.prod)
# Generic (stack-agnostic); identical contract to java-boot/sh/compose.sh.
set -euo pipefail

# shellcheck source=../_init.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_init.sh"

cd "$PROJECT_DIR"

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
  COMPOSE_FILE=docker-compose.dev.yml
fi

ENV_ARGS=()
while IFS= read -r f; do
  [[ -n "$f" ]] && ENV_ARGS+=(--env-file "$f")
done < <(geostat_env_files "$OPS_SECRETS_MODULE" "$PROFILE")

exec docker compose "${ENV_ARGS[@]}" -f "$COMPOSE_FILE" "${REMAIN[@]}"
