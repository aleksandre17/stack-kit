#!/bin/bash
# Step 4 (node-api): docker compose up --build, health-gate, image rollback, info.log.
# Same lifecycle as java-boot docker-up.sh (build artifact -> up -d -> health-gate ->
# rollback on failure), but rollback restores the previous IMAGE tag instead of app.jar
# (node-api builds its image server-side; there is no uploaded jar to swap).
#
# Requires: SERVER, ENVIRONMENT, ENV_FILE, HEALTH_RETRIES, DEPLOY_VERSION.

node_docker_up() {
  local s="$1"
  local rp srv_log container healthy status running i
  rp=$(remote_path_for_service "$s")
  srv_log="$rp/logs"
  container="$(container_name_for "$s")"

  ssh -n "$SERVER" "mkdir -p '$rp/logs'"
  ssh "$SERVER" "
    echo '=== Deploy [$container] \$(date) ===' >> '$srv_log'/deploy.log
    cd '$rp'
    if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC=docker-compose; fi
    \$DC -f docker-compose.${ENVIRONMENT}.yml --env-file ./$ENV_FILE up --build -d 2>&1 | tee -a '$srv_log'/deploy.log
  "

  deploy_log "  ... waiting for $container to become healthy"
  healthy=0
  for i in $(seq 1 "$HEALTH_RETRIES"); do
    status=$(ssh -n "$SERVER" \
      "docker inspect --format='{{.State.Health.Status}}' $container 2>/dev/null || echo no-healthcheck")
    case "$status" in
      healthy)
        deploy_log "  [OK]   $container healthy"
        healthy=1
        break
        ;;
      unhealthy)
        deploy_log "  [FAIL] $container unhealthy after $((i * 10))s"
        break
        ;;
      no-healthcheck)
        running=$(ssh -n "$SERVER" "docker inspect --format='{{.State.Running}}' $container 2>/dev/null")
        if [ "$running" = "true" ]; then
          deploy_log "  [OK]   $container running (no healthcheck — add HEALTHCHECK on /health)"
          healthy=1
        else
          deploy_log "  [FAIL] $container is not running"
        fi
        break
        ;;
      *)
        echo "  ... $container starting ($((i * 10))s / $((HEALTH_RETRIES * 10))s)"
        sleep 10
        ;;
    esac
  done

  if [ "$healthy" = "0" ] && [ "$ENVIRONMENT" = "prod" ]; then
    local has_prev
    has_prev=$(ssh -n "$SERVER" "docker image inspect '${container}:previous' >/dev/null 2>&1 && echo yes || echo no")
    if [ "$has_prev" = "yes" ]; then
      deploy_log "  [ROLLBACK] $container → restoring previous image..."
      ssh "$SERVER" "
        set -e
        cd '$rp'
        if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC=docker-compose; fi
        \$DC -f docker-compose.${ENVIRONMENT}.yml --env-file ./$ENV_FILE down 2>/dev/null || true
        cur=\$(docker inspect --format='{{.Config.Image}}' '$container' 2>/dev/null || echo '${container}:latest')
        docker tag '${container}:previous' \"\$cur\" 2>/dev/null || true
        \$DC -f docker-compose.${ENVIRONMENT}.yml --env-file ./$ENV_FILE up -d 2>&1 | tee -a '$srv_log'/deploy.log
      "
      deploy_log "  [ROLLBACK] $container restored to previous image"
    else
      deploy_log "  [WARN] $container — no previous image to roll back to"
    fi
  fi

  ssh -n "$SERVER" "docker ps --filter name=$container --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
  # shellcheck disable=SC2016
  ssh -n "$SERVER" "f='$rp/info.log'; ctr='$container';
    c_status=\$(docker inspect --format='{{.State.Status}}' \"\$ctr\" 2>/dev/null || echo unknown);
    c_health=\$(docker inspect --format='{{.State.Health.Status}}' \"\$ctr\" 2>/dev/null);
    [ -z \"\$c_health\" ] && c_health='no healthcheck';
    img=\$(docker inspect --format='{{.Config.Image}}' \"\$ctr\" 2>/dev/null || echo unknown);
    { echo 'Application Info — $container'; echo \"Environment: $ENVIRONMENT\"; echo \"Deploy version: $DEPLOY_VERSION\";
      echo \"Deploy path: $rp\"; echo \"Status: \$c_status\"; echo \"Health: \$c_health\"; echo \"Image: \$img\"; } > \"\$f\""
}

deploy_step_node_docker_up() {
  deploy_log "  [4/4] Starting containers..."
  local s
  TO_START=()
  for s in "${SERVICES[@]}"; do
    [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue
    TO_START+=("$s")
  done
  for s in "${TO_START[@]}"; do node_docker_up "$s"; done
}
