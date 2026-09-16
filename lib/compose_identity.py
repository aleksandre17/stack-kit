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
    "GEOSTAT_DOCKER_NETWORK",
)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (text or "").strip()).strip("-").lower()
    return s or "app"


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("\"'")
        if key and val:
            out[key] = val
    return out


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


def primary_api_module_id(manifest: dict[str, Any], module_ids: list[str] | None = None) -> str | None:
    ids = module_ids if module_ids is not None else stack_compose_module_ids(manifest)
    mods = manifest.get("modules") or {}
    if "backend" in ids and isinstance(mods.get("backend"), dict):
        return "backend"
    if "chat-api" in ids and isinstance(mods.get("chat-api"), dict):
        return "chat-api"
    for mid in ids:
        cfg = mods.get(mid)
        if isinstance(cfg, dict) and cfg.get("role") == "api":
            return mid
    return None


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
    ids = module_ids if module_ids is not None else stack_compose_module_ids(manifest)
    mods = manifest.get("modules") or {}
    for mid in ids:
        cfg = mods.get(mid)
        if isinstance(cfg, dict) and cfg.get("role") == "worker":
            return mid
    return None


def primary_ui_module_id(manifest: dict[str, Any], module_ids: list[str] | None = None) -> str | None:
    ids = module_ids if module_ids is not None else stack_compose_module_ids(manifest)
    mods = manifest.get("modules") or {}
    if "frontend" in ids and isinstance(mods.get("frontend"), dict):
        return "frontend"
    for mid in ids:
        cfg = mods.get(mid)
        if isinstance(cfg, dict) and cfg.get("role") == "ui":
            return mid
    return None


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
    role = str(cfg.get("role") or "")
    target = str(cfg.get("target") or module_id)
    slug = compose_slug(deploy, repo_name)

    if module_id == "backend" or target == "backend":
        return deploy.get("COMPOSE_API_SERVICE") or f"{slug}-api"
    if role == "ui" and module_id == "frontend":
        return deploy.get("COMPOSE_APP_SERVICE") or f"{slug}-app"
    if role == "ui":
        return deploy.get("COMPOSE_APP_SERVICE") or f"{slug}-{(target or module_id).replace('_', '-')}"
    if role == "worker":
        override = deploy.get("COMPOSE_WORKER_SERVICE")
        if override and module_id == (primary_worker_module_id(manifest) or module_id):
            return override
        return f"{slug}-{(target or module_id).replace('_', '-')}"
    if role == "api":
        if module_id == primary_api_module_id(manifest):
            # Primary API: honor the legacy override, else derive from the slug.
            # (Previously returned the override unconditionally — yielding None
            # when COMPOSE_API_SERVICE was unset for a primary api not named
            # "backend". The "backend" branch above already had this fallback.)
            return deploy.get("COMPOSE_API_SERVICE") or f"{slug}-api"
        return f"{slug}-{(target or module_id).replace('_', '-')}"
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
        or deploy.get("GEOSTAT_DOCKER_NETWORK")
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
