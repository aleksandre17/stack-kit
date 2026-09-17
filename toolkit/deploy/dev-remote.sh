#!/bin/bash
# Backend remote dev — rsync Gradle tree to workspace/ + bootRun in container
# Requires: deploy-path.sh, modules.sh, Git rsync (Windows: Git for Windows)

DEV_RSYNC_EXCLUDES=(
  ".git/"
  ".gradle/"
  "build/"
  "**/build/"
  "logs/"
  "app.jar"
  "*.log"
  ".idea/"
  ".vscode/"
  "deploy-staging/"
  ".cache/"
  "node_modules/"
  # Generated on the server by bootstrap; rsync --delete must not remove them.
  ".env.dev"
  "docker-compose.workspace.yml"
  "docker-compose.base.yml"
  ".geostat-deploy.json"
)

DEV_COMPOSE_BASE_FILE="docker-compose.base.yml"

dev_rsync_executable() {
  local c
  for c in \
    "${ProgramFiles}/Git/usr/bin/rsync.exe" \
    "${ProgramFiles}/Git/bin/rsync.exe" \
    rsync; do
    if command -v "$c" >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
    [[ -f "$c" ]] && echo "$c" && return 0
  done
  return 1
}

dev_to_rsync_path() {
  local p="$1"
  if [[ "$p" =~ ^([A-Za-z]):(.*)$ ]]; then
    local drive="${BASH_REMATCH[1],,}"
    local rest="${BASH_REMATCH[2]//\\//}"
    echo "/$drive$rest"
    return
  fi
  echo "${p//\\//}"
}

dev_workspace_path_for() {
  local s="$1" cname
  cname="$(container_name_for "$s")"
  resolve_backend_deploy_path "$cname" "workspace"
}

dev_assert_structured_layout() {
  deploy_path_load_config
  if [[ "$DEPLOY_LAYOUT" != "structured" ]]; then
    echo "  ERROR: dev requires DEPLOY_LAYOUT=structured in ${SECRETS_DIR}/.env.deploy" >&2
    echo "  Copy ${SECRETS_DIR}/.env.deploy.example → .env.deploy" >&2
    return 1
  fi
  return 0
}

# rsync exclude pattern -> GNU tar --exclude glob (both match any path component).
dev_tar_exclude_pattern() {
  local p="${1%/}"
  echo "${p#\*\*/}"
}

# Same mirror semantics without a local rsync: stream a tar to a server-side
# staging dir, then mirror it with the server's rsync (--delete, same excludes).
dev_tar_mirror_to_workspace() {
  local rp="$1" stage exclude
  local -a tar_args=() remote_excludes=()
  command -v tar >/dev/null 2>&1 || { echo "  ERROR: neither rsync nor tar available locally" >&2; return 1; }
  for exclude in "${DEV_RSYNC_EXCLUDES[@]}"; do
    tar_args+=(--exclude="$(dev_tar_exclude_pattern "$exclude")")
    remote_excludes+=("--exclude=$(printf '%q' "$exclude")")
  done
  stage="$(dirname "$rp")/.$(basename "$rp").sync"
  echo "  tar+ssh → $rp (server-side rsync mirror)"
  ssh -n "$SERVER" "command -v rsync >/dev/null || { echo '  ERROR: rsync missing on server' >&2; exit 1; }; rm -rf '$stage' && mkdir -p '$stage' '$rp'" || return 1
  tar -C "$PROJECT_DIR" "${tar_args[@]}" -czf - . | ssh "$SERVER" "tar -xzf - -C '$stage'" || return 1
  ssh -n "$SERVER" "rsync -a --delete ${remote_excludes[*]} '$stage/' '$rp/' && rm -rf '$stage'"
}

dev_rsync_to_workspace() {
  local s="$1" rp rsync_exe src exclude
  rp="$(dev_workspace_path_for "$s")"
  rsync_exe="$(dev_rsync_executable)" || {
    dev_tar_mirror_to_workspace "$rp"
    return
  }

  src="$(dev_to_rsync_path "$PROJECT_DIR")"
  ssh -n "$SERVER" "mkdir -p '$rp'" || return 1

  local -a args=(-avz --delete)
  # Carry declared DEPLOY_SSH_* settings into rsync's transport (ssh/scp already honour them).
  local ssh_extra
  ssh_extra="$(geostat_ssh_extra_args 2>/dev/null | tr '\n' ' ')"
  [[ -n "${ssh_extra// /}" ]] && args+=(-e "ssh ${ssh_extra% }")
  for exclude in "${DEV_RSYNC_EXCLUDES[@]}"; do
    args+=(--exclude="$exclude")
  done
  args+=("${src}/" "$SERVER:$rp/")

  echo "  rsync → $rp"
  "$rsync_exe" "${args[@]}"
}

