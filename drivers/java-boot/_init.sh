#!/bin/bash
# java-boot driver init — set GEOSTAT_MODULE_ID before sourcing
: "${GEOSTAT_MODULE_ID:?GEOSTAT_MODULE_ID required (e.g. backend)}"

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
COMPOSE_DIR="$(geostat_module_compose_dir "$GEOSTAT_MODULE_ID" 2>/dev/null || echo "$PROJECT_DIR")"
MONOREPO="$GEOSTAT_PROJECT_ROOT"
OPS_SCRIPT_DIR="$PROJECT_DIR"
mkdir -p "$OPS_SCRIPT_DIR/logs"

if [[ -f "$PROJECT_DIR/ops.config.sh" ]]; then
  # shellcheck source=/dev/null
  source "$PROJECT_DIR/ops.config.sh"
else
  OPS_SECRETS_MODULE="$(geostat_secrets_module_name "$GEOSTAT_MODULE_ID")"
  OPS_TARGET_DEFAULT="backend"
  VERSIONS_KEEP=5
  HEALTH_RETRIES=24
fi

# shellcheck source=../../toolkit/bash/_common.sh
source "$GEOSTAT_KIT_ROOT/toolkit/bash/_common.sh"
