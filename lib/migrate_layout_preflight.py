"""P6-migrate preflight — structured deploy targets from manifest (no SSH)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib.compose_identity import compose_service_names, load_deploy_env, resolve_module_service_name
from lib.deploy_paths import resolve_backend_deploy_path, resolve_module_deploy_path
from lib.modules import driver_deploy_kind, modules_by_role
from lib.project_context import ProjectContext


def _read_deploy_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def check_structured_layout(ctx: ProjectContext) -> list[str]:
    issues: list[str] = []
    for role in ("api", "ui"):
        ids = modules_by_role(ctx.manifest, role)
        if not ids:
            continue
        mid = ids[0]
        deploy_file = ctx.secrets_module_dir(mid) / ".env.deploy"
        if not deploy_file.is_file():
            issues.append(f"{mid}: missing {deploy_file.relative_to(ctx.root)}")
            continue
        vals = _read_deploy_file(deploy_file)
        if vals.get("DEPLOY_LAYOUT") != "structured":
            issues.append(f"{mid}: DEPLOY_LAYOUT must be structured in {deploy_file.name}")
        if not vals.get("DEPLOY_PATH"):
            issues.append(f"{mid}: DEPLOY_PATH missing in {deploy_file.name}")
    return issues


def migration_targets(ctx: ProjectContext) -> list[dict[str, str]]:
    deploy = load_deploy_env(ctx.secrets_root)
    repo = ctx.root.name
    rows: list[dict[str, str]] = []
    for mid in ctx.list_module_ids():
        cfg = (ctx.manifest.get("modules") or {}).get(mid) or {}
        if not isinstance(cfg, dict):
            continue
        role = str(cfg.get("role") or "")
        typ = str(cfg.get("type") or "")
        secrets = ctx.secrets_module_dir(mid)
        dep = _read_deploy_file(secrets / ".env.deploy")
        base = dep.get("DEPLOY_PATH") or ""
        if not base:
            continue
        svc = resolve_module_service_name(mid, ctx.manifest, deploy, repo)
        layout = dep.get("DEPLOY_LAYOUT") or "flat"
        path_mode = dep.get("DEPLOY_PATH_MODE") or "base"
        # Which deploy artefact this module produces: the module's ROLE, or the
        # kind its DRIVER declares. No driver is named here.
        declared_kind = driver_deploy_kind(typ)
        if role == "api" or declared_kind == "runtime":
            target = resolve_backend_deploy_path(
                base=base,
                container_name=svc,
                kind="runtime",
                layout=layout,
                path_mode=path_mode,
            )
            kind = "runtime"
        elif role == "ui" or declared_kind == "static":
            target = resolve_module_deploy_path(
                base=base,
                container_name=svc,
                kind="static",
                layout=layout,
                path_mode=path_mode,
            )
            kind = "static"
        else:
            continue
        rows.append(
            {
                "module": mid,
                "role": role or typ,
                "service": svc,
                "kind": kind,
                "target": target,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P6-migrate preflight (structured paths)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    ctx = ProjectContext.discover()
    issues = check_structured_layout(ctx)
    rows = migration_targets(ctx)

    if args.json:
        print(json.dumps({"issues": issues, "targets": rows}, indent=2))
    else:
        print("[p6-migrate] structured deploy targets")
        for row in rows:
            print(f"  {row['module']} ({row['role']}) -> {row['kind']}/{row['service']}")
            print(f"    {row['target']}")
        names = compose_service_names(ctx.manifest, load_deploy_env(ctx.secrets_root), ctx.root.name)
        print(
            "[p6-migrate] compose:",
            f"api={names['api']}",
            f"app={names['app']}",
            f"worker={names.get('worker')}",
        )
        print("[p6-migrate] modules:", names.get("modules"))
        if issues:
            print("[p6-migrate] issues:", file=sys.stderr)
            for msg in issues:
                print(f"  - {msg}", file=sys.stderr)

    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
