"""N-module manifest resolution — roles, types, CLI aliases (package boundary)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

MODULE_ROLES = frozenset({"ui", "api", "worker", "gateway", "data", "other"})


KIT_DRIVERS = Path(__file__).resolve().parent.parent / "drivers"


class DriverCollision(ValueError):
    """A project registry declares a driver id the kit already has: two homes for one name."""


def _read_registry(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def project_registry_path(root: Path, manifest: dict[str, Any]) -> Path | None:
    """The project's own driver registry, when its manifest declares one (`drivers.registry`)."""
    rel = (manifest.get("drivers") or {}).get("registry") if isinstance(manifest.get("drivers"), dict) else None
    return root / str(rel) if rel else None


def compose_registry(root: Path | None, manifest: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Path]]:
    """(registry, home of each driver): the kit's drivers, then the project's (ADR-001 decision 7).

    A project driver lives beside its registry, `<registry dir>/<id>/`, exactly as a kit driver
    lives under the kit's `drivers/<id>/`. An id the kit already has is refused, never shadowed:
    a host that wants its own flavour of a kit driver gives it its own name.
    """
    registry = _read_registry(KIT_DRIVERS / "registry.json")
    homes = {typ: KIT_DRIVERS / typ for typ in registry}
    path = project_registry_path(root, manifest or {}) if root is not None else None
    if path is not None:
        own = _read_registry(path)
        clash = sorted(set(own) & set(registry))
        if clash:
            raise DriverCollision(f"{path}: driver id(s) {', '.join(clash)} are the kit's -- name the project's "
                                  "driver differently")
        registry.update(own)
        homes.update({typ: path.parent / typ for typ in own})
    return registry, homes


@lru_cache(maxsize=8)
def _composed_for(root_key: str) -> tuple[dict[str, Any], dict[str, Path]]:
    if not root_key:
        return compose_registry(None, None)
    from lib.project_context import load_manifest

    root = Path(root_key)
    return compose_registry(root, load_manifest(root))


def _current_root() -> str:
    try:
        from lib.project_context import find_project_root

        return str(find_project_root())
    except FileNotFoundError:
        return ""


def driver_registry() -> dict[str, Any]:
    """The declared driver registry — the ONE home of what a driver is and can do: the kit's,
    composed with the current project's own (`drivers.registry`)."""
    return _composed_for(_current_root())[0]


def driver_home(driver_id: str) -> Path:
    """The directory a driver's command scripts are resolved under."""
    return _composed_for(_current_root())[1].get(str(driver_id), KIT_DRIVERS / str(driver_id))


def driver_capability(driver_id: str, key: str, default: Any = None) -> Any:
    """One DECLARED capability of a driver.

    The single accessor every interpreter uses to ask a driver what it can do.
    An interpreter never names a driver; it names a CAPABILITY, and the registry
    answers. A driver that declares nothing for `key` gets `default` — which is
    how a new driver stays safe by omission instead of silently mis-behaving.
    """
    entry = driver_registry().get(str(driver_id))
    if not isinstance(entry, dict):
        return default
    value = entry.get(key)
    return default if value is None else value


def driver_default_role(driver_id: str) -> str:
    """First role the driver DECLARES it serves — never a name hardcoded here."""
    entry = driver_registry().get(str(driver_id)) or {}
    roles = entry.get("roles")
    if isinstance(roles, list):
        for r in roles:
            if str(r).strip().lower() in MODULE_ROLES:
                return str(r).strip().lower()
    return ""


def module_ids(manifest: dict[str, Any]) -> list[str]:
    return list(_modules(manifest).keys())


def _modules(manifest: dict[str, Any]) -> dict[str, Any]:
    raw = manifest.get("modules") or {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def module_role(manifest: dict[str, Any], module_id: str) -> str:
    cfg = _modules(manifest).get(module_id) or {}
    role = str(cfg.get("role", "")).strip().lower()
    if role in MODULE_ROLES:
        return role
    # Infer from driver registry roles when manifest omits role (migration)
    return driver_default_role(str(cfg.get("type", ""))) or "other"


def modules_by_role(manifest: dict[str, Any], role: str) -> list[str]:
    role = role.strip().lower()
    out: list[str] = []
    for mid, cfg in _modules(manifest).items():
        r = str(cfg.get("role", "")).strip().lower() or module_role(manifest, mid)
        if r == role:
            out.append(mid)
    return out


def module_by_role(manifest: dict[str, Any], role: str, index: int = 0) -> str | None:
    ids = modules_by_role(manifest, role)
    if 0 <= index < len(ids):
        return ids[index]
    return None


def modules_by_type(manifest: dict[str, Any], driver_type: str) -> list[str]:
    out: list[str] = []
    for mid, cfg in _modules(manifest).items():
        if cfg.get("type") == driver_type:
            out.append(mid)
    return out


def module_by_type(manifest: dict[str, Any], driver_type: str, index: int = 0) -> str | None:
    ids = modules_by_type(manifest, driver_type)
    if 0 <= index < len(ids):
        return ids[index]
    return None


def infer_cli_aliases(manifest: dict[str, Any]) -> dict[str, str]:
    """cli.aliases + role shortcuts (ui, api) when exactly one module per role."""
    custom = (manifest.get("cli") or {}).get("aliases") or {}
    out: dict[str, str] = {str(k): str(v) for k, v in custom.items()} if isinstance(custom, dict) else {}
    for role in ("ui", "api", "worker", "gateway"):
        ids = modules_by_role(manifest, role)
        if len(ids) == 1 and role not in out:
            out[role] = ids[0]
    return out


def resolve_cli_alias(alias: str, manifest: dict[str, Any]) -> str | None:
    aliases = infer_cli_aliases(manifest)
    if alias in aliases:
        return aliases[alias]
    if alias in _modules(manifest):
        return alias
    return None


def layout_simulator_for_type(driver_type: str) -> str | None:
    """The layout simulator a driver DECLARES, or None when it declares none."""
    value = driver_capability(driver_type, "layoutSimulator")
    return str(value) if isinstance(value, str) and value else None


def driver_supports_config_gen(driver_type: str) -> bool:
    """Does this driver DECLARE that its modules take generated config?"""
    return bool(driver_capability(driver_type, "configGen", False))


def driver_accepts_global_credentials(driver_type: str) -> bool:
    """Does this driver DECLARE that its modules accept the manifest-wide credential?"""
    return bool(driver_capability(driver_type, "acceptsGlobalCredentials", False))


def driver_deploy_kind(driver_type: str) -> str:
    """The deploy artefact a driver DECLARES it produces ('runtime', 'static', ...)."""
    value = driver_capability(driver_type, "deployKind", "")
    return str(value).strip().lower()


def driver_deploy_args(driver_type: str) -> list[str]:
    """Extra argv a driver DECLARES for its stack deploy step (default: none)."""
    value = driver_capability(driver_type, "deployArgs", [])
    return [str(a) for a in value] if isinstance(value, list) else []


def module_driver_type(manifest: dict[str, Any], module_id: str) -> str:
    cfg = _modules(manifest).get(module_id) or {}
    return str(cfg.get("type") or "")


def default_stack_deploy_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Role-ordered deploy plan when stackDeploy.steps omitted."""
    from lib.stack_deploy import default_stack_deploy_steps as _steps

    return _steps(manifest)
