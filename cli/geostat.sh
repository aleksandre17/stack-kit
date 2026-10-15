#!/bin/bash
# The kit's former command name (ADR-001 decision 1): one notice, then the current command.
# Nothing here holds a rule; the names are read from lib/identity.json.
set -euo pipefail
CLI="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../lib/project.sh
source "$CLI/../lib/project.sh"
_stack_kit_notice "cli/$(_stack_kit_identity legacyKitName).sh" "cli/$(_stack_kit_identity kitName).sh"
exec bash "$CLI/$(_stack_kit_identity kitName).sh" "$@"
