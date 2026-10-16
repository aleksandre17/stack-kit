"""The environment's running stack: what each unit runs, the one compose file, and its health.

Shared by release, rollback, remote dev and the manage verbs, so the stack has one writer:

    states        each service's state, read from the server (`current`, the stack state file)
    regenerate    the environment's compose file from the declarations and those states,
                  written only when it changes; every network it joins created first
    up            `compose up -d` of the named services
    wait_healthy  each container running, and healthy when it declares a healthcheck, within its
                  declared wait (retries x interval); the failures, named
"""
from __future__ import annotations

import json
import posixpath
from pathlib import Path
from typing import Any

from lib import envfile, naming
from lib.delivery import stack
from lib.delivery.context import Delivery, DeliveryError
from lib.delivery.model import Service, all_services, defaults, wait_of


def write_if_changed(ctx: Delivery, path: str, data: bytes, mode: str = "644") -> bool:
    if ctx.transport.read(path) == data:
        return False
    ctx.transport.write(path, data, mode)
    return True


def services(ctx: Delivery) -> list[Service]:
    return all_services(ctx.manifest)


def find(ctx: Delivery, wanted: list[str]) -> list[Service]:
    """The services named by module id, service id or tier (`all` / none: every one)."""
    every = services(ctx)
    if not wanted or wanted == ["all"]:
        return every
    out: list[Service] = []
    for w in wanted:
        hit = [s for s in every if w in (s.id, s.module, s.tier)]
        if not hit:
            known = sorted({s.id for s in every} | {s.module for s in every if s.module} | {s.tier for s in every})
            raise DeliveryError(f"'{w}' is no module, service or tier of this project ({', '.join(known)})")
        out += [s for s in hit if s not in out]
    return out


def read_state_file(ctx: Delivery) -> dict[str, Any]:
    raw = ctx.transport.read(ctx.places.of("stackState"))
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def current_release(ctx: Delivery, service: Service) -> str | None:
    if service.kind == "image" and service.module is None:
        return None
    target = ctx.transport.readlink(ctx.places.of("current", service))
    return posixpath.basename(target.rstrip("/")) if target else None


def states(ctx: Delivery, override: dict[str, stack.State] | None = None) -> dict[str, stack.State]:
    modes = read_state_file(ctx)
    out = {}
    for s in services(ctx):
        out[s.id] = stack.State(release=current_release(ctx, s),
                                workspace=(modes.get(s.id) or {}).get("mode") == "workspace")
    out.update(override or {})
    return out


def env_file(ctx: Delivery, service: Service) -> bytes:
    from lib import catalogs

    folder = service.secrets_folder
    values = envfile.merged(envfile.run_files(ctx.secrets_root, folder, ctx.environment,
                                              catalogs.ids("environments", ctx.manifest))) if folder else {}
    return "".join(f"{k}={v}\n" for k, v in sorted(values.items())).encode("utf-8")


def credential_files(ctx: Delivery, service: Service) -> dict[str, Path]:
    """The module's credential files: its secrets folder's files matching the declared patterns."""
    import fnmatch

    if not service.secrets_folder:
        return {}
    patterns = service.spec.get("credentialPatterns") or defaults()["credentialPatterns"]
    folder = ctx.secrets_root / service.secrets_folder
    return {p.name: p for p in sorted(folder.iterdir()) if p.is_file() and any(fnmatch.fnmatch(p.name, g) for g in patterns)} \
        if folder.is_dir() else {}


def place_files(ctx: Delivery, service: Service) -> list[str]:
    """The env file (mode 600), the runtime config and the credential files of a service, each written
    only when it differs; returns the credential names the stack mounts."""
    unit = ctx.places.unit(service)
    write_if_changed(ctx, unit["stackEnv"], env_file(ctx, service), "600")
    for item in service.runtime_config:
        if ctx.environment in (item.get("environments") or []):
            src = ctx.root / str(item["from"])
            if not src.is_file():
                raise DeliveryError(f"runtimeConfig {item['from']} is not there")
            write_if_changed(ctx, posixpath.join(unit["runtime"], str(item["to"])), src.read_bytes(), "644")
    creds = credential_files(ctx, service)
    for name, path in creds.items():
        write_if_changed(ctx, posixpath.join(unit["runtime"], "credentials", name), path.read_bytes(), "600")
    return sorted(creds)


