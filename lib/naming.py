"""Every name the kit derives -- the ONE home of each (ADR-001 amendment 13).

A name is never declared twice and never read from an env file: the project slug is the manifest's
`project` (else the repository folder), and everything else is derived from it, the module, its
role and the environment. Before 2.0.0 several of these were also overridable from deploy.env
(the former keys lib/legacy.py names); a host that still
carries them is refused by `validate`, naming `migrate`.

    project slug          manifest `project`, else the repository folder, slugified
    service id            a role's primary module: the role's `primaryService`; else the module's
                          `target`, else its id (a module may declare several `services`)
    local service         {project}-{service id}            (compose-gen, the local stack)
    local network         {project}-net
    remote compose        {project}-{environment}           (one compose project per environment)
    remote container      {project}-{environment}-{service id}
    remote image          {project}-{environment}-{service id}:{release}
    remote network        {project}-{environment}  (a declared extra one: {project}-{environment}-{name})
    remote volume         {project}-{environment}-{volume}
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (text or "").strip()).strip("-").lower()
    return s or "app"


def project_slug(manifest: dict[str, Any], root: Path) -> str:
    """The project's one name: the manifest's `project`, else the repository folder."""
    return slugify(str(manifest.get("project") or Path(root).name))


def _modules(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(k): v for k, v in (manifest.get("modules") or {}).items() if isinstance(v, dict)}


def primary_module_id(manifest: dict[str, Any], role: str, module_ids: list[str] | None = None) -> str | None:
    """A role's primary module: the one the role's `primaryField` names, else the first of the role."""
    from lib import catalogs

    mods = _modules(manifest)
    ids = module_ids if module_ids is not None else list(mods)
    field = (catalogs.entry("roles", role, manifest) or {}).get("primaryField")
    if field:
        cur: Any = manifest
        for part in str(field).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur in ids and cur in mods:
            return str(cur)
    return next((m for m in ids if (mods.get(m) or {}).get("role") == role), None)


def module_service_ids(manifest: dict[str, Any], module_id: str) -> list[str]:
    """The service ids a module deploys: its declared `services`, else one."""
    cfg = _modules(manifest).get(module_id)
    if cfg is None:
        raise KeyError(f"manifest modules.{module_id} missing")
    if isinstance(cfg.get("services"), dict) and cfg["services"]:
        return [str(s) for s in cfg["services"]]
    from lib import catalogs

    role = str(cfg.get("role") or "")
    declared = catalogs.entry("roles", role, manifest) or {}
    if declared.get("primaryService") and module_id == primary_module_id(manifest, role):
        return [str(declared["primaryService"])]
    return [str(cfg.get("target") or module_id).replace("_", "-")]


def service_id(manifest: dict[str, Any], module_id: str) -> str:
    """A single-service module's service id (the first, for a module with several)."""
    return module_service_ids(manifest, module_id)[0]


def local_service(manifest: dict[str, Any], root: Path, module_id: str) -> str:
    return f"{project_slug(manifest, root)}-{service_id(manifest, module_id)}"


def local_network(manifest: dict[str, Any], root: Path) -> str:
    return f"{project_slug(manifest, root)}-net"


def remote_compose_project(project: str, environment: str) -> str:
    return f"{project}-{environment}"


def remote_container(project: str, environment: str, service: str) -> str:
    return f"{project}-{environment}-{service}"


def remote_image(project: str, environment: str, service: str, release: str) -> str:
    return f"{project}-{environment}-{service}:{release}"


def remote_network(project: str, environment: str) -> str:
    return f"{project}-{environment}"


def remote_named_network(project: str, environment: str, name: str) -> str:
    return f"{project}-{environment}-{name}"


def remote_volume(project: str, environment: str, volume: str) -> str:
    return f"{project}-{environment}-{volume}"


def module_tier(manifest: dict[str, Any], module_id: str) -> str:
    """The tier a module's units live in on a server: its role's (catalogs.roles `tier`)."""
    from lib import catalogs

    role = str((_modules(manifest).get(module_id) or {}).get("role") or "")
    tier = (catalogs.entry("roles", role, manifest) or {}).get("tier")
    if not tier:
        raise ValueError(f"modules.{module_id}: role '{role}' names no tier (catalogs.roles `tier`)")
    return catalogs.require("tiers", str(tier), manifest, what=f"roles.{role}.tier")