dev_publish_workspace_env() {
  local s="$1" rp env_src
  rp="$(dev_workspace_path_for "$s")"
  env_src="$SECRETS_DIR/.env.dev"
  [[ -f "$env_src" ]] || {
    echo "  ERROR: missing $env_src" >&2
    return 1
  }
  scp "$env_src" "$SERVER:$rp/.env.dev" || return 1
  local line cred_file mount remote_name
  while IFS=$'\t' read -r cred_file mount _env_var; do
    [[ -n "$cred_file" ]] || continue
    cred="$SECRETS_DIR/$cred_file"
    if [[ -f "$cred" ]]; then
      remote_name="$(basename "${mount:-$cred_file}")"
      scp "$cred" "$SERVER:$rp/$remote_name" || return 1
    fi
  done < <(geostat_module_credentials_lines "$s")
}

# Declared per-service remote-dev settings:
#   modules.<id>.dev.services.<service>.{dockerfile,portEnv,port,healthPath}
# Empty when undeclared, so callers keep the conventional default.
dev_service_setting() {
  local s="$1" key="$2"
  [[ -n "${GEOSTAT_MODULE_ID:-}" ]] || return 0
  geostat_read_manifest_field "modules.${GEOSTAT_MODULE_ID}.dev.services.${s}.${key}" "" 2>/dev/null || true
}

dev_gradle_task_for() {
  local s="$1" gn
  gn="$(module_gradle_name "$s")"
  if [[ -n "$gn" ]]; then
    echo ":${gn}:bootRun"
  else
    echo "bootRun"
  fi
}

dev_dockerfile_for() {
  local s="$1" gn declared
  declared="$(dev_service_setting "$s" dockerfile)"
  [[ -n "$declared" ]] && { echo "$declared"; return 0; }
  gn="$(module_gradle_name "$s")"
  if [[ -n "$gn" ]]; then
    echo "$gn/Dockerfile.dev.remote"
  else
    echo "src/Dockerfile.dev.remote"
  fi
}

dev_health_path_for() {
  local s="$1" gn declared
  declared="$(dev_service_setting "$s" healthPath)"
  [[ -n "$declared" ]] && { echo "$declared"; return 0; }
  gn="$(module_gradle_name "$s")"
  if [[ -n "$gn" ]]; then
    echo "/actuator/health"
  else
    echo "/health"
  fi
}

dev_port_var_for() {
  local s="$1" gn declared
  declared="$(dev_service_setting "$s" portEnv)"
  [[ -n "$declared" ]] && { echo "$declared"; return 0; }
  gn="$(module_gradle_name "$s")"
  if [[ -n "$gn" ]]; then
    echo "WORKER_PORT"
  else
    echo "API_PORT"
  fi
}

dev_default_port_for() {
  local s="$1" gn declared
  declared="$(dev_service_setting "$s" port)"
  [[ -n "$declared" ]] && { echo "$declared"; return 0; }
  gn="$(module_gradle_name "$s")"
  if [[ -n "$gn" ]]; then
    echo "8091"
  else
    echo "8090"
  fi
}

dev_profile_for() {
  local s="$1" declared
  declared="$(dev_service_setting "$s" profile)"
  echo "${declared:-dev}"
}

# Declared extra volumes: modules.<id>.dev.services.<service>.volumes[]
dev_declared_volumes() {
  local s="$1"
  [[ -n "${GEOSTAT_MODULE_ID:-}" ]] || return 0
  geostat_read_manifest_list "modules.${GEOSTAT_MODULE_ID}.dev.services.${s}.volumes"
}

dev_compose_volumes_yaml() {
  local s="$1" v
  while IFS= read -r v; do
    if [[ -n "$v" ]]; then printf '      - %s\n' "$v"; fi
  done < <(dev_declared_volumes "$s")
}

# Declared shared service definition: modules.<id>.dev.services.<service>.composeBase
# (path from the project root). The workspace service extends it, so every
# environment line shares one declaration and adds only its run mode.
dev_compose_base_for() {
  dev_service_setting "$1" composeBase
}

dev_compose_base_local_path() {
  local base
  base="$(dev_compose_base_for "$1")"
  [[ -n "$base" ]] || return 0
  echo "$(geostat_monorepo_root)/$base"
}