def regenerate(ctx: Delivery, override: dict[str, stack.State] | None = None, revision: str = "") -> bool:
    """The environment's compose file from the declarations and every unit's state. A service that
    runs nothing (no release, no workspace) is not in it; a stack service always is."""
    docs: dict[str, dict[str, Any]] = {}
    st = states(ctx, override)
    for s in services(ctx):
        state = st.get(s.id) or stack.State()
        if s.module is not None and not state.running:
            continue
        creds = sorted(credential_files(ctx, s)) if s.module else []
        docs[s.id] = stack.service_document(s, project=ctx.project, environment=ctx.environment, target=ctx.target,
                                            places=ctx.places, state=state, revision=revision or (state.release or ""),
                                            credentials=creds, env_file=bool(s.secrets_folder))
    doc = stack.compose_document(project=ctx.project, environment=ctx.environment, services=docs)
    changed = write_if_changed(ctx, ctx.places.of("stackCompose"), stack.render(doc))
    for net in stack.networks_of(docs, ctx.project, ctx.environment):
        if ctx.transport.exec(ctx.engine("network", "inspect", net), readonly=True).code != 0:
            ctx.run(ctx.engine("network", "create", net))
    return changed


def up(ctx: Delivery, ids: list[str], *, build: bool = False) -> None:
    ctx.run(ctx.compose("up", "-d", *(["--build"] if build else []), *ids))


def build_missing(ctx: Delivery, svc: list[Service], release: str) -> list[str]:
    """Build each service's image of this release unless the engine already has it (idempotent)."""
    built = []
    for s in svc:
        if s.kind != "build":
            continue
        image = naming.remote_image(ctx.project, ctx.environment, s.id, release)
        if ctx.transport.exec(ctx.engine("image", "inspect", image), readonly=True).code == 0:
            continue
        r = ctx.run(ctx.compose("build", s.id), check=False)
        log = ctx.places.of("logs", s) + "/build.log"
        prior = ctx.transport.read(log) or b""
        ctx.transport.write(log, prior + f"== build {image}\n{r.out}{r.err}\n".encode("utf-8"))
        if r.code != 0:
            raise DeliveryError(f"build of {s.id} failed (exit {r.code}); see {log}", 6)
        built.append(s.id)
    return built


def health_of(ctx: Delivery, service: Service) -> str:
    """running | healthy | starting | unhealthy | exited | absent -- the engine's own answer."""
    name = naming.remote_container(ctx.project, ctx.environment, service.id)
    r = ctx.transport.exec(ctx.engine("inspect", "-f", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
                                      name), readonly=True)
    if r.code != 0:
        return "absent"
    status, _, health = r.out.strip().partition(" ")
    if status != "running":
        return status or "absent"
    return health.strip() or "running"


def wait_healthy(ctx: Delivery, svc: list[Service]) -> list[str]:
    """Each service healthy (or running, without a healthcheck) within its declared wait; failures named."""
    failed = []
    for s in svc:
        wait = wait_of(s, ctx.target)
        last = ""
        for i in range(int(wait["retries"])):
            last = health_of(ctx, s)
            if last in ("healthy", "running"):
                ctx.out(f"[health] {s.id}: {last}")
                break
            if last in ("unhealthy", "exited", "dead"):
                break
            if i + 1 < int(wait["retries"]):
                ctx.sleep(float(wait["interval"]))
        else:
            last = last or "absent"
        if last not in ("healthy", "running"):
            failed.append(f"{s.id}: {last}")
    return failed


def set_mode(ctx: Delivery, service: Service, mode: str | None) -> None:
    modes = read_state_file(ctx)
    if mode:
        modes[service.id] = {"mode": mode}
    else:
        modes.pop(service.id, None)
    write_if_changed(ctx, ctx.places.of("stackState"), (json.dumps(modes, indent=1, sort_keys=True) + "\n").encode("utf-8"))
