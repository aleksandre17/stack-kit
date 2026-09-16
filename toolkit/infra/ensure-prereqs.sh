#!/bin/bash
# One-time server prerequisites — SSH from local machine
# Usage: geostat infra  |  bash kits/geostat-kit/toolkit/infra/ensure-prereqs.sh

set -euo pipefail
PKG="$(cd "$(dirname "$0")/../.." && pwd)"
ROOT="$(cd "$PKG/../.." && pwd)"
export GEOSTAT_PROJECT_ROOT="$ROOT"
# shellcheck source=../../lib/env.sh
source "$PKG/lib/env.sh"

SERVER="${DEPLOY_SERVER:-${1:-}}"
if [ -z "$SERVER" ]; then
  SERVER="$(geostat_deploy_env_value DEPLOY_SERVER "")"
fi
if [ -z "$SERVER" ]; then
  echo "Set DEPLOY_SERVER in ops/config/deploy.env or pass user@host"
  exit 1
fi

NETWORK="$(geostat_docker_network)"

run_remote() {
  ssh "$SERVER" "DOCKER_NETWORK='$NETWORK' bash -s" <<'REMOTE'
set -euo pipefail
NET="${DOCKER_NETWORK:-}"
echo "[infra] python3-yaml..."
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-yaml 2>/dev/null || true
fi
python3 -c "import yaml" 2>/dev/null && echo "[infra] python3-yaml OK" || echo "[infra] WARN: python3-yaml missing"

echo "[infra] docker network ${NET}..."
if docker network inspect "$NET" >/dev/null 2>&1; then
  echo "[infra] network exists"
else
  docker network create "$NET"
  echo "[infra] network created"
fi

echo "[infra] docker compose..."
docker compose version >/dev/null 2>&1 && echo "[infra] docker compose OK" || echo "[infra] WARN: install compose plugin"
REMOTE
}

run_remote
echo "[infra] Done for $SERVER"
