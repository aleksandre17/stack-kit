#!/bin/bash
# Node remote dev — rsync workspace + `pnpm dev` (tsx watch) in a dev container.
# Reuses the generic rsync / path / network / compose-up helpers from dev-remote.sh;
# overrides only the workspace compose generation, port/health, and the source-watch
# file globs that are stack-specific (Gradle/Spring -> pnpm/Node).
#
# Requires dev-remote.sh sourced first (for dev_rsync_to_workspace, dev_compose_up, …).

# Node service port var + default come from env.ts (PORT, default 3001) and /health.
node_dev_port_var()      { echo "PORT"; }
node_dev_default_port()  { echo "3001"; }
node_dev_health_path()   { echo "/health"; }

# Dockerfile used for the dev container. Prefer a dev-remote variant; fall back to the
# module Dockerfile (the app runs `pnpm dev` via the compose `command`).
node_dev_dockerfile_for() {
  local s="$1"
  if [[ -f "$PROJECT_DIR/Dockerfile.dev.remote" ]]; then
    echo "Dockerfile.dev.remote"
  else
    echo "Dockerfile"
  fi
}

# Override dev-remote.sh's gradle workspace compose with a node one.
dev_write_workspace_compose() {
  local s="$1" rp df port_var health_path cname def_port net run_script
  rp="$(dev_workspace_path_for "$s")"
  df="$(node_dev_dockerfile_for "$s")"
  port_var="$(node_dev_port_var)"
  health_path="$(node_dev_health_path)"
  cname="$(container_name_for "$s")"
  def_port="$(node_dev_default_port)"
  net="${DOCKER_NETWORK:-${PROJECT}-net}"
  run_script="${NODE_RUN_SCRIPT:-dev}"

  ssh -n "$SERVER" "cat > '$rp/docker-compose.workspace.yml'" <<YML
services:
  ${s}:
    image: ${cname}-workspace
    container_name: ${cname}
    build:
      context: .
      dockerfile: ${df}
    working_dir: /app
    command: ["pnpm", "run", "${run_script}"]
    ports:
      - "\${${port_var}:-${def_port}}:\${${port_var}:-${def_port}}"
    volumes:
      - .:/app
      - node_modules_${cname}:/app/node_modules
    env_file:
      - .env.dev
    environment:
      NODE_ENV: development
    networks:
      - ${net}
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:\${${port_var}:-${def_port}}${health_path} | grep -q ok || exit 1"]
      interval: 20s
      timeout: 5s
      retries: 8
      start_period: 60s

networks:
  ${net}:
    external: true

volumes:
  node_modules_${cname}:
YML
}

# Override the gradle/java watch globs with node source globs.
dev_watch_poll() {
  local s="$1" debounce_ms="${2:-1500}" restart="${3:-0}"
  local debounce_sec
  debounce_sec="$(awk "BEGIN { printf \"%.2f\", ${debounce_ms}/1000 }" 2>/dev/null || echo "1.5")"
  local -a find_roots=("$PROJECT_DIR/src" "$PROJECT_DIR/scripts")
  local busy=0

  echo ""
  echo "  dev watch (node): debounce ${debounce_ms}ms. Ctrl+C to stop."
  if [[ "$restart" -eq 1 ]]; then
    echo "  Changes → rsync + compose restart."
  else
    echo "  Changes → rsync only (tsx watch reloads in the container)."
  fi
  echo ""

  while true; do
    local changed=0 root
    for root in "${find_roots[@]}"; do
      [[ -d "$root" ]] || continue
      if find "$root" -type f \( \
        -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.json' -o -name '*.yml' -o -name '*.yaml' \
        \) -mmin -0.05 2>/dev/null | grep -q .; then
        changed=1
        break
      fi
    done
    if [[ "$changed" -eq 1 && "$busy" -eq 0 ]]; then
      busy=1
      sleep "$debounce_sec"
      echo "  [watch] rsync..."
      dev_rsync_to_workspace "$s" || true
      if [[ "$restart" -eq 1 ]]; then
        echo "  [watch] restart..."
        dev_compose_restart "$s" || true
      fi
      sleep 2
      busy=0
    fi
    sleep 0.5
  done
}