dev_publish_compose_base() {
  local s="$1" rp local_base
  local_base="$(dev_compose_base_local_path "$s")"
  [[ -n "$local_base" ]] || return 0
  [[ -f "$local_base" ]] || {
    echo "  ERROR: composeBase not found: $local_base" >&2
    return 1
  }
  rp="$(dev_workspace_path_for "$s")"
  scp "$local_base" "$SERVER:$rp/$DEV_COMPOSE_BASE_FILE"
}

dev_compose_extends_yaml() {
  local s="$1"
  [[ -n "$(dev_compose_base_for "$s")" ]] || return 0
  printf '    extends:\n      file: %s\n      service: %s\n' "$DEV_COMPOSE_BASE_FILE" "$s"
}

# Named volumes the extended base service uses (extends does not carry top-level volumes).
dev_compose_base_named_volumes() {
  local s="$1" local_base
  local_base="$(dev_compose_base_local_path "$s")"
  [[ -n "$local_base" && -f "$local_base" ]] || return 0
  geostat_python -c "
import sys, yaml
with open(sys.argv[1], encoding='utf-8') as fh:
    doc = yaml.safe_load(fh) or {}
svc = (doc.get('services') or {}).get(sys.argv[2]) or {}
for v in svc.get('volumes') or []:
    src = v.get('source') if isinstance(v, dict) and v.get('type', 'volume') == 'volume' else (str(v).split(':', 1)[0] if ':' in str(v) else '')
    if src and '/' not in src and not src.startswith(('.', '\$')):
        print(src)
" "$local_base" "$s"
}

