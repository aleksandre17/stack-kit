#!/bin/bash
# SSH helpers for stack-kit deploy — optional project-local keys under ops/config/ssh/
# Source after stack_kit_monorepo_root / stack_kit_deploy_env_value are available.

stack_kit_resolve_repo_path() {
  local p="$1"
  [[ -z "$p" ]] && return 1
  if [[ "$p" == /* ]] || [[ "$p" =~ ^[A-Za-z]:[/\\] ]]; then
    echo "$p"
    return 0
  fi
  echo "$(stack_kit_monorepo_root)/$p"
}

# Print extra openssh args: -F config, -i identity (one line, eval-safe with array)
stack_kit_ssh_extra_args() {
  local cfg id root opts=""
  root="$(stack_kit_monorepo_root)"
  cfg="$(stack_kit_deploy_env_value DEPLOY_SSH_CONFIG_FILE "")"
  id="$(stack_kit_deploy_env_value DEPLOY_SSH_IDENTITY_FILE "")"
  [[ -n "$cfg" ]] && cfg="$(stack_kit_resolve_repo_path "$cfg")"
  [[ -n "$id" ]] && id="$(stack_kit_resolve_repo_path "$id")"
  if [[ -n "$cfg" && -f "$cfg" ]]; then
    printf '%s\n' "-F" "$cfg"
  fi
  if [[ -n "$id" && -f "$id" ]]; then
    printf '%s\n' "-i" "$id"
  fi
  local extra
  extra="$(stack_kit_deploy_env_value DEPLOY_SSH_OPTIONS "")"
  if [[ -n "$extra" ]]; then
    # shellcheck disable=SC2086
    printf '%s\n' $extra
  fi
}

stack_kit_ssh() {
  local -a _extra=()
  while IFS= read -r _line; do
    [[ -n "$_line" ]] && _extra+=("$_line")
  done < <(stack_kit_ssh_extra_args)
  command ssh "${_extra[@]}" "$@"
}

stack_kit_scp() {
  local -a _extra=()
  while IFS= read -r _line; do
    [[ -n "$_line" ]] && _extra+=("$_line")
  done < <(stack_kit_ssh_extra_args)
  command scp "${_extra[@]}" "$@"
}

# When deploy.env sets SSH options, prefer stack_kit_ssh/stack_kit_scp in toolkit scripts.
stack_kit_ssh_maybe_alias() {
  if [[ -n "$(stack_kit_deploy_env_value DEPLOY_SSH_CONFIG_FILE "")" ]] \
    || [[ -n "$(stack_kit_deploy_env_value DEPLOY_SSH_IDENTITY_FILE "")" ]] \
    || [[ -n "$(stack_kit_deploy_env_value DEPLOY_SSH_OPTIONS "")" ]]; then
    ssh() { stack_kit_ssh "$@"; }
    scp() { stack_kit_scp "$@"; }
  fi
}
