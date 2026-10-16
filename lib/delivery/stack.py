"""One compose file per environment, derived -- never edited, never a second home (ADR-001 am. 13).

`{stack}/compose.yml` is regenerated from the declarations and each unit's state on every deploy,
rollback and dev change: a service whose unit has a `current` release runs that release; one in
workspace mode runs its remote-dev definition; a stack service runs its image. It is JSON, which
compose reads as YAML, so the kit needs no YAML writer. Every name is namespaced by the project and
the environment (lib/naming.py); every host port is the target's; every path is the layout's.
"""
from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass
from typing import Any

from lib import naming
from lib.delivery.model import Service, defaults
from lib.targets import Places


class StackError(ValueError):
    """A service that cannot be written into the stack honestly, named."""


@dataclass
class State:
    """What a unit runs now: a release (its `current`), its workspace (remote dev), or neither."""
    release: str | None = None
    workspace: bool = False

    @property
    def running(self) -> bool:
        return bool(self.release) or self.workspace


def host_ports(service: Service, target: dict[str, Any], environment: str) -> list[int]:
    return [int(p) for p in (((target.get("ports") or {}).get(environment) or {}).get(service.id)) or []]


def _ports(service: Service, target: dict[str, Any], environment: str, workspace: bool) -> list[str]:
    host = host_ports(service, target, environment)
    inner = (service.dev.get("port") if workspace else None) or service.spec.get("port")
    if host and not inner:
        raise StackError(f"service {service.id}: the target publishes {host} but the service declares no internal "
                         f"`port` to map them to")
    return [f"{p}:{int(inner)}" for p in host]


def service_document(service: Service, *, project: str, environment: str, target: dict[str, Any],
                     places: Places, state: State, revision: str = "", credentials: list[str] | None = None,
                     env_file: bool = True) -> dict[str, Any]:
    """The compose definition of one service in its current state."""
    spec = service.spec
    unit = places.unit(service) if service.module or service.kind != "image" else None
    doc: dict[str, Any] = {"container_name": naming.remote_container(project, environment, service.id),
                           "restart": "unless-stopped",
                           "networks": ["default", *(naming.remote_named_network(project, environment, n)
                                                     for n in spec.get("networks") or [])],
                           "labels": {"stack-kit.project": project, "stack-kit.environment": environment,
                                      "stack-kit.service": service.id, "stack-kit.tier": service.tier}}
    volumes: list[str] = []
    if state.workspace:
        dev = service.dev
        if not dev.get("image") or not dev.get("command"):
            raise StackError(f"service {service.id}: remote dev needs the driver's or module's `dev.image` and `dev.command`")
        doc.update({"image": dev["image"], "working_dir": "/workspace", "command": dev["command"]})
        doc["labels"]["stack-kit.mode"] = "workspace"
        volumes.append(f"{unit['workspace']}:/workspace")
        for name, mount in sorted((dev.get("caches") or {}).items()):
            volumes.append(f"{naming.remote_volume(project, environment, f'{service.id}-{name}')}:{mount}")
    elif service.kind == "build":
        if not state.release:
            raise StackError(f"service {service.id}: no release to run")
        doc.update({"image": naming.remote_image(project, environment, service.id, state.release),
                    "build": {"context": posixpath.join(unit["releases"], state.release)}})
        doc["labels"]["org.opencontainers.image.revision"] = revision
    elif service.kind == "static":
        if not state.release:
            raise StackError(f"service {service.id}: no release to serve")
        static = spec.get("static") or {}
        release_dir = posixpath.join(unit["releases"], state.release)
        doc["image"] = static["image"]
        serve = str(spec.get("serve") or "").strip("/")
        volumes.append(f"{posixpath.join(release_dir, serve) if serve else release_dir}:{static['mount']}:ro")
        if static.get("config"):
            volumes.append(f"{posixpath.join(release_dir, '.stack-kit/static.conf')}:{static['configMount']}:ro")
        doc["labels"]["org.opencontainers.image.revision"] = revision
    else:
        doc["image"] = spec["image"]
    if spec.get("command") and not state.workspace:
        doc["command"] = spec["command"]
    if env_file and unit:
        doc["env_file"] = [unit["stackEnv"]]
    ports = _ports(service, target, environment, state.workspace)
    if ports:
        doc["ports"] = ports
    if spec.get("healthcheck") and not state.workspace:
        doc["healthcheck"] = spec["healthcheck"]
    environment_vars = {**(spec.get("environment") or {}), **((service.dev.get("environment") or {}) if state.workspace else {})}
    d = defaults()
    for item in service.runtime_config:
        if environment in (item.get("environments") or [environment]):
            mount = item.get("mount") or posixpath.join(d["runtimeConfigMount"], str(item["to"]))
            volumes.append(f"{posixpath.join(unit['runtime'], str(item['to']))}:{mount}:ro")
    names = credentials or []
    if names:
        volumes.append(f"{posixpath.join(unit['runtime'], 'credentials')}:{d['credentialsMount']}:ro")
    for cred in service.credentials:
        name = posixpath.basename(str(cred["file"]))
        if name in names:
            volumes.append(f"{posixpath.join(unit['runtime'], 'credentials', name)}:{cred['mount']}:ro")
            if cred.get("envVar"):
                environment_vars[cred["envVar"]] = cred["mount"]
    if spec.get("logs") and unit:
        volumes.append(f"{unit['logs']}:{spec['logs']}")
    for name, mount in sorted((spec.get("volumes") or {}).items()):
        volumes.append(f"{naming.remote_volume(project, environment, name)}:{mount}")
    if environment_vars:
        doc["environment"] = {k: str(v) for k, v in sorted(environment_vars.items())}
    if volumes:
        doc["volumes"] = volumes
    if spec.get("dependsOn"):
        doc["depends_on"] = list(spec["dependsOn"])
    doc["logging"] = target.get("logging") or d["logging"]  # rotated: a disk the projects share stays finite
    return doc


def networks_of(services: dict[str, dict[str, Any]], project: str, environment: str) -> list[str]:
    """Every network the stack joins -- all external, all namespaced, all created before `up`."""
    found = {naming.remote_network(project, environment)}
    for doc in services.values():
        found |= {n for n in doc.get("networks") or [] if n != "default"}
    return sorted(found)


def named_volumes_of(services: dict[str, dict[str, Any]]) -> list[str]:
    out = []
    for doc in services.values():
        for v in doc.get("volumes") or []:
            source = v.split(":", 1)[0]
            if not source.startswith("/"):
                out.append(source)
    return sorted(set(out))


def compose_document(*, project: str, environment: str, services: dict[str, dict[str, Any]]) -> dict[str, Any]:
    nets = {"default": {"name": naming.remote_network(project, environment), "external": True}}
    for n in networks_of(services, project, environment):
        if n != naming.remote_network(project, environment):
            nets[n] = {"name": n, "external": True}
    doc: dict[str, Any] = {"name": naming.remote_compose_project(project, environment),
                           "services": {sid: services[sid] for sid in sorted(services)}, "networks": nets}
    vols = named_volumes_of(services)
    if vols:
        doc["volumes"] = {v: {"name": v} for v in vols}
    return doc


def render(doc: dict[str, Any]) -> bytes:
    """Byte-identical for an identical stack: a deploy that changes nothing writes nothing new."""
    return (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
