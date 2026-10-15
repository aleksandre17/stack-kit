#!/bin/bash
# stack-kit package — env & naming (no application logic)
# Source: stack_kit_kit_package_root/lib/env.sh (after project.sh)

# shellcheck source=project.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/project.sh"

stack_kit_monorepo_root() {
  if [[ -n "${OPS_MONOREPO_ROOT:-}" ]]; then
    echo "$OPS_MONOREPO_ROOT"
    return
  fi
  if [[ -n "${STACK_KIT_MONOREPO_ROOT:-}" ]]; then
    echo "$STACK_KIT_MONOREPO_ROOT"
    return
  fi
  if [[ -n "${STACK_KIT_PROJECT_ROOT:-}" ]]; then
    echo "$STACK_KIT_PROJECT_ROOT"
    return
  fi
  stack_kit_find_project_root "$(pwd)" || {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    echo "$(cd "$script_dir/../../.." && pwd)"
  }
}

# Read ops/config/deploy.env only (shared deploy identity)
stack_kit_deploy_env_value() {
  local key="$1" default="${2:-}"
  local f root line k v
  root="$(stack_kit_monorepo_root)"
  f="$(stack_kit_secrets_root)/deploy.env"
  [[ -f "$f" ]] || { echo "${!key:-$default}"; return; }
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$ ]] || continue
    k="${BASH_REMATCH[1]}"
    v="${BASH_REMATCH[2]}"
    v="${v%$'\r'}"
    v="${v#\"}"; v="${v%\"}"
    v="${v#\'}"; v="${v%\'}"
    [[ "$k" == "$key" && -n "$v" ]] && echo "$v" && return 0
  done <"$f"
  if [[ -n "${!key:-}" ]]; then
    echo "${!key}"
    return 0
  fi
  echo "$default"
}

stack_kit_slugify() {
  local s="$1"
  s="$(echo "$s" | tr '[:upper:]' '[:lower:]')"
  s="$(echo "$s" | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+|-+$//g')"
  echo "$s"
}

# SSH remote path segment ($SERVER_BASE/$PROJECT/...)
stack_kit_project_slug() {
  local slug
  slug="$(stack_kit_deploy_env_value DEPLOY_PROJECT "")"
  [[ -n "$slug" ]] || slug="$(basename "$(stack_kit_monorepo_root)")"
  stack_kit_slugify "$slug"
}

# Docker compose / network naming (repo folder unless COMPOSE_PROJECT_NAME set)
stack_kit_compose_slug() {
  local slug
  slug="$(stack_kit_deploy_env_value COMPOSE_PROJECT_NAME "")"
  [[ -n "$slug" ]] || slug="$(basename "$(stack_kit_monorepo_root)")"
  stack_kit_slugify "$slug"
}

stack_kit_docker_network() {
  local slug net
  slug="$(stack_kit_compose_slug)"
  net="$(stack_kit_deploy_env_value DOCKER_NETWORK "")"
  [[ -n "$net" ]] || net="$(stack_kit_deploy_env_value STACK_KIT_DOCKER_NETWORK "")"
  [[ -n "$net" ]] || net="${slug}-net"
  echo "$net"
}

stack_kit_server_base() {
  local base server
  base="$(stack_kit_deploy_env_value DEPLOY_SERVER_BASE "")"
  [[ -n "$base" ]] && echo "$base" && return 0
  server="$(stack_kit_deploy_env_value DEPLOY_SERVER "")"
  if [[ "$server" =~ ^([^@]+)@ ]]; then
    echo "/home/${BASH_REMATCH[1]}"
    return 0
  fi
  echo ""
}

stack_kit_secrets_root() {
  local root rel
  root="$(stack_kit_monorepo_root)"
  rel="$(stack_kit_read_manifest_field secrets "ops/config")"
  echo "$root/$rel"
}

stack_kit_secrets_module_dir() {
  echo "$(stack_kit_secrets_root)/$1"
}

# Prints one path per line: .env.dev | .env.prod | deploy.env | .env.deploy
stack_kit_env_files() {
  local module="$1" profile="${2:-all}"
  local dir root
  dir="$(stack_kit_secrets_module_dir "$module")"
  root="$(stack_kit_monorepo_root)"

  if [[ "$profile" == "dev" || "$profile" == "all" ]] && [[ -f "$dir/.env.dev" ]]; then
    echo "$dir/.env.dev"
  fi
  if [[ "$profile" == "prod" || "$profile" == "all" ]] && [[ -f "$dir/.env.prod" ]]; then
    echo "$dir/.env.prod"
  fi
  if [[ "$profile" == "deploy" || "$profile" == "all" ]]; then
    [[ -f "$(stack_kit_secrets_root)/deploy.env" ]] && echo "$(stack_kit_secrets_root)/deploy.env"
    [[ -f "$dir/.env.deploy" ]] && echo "$dir/.env.deploy"
  fi
}

# stack_kit_env_value <module> <KEY> [default]
stack_kit_env_value() {
  local module="$1" key="$2" default="${3:-}"
  local f line k v
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    while IFS= read -r line || [[ -n "$line" ]]; do
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$ ]] || continue
      k="${BASH_REMATCH[1]}"
      v="${BASH_REMATCH[2]}"
      v="${v%$'\r'}"
      v="${v#\"}"; v="${v%\"}"
      v="${v#\'}"; v="${v%\'}"
      [[ "$k" == "$key" && -n "$v" ]] && echo "$v" && return 0
    done < "$f"
  done < <(stack_kit_env_files "$module" all)
  echo "$default"
}

stack_kit_infra_consumer_slug() {
  local slug
  slug="$(stack_kit_env_value infra INFRA_SLUG "")"
  [[ -n "$slug" ]] || slug="$(basename "$(stack_kit_monorepo_root)")"
  stack_kit_slugify "$slug"
}

# Remote: {server_base}/{DEPLOY_PROJECT}/infra/{INFRA_SLUG}
stack_kit_resolve_infra_deploy_path() {
  local explicit slug base gp
  slug="$(stack_kit_infra_consumer_slug)"
  explicit="$(stack_kit_env_value infra DEPLOY_PATH "")"
  if [[ -n "$explicit" ]]; then
    explicit="${explicit%/}"
    if [[ "$explicit" != */infra/"$slug" ]]; then
      echo "ERROR: DEPLOY_PATH must end with /infra/$slug (got: $explicit)" >&2
      return 1
    fi
    echo "$explicit"
    return 0
  fi
  base="$(stack_kit_server_base)"
  gp="$(stack_kit_project_slug)"
  if [[ -n "$base" && -n "$gp" ]]; then
    echo "${base%/}/$gp/infra/$slug"
    return 0
  fi
  echo "/home/administrator/stack-kit/infra/$slug"
}

stack_kit_infra_compose_dir() {
  local proj rel
  proj="$(stack_kit_find_project_root)" || return 1
  rel="$(stack_kit_read_manifest_field stack.infraComposeDir "ops/compose/infra")"
  echo "$proj/$rel"
}

# stack_kit_stack_env_files <dev|prod>
stack_kit_stack_env_files() {
  local profile="$1" folder seen=()
  while IFS= read -r folder; do
    [[ -n "$folder" ]] || continue
    stack_kit_env_files "$folder" "$profile"
  done < <(stack_kit_list_secrets_module_folders)
  local deploy_env
  deploy_env="$(stack_kit_secrets_root)/deploy.env"
  [[ -f "$deploy_env" ]] && echo "$deploy_env"
}
