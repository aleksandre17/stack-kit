"""A release: the packaged bytes of one commit, shipped once, pointed at by `current` (ADR-001 am. 13).

    release   preflight (marker, runtime, ports, disk) -> ship each service's tree to
              releases/<id> (through <id>.partial, so a half-shipped release never exists) -> the env
              file (600), runtime config and credentials (read-only mounts) -> `current` -> the
              environment's compose file -> build an image only when the engine lacks it -> up ->
              health; on a failed health in an environment that rolls back, `current` returns to the
              previous release -> prune to `keep` (never `current`). Every step is skipped when it
              would change nothing: a second release of the same id writes nothing.
    rollback  a transaction (ADR-001 am. 19): the target release -- a named one, or the newest one
              before `current` -- is judged against the service as declared now and refused, nothing
              changed, when it cannot run; the stack is then brought up on it (built when needed),
              healthy and on its image, and only then does `current` move; on any failure the
              previous release is brought back up, `current` never having left it, and the verb fails
    list      each unit's releases, newest first, `current` marked, one that cannot be rolled back
              to marked with why
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


def _start(ctx: Delivery, svc: list[Service], release: str, revision: str,
           override: dict[str, stack.State] | None = None) -> list[str]:
    """Stack, images, up, health -- the failures. `override`: the release each service runs instead of
    its `current` (a rollback brings the stack up on a release before `current` moves to it)."""
    running.regenerate(ctx, override)  # the revision label is the release id: what verify can derive again
    if not ctx.commands["compose"]:
        return []
    from lib.delivery import scan

    each: dict[str, list[Service]] = {}
    for s in svc:
        held = (override or {}).get(s.id)
        each.setdefault((held.release if held else None) or release, []).append(s)
    for rid, group in each.items():
        running.build_missing(ctx, group, rid)
        scan.scan(ctx, group, rid)
        running.hand_over_secrets(ctx, group, rid)  # before up: the app reads its secret as the uid it runs as
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
    from lib import secret_reach

    unread = secret_reach.release_problems(ctx.root, ctx.manifest, svc, trees) if archive is not None else []
    if unread:
        raise DeliveryError("refused: a generated secret would be made and ignored (ADR-001 amendment 20):\n  "
                            + "\n  ".join(unread), 5)
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
        if s.kind == "image":
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


#: What to do instead of rolling back to a release that cannot run as its service is declared now.
REMEDY = "check out commit {rid} and run `{kit} deploy {module} --env {env}` (it packages that commit with today's recipe)"


def unrunnable(ctx: Delivery, service: Service, rid: str) -> str:
    """Why release `rid` cannot run as `service` is declared now ("" when it can): a `build` service
    runs an image built from its release's own recipe, so a release without one -- made before the
    service was built from a recipe (a UI release before 2.4.0) -- has nothing to build from; and a
    release whose code does not read the generated secret its service is given would run without it."""
    if service.kind == "build":
        recipe = posixpath.join(ctx.places.of("releases", service), rid, "Dockerfile")
        if not ctx.transport.exists(recipe):
            return (f"it carries no Dockerfile, and {service.id} is now built from its release's recipe "
                    f"(the release was made before that)")
    from lib import secret_reach

    return secret_reach.server_problem(ctx, service, rid)


def _off_image(ctx: Delivery, svc: list[Service], choice: dict[str, str]) -> list[str]:
    """Each service whose container does not run the image of the release it was brought up on."""
    from lib import naming

    out = []
    for s in svc:
        want = naming.remote_image(ctx.project, ctx.environment, s.id, choice[s.id]) if s.kind == "build" \
            else str(s.spec.get("image") or "")
        name = naming.remote_container(ctx.project, ctx.environment, s.id)
        have = ctx.transport.exec(ctx.engine("inspect", "-f", "{{.Config.Image}}", name), readonly=True).out.strip()
        if want and have != want:
            out.append(f"{s.id}: runs {have or 'nothing'}, not {want}")
    return out


def _restore(ctx: Delivery, svc: list[Service], before: dict[str, str | None]) -> list[str]:
    """The stack back on each service's `current` (which never moved), up; the failures."""
    from lib import naming

    running.regenerate(ctx)
    for s in svc:
        if not before[s.id]:  # it ran nothing before: what the attempt started goes
            ctx.run(ctx.engine("rm", "-f", naming.remote_container(ctx.project, ctx.environment, s.id)), check=False)
    back = [s for s in svc if before[s.id]]
    if not back or not ctx.commands["compose"]:
        return []
    for s in back:
        running.hand_over_secrets(ctx, [s], str(before[s.id]))  # a secret made by the attempt is the runtime's too
    r = ctx.run(ctx.compose("up", "-d", *(s.id for s in back)), check=False)
    if r.code != 0:
        return [f"up of {', '.join(s.id for s in back)}: exit {r.code}"]
    return [] if ctx.plan else running.wait_healthy(ctx, back)


