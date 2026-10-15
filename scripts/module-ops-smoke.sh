#!/usr/bin/env bash
# Local ops smoke — manifest module paths (api role), no fixed module names
set -euo pipefail
PKG="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${PKG}${PYTHONPATH:+:$PYTHONPATH}"
export STACK_KIT_KIT_ROOT="$PKG"
if [[ -z "${STACK_KIT_PROJECT_ROOT:-}" ]]; then
  export STACK_KIT_PROJECT_ROOT="$(cd "$PKG/../.." && pwd)"
fi

PYBIN=""
for c in python python3 py; do
  if command -v "$c" &>/dev/null; then
    if [[ "$c" == py ]]; then PYBIN="py -3"; else PYBIN="$c"; fi
    break
  fi
done
[[ -n "$PYBIN" ]] || { echo "FAIL: python not found"; exit 1; }
$PYBIN - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.deploy_paths import resolve_backend_deploy_path
from lib.modules import module_by_role
from lib.project_context import ProjectContext

ctx = ProjectContext.discover()
api_id = module_by_role(ctx.manifest, "api", 0)
if not api_id:
    raise SystemExit("FAIL: no modules.*.role=api in stack-kit.json")
deploy = ctx.secrets_module_dir(api_id) / ".env.deploy"
if not deploy.is_file():
    raise SystemExit(f"FAIL: missing {deploy}")
if "DEPLOY_LAYOUT=structured" not in deploy.read_text(encoding="utf-8"):
    raise SystemExit("FAIL: DEPLOY_LAYOUT=structured required")
names = ctx.compose_service_names()
api = names["api"]
base = "/home/example/my-app/" + ctx.module_path(api_id).name
assert "runtime" in resolve_backend_deploy_path(
    base=base, container_name=api, kind="runtime", layout="structured"
)
assert "workspace" in resolve_backend_deploy_path(
    base=base, container_name=api, kind="workspace", layout="structured"
)
print(f"  OK module={api_id} paths + deploy resolution")
PY

cd "$PKG"
$PYBIN -m pytest tests/ -q --tb=line -k "deploy or module or manifest" 2>/dev/null \
  || $PYBIN -m pytest tests/ -q --tb=line

echo ""
echo "  Module ops smoke passed (local)."
echo ""
