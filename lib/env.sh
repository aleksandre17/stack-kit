#!/bin/bash
# Env files, deploy values and naming for bash -- a SHIM over lib/resolve_cli.py (ADR-001 decision 2).
#
# What the environment says changes during a run (an env file written, a variable exported), so
# none of it is cached: each function asks the resolver, which holds the one rule -- which files a
# secrets folder reads and in what order, that a later file's value wins, that an operator's
# process environment beats deploy.env, how a slug is made.

# shellcheck source=project.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/project.sh"

stack_kit_monorepo_root() {
  _stack_kit_ctx monorepoRoot
}

# A shared deploy value: the process environment first, then ops/config/deploy.env.
stack_kit_deploy_env_value() {
  _stack_kit_resolve deploy-env-value "$@"
}

stack_kit_slugify() {
  _stack_kit_resolve slugify "$1"
}

# The remote path segment ($SERVER_BASE/$PROJECT/...).
stack_kit_project_slug() {
  _stack_kit_resolve project-slug
}

# Docker compose / network naming.
stack_kit_compose_slug() {
  _stack_kit_resolve compose-slug
}

stack_kit_docker_network() {
  _stack_kit_resolve docker-network
}

stack_kit_server_base() {
  _stack_kit_resolve server-base
}

stack_kit_secrets_root() {
  _stack_kit_ctx secretsRoot
}

stack_kit_secrets_module_dir() {
  echo "$(stack_kit_secrets_root)/$1"
}

# A secrets folder's env files, one path per line: .env.dev | .env.prod | deploy.env | .env.deploy
stack_kit_env_files() {
  _stack_kit_resolve env-files "$1" "${2:-all}"
}

# stack_kit_env_value <folder> <KEY> [default] -- the last non-empty value across its env files.
stack_kit_env_value() {
  _stack_kit_resolve env-value "$@"
}

stack_kit_infra_consumer_slug() {
  _stack_kit_resolve infra-slug
}

# Remote: {server_base}/{DEPLOY_PROJECT}/infra/{INFRA_SLUG}
stack_kit_resolve_infra_deploy_path() {
  _stack_kit_resolve infra-deploy-path
}

stack_kit_infra_compose_dir() {
  _stack_kit_ctx path:infraComposeDir
}

# stack_kit_stack_env_files <dev|prod> -- every module folder's files for the profile, then deploy.env.
stack_kit_stack_env_files() {
  local folder f seen=$'\n'
  while IFS= read -r folder; do
    [[ -n "$folder" ]] || continue
    while IFS= read -r f; do
      [[ -n "$f" && "$seen" != *$'\n'"$f"$'\n'* ]] || continue
      seen+="$f"$'\n'
      echo "$f"
    done < <(stack_kit_env_files "$folder" "$1")
  done < <(stack_kit_list_secrets_module_folders)
  f="$(stack_kit_secrets_root)/deploy.env"
  [[ -f "$f" && "$seen" != *$'\n'"$f"$'\n'* ]] && echo "$f"
  return 0
}
