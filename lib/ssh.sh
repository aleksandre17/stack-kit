#!/bin/bash
# SSH for stack-kit deploys -- a SHIM over the resolver (ADR-001 amendment 9): the options every
# ssh, scp and rsync takes are the selected deploy target's (`resolve_cli.py ssh-args`: port, strict
# host keys against the target's pinned file, its identity reference, its options), or -- without a
# declared target -- the deprecated DEPLOY_SSH_* of deploy.env. No option is decided here.

stack_kit_resolve_repo_path() {
  local p="$1"
  [[ -z "$p" ]] && return 1
  if [[ "$p" == /* ]] || [[ "$p" =~ ^[A-Za-z]:[/\\] ]]; then
    echo "$p"
    return 0
  fi
  echo "$(stack_kit_monorepo_root)/$p"
}

# The openssh arguments of the selected target, one per line.
stack_kit_ssh_extra_args() {
  _stack_kit_resolve ssh-args
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

# The server-side preflight of a deploy (resolve_cli.py remote-preflight): claim the project's
# directory with its ownership marker, or refuse one another project owns, and refuse a declared
# host port another compose project publishes. Run before a deploy writes anything; nothing to run
# without a declared target.
stack_kit_remote_preflight() {
  local script
  script="$(_stack_kit_resolve remote-preflight "$@")" || return 1
  [[ -n "$script" ]] || return 0
  printf '%s\n' "$script" | ssh "$SERVER" bash -s
}

# A remote path a remove or prune may touch: inside this project's directory on the target.
stack_kit_confined() {
  _stack_kit_resolve confined "$1" >/dev/null || {
    echo "  REFUSED: $1 is outside this project's directory on the target" >&2
    return 1
  }
}

# Every ssh/scp of a sourced toolkit script goes through the target's options, and rsync's
# transport is the same ssh (RSYNC_RSH).
stack_kit_ssh_maybe_alias() {
  local -a _extra=()
  while IFS= read -r _line; do
    [[ -n "$_line" ]] && _extra+=("$_line")
  done < <(stack_kit_ssh_extra_args)
  [[ ${#_extra[@]} -gt 0 ]] || return 0
  ssh() { stack_kit_ssh "$@"; }
  scp() { stack_kit_scp "$@"; }
  local rsh="ssh" a
  for a in "${_extra[@]}"; do rsh+=" $(printf '%q' "$a")"; done
  export RSYNC_RSH="$rsh"
}
