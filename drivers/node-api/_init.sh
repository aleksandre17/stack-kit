#!/bin/bash
# node-api driver init — set STACK_KIT_MODULE_ID before sourcing
# Mirror of java-boot/_init.sh: only the build/run stack differs (pnpm/node vs gradle/jar),
# the project/env/secrets/toolkit bootstrap is identical.
: "${STACK_KIT_MODULE_ID:?STACK_KIT_MODULE_ID required (e.g. api)}"

STACK_KIT_KIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export STACK_KIT_KIT_ROOT

if [[ -z "${STACK_KIT_PROJECT_ROOT:-}" ]]; then
  # shellcheck source=../../lib/project.sh
  source "$STACK_KIT_KIT_ROOT/lib/project.sh"
  STACK_KIT_PROJECT_ROOT="$(stack_kit_find_project_root "$(pwd)")"
fi
export STACK_KIT_PROJECT_ROOT

# shellcheck source=../../lib/project.sh
source "$STACK_KIT_KIT_ROOT/lib/project.sh"
# shellcheck source=../../lib/env.sh
source "$STACK_KIT_KIT_ROOT/lib/env.sh"
# shellcheck source=../../lib/drivers.sh
source "$STACK_KIT_KIT_ROOT/lib/drivers.sh"

PROJECT_DIR="$(stack_kit_module_project_dir "$STACK_KIT_MODULE_ID")"
MONOREPO="$STACK_KIT_PROJECT_ROOT"
OPS_SCRIPT_DIR="$PROJECT_DIR"
mkdir -p "$OPS_SCRIPT_DIR/logs"

if [[ -f "$PROJECT_DIR/ops.config.sh" ]]; then
  # shellcheck source=/dev/null
  source "$PROJECT_DIR/ops.config.sh"
else
  OPS_SECRETS_MODULE="$(stack_kit_secrets_module_name "$STACK_KIT_MODULE_ID")"
  OPS_TARGET_DEFAULT="api"
  VERSIONS_KEEP=5
  HEALTH_RETRIES=24
fi

# pnpm workspace root for the node build (build:engine + --filter run from here).
# Default: the directory that holds pnpm-workspace.yaml at/above the module path.
if [[ -z "${NODE_WORKSPACE_DIR:-}" ]]; then
  _ws="$PROJECT_DIR"
  while [[ "$_ws" != "$STACK_KIT_PROJECT_ROOT" && "$_ws" != "/" ]]; do
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
    NODE_PKG_FILTER="$(stack_kit_python -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8')).get('name',''))" "$PROJECT_DIR/package.json" 2>/dev/null)"
  fi
  [[ -n "${NODE_PKG_FILTER:-}" ]] || NODE_PKG_FILTER="$STACK_KIT_MODULE_ID"
fi
export NODE_PKG_FILTER

# Workspace scripts that MUST build before this module's package, in declared order.
# Declared by the consumer as modules.<id>.node.prebuildScripts (default: none).
if [[ -z "${NODE_PREBUILD_SCRIPTS:-}" ]]; then
  NODE_PREBUILD_SCRIPTS="$(stack_kit_read_manifest_list "modules.${STACK_KIT_MODULE_ID}.node.prebuildScripts" 2>/dev/null)"
fi
export NODE_PREBUILD_SCRIPTS

# Local npm/pnpm script for `run` / dev (manifest debug.npmScript, default dev).
if [[ -z "${NODE_RUN_SCRIPT:-}" ]]; then
  NODE_RUN_SCRIPT="$(stack_kit_read_manifest_field "modules.${STACK_KIT_MODULE_ID}.debug.npmScript" "" 2>/dev/null)"
  [[ -n "$NODE_RUN_SCRIPT" ]] || NODE_RUN_SCRIPT="dev"
fi
export NODE_RUN_SCRIPT

# shellcheck source=../../toolkit/bash/_common.sh
source "$STACK_KIT_KIT_ROOT/toolkit/bash/_common.sh"
