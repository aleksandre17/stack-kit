#!/bin/bash
# Project resolution for bash -- a SHIM over lib/resolve_cli.py (ADR-001 decision 2).
#
# This file holds no rule. Which directory is the project, which manifest name is read, what a
# field defaults to, which module has which role: the resolver answers, once per shell, as one
# associative array `_SK` of `kind:key` -> text; every function below is a lookup into it. What
# the ENVIRONMENT says (env files, deploy values, slugs) is asked of the resolver each time, in
# lib/env.sh. A test holds this: no manifest field is spelled here.

stack_kit_python() {
  if command -v python3 &>/dev/null; then
    if python3 -c "import sys" &>/dev/null 2>&1; then
      python3 "$@"
      return $?
    fi
  fi
  if command -v py &>/dev/null; then
    py -3 "$@"
  elif command -v python &>/dev/null; then
    python "$@"
  else
    echo "  ERROR: python not found (need python3, py, or python)" >&2
    return 127
  fi
}

_STACK_KIT_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ask the resolver. Arguments are its verb and operands; paths come back as this shell spells them.
_stack_kit_resolve() {
  stack_kit_python -B "$_STACK_KIT_LIB/resolve_cli.py" --shell bash "$@"
}

# The context, resolved once per (declared root, else working directory) for the shell's life.
_stack_kit_context() {
  local key="${STACK_KIT_PROJECT_ROOT:-cwd:$PWD}"
  [[ "${_SK_KEY:-}" == "$key" ]] && return 0
  local resolved
  resolved="$(_stack_kit_resolve context)" || { echo "  ERROR: the kit's resolver failed" >&2; return 1; }
  eval "$resolved"
  _SK_KEY="${STACK_KIT_PROJECT_ROOT:-cwd:$PWD}"
}

# One context entry, or non-zero when it is absent or empty.
_stack_kit_ctx() {
  _stack_kit_context || return 1
  local v="${_SK[$1]:-}"
  [[ -n "$v" ]] || return 1
  printf '%s\n' "$v"
}

# One string of the kit's identity declaration (kitName, manifestFilename, legacyKitName, ...).
_stack_kit_identity() {
  _stack_kit_ctx "identity:$1"
}

# One line, once per former name and process tree (ADR-001 decision 1).
_stack_kit_notice() {
  local told
  told="$(_stack_kit_resolve notice "$1" "$2")" && eval "$told"
}

_stack_kit_manifest_file() {
  _stack_kit_ctx manifest
}

# Kept for callers: the resolver already prints paths as this shell spells them.
stack_kit_normalize_unix_path() {
  local p="${1:-}"
  [[ -n "$p" ]] || return 1
  if [[ "$p" =~ ^[A-Za-z]:[/\\] ]]; then
    (cd "$p" && pwd) || echo "$p"
  else
    echo "$p"
  fi
}

stack_kit_find_project_root() {
  _stack_kit_ctx root
}

# A scalar manifest field: the manifest's value, else the given default, else the declared
# convention default.
stack_kit_read_manifest_field() {
  _stack_kit_ctx "field:$1" && return 0
  if [[ $# -ge 2 ]]; then
    echo "$2"
    return 0
  fi
  _stack_kit_ctx "default:$1" || echo ""
}

# An array-valued manifest field, one item per line (nothing when absent).
stack_kit_read_manifest_list() {
  _stack_kit_ctx "list:$1" || true
}

stack_kit_kit_package_root() {
  _stack_kit_ctx packageRoot
}

stack_kit_kit_toolkit_bash() {
  echo "$(stack_kit_kit_package_root)/toolkit/bash"
}

stack_kit_kit_deploy_lib() {
  echo "$(stack_kit_kit_package_root)/toolkit/deploy"
}

stack_kit_kit_compose_catalog() {
  _stack_kit_ctx path:composeCatalog
}

stack_kit_kit_sync_modules_path() {
  _stack_kit_ctx path:syncModules
}

stack_kit_module_path() {
  _stack_kit_ctx "module:$1:path"
}

stack_kit_secrets_module_name() {
  _stack_kit_ctx "module:$1:secretsFolder" || echo "$1"
}

stack_kit_secrets_dir_for_module() {
  _stack_kit_ctx "module:$1:secretsDir" || echo "$(_stack_kit_ctx secretsRoot)/$1"
}

stack_kit_stack_compose_dir() {
  _stack_kit_ctx path:stackComposeDir
}

stack_kit_manifest_feature_enabled() {
  _stack_kit_ctx "feature:$1" || echo "false"
}

# The idx-th module (0-based) whose role is $1.
stack_kit_module_id_for_role() {
  local ids
  ids="$(_stack_kit_ctx "role:$1")" || return 1
  sed -n "$(( ${2:-0} + 1 ))p" <<<"$ids" | grep .
}

# The idx-th module (0-based) whose driver type is $1.
stack_kit_module_id_for_type() {
  local ids
  ids="$(_stack_kit_ctx "type:$1")" || return 1
  sed -n "$(( ${2:-0} + 1 ))p" <<<"$ids" | grep .
}

# Secrets folder names of the manifest's modules, one per line, in declaration order.
stack_kit_list_secrets_module_folders() {
  _stack_kit_ctx secretsFolders || true
}

# A module's credential files: file<TAB>mount<TAB>envVar per line.
stack_kit_module_credentials_lines() {
  _stack_kit_ctx "module:$1:credentials" || true
}

# A secrets folder's remote base: its DEPLOY_PATH, else {server base}/{project slug}/{folder}.
stack_kit_default_remote_deploy_base() {
  _stack_kit_resolve deploy-base "$1"
}

# Resolved here, in the sourcing shell: former variables are carried to their current names
# before anything reads them, and a former manifest name is told once -- a resolution first made
# inside a $(...) subshell could not export what it told to this shell.
_stack_kit_context >/dev/null || true
