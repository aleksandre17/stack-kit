"""What is checked on the server before any write of a deploy, and what claims the project there.

    claim     the ownership marker: written into an absent or empty project directory, accepted
              when it names this project (and repository), refused otherwise -- a non-empty
              directory without the marker is never claimed (it may be another project's, or a
              tree the platform shares); nothing is ever done at the root
    runtime   the declared engine and compose invocations answer (targets.<t>.compose overrides)
    ports     every host port this environment publishes is free, or already this compose
              project's: another project's container, or a process outside the engine, refuses it.
              One listing answers however many ports other projects use.
    consumes  each platform network the deployed services consume exists there (a read); a missing
              one is NOT RUN with its owner's action -- never created (lib/delivery/consumes.py)
    disk      the free space under the project's directory (reported; a declared floor refuses)
"""
from __future__ import annotations

import json
import re
from typing import Any

from lib import naming
from lib.delivery import consumes
from lib.delivery.context import Delivery, DeliveryError

_PUBLISHED = re.compile(r":(\d+)->")


def marker_of(ctx: Delivery) -> dict[str, Any] | None:
    raw = ctx.transport.read(ctx.places.marker())
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def owned(ctx: Delivery) -> bool:
    """Whether the project's directory carries this project's marker (read only)."""
    have = marker_of(ctx)
    return bool(have) and have.get("project") == ctx.project and not (
        have.get("repository") and ctx.repository and have.get("repository") != ctx.repository)


def claim(ctx: Delivery) -> str:
    """The marker, checked or written; returns what was found ("claimed" | "ours")."""
    project_dir = ctx.places.project_dir
    have = marker_of(ctx)
    if have is not None:
        if have.get("project") != ctx.project or (have.get("repository") and ctx.repository
                                                   and have.get("repository") != ctx.repository):
            raise DeliveryError(f"refused: {project_dir} belongs to project {have.get('project')!r} "
                                f"({have.get('repository') or '?'}), not {ctx.project!r} ({ctx.repository or '?'})", 3)
        return "ours"
    if ctx.transport.exists(project_dir) and ctx.transport.listdir(project_dir):
        raise DeliveryError(f"refused: {project_dir} exists, is not empty and carries no ownership marker -- it is "
                            f"not claimed; if it is this project's old tree, plan its move with `layout migrate`", 3)
    ctx.transport.mkdir(project_dir)
    ctx.transport.write(ctx.places.marker(), (json.dumps({"project": ctx.project, "repository": ctx.repository},
                                                         sort_keys=True) + "\n").encode("utf-8"))
    return "claimed"


def runtime(ctx: Delivery) -> list[str]:
    """The engine and compose versions, or a refusal naming the declared command to change."""
    found = []
    for what, argv in (("engine", ctx.engine("version", "--format", "{{.Server.Version}}")), ("compose", ctx.compose("version"))):
        r = ctx.transport.exec(argv, readonly=True)
        if r.code != 0:
            raise DeliveryError(f"target {ctx.target_name}: `{' '.join(argv[:3])}` does not answer there (exit {r.code}): "
                                f"{(r.err or r.out).strip()[:200]} -- declare the {what} invocation on the target "
                                f"(targets.{ctx.target_name}.{what}) if it differs", 4)
        found.append(f"{what} {(r.out.strip().splitlines() or ['?'])[0]}")
    return found


def published(ctx: Delivery) -> dict[int, str]:
    """{host port: the compose project publishing it} across every container on the host."""
    r = ctx.transport.exec(ctx.engine("ps", "--format", '{{.Label "com.docker.compose.project"}}\t{{.Ports}}'), readonly=True)
    out: dict[int, str] = {}
    for line in r.out.splitlines() if r.code == 0 else []:
        project, _, ports = line.partition("\t")
        for p in _PUBLISHED.findall(ports):
            out.setdefault(int(p), project or "(no compose project)")
    return out


def listening(ctx: Delivery) -> set[int] | None:
    r = ctx.transport.exec(["ss", "-Htln"], readonly=True)
    if r.code != 0:
        return None
    return {int(m) for m in re.findall(r":(\d+)\s", r.out + " ")}


def ports(ctx: Delivery, services: list[str] | None = None) -> list[str]:
    """Refuses a declared host port someone else holds; returns the notices."""
    declared = {svc: [int(p) for p in ps or []]
                for svc, ps in ((ctx.target.get("ports") or {}).get(ctx.environment) or {}).items()
                if services is None or svc in services}
    if not declared:
        return []
    mine = naming.remote_compose_project(ctx.project, ctx.environment)
    by_engine = published(ctx)
    held = listening(ctx)
    notices = [] if held is not None else ["ports: `ss` does not answer there; only container ports were checked"]
    for svc, ps in sorted(declared.items()):
        for p in ps:
            owner = by_engine.get(p)
            if owner and owner != mine:
                raise DeliveryError(f"refused: host port {p} ({svc}) is published by compose project '{owner}', not {mine}", 4)
            if owner is None and held is not None and p in held:
                raise DeliveryError(f"refused: host port {p} ({svc}) is held by a process outside the container engine", 4)
    return notices


def disk(ctx: Delivery) -> str:
    path = ctx.places.project_dir
    if not ctx.transport.exists(path):
        return "disk: not reported (the project's directory is not there yet)"
    r = ctx.transport.exec(["df", "-Pk", path], readonly=True)
    rows = r.out.strip().splitlines() if r.code == 0 else []
    if len(rows) < 2:
        return "disk: not reported"
    cols = rows[-1].split()
    free_mb = int(cols[3]) // 1024 if len(cols) > 3 and cols[3].isdigit() else -1
    floor = int(ctx.target.get("minFreeMb") or 0)
    if floor and 0 <= free_mb < floor:
        raise DeliveryError(f"refused: {free_mb} MB free under {path}, below the target's minFreeMb {floor}", 4)
    return f"disk: {free_mb} MB free under {path}"


def all_checks(ctx: Delivery, services: list[str] | None = None) -> list[str]:
    said = [f"marker: {claim(ctx)}"]
    if ctx.commands["compose"]:
        said += runtime(ctx)
        said += ports(ctx, services)
        said += consumes.check(ctx, services)
    said.append(disk(ctx))
    return said
