# Portable ops toolkit (Bash) — sourced from java-boot driver _init.sh
# Requires: OPS_SCRIPT_DIR (= module root), OPS_SECRETS_MODULE, PROJECT_DIR, MONOREPO

: "${OPS_SCRIPT_DIR:?OPS_SCRIPT_DIR not set}"
: "${OPS_SECRETS_MODULE:?OPS_SECRETS_MODULE not set}"

SECRETS_DIR="$(stack_kit_secrets_module_dir "$OPS_SECRETS_MODULE")"
OPS_LOG_DIR="${OPS_SCRIPT_DIR}/logs"
mkdir -p "$OPS_LOG_DIR"

SERVER="$(stack_kit_env_value "$OPS_SECRETS_MODULE" DEPLOY_SERVER "$(stack_kit_deploy_env_value DEPLOY_SERVER "")")"
PROJECT="$(stack_kit_env_value "$OPS_SECRETS_MODULE" DEPLOY_PROJECT "")"
[[ -n "$PROJECT" ]] || PROJECT="${OPS_PROJECT_NAME:-}"
[[ -n "$PROJECT" ]] || PROJECT="$(stack_kit_project_slug)"
SERVER_BASE="$(stack_kit_env_value "$OPS_SECRETS_MODULE" DEPLOY_SERVER_BASE "$(stack_kit_server_base)")"
OPS_BUILD_TMP_PREFIX="$(stack_kit_deploy_env_value OPS_BUILD_TMP_PREFIX "ops-build")"
DOCKER_NETWORK="$(stack_kit_docker_network)"

# Optional module overrides (ops.config.sh)
# The compose project a deploy runs under: `{project}-{environment}` on a declared target (one
# project's environments never share containers, networks or volumes); compose's default without one.
COMPOSE_PROJECT="$(_stack_kit_resolve compose-project "${ENVIRONMENT:-}" 2>/dev/null || true)"
# The releases a unit keeps: the target's `keep` (what `targets --verify` holds), else 5.
: "${VERSIONS_KEEP:=$(_stack_kit_resolve target-keep 2>/dev/null || echo 5)}"
: "${HEALTH_RETRIES:=24}"
: "${CRED_PATTERNS:=*.p12 *.jks *.keystore *.pem *.crt *credentials*.json *service-account*.json}"

# shellcheck source=../../lib/ssh.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/lib/ssh.sh"
stack_kit_ssh_maybe_alias
