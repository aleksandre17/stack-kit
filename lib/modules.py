"""N-module manifest resolution — roles, types, CLI aliases (package boundary)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from lib import catalogs


def module_roles(manifest: dict[str, Any] | None = None) -> list[str]:
    """The roles a module may take: config/catalogs/roles.json with the host's (`catalogs.roles`)."""
    return catalogs.ids("roles", manifest)


KIT_DRIVERS = Path(__file__).resolve().parent.parent / "drivers"
#: The host run is the KIT's: one runner for every driver that declares its launch step
#: (`hybrid.script`), given to it as its `run` command (ADR-001 amendment 7).
HOST_RUNNER = Path(__file__).resolve().parent.parent / "toolkit" / "hybrid" / "Invoke-HybridRun.ps1"
#: A package-script step is a driver family's, kept with the drivers: one runner for every driver
#: that declares `packageScripts` (step -> script name), given as those commands (amendment 8).
PACKAGE_SCRIPT = Path(__file__).resolve().parent.parent / "drivers" / "_shared" / "package-scripts" / "Invoke-PackageScript.ps1"


def lifecycle_steps(manifest: dict[str, Any] | None = None) -> list[str]:
    """The lifecycle steps every module may be asked for, in pipeline order (catalogs.lifecycle);
    each is a CLI verb across the modules (`stack-kit <step> [module]`)."""
    return catalogs.ids("lifecycle", manifest)


def optional_steps(manifest: dict[str, Any] | None = None) -> list[str]:
    """The steps a module may lack: skipped and said, never failed."""
    return catalogs.flagged("lifecycle", "optional", manifest)


class DriverCollision(ValueError):
    """A project registry declares a driver id the kit already has: two homes for one name."""


class DriverRegistryError(ValueError):
    """A driver registry that cannot be read as one, named -- never read as an empty registry."""


def _read_registry(path: Path) -> dict[str, Any]:
    """A registry file's drivers. An unreadable or malformed file is refused by name: read as {}, a
    typo would silently remove every driver it declares."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise DriverRegistryError(f"{path.as_posix()}: unreadable ({e})") from e
    except ValueError as e:
        raise DriverRegistryError(f"{path.as_posix()}: not JSON ({e})") from e
    if not isinstance(data, dict):
        raise DriverRegistryError(f"{path.as_posix()}: a registry is an object of drivers")
    bad = sorted(k for k, v in data.items() if not isinstance(v, dict) and not str(k).startswith("$"))
    if bad:
        raise DriverRegistryError(f"{path.as_posix()}: {', '.join(bad)} not a driver declaration (an object)")
    return {k: v for k, v in data.items() if isinstance(v, dict)}


#: Where a project's own drivers are declared when its manifest names no other place -- the place
#: `extend driver` writes them (the extension point's default, held equal to this by a test).
DEFAULT_PROJECT_REGISTRY = "ops/drivers/registry.json"


def kit_registry() -> dict[str, Any]:
    """The kit's own drivers, without a host's -- what the operator documentation tabulates."""
    return _read_registry(KIT_DRIVERS / "registry.json")


def project_registry_path(root: Path, manifest: dict[str, Any]) -> Path | None:
    """The project's own driver registry: the one its manifest declares (`drivers.registry`), else the
    default place, when a registry is there -- a driver `extend driver` made is read where it was made."""
    rel = (manifest.get("drivers") or {}).get("registry") if isinstance(manifest.get("drivers"), dict) else None
    if rel:
        return root / str(rel)
    default = root / DEFAULT_PROJECT_REGISTRY
    return default if default.is_file() else None


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
    from lib.project_root import load_manifest

    root = Path(root_key)
    return compose_registry(root, load_manifest(root))


def _current_root() -> str:
    try:
        from lib.project_root import find_project_root

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


def driver_commands(driver_id: str) -> dict[str, Path]:
    """command -> script, for one driver: what it declares under `commands`; `run` -- the kit's
    host run -- when it declares a launch step and no `run` of its own; and each step it declares
    under `packageScripts` -- the kit's package-script runner -- that it does not script itself.
    The one home of the rule."""
    entry = driver_registry().get(str(driver_id))
    if not isinstance(entry, dict):
        return {}
    home = driver_home(driver_id)
    out = {str(name): home / str(rel["script"] if isinstance(rel, dict) else rel)
           for name, rel in (entry.get("commands") or {}).items()}
    if (entry.get("hybrid") or {}).get("script") and "run" not in out:
        out["run"] = HOST_RUNNER
    for step in driver_package_scripts(driver_id):
        if step in lifecycle_steps():
            out.setdefault(step, PACKAGE_SCRIPT)
    return out


def driver_command_runtimes(driver_id: str) -> dict[str, str]:
    """command -> runtime, for the commands a driver names a runtime for ({script, runtime}); every
    other command runs by its script's runtime (config/runtimes.json)."""
    entry = driver_registry().get(str(driver_id)) or {}
    return {str(n): str(c["runtime"]) for n, c in (entry.get("commands") or {}).items()
            if isinstance(c, dict) and c.get("runtime")}


KIT_RUNTIMES = Path(__file__).resolve().parent.parent / "config" / "runtimes.json"


def script_runtimes(manifest: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """id -> {match, argv | inSession}: the kit's runtimes with the host's over them (`runtimes`)."""
    kit = json.loads(KIT_RUNTIMES.read_text(encoding="utf-8"))["runtimes"]
    if manifest is None:
        from lib import catalogs

        manifest = catalogs._current_manifest()
    own = (manifest or {}).get("runtimes") or {}
    return {**kit, **{str(k): v for k, v in own.items() if isinstance(v, dict)}}


def driver_package_scripts(driver_id: str) -> dict[str, str]:
    """step -> package script name, as a driver declares them (`packageScripts`)."""
    value = driver_capability(driver_id, "packageScripts", {})
    return {str(k): str(v) for k, v in value.items() if v} if isinstance(value, dict) else {}


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
            if str(r).strip().lower() in module_roles():
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
    if role in module_roles(manifest):
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



def driver_supports_config_gen(driver_type: str) -> bool:
    """Does this driver DECLARE that its modules take generated config?"""
    return bool(driver_capability(driver_type, "configGen", False))


def driver_accepts_global_credentials(driver_type: str) -> bool:
    """Does this driver DECLARE that its modules accept the manifest-wide credential?"""
    return bool(driver_capability(driver_type, "acceptsGlobalCredentials", False))



def driver_delivery(driver_type: str) -> dict[str, dict[str, Any]]:
    """The delivery ladder a driver DECLARES: rung name -> `{command, args}`, `{via}` (a kit verb)
    or `{pending}` (named, not built). A rung the driver does not declare does not exist for it."""
    value = driver_capability(driver_type, "delivery", {})
    return {str(k): v for k, v in value.items() if isinstance(v, dict)} if isinstance(value, dict) else {}



def module_driver_type(manifest: dict[str, Any], module_id: str) -> str:
    cfg = _modules(manifest).get(module_id) or {}
    return str(cfg.get("type") or "")
