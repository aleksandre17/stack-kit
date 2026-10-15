#!/bin/bash
# Module drivers for bash -- a SHIM over the resolver's context (ADR-001 decision 2).
# Requires lib/project.sh (sourced first by every caller).

stack_kit_driver_api() {
  stack_kit_python "$(stack_kit_kit_package_root)/lib/driver_api.py" "$@"
}

stack_kit_driver_registry() {
  echo "$(stack_kit_kit_package_root)/drivers/registry.json"
}

stack_kit_module_type() {
  _stack_kit_ctx "module:$1:type" || {
    echo "  ERROR: module '$1' is not declared, or declares no type" >&2
    return 1
  }
}

stack_kit_module_project_dir() {
  stack_kit_module_path "$1"
}

stack_kit_driver_root() {
  _stack_kit_ctx "module:$1:driverRoot"
}

stack_kit_driver_command_path() {
  local typ
  typ="$(stack_kit_module_type "$1")" || return 1
  _stack_kit_ctx "driver:$typ:command:$2" || {
    echo "  ERROR: driver '$typ' has no command '$2' (available: $(_stack_kit_ctx "driver:$typ:commands" | paste -sd, -))" >&2
    return 1
  }
}

stack_kit_driver_capabilities() {
  local typ
  typ="$(stack_kit_module_type "$1")" || return 1
  _stack_kit_ctx "driver:$typ:commands"
}

stack_kit_cli_resolve_alias() {
  _stack_kit_ctx "alias:$1" || { _stack_kit_ctx "module:$1:type" >/dev/null && echo "$1"; }
}
