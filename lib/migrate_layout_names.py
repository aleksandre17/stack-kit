"""Legacy flat dir names -> manifest compose service names (P6-migrate)."""
from __future__ import annotations

import json
import sys

from lib.compose_identity import load_deploy_env, resolve_module_service_name
from lib.modules import modules_by_role
from lib.project_context import ProjectContext

# Legacy flat folder names are project-specific (a consumer's pre-migration server
# layout), so they are NOT hardcoded here — they are read from the consumer manifest:
#
#   "migration": {
#     "legacyDirs": {
#       "api": ["geostat-chat-api"],
#       "ui":  ["geostat-chat-app", "geostat-chat-ai-fe"]
#     }
#   }
#
# A consumer with no prior server (greenfield) simply omits the block; both lists
# default to empty and the rename map carries only the deploy.env-derived overrides.
def _legacy_dirs(ctx: ProjectContext, role: str) -> frozenset[str]:
    """Project-declared legacy flat dir names for a role, from manifest.migration.legacyDirs."""
    migration = ctx.manifest.get("migration") or {}
    legacy = migration.get("legacyDirs") or {}
    names = legacy.get(role) or []
    return frozenset(str(n) for n in names if n)


def migration_rename_map(ctx: ProjectContext) -> dict[str, str]:
    deploy = load_deploy_env(ctx.secrets_root)
    repo = ctx.root.name
    out: dict[str, str] = {}

    api_ids = modules_by_role(ctx.manifest, "api")
    ui_ids = modules_by_role(ctx.manifest, "ui")

    if api_ids:
        api_target = resolve_module_service_name(api_ids[0], ctx.manifest, deploy, repo)
        for legacy in _legacy_dirs(ctx, "api"):
            out[legacy] = api_target
        legacy_api = deploy.get("COMPOSE_API_SERVICE")
        if legacy_api and legacy_api != api_target:
            out[str(legacy_api)] = api_target

    if ui_ids:
        ui_target = resolve_module_service_name(ui_ids[0], ctx.manifest, deploy, repo)
        for legacy in _legacy_dirs(ctx, "ui"):
            out[legacy] = ui_target
        legacy_app = deploy.get("COMPOSE_APP_SERVICE")
        if legacy_app and legacy_app != ui_target:
            out[str(legacy_app)] = ui_target

    return out


def _api_target(ctx: ProjectContext) -> str | None:
    deploy = load_deploy_env(ctx.secrets_root)
    api_ids = modules_by_role(ctx.manifest, "api")
    if not api_ids:
        return None
    return resolve_module_service_name(api_ids[0], ctx.manifest, deploy, ctx.root.name)


def _ui_target(ctx: ProjectContext) -> str | None:
    deploy = load_deploy_env(ctx.secrets_root)
    ui_ids = modules_by_role(ctx.manifest, "ui")
    if not ui_ids:
        return None
    return resolve_module_service_name(ui_ids[0], ctx.manifest, deploy, ctx.root.name)


def migration_source_dirs(ctx: ProjectContext, role: str) -> frozenset[str]:
    """Flat dir names on shared DEPLOY_PATH base that belong to this consumer only."""
    deploy = load_deploy_env(ctx.secrets_root)
    mapping = migration_rename_map(ctx)
    out: set[str] = set()

    if role == "api":
        target = _api_target(ctx)
        if not target:
            return frozenset()
        out.update(_legacy_dirs(ctx, "api"))
        out.update(k for k, v in mapping.items() if v == target)
        legacy = deploy.get("COMPOSE_API_SERVICE")
        if legacy:
            out.add(str(legacy))
        out.discard(target)
        return frozenset(out)

    if role == "ui":
        target = _ui_target(ctx)
        if not target:
            return frozenset()
        out.update(_legacy_dirs(ctx, "ui"))
        out.update(k for k, v in mapping.items() if v == target)
        legacy = deploy.get("COMPOSE_APP_SERVICE")
        if legacy:
            out.add(str(legacy))
        out.discard(target)
        return frozenset(out)

    return frozenset()


def pairs_arg(mapping: dict[str, str]) -> str:
    items = [f"{old}:{new}" for old, new in sorted(mapping.items()) if old and new and old != new]
    return ",".join(items)


def pairs_arg_for_role(mapping: dict[str, str], ctx: ProjectContext, role: str) -> str:
    if role == "api":
        target = _api_target(ctx)
    elif role == "ui":
        target = _ui_target(ctx)
    else:
        return ""
    if not target:
        return ""
    items = [
        f"{old}:{new}"
        for old, new in sorted(mapping.items())
        if old and new and old != new and new == target
    ]
    return ",".join(items)


def sources_arg(names: frozenset[str]) -> str:
    return ",".join(sorted(names))


def main() -> int:
    ctx = ProjectContext.discover()
    mapping = migration_rename_map(ctx)
    if "--json" in sys.argv:
        print(json.dumps(mapping, indent=2, sort_keys=True))
    elif "--pairs-api" in sys.argv:
        print(pairs_arg_for_role(mapping, ctx, "api"))
    elif "--pairs-ui" in sys.argv:
        print(pairs_arg_for_role(mapping, ctx, "ui"))
    elif "--sources-api" in sys.argv:
        print(sources_arg(migration_source_dirs(ctx, "api")))
    elif "--sources-ui" in sys.argv:
        print(sources_arg(migration_source_dirs(ctx, "ui")))
    elif "--pairs" in sys.argv:
        print(pairs_arg(mapping))
    else:
        for old, new in sorted(mapping.items()):
            if old != new:
                print(f"{old}={new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
