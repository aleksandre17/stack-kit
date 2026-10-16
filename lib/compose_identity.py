"""Compose service naming — manifest modules + optional deploy.env legacy overrides."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# Keys read from deploy.env (optional overrides for canonical slots only).
DEPLOY_IDENTITY_KEYS = (
    "DEPLOY_PROJECT",
    "COMPOSE_PROJECT_NAME",
    "COMPOSE_API_SERVICE",
    "COMPOSE_APP_SERVICE",
    "COMPOSE_WORKER_SERVICE",
    "DOCKER_NETWORK",
    "STACK_KIT_DOCKER_NETWORK",
)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (text or "").strip()).strip("-").lower()
    return s or "app"


def parse_env_file(path: Path) -> dict[str, str]:
    from lib.envfile import parse

    return parse(path)


def load_deploy_env(secrets_root: Path) -> dict[str, str]:
    deploy = parse_env_file(secrets_root / "deploy.env")
    for key in DEPLOY_IDENTITY_KEYS:
        if key in os.environ and os.environ[key]:
            deploy[key] = os.environ[key]
    return deploy


def compose_slug(deploy: dict[str, str], repo_name: str) -> str:
    """Docker service prefix. Uses COMPOSE_PROJECT_NAME or repo folder — not DEPLOY_PROJECT (remote tree)."""
    return slugify(deploy.get("COMPOSE_PROJECT_NAME") or repo_name)


def stack_compose_module_ids(manifest: dict[str, Any]) -> list[str]:
    stack = manifest.get("stack") or {}
    explicit = stack.get("composeModules")
    if isinstance(explicit, list) and explicit:
        return [str(m) for m in explicit]
    mods = manifest.get("modules") or {}
    return list(mods.keys()) if isinstance(mods, dict) else []


def primary_module_id(manifest: dict[str, Any], role: str, module_ids: list[str] | None = None) -> str | None:
    """A role's primary module: the one the role's `primaryField` names (catalogs.roles), else the
    first module of the role. No module id is spelled here -- an id is the project's word (ADR-001)."""
    from lib import catalogs

    ids = module_ids if module_ids is not None else stack_compose_module_ids(manifest)
    mods = manifest.get("modules") or {}
    field = (catalogs.entry("roles", role, manifest) or {}).get("primaryField")
    if field:
        cur: Any = manifest
        for part in str(field).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur in ids and isinstance(mods.get(cur), dict):
            return cur
    for mid in ids:
        cfg = mods.get(mid)
        if isinstance(cfg, dict) and cfg.get("role") == role:
            return mid
    return None


def primary_api_module_id(manifest: dict[str, Any], module_ids: list[str] | None = None) -> str | None:
    """The module the stack's API is (`stack.primaryApiModule`, else the first `api`)."""
    return primary_module_id(manifest, "api", module_ids)


def embedded_worker_enabled(
    manifest: dict[str, Any], catalog_features: dict[str, Any] | None = None
) -> bool:
    """P0-kit-13: manifest modules.<primary-api>.compose.embeddedWorker replaces catalog features.worker."""
    primary = primary_api_module_id(manifest)
    if primary:
        cfg = (manifest.get("modules") or {}).get(primary) or {}
        compose = cfg.get("compose") if isinstance(cfg, dict) else None
        if isinstance(compose, dict) and "embeddedWorker" in compose:
            return bool(compose.get("embeddedWorker"))
    catalog = catalog_features if isinstance(catalog_features, dict) else {}
    return bool(catalog.get("worker", False))


