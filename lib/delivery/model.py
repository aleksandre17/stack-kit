"""What a deployed service IS, assembled from declarations -- each fact from its one home
(ADR-001 amendment 13).

    the driver   (registry `container`, `dev`)    how its modules are built into an image or served:
                 a recipe template (a web server's with its server config), an internal port, a command
    the module   (manifest `modules.<id>`)         `container` overrides, `services` (several from
                 one module, each with its `context`), `runtimeConfig`, `credentials`
    the stack    (manifest `stack.services`)       services no module builds (an object store, a
                 cache): an image and its settings
    the target   (targets.json)                    host ports per environment, `keep`, `healthWait`
    the catalogs                                   each service's tier, through its module's role

Nothing here names a tool, a driver or a version: those live in the declarations.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib import naming

KIT = Path(__file__).resolve().parents[2]
DEFAULTS = KIT / "config" / "delivery.json"

#: The fields a service declaration may carry -- driver `container`, module `container`, a module's
#: `services.<id>`, a stack service -- one vocabulary at every level, a later level winning.
SERVICE_FIELDS = ("template", "dockerfile", "serverConfig", "webRoot", "image", "port", "command", "entry", "healthcheck",
                  "environment", "volumes", "logs", "serve", "dependsOn", "healthWait", "keep", "context",
                  "artifact", "artifactExclude", "networks", "tier", "healthPath", "probe", "proxy", "builtChecks",
                  "allowBaked", "generatedSecrets")
#: The fields a remote-dev declaration may carry -- driver `dev`, module `dev` -- a later level winning.
DEV_FIELDS = ("image", "command", "build", "port", "debugPort", "caches", "excludes", "reactions", "watch",
              "environment", "debounceMs", "projectReferences")


class ModelError(ValueError):
    """A service that cannot be assembled honestly from its declarations, named."""


def defaults() -> dict[str, Any]:
    return json.loads(DEFAULTS.read_text(encoding="utf-8"))


@dataclass
class Service:
    id: str
    module: str | None            # None: a stack service no module builds
    tier: str
    kind: str                     # "build" (an image built from a release), "image" (a declared image)
    spec: dict[str, Any]          # the merged service declaration (SERVICE_FIELDS)
    driver: str = ""
    runtime_config: list[dict[str, Any]] = field(default_factory=list)
    credentials: list[dict[str, Any]] = field(default_factory=list)
    secrets_folder: str = ""
    dev: dict[str, Any] = field(default_factory=dict)

    @property
    def context(self) -> str:
        return str(self.spec.get("context") or "")


def _driver(manifest: dict[str, Any], typ: str) -> dict[str, Any]:
    from lib.modules import driver_registry

    return driver_registry().get(typ) or {}


def driver_home(typ: str) -> Path:
    from lib.modules import driver_home as home

    return home(typ)


def deployable(manifest: dict[str, Any], module_id: str) -> bool:
    """Whether a module deploys at all: its driver packages it, or it declares its own container."""
    from lib.modules import driver_capability

    cfg = (manifest.get("modules") or {}).get(module_id) or {}
    typ = str(cfg.get("type") or "")
    return bool((driver_capability(typ, "package", None) or {}).get("command")
                or cfg.get("container") or cfg.get("services"))


def module_services(manifest: dict[str, Any], module_id: str) -> list[Service]:
    """The services one module deploys, each with its merged declaration."""
    cfg = (manifest.get("modules") or {}).get(module_id)
    if not isinstance(cfg, dict):
        raise ModelError(f"no module '{module_id}'")
    from lib import templating

    typ = str(cfg.get("type") or "")
    driver = _driver(manifest, typ)
    base = {**(driver.get("container") or {}), **(cfg.get("container") or {})}
    dev = templating.render_tree({**(driver.get("dev") or {}), **(cfg.get("dev") or {})}, cfg)
    declared = cfg.get("services") if isinstance(cfg.get("services"), dict) else {}
    out = []
    for sid in naming.module_service_ids(manifest, module_id):
        spec = {**base, **(declared.get(sid) or {})}
        port = {"port": str(spec.get("port") or "")}  # a probe keeps its {path} for the recipe to fill
        spec = {k: v if k == "probe" else templating.render_tree(v, cfg, port) for k, v in spec.items()}
        if spec.get("static"):  # retired in 2.4.0 (ADR-001 amendment 18): one recipe shape for every module
            raise ModelError(f"modules.{module_id} ({typ}): service '{sid}' declares `container.static`, retired in "
                             f"2.4.0 -- a release is an image built from its driver's recipe (a web server's "
                             f"`template` with its `serverConfig`); remove the field")
        kind = "image" if spec.get("image") and not spec.get("template") and not spec.get("dockerfile") else "build"
        own = {**(cfg.get("container") or {}), **(declared.get(sid) or {})}
        if "generatedSecrets" in own and not own.get("dockerfile"):
            raise ModelError(f"modules.{module_id} ({typ}): service '{sid}' declares `generatedSecrets` -- how a "
                             f"runtime reads a generated secret is its driver's declaration, and the checks that it "
                             f"is read are only as true as that; declare it with the module's own `dockerfile`, or "
                             f"in the driver")
        if kind == "build" and not (spec.get("template") or spec.get("dockerfile")):
            raise ModelError(f"modules.{module_id} ({typ}): service '{sid}' has no container recipe -- its driver "
                             f"declares no `container.template` and the module no `container.dockerfile`")
        out.append(Service(
            id=sid, module=module_id, tier=naming.module_tier(manifest, module_id), kind=kind, spec=spec, driver=typ,
            runtime_config=[i for i in cfg.get("runtimeConfig") or [] if isinstance(i, dict)],
            credentials=[c for c in cfg.get("credentials") or [] if isinstance(c, dict)],
            secrets_folder=str(cfg.get("secretsModule") or module_id),
            dev=dev,
        ))
    return out


def stack_services(manifest: dict[str, Any]) -> list[Service]:
    """The services the stack runs that no module builds (`stack.services`): an image each."""
    from lib import catalogs

    out = []
    for sid, spec in ((manifest.get("stack") or {}).get("services") or {}).items():
        if not isinstance(spec, dict) or not spec.get("image"):
            raise ModelError(f"stack.services.{sid}: a stack service declares its `image`")
        tier = catalogs.require("tiers", str(spec.get("tier") or ""), manifest, what=f"stack.services.{sid}.tier")
        out.append(Service(id=str(sid), module=None, tier=tier, kind="image", spec=dict(spec),
                           secrets_folder=str(spec.get("secretsModule") or "")))
    return out


def all_services(manifest: dict[str, Any]) -> list[Service]:
    out = []
    for mid, cfg in (manifest.get("modules") or {}).items():
        if isinstance(cfg, dict) and deployable(manifest, mid):
            out += module_services(manifest, mid)
    out += stack_services(manifest)
    ids = [s.id for s in out]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ModelError(f"service ids declared twice: {', '.join(dup)} -- each service has one home")
    return out


def wait_of(service: Service, target: dict[str, Any]) -> dict[str, int]:
    d = defaults()["healthWait"]
    return {**d, **(target.get("healthWait") or {}), **(service.spec.get("healthWait") or {})}


def keep_of(service: Service, target: dict[str, Any]) -> int:
    return int(service.spec.get("keep") or target.get("keep") or defaults()["keep"])
