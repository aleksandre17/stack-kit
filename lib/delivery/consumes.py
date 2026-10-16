"""What this project uses from a platform it does not own, by declaration (ADR-001 amendment 17).

A shared host may run another project's platform -- an edge that terminates TLS and routes by name,
a collector that receives telemetry, the network they are reached on. This project never creates,
changes or removes any of it: it declares what it consumes, and the platform's owner provides it.

    manifest `consumes`   networks   {<name>: {services, owner?}}        services that join a platform network
                          endpoints  {<name>: {env, services, owner?}}   an address given to services as env
                          routes     [{environment, host?, path?, service, port?, network?, tls}]
    target `consumes`     networks   {<name>: the network's name on that host}
                          endpoints  {<name>: {<environment>: the address there}}

    compose      a consuming service joins the network by its name on the target (external, as every
                 network of the stack is) and is given the endpoint's variable; a consumed network is
                 never created by a deploy nor removed by `nuke`
    preflight    each consumed network exists on the target -- a read; a missing one is NOT RUN,
                 naming the action its owner takes
    projection   each environment's routes (`projections.routes`), a document the platform's owner
                 applies -- this project writes nothing of the platform's
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from lib import naming

#: An address that carries a credential (`scheme://user:secret@host`) is a secret, not an endpoint.
_USERINFO = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/@]*@")


class ConsumeError(ValueError):
    """A consumption the declarations cannot answer, named with the declaration that would."""


@dataclass
class Uses:
    """What one service takes from the platform: networks by their names there, and env values."""
    networks: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)


def declared(manifest: dict[str, Any]) -> dict[str, Any]:
    c = manifest.get("consumes")
    return c if isinstance(c, dict) else {}


def _given(target: dict[str, Any]) -> dict[str, Any]:
    c = target.get("consumes")
    return c if isinstance(c, dict) else {}


def _owner(spec: dict[str, Any]) -> str:
    return str(spec.get("owner") or "the platform's owner")


def network_name(manifest: dict[str, Any], target: dict[str, Any], name: str) -> str:
    actual = (_given(target).get("networks") or {}).get(name)
    if not actual:
        raise ConsumeError(f"consumes.networks.{name}: the target names no network for it "
                           f"(targets.<target>.consumes.networks.{name}: its name on that host)")
    return str(actual)


def networks(manifest: dict[str, Any], target: dict[str, Any], service: str | None = None) -> dict[str, str]:
    """{declared name: its name on the target} of the networks `service` joins (every one when None)."""
    return {n: network_name(manifest, target, n) for n, spec in sorted((declared(manifest).get("networks") or {}).items())
            if service is None or service in (spec.get("services") or [])}


def uses(manifest: dict[str, Any], target: dict[str, Any], environment: str, service: str) -> Uses:
    out = Uses(networks=sorted(set(networks(manifest, target, service).values())))
    for name, spec in sorted((declared(manifest).get("endpoints") or {}).items()):
        if service not in (spec.get("services") or []):
            continue
        values = (_given(target).get("endpoints") or {}).get(name) or {}
        if environment not in values:
            raise ConsumeError(f"consumes.endpoints.{name}: the target gives no address for {environment} "
                               f"(targets.<target>.consumes.endpoints.{name}.{environment})")
        out.environment[str(spec["env"])] = str(values[environment])
    return out


# ── preflight: present, or NOT RUN with the owner's action ───────────────────

def check(ctx, services: list[str] | None = None) -> list[str]:
    """Each network the deployed services consume exists on the target (read only)."""
    from lib.delivery.context import DeliveryError

    specs = declared(ctx.manifest).get("networks") or {}
    wanted = {n: s for n, s in specs.items() if services is None or set(s.get("services") or []) & set(services)}
    if not wanted:
        return []
    said, missing = [], []
    for name, spec in sorted(wanted.items()):
        try:
            actual = network_name(ctx.manifest, ctx.target, name)
        except ConsumeError as e:
            raise DeliveryError(f"refused: {e}", 4) from None
        if ctx.transport.exec(ctx.engine("network", "inspect", actual), readonly=True).code == 0:
            said.append(f"consumes: network {actual} ({name}) is there")
        else:
            missing.append(f"network {actual} (consumes.networks.{name}, joined by {', '.join(spec.get('services') or [])}) "
                           f"is not on target {ctx.target_name} -- {_owner(spec)} provides it there "
                           f"(`{' '.join(ctx.engine('network', 'create', actual))}`, or the platform that declares it)")
    if missing:
        raise DeliveryError("NOT RUN: a platform network this project consumes is missing; this project never "
                            "creates, changes or removes one:\n  " + "\n  ".join(missing), 4)
    return said


# ── the routes projection: what the platform's owner applies ─────────────────

def routes_of(manifest: dict[str, Any], environment: str) -> list[dict[str, Any]]:
    return [r for r in declared(manifest).get("routes") or [] if isinstance(r, dict) and r.get("environment") == environment]


def _port(route: dict[str, Any], service: Any) -> int:
    port = route.get("port") or (service.spec.get("port") if service else None)
    if not port:
        raise ConsumeError(f"consumes.routes ({route.get('service')}): no `port` and the service declares none")
    return int(port)


def _route_network(manifest: dict[str, Any], target: dict[str, Any], route: dict[str, Any]) -> str:
    joined = networks(manifest, target, str(route.get("service")))
    if route.get("network"):
        if route["network"] not in joined:
            raise ConsumeError(f"consumes.routes ({route['service']}): network '{route['network']}' is not one the "
                               f"service joins (consumes.networks.{route['network']}.services)")
        return joined[route["network"]]
    if len(joined) != 1:
        raise ConsumeError(f"consumes.routes ({route.get('service')}): the service joins "
                           f"{'no platform network -- the edge could not reach it' if not joined else 'several platform networks -- name the route its `network`'}")
    return next(iter(joined.values()))


def routes_document(manifest: dict[str, Any], *, project: str, environment: str, target_name: str,
                    target: dict[str, Any], services: dict[str, Any], header: str) -> dict[str, Any] | None:
    """The environment's routes as the platform's owner applies them; None when it declares none."""
    declared_routes = routes_of(manifest, environment)
    if not declared_routes:
        return None
    rows = []
    for r in declared_routes:
        sid = str(r.get("service"))
        if sid not in services:
            raise ConsumeError(f"consumes.routes: service '{sid}' is not a service this project deploys")
        row = {"path": str(r.get("path") or "/"), "tls": r["tls"],
               "upstream": {"service": sid, "container": naming.remote_container(project, environment, sid),
                            "port": _port(r, services[sid]), "network": _route_network(manifest, target, r)}}
        if r.get("host"):
            row["host"] = str(r["host"])
        rows.append(row)
    rows.sort(key=lambda x: (x.get("host", ""), x["path"]))
    return {"generated": header, "schema": 1, "project": project, "environment": environment,
            "target": target_name, "routes": rows}


# ── validate: what is refused before any deploy ──────────────────────────────

def problems(manifest: dict[str, Any], data: dict[str, Any] | None, environments: list[str],
             services: dict[str, Any], project: str) -> list[str]:
    """Each consumption that names an unknown service or environment, a route the edge could not
    reach, a target that serves an environment without the names and addresses it consumes there,
    a consumed name inside this project's own namespace, an address that carries a credential."""
    c = declared(manifest)
    if not c:
        return []
    out: list[str] = []
    for kind in ("networks", "endpoints"):
        for name, spec in (c.get(kind) or {}).items():
            for sid in spec.get("services") or []:
                if sid not in services:
                    out.append(f"consumes.{kind}.{name}.services: '{sid}' is not a service this project deploys")
    for name, spec in (c.get("endpoints") or {}).items():
        for sid in spec.get("services") or []:
            if sid in services and str(spec.get("env")) in (services[sid].spec.get("environment") or {}):
                out.append(f"consumes.endpoints.{name}: {spec.get('env')} is also set by service {sid}'s `environment` "
                           f"-- one home: the target gives it")
    seen: set[tuple[str, str, str]] = set()
    for i, r in enumerate(c.get("routes") or []):
        where = f"consumes.routes[{i}]"
        if r.get("environment") not in environments:
            out.append(f"{where}.environment: '{r.get('environment')}' is not a declared environment")
        if not r.get("host") and not r.get("path"):
            out.append(f"{where}: a route names its `host`, its `path` prefix, or both")
        key = (str(r.get("environment")), str(r.get("host") or ""), str(r.get("path") or "/"))
        if key in seen:
            out.append(f"{where}: {key[1] or '(any host)'}{key[2]} in {key[0]} is routed twice")
        seen.add(key)
        if r.get("service") not in services:
            out.append(f"{where}.service: '{r.get('service')}' is not a service this project deploys")
            continue
        if not r.get("port") and not services[r["service"]].spec.get("port"):
            out.append(f"{where}: no `port`, and service {r['service']} declares none")
        joined = [n for n, s in (c.get("networks") or {}).items() if r["service"] in (s.get("services") or [])]
        if r.get("network") and r["network"] not in joined:
            out.append(f"{where}.network: '{r['network']}' is not a network service {r['service']} joins")
        elif not r.get("network") and len(joined) != 1:
            out.append(f"{where}: service {r['service']} joins {len(joined)} platform networks -- "
                       f"{'the edge could not reach it' if not joined else 'name the route its `network`'}")
    if not data:
        return out
    targets = data.get("targets") or {}
    for env in environments:
        tname = (data.get("defaults") or {}).get(env) or (next(iter(targets)) if len(targets) == 1 else "")
        t = targets.get(tname)
        if not isinstance(t, dict) or t.get("pending"):
            continue
        where = f"targets.{tname}.consumes"
        for name in c.get("networks") or {}:
            if not (_given(t).get("networks") or {}).get(name):
                out.append(f"{where}.networks.{name}: required -- {env} deploys there and consumes it")
        for name in c.get("endpoints") or {}:
            if env not in ((_given(t).get("endpoints") or {}).get(name) or {}):
                out.append(f"{where}.endpoints.{name}.{env}: required -- {env} deploys there and consumes it")
    for tname, t in targets.items():
        if not isinstance(t, dict):
            continue
        given = _given(t)
        for name, actual in (given.get("networks") or {}).items():
            if name not in (c.get("networks") or {}):
                out.append(f"targets.{tname}.consumes.networks.{name}: no `consumes.networks.{name}` in the manifest")
            elif any(str(actual) == naming.remote_network(project, e)
                     or str(actual).startswith(naming.remote_network(project, e) + "-") for e in environments):
                out.append(f"targets.{tname}.consumes.networks.{name}: '{actual}' is in this project's own namespace "
                           f"-- a consumed network is the platform's")
        for name, values in (given.get("endpoints") or {}).items():
            if name not in (c.get("endpoints") or {}):
                out.append(f"targets.{tname}.consumes.endpoints.{name}: no `consumes.endpoints.{name}` in the manifest")
            for env, value in (values or {}).items():
                if env not in environments:
                    out.append(f"targets.{tname}.consumes.endpoints.{name}.{env}: '{env}' is not a declared environment")
                if _USERINFO.match(str(value)):
                    out.append(f"targets.{tname}.consumes.endpoints.{name}.{env}: the address carries a credential "
                               f"-- a credential lives in the secret store, never in a target")
    return out
