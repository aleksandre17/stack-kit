"""Manifest-driven stack local endpoint lines (compose up hints)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from lib import envfile
from lib.project_context import ProjectContext

def load_stack_catalog(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"roles": {}, "roleOrder": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_env_files(paths: list[Path]) -> dict[str, str]:
    return envfile.merged(paths)


def _secrets_env_files(secrets_dir: Path) -> list[Path]:
    return envfile.folder_files(secrets_dir.parent, secrets_dir.name)


def _module_port_env_keys(
    role_cfg: dict[str, Any],
    secrets_folder: str,
) -> list[str]:
    keys: list[str] = [str(k) for k in (role_cfg.get("portEnv") or [])]
    slug = secrets_folder.upper().replace("-", "_")
    extra = f"{slug}_PORT"
    if extra not in keys:
        keys.append(extra)
    return keys


def resolve_module_port(
    *,
    role: str,
    role_cfg: dict[str, Any],
    secrets_folder: str,
    env: dict[str, str],
) -> str:
    slug_key = f"{secrets_folder.upper().replace('-', '_')}_PORT"
    if env.get(slug_key):
        return env[slug_key]
    for key in _module_port_env_keys(role_cfg, secrets_folder):
        if env.get(key):
            return env[key]
    return str(role_cfg.get("defaultPort") or "")


def format_endpoint_line(
    *,
    module_id: str,
    role: str,
    port: str,
    url_path: str,
) -> str:
    path = url_path if url_path.startswith("/") else f"/{url_path}"
    if path == "/":
        url = f"http://localhost:{port}"
    else:
        url = f"http://localhost:{port}{path}"
    return f"{role:<4} ({module_id}) -> {url}"


def stack_endpoint_lines(
    ctx: ProjectContext,
    *,
    catalog: dict[str, Any] | None = None,
    env_loader: Callable[[str], dict[str, str]] | None = None,
) -> list[str]:
    """
    One line per manifest module with a catalog role.
    Optional manifest filter: stack.modules (module ids).
    """
    cat = catalog if catalog is not None else load_stack_catalog(
        ctx.package_root / "compose" / "stack-catalog.json"
    )
    roles_cfg: dict[str, Any] = cat.get("roles") or {}
    order: list[str] = list(cat.get("roleOrder") or [])
    for r in roles_cfg:
        if r not in order:
            order.append(r)

    stack = ctx.manifest.get("stack") or {}
    module_filter = stack.get("modules")
    if module_filter is not None:
        allowed = {str(m) for m in module_filter}
    else:
        allowed = None

    def load_env(secrets_folder: str) -> dict[str, str]:
        if env_loader:
            return env_loader(secrets_folder)
        return _parse_env_files(_secrets_env_files(ctx.secrets_folder_path(secrets_folder)))

    rows: list[tuple[int, str, str]] = []
    for module_id in ctx.list_module_ids():
        if allowed is not None and module_id not in allowed:
            continue
        role = ctx.get_module_role(module_id)
        role_cfg = roles_cfg.get(role)
        if not role_cfg:
            continue
        secrets_folder = ctx.secrets_module_folder(module_id)
        port = resolve_module_port(
            role=role,
            role_cfg=role_cfg,
            secrets_folder=secrets_folder,
            env=load_env(secrets_folder),
        )
        if not port:
            continue
        try:
            sort_key = order.index(role)
        except ValueError:
            sort_key = len(order)
        line = format_endpoint_line(
            module_id=module_id,
            role=role,
            port=port,
            url_path=str(role_cfg.get("urlPath") or "/"),
        )
        rows.append((sort_key, module_id, line))

    rows.sort(key=lambda r: (r[0], r[1]))
    return [r[2] for r in rows]
