#!/bin/bash
# Step 5: docker compose up, health, rollback, info.log

docker_up() {
  local s="$1"
  local rp srv_log container healthy status running prev_jar i
  rp=$(remote_path_for_service "$s")
  srv_log="$rp/logs"
  container="$(container_name_for "$s")"

  ssh -n "$SERVER" "mkdir -p '$rp/logs'"
  ssh "$SERVER" "
    echo '=== Deploy [$container] \$(date) ===' >> '$srv_log'/deploy.log
    cd '$rp'
    if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC=docker-compose; fi
    IMAGE_REVISION='${IMAGE_REVISION:-}' \$DC ${COMPOSE_PROJECT:+-p '$COMPOSE_PROJECT'} -f docker-compose.${ENVIRONMENT}.yml --env-file ./$ENV_FILE up --build -d 2>&1 | tee -a '$srv_log'/deploy.log
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
          deploy_log "  [OK]   $container running (no healthcheck)"
          healthy=1
        else
          deploy_log "  [FAIL] $container container is not running"
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
    prev_jar=$(ssh -n "$SERVER" "ls -t '$rp'/versions/app-*.jar 2>/dev/null | sed -n '2p'")
    if [ -n "$prev_jar" ]; then
      deploy_log "  [ROLLBACK] $container → restoring $(basename "$prev_jar")..."
      ssh "$SERVER" "
        set -e
        cp '$prev_jar' '$rp'/app.jar
        cd '$rp'
        if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC=docker-compose; fi
        IMAGE_REVISION='${IMAGE_REVISION:-}' \$DC ${COMPOSE_PROJECT:+-p '$COMPOSE_PROJECT'} -f docker-compose.${ENVIRONMENT}.yml --env-file ./$ENV_FILE up --build -d 2>&1 | tee -a '$srv_log'/deploy.log
      "
      deploy_log "  [ROLLBACK] $container restored"
    else
      deploy_log "  [WARN] $container — no previous version to roll back to"
    fi
  fi

  ssh -n "$SERVER" "docker ps --filter name=$container --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
  # shellcheck disable=SC2016
  ssh -n "$SERVER" "f='$rp/info.log'; ctr='$container';
    c_status=\$(docker inspect --format='{{.State.Status}}' \"\$ctr\" 2>/dev/null || echo unknown);
    c_health=\$(docker inspect --format='{{.State.Health.Status}}' \"\$ctr\" 2>/dev/null);
    [ -z \"\$c_health\" ] && c_health='no healthcheck';
    jar_size=\$(du -h '$rp/app.jar' 2>/dev/null | cut -f1 || echo unknown);
    { echo 'Application Info — $container'; echo \"Environment: $ENVIRONMENT\"; echo \"Deploy version: $DEPLOY_VERSION\";
      echo \"Deploy path: $rp\"; echo \"Status: \$c_status\"; echo \"Health: \$c_health\"; echo \"Jar: \$jar_size\"; } > \"\$f\""
}

deploy_step_docker_up() {
  deploy_log "  [5/5] Starting containers..."
  TO_START=()
  local s sc
  for s in "${SERVICES[@]}"; do
    [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue
    TO_START+=("$s")
  done
  if [ "${#TO_START[@]}" -gt 1 ] && [ $# -eq 0 ]; then
    echo ""
    echo "   Which containers to start?"
    local i
    for i in "${!TO_START[@]}"; do echo "     $((i + 1))) ${TO_START[$i]}"; done
    echo "     $((${#TO_START[@]} + 1))) all"
    echo "     0) none"
    read -rp "  Start [0-$((${#TO_START[@]} + 1))]: " sc
    if [ "$sc" = "0" ]; then TO_START=()
    elif [ "$sc" != "$((${#TO_START[@]} + 1))" ]; then
      TO_START=("${TO_START[$((sc - 1))]}")
    fi
  fi
  for s in "${TO_START[@]}"; do docker_up "$s"; done
}
