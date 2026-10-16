"""The local stack's compose names (compose-gen), each from lib/naming.py -- its one home.

Before 2.0.0 deploy.env could rename any of them (the former keys lib/legacy.py names); those keys
are now a validate error naming `migrate` (ADR-001 amendment 13).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lib import naming


def stack_compose_module_ids(manifest: dict[str, Any]) -> list[str]:
    stack = manifest.get("stack") or {}
    explicit = stack.get("composeModules")
    if isinstance(explicit, list) and explicit:
        return [str(m) for m in explicit]
    mods = manifest.get("modules") or {}
    return list(mods.keys()) if isinstance(mods, dict) else []


def primary_module_id(manifest: dict[str, Any], role: str, module_ids: list[str] | None = None) -> str | None:
    return naming.primary_module_id(manifest, role, module_ids if module_ids is not None else stack_compose_module_ids(manifest))


def primary_api_module_id(manifest: dict[str, Any], module_ids: list[str] | None = None) -> str | None:
    """The module the stack's API is (`stack.primaryApiModule`, else the first `api`)."""
    return primary_module_id(manifest, "api", module_ids)


def primary_worker_module_id(manifest: dict[str, Any], module_ids: list[str] | None = None) -> str | None:
    return primary_module_id(manifest, "worker", module_ids)


def primary_ui_module_id(manifest: dict[str, Any], module_ids: list[str] | None = None) -> str | None:
    return primary_module_id(manifest, "ui", module_ids)


def embedded_worker_enabled(manifest: dict[str, Any], catalog_features: dict[str, Any] | None = None) -> bool:
    """manifest modules.<primary-api>.compose.embeddedWorker replaces the catalog's features.worker."""
    primary = primary_api_module_id(manifest)
    if primary:
        cfg = (manifest.get("modules") or {}).get(primary) or {}
        compose = cfg.get("compose") if isinstance(cfg, dict) else None
        if isinstance(compose, dict) and "embeddedWorker" in compose:
            return bool(compose.get("embeddedWorker"))
    return bool((catalog_features or {}).get("worker", False)) if isinstance(catalog_features, dict) else False


def effective_compose_features(manifest: dict[str, Any], catalog_features: dict[str, Any] | None = None) -> dict[str, Any]:
    catalog = dict(catalog_features) if isinstance(catalog_features, dict) else {}
    catalog["worker"] = embedded_worker_enabled(manifest, catalog_features)
    return catalog


def resolve_module_service_name(module_id: str, manifest: dict[str, Any], root: Path) -> str:
    """The local compose service of a module: {project}-{service id}."""
    if not isinstance((manifest.get("modules") or {}).get(module_id), dict):
        raise KeyError(f"manifest modules.{module_id} missing")
    return naming.local_service(manifest, Path(root), module_id)


def module_service_names(manifest: dict[str, Any], root: Path) -> dict[str, str]:
    mods = manifest.get("modules") or {}
    return {str(m): resolve_module_service_name(str(m), manifest, root) for m in mods if isinstance(mods.get(m), dict)}


def compose_service_names(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    """The role aliases (`api`, `app`, `worker`) and the per-module map."""
    slug = naming.project_slug(manifest, Path(root))
    by_module = module_service_names(manifest, root)
    api_mid, ui_mid, worker_mid = (primary_api_module_id(manifest), primary_ui_module_id(manifest),
                                   primary_worker_module_id(manifest))
    return {
        "compose_slug": slug,
        "modules": by_module,
        "api": by_module.get(api_mid or "") or f"{slug}-api",
        "app": by_module.get(ui_mid or "") or f"{slug}-app",
        "worker": by_module.get(worker_mid or "") or f"{slug}-worker",
        "primary_api_module": api_mid,
        "primary_ui_module": ui_mid,
        "primary_worker_module": worker_mid,
    }


def build_global_fmt(*, manifest: dict[str, Any], root: Path) -> dict[str, str]:
    """Placeholders for the catalog templates (compose-gen)."""
    names = compose_service_names(manifest, root)
    slug = names["compose_slug"]
    api_svc = names["api"]
    network = naming.local_network(manifest, Path(root))
    return {
        "compose_project_name": slug,
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
        # An optional resource-limit block a consumer's compose target supplies in its `fmt`.
        "resource_limits": "",
    }
