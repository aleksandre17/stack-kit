#!/usr/bin/env python3
"""CLI for PowerShell: module roles / lists (STACK_KIT_PROJECT_ROOT required)."""
from __future__ import annotations

import sys

from lib.project_context import ProjectContext


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    op = sys.argv[1]
    try:
        ctx = ProjectContext.discover()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    if op == "role" and len(sys.argv) >= 3:
        print(ctx.get_module_role(sys.argv[2]))
        return 0
    if op == "by-role" and len(sys.argv) >= 3:
        for mid in ctx.module_ids_for_role(sys.argv[2]):
            print(mid)
        return 0
    if op == "aliases":
        for k, v in sorted(ctx.cli_aliases().items()):
            print(f"{k}\t{v}")
        return 0
    if op == "stack-endpoints":
        from lib.stack_endpoints import stack_endpoint_lines

        for line in stack_endpoint_lines(ctx):
            print(line)
        return 0
    if op == "compose-service" and len(sys.argv) >= 3:
        from lib.compose_identity import load_deploy_env, resolve_module_service_name

        deploy = load_deploy_env(ctx.secrets_root)
        print(resolve_module_service_name(sys.argv[2], ctx.manifest, deploy, ctx.root.name))
        return 0
    if op == "compose-names":
        import json
        from lib.compose_identity import compose_service_names, load_deploy_env

        deploy = load_deploy_env(ctx.secrets_root)
        print(json.dumps(compose_service_names(ctx.manifest, deploy, ctx.root.name)))
        return 0
    if op == "stack-deploy-steps":
        from lib.driver_api import substitute_stack_args
        from lib.stack_deploy import stack_deploy_steps

        env = "prod"
        if len(sys.argv) >= 3 and sys.argv[2] in ("dev", "prod"):
            env = sys.argv[2]
        for step in stack_deploy_steps(ctx.manifest):
            mod = step["module"]
            cmd = step["command"]
            args = substitute_stack_args(step.get("args", []), env)
            print(f"{mod}\t{cmd}\t" + "\t".join(args))
        return 0
    if op == "stack-health":
        from lib.ci_health import stack_health_targets

        for target in stack_health_targets(ctx):
            expect = target.expect if target.expect else "-"
            print(f"{target.module_id}\t{target.url}\t{expect}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
