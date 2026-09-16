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
)

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

dev_rsync_to_workspace() {
  local s="$1" rp rsync_exe src exclude
  rp="$(dev_workspace_path_for "$s")"
  rsync_exe="$(dev_rsync_executable)" || {
    echo "  ERROR: rsync not found (install Git for Windows)" >&2
    return 1
  }

  src="$(dev_to_rsync_path "$PROJECT_DIR")"
  ssh -n "$SERVER" "mkdir -p '$rp'" || return 1

  local -a args=(-avz --delete)
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

  ssh -n "$SERVER" "cat > '$rp/docker-compose.workspace.yml'" <<YML
services:
  ${s}:
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
    env_file:
      - .env.dev
    environment:
      SPRING_PROFILES_ACTIVE: dev
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
    set -a && source ./.env.dev && set +a
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
  ssh -n "$SERVER" "cat > '$rp/.geostat-deploy.json'" <<JSON
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