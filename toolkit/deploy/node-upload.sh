#!/bin/bash
# Step 3 (node-api): upload build context + Dockerfile + env to server runtime path.
# Mirror of upload.sh, minus the JAR. The node-api image is built server-side from the
# pnpm workspace (multi-stage Dockerfile), so we ship the workspace source (no node_modules/
# dist/.git) instead of an app.jar. The previously-running image is tagged :previous for
# rollback (image rollback replaces the JAR-version rollback in node-docker-up.sh).
#
# Requires: SERVICES, SERVICE, SERVER, ENVIRONMENT, ENV_FILE, DEPLOY_VERSION,
#           PROJECT_DIR, SECRETS_DIR, NODE_WORKSPACE_DIR (from _init.sh / deploy.sh).

# Declare the server-side build layout for gen_server_compose.py (server-compose.sh reads
# SERVER_BUILD_LAYOUT). node-api lands the pnpm workspace under $rp/context/ and the
# Dockerfile at $rp/Dockerfile, so the emitted build.context must be ./context with the
# Dockerfile resolved as ../Dockerfile. (java-boot uses the default 'jar' layout: context $rp.)
export SERVER_BUILD_LAYOUT="context-dir"

node_upload_service() {
  local s="$1"
  local rp srv_log dockerfile_src container f
  rp=$(remote_path_for_service "$s")
  srv_log="$rp/logs"
  container="$(container_name_for "$s")"

  ssh -n "$SERVER" "mkdir -p '$rp/logs' '$rp/context'"

  dockerfile_src="$(module_dockerfile "$s")"

  # Tag the currently-running image as :previous so node-docker-up can roll back.
  ssh -n "$SERVER" "
    img=\$(docker inspect --format='{{.Config.Image}}' '$container' 2>/dev/null || true)
    if [ -n \"\$img\" ]; then
      docker tag \"\$img\" '${container}:previous' 2>/dev/null || true
    fi
  " || true

  {
    echo "=== Upload [$s] $(date) ==="
    # Workspace build context (server image build needs the whole pnpm workspace).
    rsync -az --delete \
      --exclude '.git' --exclude 'node_modules' --exclude '**/node_modules' \
      --exclude 'dist' --exclude '**/dist' --exclude '.idea' --exclude '.vscode' \
      -e ssh "$NODE_WORKSPACE_DIR/" "$SERVER:$rp/context/" 2>&1
    scp "$dockerfile_src" "$SERVER:$rp/Dockerfile" 2>&1
    scp "$SECRETS_DIR/$ENV_FILE" "$SERVER:$rp/$ENV_FILE" 2>&1
  } | ssh "$SERVER" "cat >> '$srv_log'/upload.log"

  local prefix="${OPS_BUILD_TMP_PREFIX:-ops-build}"
  if [ -f "/tmp/${prefix}-${GEOSTAT_MODULE_ID}.log" ]; then
    scp "/tmp/${prefix}-${GEOSTAT_MODULE_ID}.log" "$SERVER:$srv_log/build.log" >/dev/null 2>&1
    rm -f "/tmp/${prefix}-${GEOSTAT_MODULE_ID}.log"
  fi

  # Manifest-declared credentials (same contract as java-boot upload.sh).
  local cred_file
  while IFS=$'\t' read -r cred_file _mount _ev; do
    [[ -n "$cred_file" ]] || continue
    f="$SECRETS_DIR/$cred_file"
    if [[ -f "$f" ]]; then
      scp "$f" "$SERVER:$rp/$(basename "$cred_file")" 2>/dev/null
      echo "  [cred] $(basename "$cred_file") (manifest)"
    fi
  done < <(geostat_module_credentials_lines "$s")

  for pattern in $CRED_PATTERNS; do
    for f in "$SECRETS_DIR/"$pattern; do
      [ -f "$f" ] || continue
      scp "$f" "$SERVER:$rp/" 2>/dev/null
      echo "  [cred] $(basename "$f")"
    done
  done

  deploy_log "  [OK]   $s uploaded → $rp  (version: $DEPLOY_VERSION)"
}

deploy_step_node_upload() {
  deploy_log "  [3/4] Uploading build context..."
  if ! command -v rsync >/dev/null 2>&1; then
    deploy_log "  [FAIL] rsync required to upload node workspace context"
    return 1
  fi
  local s
  for s in "${SERVICES[@]}"; do
    [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue
    is_deployable_service "$s" || continue
    node_upload_service "$s"
  done
}