# Named volumes (source without '/') must be declared at top level.
dev_compose_named_volumes_yaml() {
  local s="$1" v src
  {
    while IFS= read -r v; do
      src="${v%%:*}"
      if [[ -n "$src" && "$src" != */* && "$src" != .* && "$src" != \$* ]]; then echo "$src"; fi
    done < <(dev_declared_volumes "$s")
    dev_compose_base_named_volumes "$s"
  } | awk 'NF && !seen[$0]++ { printf "  %s:\n", $0 }'
}

dev_compose_command_yaml() {
  local s="$1" gn
  gn="$(module_gradle_name "$s")"
  if [[ -n "$gn" ]]; then
    echo "[\"./gradlew\", \":${gn}:bootRun\", \"-x\", \"test\", \"--no-daemon\"]"
  else
    echo "[\"./gradlew\", \"bootRun\", \"-x\", \"test\", \"--no-daemon\"]"
  fi
}

dev_ensure_docker_network() {
  local net="${DOCKER_NETWORK:-${PROJECT}-net}"
  ssh -n "$SERVER" "docker network inspect '$net' >/dev/null 2>&1 || docker network create '$net'" || return 1
}

dev_compose_credential_env_yaml() {
  local module_id="$1" line cred_file mount env_var
  while IFS=$'\t' read -r cred_file mount env_var; do
    [[ -n "$env_var" ]] || continue
    printf '      %s: %s\n' "$env_var" "$mount"
  done < <(geostat_module_credentials_lines "$module_id")
}

dev_write_workspace_compose() {
  local s="$1" rp df cmd port_var health_path cname def_port net
  rp="$(dev_workspace_path_for "$s")"
  df="$(dev_dockerfile_for "$s")"
  cmd="$(dev_compose_command_yaml "$s")"
  port_var="$(dev_port_var_for "$s")"
  health_path="$(dev_health_path_for "$s")"
  cname="$(container_name_for "$s")"
  def_port="$(dev_default_port_for "$s")"
  net="${DOCKER_NETWORK:-${PROJECT}-net}"

  dev_publish_compose_base "$s" || return 1
  ssh "$SERVER" "cat > '$rp/docker-compose.workspace.yml'" <<YML
services:
  ${s}:
$(dev_compose_extends_yaml "$s")
    image: ${cname}-workspace
    container_name: ${cname}
    build:
      context: .
      dockerfile: ${df}
    working_dir: /app
    command: ${cmd}
    ports:
      - "\${${port_var}:-${def_port}}:\${${port_var}:-${def_port}}"
    volumes:
      - .:/app
      - gradle_cache_${cname}:/home/gradle/.gradle
$(dev_compose_volumes_yaml "$s")
    env_file:
      - .env.dev
    environment:
      SPRING_PROFILES_ACTIVE: $(dev_profile_for "$s")
$(dev_compose_credential_env_yaml "$s")
      GRADLE_USER_HOME: /home/gradle/.gradle
    networks:
      - ${net}
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:\${${port_var}:-${def_port}}${health_path} | grep -q UP || exit 1"]
      interval: 20s
      timeout: 5s
      retries: 8
      start_period: 180s

networks:
  ${net}:
    external: true

volumes:
  gradle_cache_${cname}:
$(dev_compose_named_volumes_yaml "$s")
YML
}

dev_compose_up() {
  local s="$1" build_flag="${2:-}"
  local rp cname
  rp="$(dev_workspace_path_for "$s")"
  cname="$(container_name_for "$s")"
  dev_ensure_docker_network || return 1
  ssh "$SERVER" "
    set -euo pipefail
    cd '$rp'
    # dotenv is not shell syntax (values may hold ';', spaces, '\$'): compose reads it
    # via --env-file only. Sourcing it would export truncated values that then win
    # over --env-file during interpolation.
    if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC=docker-compose; fi
    \$DC -f docker-compose.workspace.yml --env-file ./.env.dev up -d $build_flag
    docker ps --filter name=$cname --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  "
}

dev_compose_restart() {
  local s="$1" rp
  rp="$(dev_workspace_path_for "$s")"
  ssh "$SERVER" "
    cd '$rp'
    if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC=docker-compose; fi
    \$DC -f docker-compose.workspace.yml --env-file ./.env.dev restart
  "
}

dev_write_workspace_manifest() {
  local s="$1" rp cname
  rp="$(dev_workspace_path_for "$s")"
  cname="$(container_name_for "$s")"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date)"
  ssh "$SERVER" "cat > '$rp/.geostat-deploy.json'" <<JSON
{"version":1,"module":"${GEOSTAT_MODULE_ID:-}","service":"${cname}","deployMode":"dev-bootstrap","kind":"workspace","environment":"dev","deployPath":"${rp}","updatedAt":"${ts}"}
JSON
}

# Watch roots relative to the module path: modules.<id>.dev.watchRoots, else
# the conventional single-project layout.
dev_watch_roots() {
  local declared=""
  [[ -n "${GEOSTAT_MODULE_ID:-}" ]] && declared="$(geostat_read_manifest_list "modules.${GEOSTAT_MODULE_ID}.dev.watchRoots")"
  if [[ -n "$declared" ]]; then
    printf '%s
' "$declared"
  else
    printf '%s
' src shared worker
  fi
}

# Polling watch (Git Bash / Linux) — debounced rsync + compose restart on source changes
dev_watch_poll() {
  local s="$1" debounce_ms="${2:-1500}" restart_java="${3:-1}"
  local debounce_sec
  debounce_sec="$(awk "BEGIN { printf \"%.2f\", ${debounce_ms}/1000 }" 2>/dev/null || echo "1.5")"
  local -a find_roots=()
  local declared_root
  while IFS= read -r declared_root; do
    [[ -n "$declared_root" ]] && find_roots+=("$PROJECT_DIR/$declared_root")
  done < <(dev_watch_roots)
  local busy=0

  echo ""
  echo "  dev watch: debounce ${debounce_ms}ms. Ctrl+C to stop."
  if [[ "$restart_java" -eq 1 ]]; then
    echo "  Changes → rsync + compose restart (--restart)."
  else
    echo "  Changes → rsync only (Spring DevTools reload in bootRun container)."
  fi
  echo ""

  while true; do
    local changed=0 root
    for root in "${find_roots[@]}"; do
      [[ -d "$root" ]] || continue
      if find "$root" -type f \( \
        -name '*.java' -o -name '*.kts' -o -name '*.yml' -o -name '*.yaml' -o -name '*.properties' \
        \) -mmin -0.05 2>/dev/null | grep -q .; then
        changed=1
        break
      fi
    done
    for root in "$PROJECT_DIR/build.gradle.kts" "$PROJECT_DIR/settings.gradle.kts"       "$PROJECT_DIR/build.gradle" "$PROJECT_DIR/settings.gradle"; do
      [[ -f "$root" ]] && find "$root" -mmin -0.05 2>/dev/null | grep -q . && changed=1
    done

    if [[ "$changed" -eq 1 && "$busy" -eq 0 ]]; then
      busy=1
      sleep "$debounce_sec"
      echo "  [watch] rsync..."
      dev_rsync_to_workspace "$s" || true
      if [[ "$restart_java" -eq 1 ]]; then
        echo "  [watch] restart..."
        dev_compose_restart "$s" || true
      fi
      sleep 2
      busy=0
    fi
    sleep 0.5
  done
}