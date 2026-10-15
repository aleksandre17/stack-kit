#!/bin/bash
# Step 3: SCP artifacts to server

upload_service() {
  local s="$1"
  local rp srv_log dockerfile_src jar_src cred_base f
  rp=$(remote_path_for_service "$s")
  srv_log="$rp/logs"

  ssh -n "$SERVER" "mkdir -p '$rp/logs' '$rp/versions'"

  dockerfile_src="$(module_dockerfile "$s")"
  jar_src="$(module_jar_dest "$s")"
  cred_base="$(module_project_dir "$s")"
  if [[ "$cred_base" == "$PROJECT_DIR" ]]; then
    cred_base="$SECRETS_DIR"
  fi

  {
    echo "=== Upload [$s] $(date) ==="
    scp "$dockerfile_src" "$SERVER:$rp/Dockerfile" 2>&1
    scp "$jar_src" "$SERVER:$rp/app.jar" 2>&1
    scp "$SECRETS_DIR/$ENV_FILE" "$SERVER:$rp/$ENV_FILE" 2>&1
  } | ssh "$SERVER" "cat >> '$srv_log'/upload.log"

  local prefix="${OPS_BUILD_TMP_PREFIX:-ops-build}"
  if [ -f "/tmp/${prefix}-$s.log" ]; then
    scp "/tmp/${prefix}-$s.log" "$SERVER:$srv_log/build.log" >/dev/null 2>&1
    rm -f "/tmp/${prefix}-$s.log"
  fi

  if [ "$ENVIRONMENT" = "prod" ]; then
    ssh -n "$SERVER" "
      cp '$rp'/app.jar '$rp'/versions/app-$DEPLOY_VERSION.jar
      ls -t '$rp'/versions/app-*.jar 2>/dev/null | tail -n +$((VERSIONS_KEEP+1)) | xargs rm -f
    "
  fi

  local cred_file
  while IFS=$'\t' read -r cred_file _mount _ev; do
    [[ -n "$cred_file" ]] || continue
    f="$SECRETS_DIR/$cred_file"
    if [[ -f "$f" ]]; then
      scp "$f" "$SERVER:$rp/$(basename "$cred_file")" 2>/dev/null
      echo "  [cred] $(basename "$cred_file") (manifest)"
    fi
  done < <(stack_kit_module_credentials_lines "$s")

  for pattern in $CRED_PATTERNS; do
    for f in "$cred_base/"$pattern; do
      [ -f "$f" ] || continue
      scp "$f" "$SERVER:$rp/" 2>/dev/null
      echo "  [cred] $(basename "$f")"
    done
  done

  deploy_log "  [OK]   $s uploaded → $rp  (version: $DEPLOY_VERSION)"
}

deploy_step_upload() {
  deploy_log "  [3/5] Uploading..."
  local s
  for s in "${SERVICES[@]}"; do
    [ "$SERVICE" != "all" ] && [ "$SERVICE" != "$s" ] && continue
    is_deployable_service "$s" || continue
    upload_service "$s"
  done
}
