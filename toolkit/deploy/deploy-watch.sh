#!/bin/bash
# Backend deploy watch — local Gradle bootJar loop → runtime/ on server (NOT be dev rsync)
# Source from deploy.sh when first arg is "watch", after common.sh + gradle/upload libs.

: "${PROJECT_DIR:?}"
: "${SERVER:?}"

DEPLOY_WATCH_DEBOUNCE_MS="${DEPLOY_WATCH_DEBOUNCE_MS:-8000}"
DEPLOY_WATCH_NO_INITIAL=0

deploy_watch_usage() {
  echo ""
  echo "  be deploy watch — Gradle build + upload app.jar + compose up --build on server"
  echo ""
  echo "  Usage: geostat be deploy watch [service] [--dev|--prod] [--debounce-ms N] [--no-initial]"
  echo ""
  echo "  Requires: prior be deploy (runtime/ + docker-compose on server)"
  echo "  NOT the same as: be dev watch (source rsync + bootRun in workspace/)"
  echo ""
}

deploy_watch_restart_runtime() {
  local s="$1" rp
  rp="$(remote_path_for_service "$s")"
  ssh "$SERVER" "
    set -euo pipefail
    cd '$rp'
    if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC=docker-compose; fi
    \$DC -f docker-compose.${ENVIRONMENT}.yml --env-file ./$ENV_FILE up -d --build
  "
}

deploy_watch_write_manifest() {
  local s="$1" rp cname ts
  rp="$(remote_path_for_service "$s")"
  cname="$(container_name_for "$s")"
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date)"
  ssh "$SERVER" "cat > '$rp/.geostat-deploy.json'" <<JSON
{"version":1,"module":"backend","service":"${cname}","deployMode":"deploy-watch","kind":"runtime","environment":"${ENVIRONMENT}","deployPath":"${rp}","updatedAt":"${ts}"}
JSON
}

deploy_watch_publish_service() {
  local s="$1" saved
  saved="$SERVICE"
  SERVICE="$s"

  deploy_log "  [watch] build → upload → up --build ($s)"
  if ! deploy_step_build; then
    SERVICE="$saved"
    return 1
  fi
  deploy_step_prepare_jars
  upload_service "$s"
  if ! deploy_watch_restart_runtime "$s"; then
    SERVICE="$saved"
    return 1
  fi
  deploy_watch_write_manifest "$s"
  SERVICE="$saved"
  deploy_log "  [watch] OK $s → $(remote_path_for_service "$s")"
  return 0
}

deploy_watch_assert_runtime_ready() {
  local s="$1" rp
  rp="$(remote_path_for_service "$s")"
  if ! ssh -n "$SERVER" "test -f '$rp/docker-compose.${ENVIRONMENT}.yml'" 2>/dev/null; then
    echo "  ERROR: $rp/docker-compose.${ENVIRONMENT}.yml missing" >&2
    echo "  Run once: geostat be deploy $s --$ENVIRONMENT" >&2
    return 1
  fi
  return 0
}

# Debounced poll (Git Bash / Linux) — same roots as be dev watch
deploy_watch_poll() {
  local debounce_ms="${1:-$DEPLOY_WATCH_DEBOUNCE_MS}"
  local debounce_sec
  debounce_sec="$(awk "BEGIN { printf \"%.2f\", ${debounce_ms}/1000 }" 2>/dev/null || echo "8")"
  local -a find_roots=("$PROJECT_DIR/src" "$PROJECT_DIR/shared" "$PROJECT_DIR/worker")
  local busy=0

  echo ""
  echo "  deploy watch: debounce ${debounce_ms}ms. Ctrl+C to stop."
  echo "  Each cycle: ./gradlew bootJar → scp app.jar → docker compose up --build"
  echo "  Remote dev (rsync only): geostat be dev watch"
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
    for root in "$PROJECT_DIR/build.gradle.kts" "$PROJECT_DIR/settings.gradle.kts"; do
      [[ -f "$root" ]] && find "$root" -mmin -0.05 2>/dev/null | grep -q . && changed=1
    done

    if [[ "$changed" -eq 1 && "$busy" -eq 0 ]]; then
      busy=1
      sleep "$debounce_sec"
      local s
      for s in "${WATCH_SERVICES[@]}"; do
        deploy_watch_publish_service "$s" || true
      done
      sleep 3
      busy=0
    fi
    sleep 0.5
  done
}

deploy_watch_main() {
  SERVICE=""
  ENVIRONMENT="${ENVIRONMENT:-dev}"
  SKIP_BUILD=0
  SKIP_CHECKS=1

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dev) ENVIRONMENT="dev"; shift ;;
      --prod) ENVIRONMENT="prod"; shift ;;
      --debounce-ms=*) DEPLOY_WATCH_DEBOUNCE_MS="${1#*=}"; shift ;;
      --debounce-ms) shift; DEPLOY_WATCH_DEBOUNCE_MS="${1:-8000}"; shift ;;
      --no-initial) DEPLOY_WATCH_NO_INITIAL=1; shift ;;
      all) SERVICE="all"; shift ;;
      help|-h|--help) deploy_watch_usage; return 0 ;;
      -*) echo "  Unknown option: $1" >&2; return 1 ;;
      *)
        [[ -z "$SERVICE" ]] && SERVICE="$1"
        shift
        ;;
    esac
  done

  COMPOSE_FILE="docker-compose.${ENVIRONMENT}.yml"
  ENV_FILE=".env.${ENVIRONMENT}"
  cd "$PROJECT_DIR" || return 1

  discover_services
  deploy_path_load_config
  deploy_resolve_gradle_modules 0

  if [[ -z "$SERVICE" ]]; then
    if [[ ${#SERVICES[@]} -eq 1 ]]; then
      SERVICE="${SERVICES[0]}"
    else
      echo ""
      echo "  deploy watch — select service:"
      local_i=1
      for s in "${SERVICES[@]}"; do echo "     $((local_i++))) $s"; done
      echo "     $local_i) all"
      read -rp "  Service: " choice
      if [[ "$choice" == "$local_i" ]]; then SERVICE="all"
      else SERVICE="${SERVICES[$((choice - 1))]}"; fi
    fi
  fi
  [[ -n "$SERVICE" ]] || SERVICE="all"

  WATCH_SERVICES=()
  local s
  for s in "${SERVICES[@]}"; do
    [[ "$SERVICE" == "all" || "$SERVICE" == "$s" ]] || continue
    is_deployable_service "$s" || continue
    deploy_watch_assert_runtime_ready "$s" || return 1
    WATCH_SERVICES+=("$s")
  done

  if [[ ${#WATCH_SERVICES[@]} -eq 0 ]]; then
    echo "  ERROR: no deployable services for watch" >&2
    return 1
  fi

  DEPLOY_VERSION="$(date +%Y%m%d-%H%M%S)"
  echo ""
  echo "  deploy watch [$SERVICE] — $ENVIRONMENT → runtime/"
  for s in "${WATCH_SERVICES[@]}"; do
    echo "    $s → $(remote_path_for_service "$s")"
  done
  echo ""

  if [[ "$DEPLOY_WATCH_NO_INITIAL" -eq 0 ]]; then
    for s in "${WATCH_SERVICES[@]}"; do
      deploy_watch_publish_service "$s" || return 1
    done
  fi

  deploy_watch_poll "$DEPLOY_WATCH_DEBOUNCE_MS"
}
