#!/bin/bash
# Step 1 (node-api): local pnpm build verify — mirror of gradle-build.sh deploy_step_build.
#
# The node-api production image (multi-stage Dockerfile) compiles tsc -> dist INSIDE the
# image at `compose up --build` time, so this host build is a fail-fast compile check
# (and warms dist/ for local run), not the artifact source. It is skipped on --no-build.
#
# Requires: SERVICES, SERVICE, SKIP_BUILD, NODE_WORKSPACE_DIR, NODE_PKG_FILTER.
#
# Build ordering is DECLARED, never privileged: a consumer whose module depends on other
# workspace packages being built first declares them, in order, as
#   modules.<id>.node.prebuildScripts: ["<workspace-script>", ...]     (default [])
# resolved by the driver into NODE_PREBUILD_SCRIPTS (newline-separated). Each is run as
# `pnpm run <script>` from NODE_WORKSPACE_DIR, in declaration order, before the module
# package build. Absent/empty → nothing runs and the output is identical to a plain build.

deploy_step_build() {
  if [ "$SKIP_BUILD" = "1" ]; then
    deploy_log "  [1/4] Build skipped (--no-build) — server image build will compile"
    return 0
  fi
  deploy_log "  [1/4] Building (pnpm, workspace: $NODE_WORKSPACE_DIR)..."

  local prefix local_build_log
  prefix="${OPS_BUILD_TMP_PREFIX:-ops-build}"
  local_build_log="/tmp/${prefix}-${STACK_KIT_MODULE_ID}.log"
  { echo "=== node-api build [$NODE_PKG_FILTER] $(date) ==="; } >"$local_build_log"

  if ! command -v pnpm >/dev/null 2>&1; then
    deploy_log "  [WARN] pnpm not on PATH locally — skipping host build (server image build still compiles)"
    return 0
  fi

  # Declared prebuild scripts, in order, before the module package build.
  local script
  while IFS= read -r script; do
    [ -n "$script" ] || continue
    if ! (cd "$NODE_WORKSPACE_DIR" && pnpm run 2>/dev/null | grep -q "^  ${script}\$"); then
      deploy_log "  [FAIL] prebuild script not defined in workspace: $script"
      return 1
    fi
    deploy_log "    prebuild: pnpm run $script"
    if ! (cd "$NODE_WORKSPACE_DIR" && pnpm run "$script") 2>&1 | tee -a "$local_build_log"; then
      deploy_log "  [FAIL] prebuild failed: $script"
      return 1
    fi
  done <<<"${NODE_PREBUILD_SCRIPTS:-}"

  deploy_log "    api: pnpm --filter ${NODE_PKG_FILTER} build"
  if ! (cd "$NODE_WORKSPACE_DIR" && pnpm --filter "$NODE_PKG_FILTER" build) 2>&1 | tee -a "$local_build_log"; then
    deploy_log "  [FAIL] Build failed: $NODE_PKG_FILTER"
    return 1
  fi
  deploy_log "  [OK]   Build: $NODE_PKG_FILTER"
}
