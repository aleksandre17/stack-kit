"""The project's declared tree on a target: created (`targets --init`) and checked (`targets --verify`).

init     claims the project's directory (the ownership marker; a non-empty unmarked directory is
         refused), then creates the environment's places and every unit's -- idempotent: a second
         init changes nothing
verify   read-only: the marker, every declared place, `current` resolving, the prune limit, what
         is under the project that nothing declares (reported, never deleted), the runtime's
         commands, the declared ports, the free disk. Drift exits 1; an unreachable target 2.
"""
from __future__ import annotations

import posixpath

from lib import catalogs
from lib.delivery import preflight, running
from lib.delivery.context import Delivery, DeliveryError
from lib.delivery.model import keep_of
from lib.delivery.release import releases_of
from lib.targets import under

ENV_KINDS = ("stack", "infra", "backups")


def places(ctx: Delivery) -> tuple[list[str], list[str]]:
    """(directories that exist once the environment is initialised, subtrees whose inside is owned)."""
    workspace = ctx.environment in catalogs.flagged("environments", "workspace", ctx.manifest)
    dirs = [ctx.places.environment_dir, *(ctx.places.of(k) for k in ENV_KINDS)]
    owned = [ctx.places.of(k) for k in ENV_KINDS]
    for s in running.services(ctx):
        if s.module is None:
            continue
        unit = ctx.places.unit(s)
        kinds = ("unit", "logs", "releases", "runtime") + (("workspace",) if workspace else ())
        dirs += [unit[k] for k in kinds]
        owned += [unit["releases"], unit["runtime"], unit["logs"]] + ([unit["workspace"]] if workspace else [])
    return list(dict.fromkeys(dirs)), owned


def init(ctx: Delivery) -> list[str]:
    said = [f"marker: {preflight.claim(ctx)} ({ctx.places.marker()})"]
    dirs, _ = places(ctx)
    made = [d for d in dirs if not ctx.transport.exists(d)]
    for d in dirs:
        ctx.transport.mkdir(d)
    said += [f"created {d}" for d in made] or [f"tree complete: {len(dirs)} directories under {ctx.places.environment_dir}"]
    return said


def _walk(ctx: Delivery, base: str, owned: list[str], depth: int = 0) -> list[str]:
    out = []
    for name in ctx.transport.listdir(base):
        p = posixpath.join(base, name)
        out.append(p)
        if depth < 8 and not any(under(p, o) for o in owned) and not ctx.transport.readlink(p):
            out += _walk(ctx, p, owned, depth + 1)
    return out


def verify(ctx: Delivery) -> list[str]:
    """Drift, one line each (empty: the server holds the declared tree)."""
    project_dir = ctx.places.project_dir
    if not ctx.transport.exists(project_dir):
        return [f"missing: {project_dir} (the project's directory -- run `targets --init`)"]
    drift: list[str] = []
    have = preflight.marker_of(ctx)
    if have is None:
        drift.append(f"marker absent: {ctx.places.marker()}")
    elif not preflight.owned(ctx):
        drift.append(f"marker names another project: {have.get('project')!r} ({have.get('repository') or '?'})")
    dirs, owned = places(ctx)
    for d in dirs:
        if not ctx.transport.exists(d):
            drift.append(f"missing: {d}")
    allowed = {ctx.places.marker(), *(ctx.places.of("current", s) for s in running.services(ctx) if s.module is not None)}
    for d in dirs:
        while under(d, project_dir) and d != project_dir:  # every declared place and its ancestors
            allowed.add(d)
            d = posixpath.dirname(d)
    others = [e for e in catalogs.ids("environments", ctx.manifest) if e != ctx.environment]
    for path in _walk(ctx, project_dir, owned):
        top = path[len(project_dir):].strip("/").split("/")[0]
        if path in allowed or any(under(path, o) for o in owned) or top in others:
            continue
        drift.append(f"undeclared: {path} (reported, never deleted)")
    for s in running.services(ctx):
        if s.module is None:
            continue
        cur = ctx.transport.readlink(ctx.places.of("current", s))
        if cur and not ctx.transport.exists(cur):
            drift.append(f"current points at nothing: {ctx.places.of('current', s)} -> {cur}")
        count = len(releases_of(ctx, s))
        if count > keep_of(s, ctx.target):
            drift.append(f"over the prune limit: {ctx.places.of('releases', s)} keeps {count}, the limit is {keep_of(s, ctx.target)}")
    if ctx.commands["compose"]:
        try:
            for line in preflight.runtime(ctx):
                ctx.out(f"[verify] {line}")
            for line in preflight.ports(ctx, None):
                ctx.out(f"[verify] {line}")
        except DeliveryError as e:
            drift.append(str(e))
    try:
        ctx.out(f"[verify] {preflight.disk(ctx)}")
    except DeliveryError as e:
        drift.append(str(e))
    if have is not None and preflight.owned(ctx):
        from lib.delivery import drift as declared_state

        drift += declared_state.drift(ctx)
    return drift
