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

from lib import identity, package
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
    running.regenerate(ctx)  # the revision label is the release id: what verify can derive again
    if not ctx.commands["compose"]:
        return []
    running.build_missing(ctx, svc, release)
    from lib.delivery import scan

    scan.scan(ctx, svc, release)
    migrate(ctx, svc)
    running.up(ctx, [s.id for s in svc])
    return [] if ctx.plan else running.wait_healthy(ctx, svc)


def ship_migrations(ctx: Delivery, step: dict) -> None:
    """The migrations directory (`stack.migrate.files`) into the infra place the migration service mounts."""
    if step.get("files"):
        src = ctx.root / str(step["files"])
        if not src.is_dir():
            raise DeliveryError(f"stack.migrate.files: {step['files']} is not there")
        ctx.transport.put_tree(src, posixpath.join(ctx.places.of("infra"), "migrations"))


def migrate(ctx: Delivery, svc: list[Service]) -> bool:
    """The declared migration step (`stack.migrate`: a one-shot infra service, e.g. flyway), before the
    apps it serves start: its files shipped into the infra place, then `run --rm` -- the database's
    healthcheck gates it (depends_on), and its own ledger refuses an edited migration. A failure stops
    the release before any app runs against a half-migrated schema."""
    step = (ctx.manifest.get("stack") or {}).get("migrate") or {}
    if not step or not ctx.commands["compose"]:
        return False
    serves = step.get("modules")
    if serves and not any(s.module in serves for s in svc):
        return False
    from lib.delivery import infra

    ship_migrations(ctx, step)
    r = ctx.run(infra.compose(ctx, "--profile", "migrate", "run", "--rm", str(step["service"])), check=False)
    if r.code != 0:
        raise DeliveryError(f"the migration step ({step['service']}) failed (exit {r.code}); no app was started", 6)
    ctx.out(f"[release] migrations applied ({step['service']})")
    return True


def release(ctx: Delivery, module_id: str, archive: Path | None) -> int:
    """`archive` None: a plan of a commit not packaged yet -- its id is this checkout's, its trees the
    package's to come (nothing is built to plan)."""
    if archive is None:
        if not ctx.plan:
            raise DeliveryError(f"{module_id}: no archive to release")
        meta = {"module": module_id, **package.provenance(ctx.root)}
        trees = {s.id: {"(the package of this commit)": b""} for s in module_services(ctx.manifest, module_id)}
    else:
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
    floating = images_floating(ctx, svc, trees)
    if floating:
        raise DeliveryError("refused: " + "; ".join(floating), 5)
    from lib import projections

    stale = projections.release_problems(ctx, svc, rid, trees) if archive is not None else []
    if stale:
        raise DeliveryError(f"refused: a committed projection is stale (`{identity.KIT_NAME} render`, then commit):\n  "
                            + "\n  ".join(stale), 5)
    ctx.out(f"[release] {module_id} {rid} ({meta.get('revision')}) -> {ctx.target_name} {ctx.environment}: "
            f"{ctx.places.environment_dir}")
    policy = config_policy_problems(ctx, svc)
    if policy:
        raise DeliveryError("refused by the env-value policy (config.keys):\n  " + "\n  ".join(policy), 4)
    shared = shared_data_sources(ctx)
    if shared:
        raise DeliveryError("refused: environments share a data source:\n  " + "\n  ".join(shared), 4)
    for line in preflight.all_checks(ctx, [s.id for s in svc]):
        ctx.out(f"[preflight] {line}")
    for kind in ("stack", "infra", "backups"):
        ctx.transport.mkdir(ctx.places.of(kind))
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


def config_policy_problems(ctx: Delivery, svc: list[Service]) -> list[str]:
    """Each service's env values for this environment against the catalogue's policy; names, never values."""
    from lib import catalogs, config_policy, envfile

    catalogue = config_policy.catalogue_of(ctx.root, ctx.manifest)
    if not catalogue:
        return []
    out: list[str] = []
    for folder in dict.fromkeys(s.secrets_folder for s in svc if s.secrets_folder):
        values = envfile.merged(envfile.run_files(ctx.secrets_root, folder, ctx.environment,
                                                  catalogs.ids("environments", ctx.manifest)))
        out += config_policy.problems(catalogue, values, folder=folder, environment=ctx.environment)
    return out


def shared_data_sources(ctx: Delivery) -> list[str]:
    """Another environment that reads this one's store through a data-source key, undeclared."""
    from lib import catalogs, config_policy, data_sources

    catalogue = config_policy.catalogue_of(ctx.root, ctx.manifest)
    if not catalogue:
        return []
    return data_sources.shared(ctx.root, ctx.manifest, catalogue, catalogs.ids("environments", ctx.manifest),
                               only=ctx.environment, targets={"targets": {ctx.target_name: ctx.target}})


def images_floating(ctx: Delivery, svc: list[Service], trees: dict[str, dict[str, bytes]]) -> list[str]:
    """Every image the release runs or builds from, held to a version (a digest where the environment
    declares `requireDigests`)."""
    import re as _re

    from lib.delivery.checks import image_tag

    digest = ctx.flag("requireDigests")
    images: list[str] = []
    for s in [*svc, *(x for x in running.services(ctx) if x.module is None)]:
        if s.kind == "static":
            images.append(str((s.spec.get("static") or {}).get("image") or ""))
        elif s.kind == "image":
            images.append(str(s.spec.get("image") or ""))
        recipe = (trees.get(s.id) or {}).get("Dockerfile")
        if recipe:
            stages = set()
            for m in _re.finditer(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?", recipe.decode("utf-8", "replace"), _re.M | _re.I):
                if m.group(1) not in stages:
                    images.append(m.group(1))
                if m.group(2):
                    stages.add(m.group(2))
    return [why for why in (image_tag(i, require_digest=digest) for i in images if i) if why]


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
