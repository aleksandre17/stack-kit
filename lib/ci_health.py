"""Manifest-driven CI health targets (stack composeModules + stack-catalog roles)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from lib.modules import driver_health, module_driver_type, module_health_path
from lib.project_context import ProjectContext
from lib.stack_endpoints import (
    load_stack_catalog,
    resolve_module_port,
    _parse_env_files,
    _secrets_env_files,
)


@dataclass(frozen=True)
class HealthTarget:
    module_id: str
    role: str
    url: str
    expect: str  # empty = HTTP status only; otherwise grep substring


def _stack_module_filter(ctx: ProjectContext) -> set[str] | None:
    stack = ctx.manifest.get("stack") or {}
    ci = ctx.manifest.get("ci") or {}
    if isinstance(ci, dict):
        explicit = ci.get("healthModules")
        if explicit is not None:
            return {str(m) for m in explicit}
    compose_modules = stack.get("composeModules")
    if compose_modules is not None:
        return {str(m) for m in compose_modules}
    return None


def _health_expect(role_cfg: dict[str, Any], driver_type: str = "") -> str:
    if role_cfg.get("ciHealth") is False:
        return ""
    if driver_health(driver_type).get("expect") == "status":  # the driver's own judgement wins over the role's
        return ""
    expect = role_cfg.get("healthExpect")
    if expect is None:
        return "UP"
    return str(expect)


def stack_health_targets(
    ctx: ProjectContext,
    *,
    catalog: dict[str, Any] | None = None,
    host: str = "127.0.0.1",
    env_loader: Callable[[str], dict[str, str]] | None = None,
) -> list[HealthTarget]:
    """
    One health probe per manifest module in stack.composeModules (or ci.healthModules)
    that has a catalog role with ciHealth != false.
    """
    cat = catalog if catalog is not None else load_stack_catalog(
        ctx.package_root / "compose" / "stack-catalog.json"
    )
    roles_cfg: dict[str, Any] = cat.get("roles") or {}
    allowed = _stack_module_filter(ctx)

    def load_env(secrets_folder: str) -> dict[str, str]:
        if env_loader:
            return env_loader(secrets_folder)
        return _parse_env_files(_secrets_env_files(ctx.secrets_folder_path(secrets_folder)))

    targets: list[HealthTarget] = []
    for module_id in ctx.list_module_ids():
        if allowed is not None and module_id not in allowed:
            continue
        role = ctx.get_module_role(module_id)
        role_cfg = roles_cfg.get(role)
        if not role_cfg:
            continue
        if role_cfg.get("ciHealth") is False:
            continue
        expect = _health_expect(role_cfg, module_driver_type(ctx.manifest, module_id))
        secrets_folder = ctx.secrets_module_folder(module_id)
        port = resolve_module_port(
            role=role,
            role_cfg=role_cfg,
            secrets_folder=secrets_folder,
            env=load_env(secrets_folder),
        )
        if not port:
            continue
        url_path = module_health_path(ctx.manifest, module_id) or str(role_cfg.get("urlPath") or "/health")
        path = url_path if url_path.startswith("/") else f"/{url_path}"
        if path == "/":
            url = f"http://{host}:{port}"
        else:
            url = f"http://{host}:{port}{path}"
        targets.append(
            HealthTarget(module_id=module_id, role=role, url=url, expect=expect)
        )
    return targets
