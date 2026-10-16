"""A release: the packaged bytes of one commit, shipped once, pointed at by `current` (ADR-001 am. 13).

    release   preflight (marker, runtime, ports, disk) -> ship each service's tree to
              releases/<id> (through <id>.partial, so a half-shipped release never exists) -> the env
              file (600), runtime config and credentials (read-only mounts) -> `current` -> the
              environment's compose file -> build an image only when the engine lacks it -> up ->
              health; on a failed health in an environment that rolls back, `current` returns to the
              previous release -> prune to `keep` (never `current`). Every step is skipped when it
              would change nothing: a second release of the same id writes nothing.
    rollback  `current` to a named release, or the newest one before it; then the same stack and
              health flow
    list      each unit's releases, newest first, `current` marked
"""
from __future__ import annotations

import posixpath
import time
from pathlib import Path

from lib import package
from lib.delivery import preflight, running, stack
from lib.delivery.context import Delivery, DeliveryError
from lib.delivery.model import Service, keep_of, module_services
from lib.delivery.transport import tar_bytes


def _log(ctx: Delivery, service: Service, line: str) -> None:
    path = ctx.places.of("logs", service) + "/upload.log"
    prior = ctx.transport.read(path) or b""
    ctx.transport.write(path, prior + f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {line}\n".encode("utf-8"))


def releases_of(ctx: Delivery, service: Service) -> list[str]:
    """A unit's releases, newest first (by when they were shipped); a partial one is not a release."""
    base = ctx.places.of("releases", service)
    names = [n for n in ctx.transport.listdir(base) if not n.endswith(".partial")]
    return sorted(names, key=lambda n: (ctx.transport.mtime(posixpath.join(base, n)), n), reverse=True)


def ship(ctx: Delivery, service: Service, release: str, tree: dict[str, bytes]) -> bool:
    """The service's tree at releases/<release>, once; False when it was there already."""
    final = posixpath.join(ctx.places.of("releases", service), release)
    if ctx.transport.exists(final):
        return False
    partial = final + ".partial"
    if ctx.transport.exists(partial):
        ctx.transport.remove(partial)
    ctx.transport.untar(partial, tar_bytes(tree))
    ctx.transport.move(partial, final)
    _log(ctx, service, f"release {release} shipped ({len(tree)} files)")
    return True


def point(ctx: Delivery, service: Service, release: str) -> bool:
    target = posixpath.join(ctx.places.of("releases", service), release)
    if ctx.transport.readlink(ctx.places.of("current", service)) == target:
        return False
    ctx.transport.link(target, ctx.places.of("current", service))
    return True


def prune(ctx: Delivery, service: Service) -> list[str]:
    limit = keep_of(service, ctx.target)
    current = running.current_release(ctx, service)
    removed = []
    for name in releases_of(ctx, service)[limit:]:
        if name != current:
            ctx.transport.remove(posixpath.join(ctx.places.of("releases", service), name))
            removed.append(name)
    return removed


def _start(ctx: Delivery, svc: list[Service], release: str, revision: str) -> list[str]:
    """Stack, images, up, health -- the failures."""
    running.regenerate(ctx, revision=revision)
    if not ctx.commands["compose"]:
        return []
    running.build_missing(ctx, svc, release)
    running.up(ctx, [s.id for s in svc])
    return [] if ctx.plan else running.wait_healthy(ctx, svc)


def release(ctx: Delivery, module_id: str, archive: Path) -> int:
    meta, trees = package.read(archive)
    if meta.get("module") != module_id:
        raise DeliveryError(f"{archive.name} is a package of {meta.get('module')!r}, not {module_id!r}")
    if meta.get("dirty") and ctx.flag("requireClean"):
        raise DeliveryError(f"refused: {archive.name} was packaged from a dirty checkout ({meta.get('revision')}); "
                            f"{ctx.environment} takes a release of a clean commit only", 5)
    rid = str(meta["id"])
    svc = module_services(ctx.manifest, module_id)
    missing = [s.id for s in svc if s.id not in trees]
    if missing:
        raise DeliveryError(f"{archive.name} carries no tree for {', '.join(missing)}")
    ctx.out(f"[release] {module_id} {rid} ({meta.get('revision')}) -> {ctx.target_name} {ctx.environment}: "
            f"{ctx.places.environment_dir}")
    for line in preflight.all_checks(ctx, [s.id for s in svc]):
        ctx.out(f"[preflight] {line}")
    previous: dict[str, str | None] = {}
    for s in svc:
        unit = ctx.places.unit(s)
        for kind in ("logs", "releases", "runtime"):
            ctx.transport.mkdir(unit[kind])
        shipped = ship(ctx, s, rid, trees[s.id])
        ctx.out(f"[release] {s.id}: {'shipped' if shipped else 'already there'} {posixpath.join(unit['releases'], rid)}")
        running.place_files(ctx, s)
        previous[s.id] = running.current_release(ctx, s)
        if point(ctx, s, rid):
            ctx.out(f"[release] {s.id}: current -> {rid} (was {previous[s.id] or 'none'})")
    failed = _start(ctx, svc, rid, str(meta.get("revision") or rid))
    if failed:
        ctx.out(f"[release] health FAILED: {'; '.join(failed)}")
        back = {s.id: previous[s.id] for s in svc if previous[s.id] and previous[s.id] != rid}
        if ctx.flag("rollbackOnFailure") and back:
            for s in svc:
                if s.id in back:
                    point(ctx, s, str(back[s.id]))
            ctx.out(f"[release] rolled back to {', '.join(f'{k}={v}' for k, v in back.items())}")
            again = _start(ctx, svc, str(next(iter(back.values()))), "")
            if again:
                ctx.out(f"[release] the previous release is not healthy either: {'; '.join(again)}")
        raise DeliveryError(f"release {rid} of {module_id} is not healthy in {ctx.environment}", 6)
    for s in svc:
        gone = prune(ctx, s)
        if gone:
            ctx.out(f"[release] {s.id}: pruned {', '.join(gone)} (keep {keep_of(s, ctx.target)})")
    ctx.out(f"[release] {module_id} {rid} is current in {ctx.environment}")
    return 0


def rollback(ctx: Delivery, wanted: list[str], to: str = "") -> int:
    svc = [s for s in running.find(ctx, wanted) if s.module is not None]
    preflight.claim(ctx)
    moved = {}
    for s in svc:
        have = releases_of(ctx, s)
        cur = running.current_release(ctx, s)
        if to:
            if to not in have:
                raise DeliveryError(f"{s.id}: no release {to} (releases: {', '.join(have) or 'none'})")
            choice = to
        else:
            older = have[have.index(cur) + 1:] if cur in have else have
            if not older:
                raise DeliveryError(f"{s.id}: no release before {cur or 'none'} to roll back to")
            choice = older[0]
        if point(ctx, s, choice):
            moved[s.id] = (cur, choice)
            ctx.out(f"[rollback] {s.id}: current {cur or 'none'} -> {choice}")
    if not moved:
        ctx.out("[rollback] nothing to move")
        return 0
    failed = _start(ctx, [s for s in svc if s.id in moved], next(iter(moved.values()))[1], "")
    if failed:
        ctx.out(f"[rollback] health FAILED: {'; '.join(failed)}")
        return 6
    return 0


def listing(ctx: Delivery, wanted: list[str]) -> list[str]:
    lines = []
    for s in running.find(ctx, wanted):
        if s.module is None:
            continue
        cur = running.current_release(ctx, s)
        rel = releases_of(ctx, s)
        lines.append(f"{s.id} ({s.tier}) {ctx.places.of('releases', s)}")
        lines += [f"  {'*' if r == cur else ' '} {r}" for r in rel] or ["    (no release)"]
    return lines


def stack_state(ctx: Delivery) -> dict[str, stack.State]:
    return running.states(ctx)