def effective_compose_features(
    manifest: dict[str, Any], catalog_features: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Merge catalog features with manifest-driven embedded worker flag."""
    catalog = dict(catalog_features) if isinstance(catalog_features, dict) else {}
    catalog["worker"] = embedded_worker_enabled(manifest, catalog_features)
    return catalog


def primary_worker_module_id(manifest: dict[str, Any], module_ids: list[str] | None = None) -> str | None:
    return primary_module_id(manifest, "worker", module_ids)


def primary_ui_module_id(manifest: dict[str, Any], module_ids: list[str] | None = None) -> str | None:
    """The first `ui` module. (It once privileged a module literally named `frontend`, a consumer's
    word; the role is the agnostic form.)"""
    return primary_module_id(manifest, "ui", module_ids)


def resolve_module_service_name(
    module_id: str,
    manifest: dict[str, Any],
    deploy: dict[str, str],
    repo_name: str,
) -> str:
    """Docker compose service key for a manifest module (single source of truth)."""
    mods = manifest.get("modules") or {}
    cfg = mods.get(module_id)
    if not isinstance(cfg, dict):
        raise KeyError(f"manifest modules.{module_id} missing")
    from lib import catalogs

    role = str(cfg.get("role") or "")
    target = str(cfg.get("target") or module_id)
    slug = compose_slug(deploy, repo_name)
    # A role's primary module takes the role's own service name (catalogs.roles `primaryService`),
    # or the deploy.env key that renames it (`serviceOverride`); every other module its target or id.
    declared = catalogs.entry("roles", role, manifest) or {}
    if declared and module_id == primary_module_id(manifest, role):
        override = declared.get("serviceOverride")
        if override and deploy.get(override):
            return deploy[override]
        if declared.get("primaryService"):
            return f"{slug}-{declared['primaryService']}"
    return f"{slug}-{(target or module_id).replace('_', '-')}"


def module_service_names(
    manifest: dict[str, Any],
    deploy: dict[str, str],
    repo_name: str,
) -> dict[str, str]:
    mods = manifest.get("modules") or {}
    return {
        str(mid): resolve_module_service_name(str(mid), manifest, deploy, repo_name)
        for mid in mods
        if isinstance(mods.get(mid), dict)
    }


def compose_service_names(
    manifest: dict[str, Any],
    deploy: dict[str, str],
    repo_name: str,
) -> dict[str, Any]:
    """
    Legacy role aliases + per-module map.
    `api` / `app` / `worker` match deploy drivers; `modules` is manifest-complete.
    """
    slug = compose_slug(deploy, repo_name)
    by_module = module_service_names(manifest, deploy, repo_name)
    api_mid = primary_api_module_id(manifest)
    ui_mid = primary_ui_module_id(manifest)
    worker_mid = primary_worker_module_id(manifest)

    api_name = (
        by_module.get(api_mid or "")
        or deploy.get("COMPOSE_API_SERVICE")
        or f"{slug}-api"
    )
    app_name = (
        by_module.get(ui_mid or "")
        or deploy.get("COMPOSE_APP_SERVICE")
        or f"{slug}-app"
    )
    if worker_mid and worker_mid in by_module:
        worker_name = by_module[worker_mid]
    else:
        worker_name = deploy.get("COMPOSE_WORKER_SERVICE") or f"{slug}-worker"

    return {
        "compose_slug": slug,
        "modules": by_module,
        "api": api_name,
        "app": app_name,
        "worker": worker_name,
        "primary_api_module": api_mid,
        "primary_ui_module": ui_mid,
        "primary_worker_module": worker_mid,
    }


def build_global_fmt(
    *,
    manifest: dict[str, Any],
    deploy: dict[str, str],
    repo_name: str,
) -> dict[str, str]:
    """Placeholders for catalog templates + manifest_compose (compose-gen)."""
    names = compose_service_names(manifest, deploy, repo_name)
    slug = names["compose_slug"]
    api_svc = names["api"]
    network = (
        deploy.get("DOCKER_NETWORK")
        or deploy.get("STACK_KIT_DOCKER_NETWORK")
        or f"{slug}-net"
    )
    compose_name = deploy.get("COMPOSE_PROJECT_NAME") or repo_name
    return {
        "compose_project_name": compose_name,
        "compose_slug": slug,
        "api_service": api_svc,
        "api_image": api_svc,
        "app_service": names["app"],
        "app_image": names["app"],
        "worker_service": names["worker"],
        "worker_image": names["worker"],
        "network_key": network.replace(".", "-"),
        "network_name": network,
        "api_storage_vol": f"{api_svc}-storage",
        "api_uploads_vol": f"{api_svc}-uploads",
        # Optional container resource-limit block (brand-agnostic seam). Empty by
        # default — a consumer opts in by supplying `resource_limits` in a compose
        # target's `fmt` (e.g. "    mem_limit: 1g\n    cpus: 1.5\n"). Keeps project
        # sizing constants in the consumer catalog, not in kit runtime (Law 10).
        "resource_limits": "",
    }
