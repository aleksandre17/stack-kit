#!/bin/bash
# java-boot driver init — set STACK_KIT_MODULE_ID before sourcing
: "${STACK_KIT_MODULE_ID:?STACK_KIT_MODULE_ID required (e.g. backend)}"

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
  OPS_SECRETS_MODULE="${STACK_KIT_MODULE_ID}"
  OPS_TARGET_DEFAULT="backend"
  VERSIONS_KEEP=5
  HEALTH_RETRIES=24
fi

# shellcheck source=../../toolkit/bash/_common.sh
source "$STACK_KIT_KIT_ROOT/toolkit/bash/_common.sh"
