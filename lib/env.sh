#!/bin/bash
# Env files and values for bash -- a SHIM over lib/resolve_cli.py (ADR-001 decision 2).
#
# What the environment says changes during a run (an env file written, a variable exported), so
# none of it is cached: each function asks the resolver, which holds the one rule -- which files a
# secrets folder reads and in what order, that a later file's value wins,
# how a slug is made.

# shellcheck source=project.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/project.sh"

stack_kit_monorepo_root() {
  _stack_kit_ctx monorepoRoot
}

stack_kit_slugify() {
  _stack_kit_resolve slugify "$1"
}

stack_kit_secrets_root() {
  _stack_kit_ctx secretsRoot
}

stack_kit_secrets_module_dir() {
  echo "$(stack_kit_secrets_root)/$1"
}

# A secrets folder's env files, one path per line: one per environment
stack_kit_env_files() {
  _stack_kit_resolve env-files "$1" "${2:-all}"
}

# stack_kit_env_value <folder> <KEY> [default] -- the last non-empty value across its env files.
stack_kit_env_value() {
  _stack_kit_resolve env-value "$@"
}

stack_kit_infra_compose_dir() {
  _stack_kit_ctx path:infraComposeDir
}

