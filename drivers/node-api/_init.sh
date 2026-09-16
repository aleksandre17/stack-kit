#!/bin/bash
# node-api driver init — set GEOSTAT_MODULE_ID before sourcing
# Mirror of java-boot/_init.sh: only the build/run stack differs (pnpm/node vs gradle/jar),
# the project/env/secrets/toolkit bootstrap is identical.
: "${GEOSTAT_MODULE_ID:?GEOSTAT_MODULE_ID required (e.g. api)}"

GEOSTAT_KIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export GEOSTAT_KIT_ROOT

if [[ -z "${GEOSTAT_PROJECT_ROOT:-}" ]]; then
  # shellcheck source=../../lib/project.sh
  source "$GEOSTAT_KIT_ROOT/lib/project.sh"
  GEOSTAT_PROJECT_ROOT="$(geostat_find_project_root "$(pwd)")"
fi
export GEOSTAT_PROJECT_ROOT

# shellcheck source=../../lib/project.sh
source "$GEOSTAT_KIT_ROOT/lib/project.sh"
# shellcheck source=../../lib/env.sh
source "$GEOSTAT_KIT_ROOT/lib/env.sh"
# shellcheck source=../../lib/drivers.sh
source "$GEOSTAT_KIT_ROOT/lib/drivers.sh"

PROJECT_DIR="$(geostat_module_project_dir "$GEOSTAT_MODULE_ID")"
MONOREPO="$GEOSTAT_PROJECT_ROOT"
OPS_SCRIPT_DIR="$PROJECT_DIR"
mkdir -p "$OPS_SCRIPT_DIR/logs"

if [[ -f "$PROJECT_DIR/ops.config.sh" ]]; then
  # shellcheck source=/dev/null
  source "$PROJECT_DIR/ops.config.sh"
else
  OPS_SECRETS_MODULE="$(geostat_secrets_module_name "$GEOSTAT_MODULE_ID")"
  OPS_TARGET_DEFAULT="api"
  VERSIONS_KEEP=5
  HEALTH_RETRIES=24
fi

# pnpm workspace root for the node build (build:engine + --filter run from here).
# Default: the directory that holds pnpm-workspace.yaml at/above the module path.
if [[ -z "${NODE_WORKSPACE_DIR:-}" ]]; then
  _ws="$PROJECT_DIR"
  while [[ "$_ws" != "$GEOSTAT_PROJECT_ROOT" && "$_ws" != "/" ]]; do
    if [[ -f "$_ws/pnpm-workspace.yaml" ]]; then break; fi
    _ws="$(dirname "$_ws")"
  done
  [[ -f "$_ws/pnpm-workspace.yaml" ]] || _ws="$PROJECT_DIR"
  NODE_WORKSPACE_DIR="$_ws"
fi
export NODE_WORKSPACE_DIR

# pnpm package filter for this module (from package.json "name"); falls back to module id.
if [[ -z "${NODE_PKG_FILTER:-}" ]]; then
  if [[ -f "$PROJECT_DIR/package.json" ]]; then
    NODE_PKG_FILTER="$(geostat_python -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8')).get('name',''))" "$PROJECT_DIR/package.json" 2>/dev/null)"
  fi
  [[ -n "${NODE_PKG_FILTER:-}" ]] || NODE_PKG_FILTER="$GEOSTAT_MODULE_ID"
fi
export NODE_PKG_FILTER

# Local npm/pnpm script for `run` / dev (manifest debug.npmScript, default dev).
if [[ -z "${NODE_RUN_SCRIPT:-}" ]]; then
  NODE_RUN_SCRIPT="$(geostat_read_manifest_field "modules.${GEOSTAT_MODULE_ID}.debug.npmScript" "" 2>/dev/null)"
  [[ -n "$NODE_RUN_SCRIPT" ]] || NODE_RUN_SCRIPT="dev"
fi
export NODE_RUN_SCRIPT

# shellcheck source=../../toolkit/bash/_common.sh
source "$GEOSTAT_KIT_ROOT/toolkit/bash/_common.sh"
