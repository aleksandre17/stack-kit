#!/bin/bash
# Step 4: Generate per-service compose on server

deploy_step_server_compose() {
  deploy_log "  [4/5] Generating compose files..."
  scp "$PROJECT_DIR/$COMPOSE_FILE" "$SERVER:/tmp/compose-src.yml" >/dev/null 2>&1
  local gen
  gen="$(geostat_kit_package_root)/toolkit/bash/gen_server_compose.py"
  scp "$gen" "$SERVER:/tmp/gen_server_compose.py" >/dev/null 2>&1

  local s rp
  for s in "${SERVICES[@]}"; do
    [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue
    rp=$(remote_path_for_service "$s")
    ssh -n "$SERVER" "mkdir -p '$rp/logs'"
    ssh "$SERVER" "python3 /tmp/gen_server_compose.py \
      --src /tmp/compose-src.yml \
      --service '$s' \
      --environment '${ENVIRONMENT}' \
      --build-layout '${SERVER_BUILD_LAYOUT:-jar}' \
      --out '$rp/docker-compose.${ENVIRONMENT}.yml'" \
      2>&1 | ssh "$SERVER" "tee -a '$rp/logs/compose.log'" || true
  done

  ssh "$SERVER" "python3 -" <<PYEOF >/dev/null 2>&1
import yaml, subprocess
with open('/tmp/compose-src.yml') as f:
    src = yaml.safe_load(f)
for n in src.get('networks', {}).keys():
    r = subprocess.run(['docker', 'network', 'create', n], capture_output=True)
    print(f'  [net] {"created" if r.returncode==0 else "exists"}: {n}')
PYEOF
  ssh -n "$SERVER" "rm -f /tmp/compose-src.yml /tmp/gen_server_compose.py"
  deploy_log "  [OK]   Compose files ready"
}