def rollback(ctx: Delivery, wanted: list[str], to: str = "") -> int:
    """A transaction: judged before anything moves, `current` moved only once the stack runs the
    release healthy and on its image, and the previous release back up on any failure -- never a
    success it is not."""
    svc = [s for s in running.find(ctx, wanted) if s.module is not None]
    choice: dict[str, str] = {}
    before: dict[str, str | None] = {}
    for s in svc:
        have = releases_of(ctx, s)
        cur = running.current_release(ctx, s)
        if to:
            if to not in have:
                raise DeliveryError(f"{s.id}: no release {to} (releases: {', '.join(have) or 'none'})")
            pick = to
        else:
            older = have[have.index(cur) + 1:] if cur in have else have
            if not older:
                raise DeliveryError(f"{s.id}: no release before {cur or 'none'} to roll back to")
            pick = older[0]
        if pick != cur:
            choice[s.id], before[s.id] = pick, cur
    moving = [s for s in svc if s.id in choice]
    refused = [f"{s.id}: release {choice[s.id]} cannot be rolled back to: {why}; instead, "
               + REMEDY.format(rid=choice[s.id], kit=identity.KIT_NAME, module=s.module, env=ctx.environment)
               for s in moving for why in [unrunnable(ctx, s, choice[s.id])] if why]
    if refused:
        raise DeliveryError("refused, nothing changed:\n  " + "\n  ".join(refused), 5)
    if not moving:
        ctx.out("[rollback] nothing to move")
        return 0
    preflight.claim(ctx)
    for s in moving:
        ctx.out(f"[rollback] {s.id}: bringing up {choice[s.id]} (current stays {before[s.id] or 'none'} until it is healthy)")
    now = running.states(ctx)
    override = {s.id: stack.State(release=choice[s.id], workspace=now[s.id].workspace) for s in moving}
    logs = ", ".join(ctx.places.of("logs", s) + "/build.log" for s in moving if s.kind == "build") or "none"
    try:
        failed = _start(ctx, moving, next(iter(choice.values())), "", override)
        if not failed and not ctx.plan and ctx.commands["compose"]:
            failed = _off_image(ctx, moving, choice)
    except DeliveryError as e:
        failed, code = [str(e)], (e.code if e.code == 5 else 6)  # a scan refusal stays a refusal
    else:
        code = 6
    if failed:
        ctx.out(f"[rollback] FAILED: {'; '.join(failed)}")
        again = _restore(ctx, moving, before)
        after = f"the previous release is not healthy either ({'; '.join(again)})" if again \
            else "the previous release is back up"
        raise DeliveryError(f"rollback to {', '.join(f'{k}={v}' for k, v in choice.items())} failed: "
                            f"{'; '.join(failed)}; current stays "
                            f"{', '.join(f'{k}={v or 'none'}' for k, v in before.items())} and {after}; "
                            f"build log: {logs}", code)
    for s in moving:
        point(ctx, s, choice[s.id])
        ctx.out(f"[rollback] {s.id}: current {before[s.id] or 'none'} -> {choice[s.id]}")
    running.regenerate(ctx)  # the same document: `current` now says what the override ran
    return 0


def listing(ctx: Delivery, wanted: list[str]) -> list[str]:
    """Newest first: `*` current, `!` a release that cannot be rolled back to, with why."""
    lines = []
    for s in running.find(ctx, wanted):
        if s.module is None:
            continue
        cur = running.current_release(ctx, s)
        rel = releases_of(ctx, s)
        lines.append(f"{s.id} ({s.tier}) {ctx.places.of('releases', s)}")
        for r in rel:
            why = "" if r == cur else unrunnable(ctx, s, r)
            lines.append(f"  {'*' if r == cur else '!' if why else ' '} {r}" + (f"  (cannot roll back: {why})" if why else ""))
        if not rel:
            lines.append("    (no release)")
    return lines


def stack_state(ctx: Delivery) -> dict[str, stack.State]:
    return running.states(ctx)
