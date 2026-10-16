"""Operating a deployed environment: the manage verbs, per service, module, tier or all.

    status    each service's state (release | workspace | image) and the engine's health
    logs      the services' container logs (`--follow`, `--tail N`)
    start, stop, restart    the containers
    rebuild   the images of the current releases, without cache, then up
    rm        the services' containers and their units (releases, runtime, logs): approval required
    nuke      the whole environment: containers, its networks and volumes, its directory: approval

rm and nuke act only inside {root}/{project}/{environment} of a directory carrying this project's
ownership marker -- never at the root, never in a folder another project (or nobody) has claimed.
"""
from __future__ import annotations

from lib import naming
from lib.delivery import dev, preflight, running, stack
from lib.delivery.context import Delivery, DeliveryError


def _ids(ctx: Delivery, wanted: list[str]) -> list[str]:
    return [s.id for s in running.find(ctx, wanted)]


def status(ctx: Delivery, wanted: list[str]) -> list[str]:
    return dev.status(ctx, wanted)


def logs(ctx: Delivery, wanted: list[str], *, follow: bool = False, tail: int = 200) -> int:
    return dev.logs(ctx, wanted, follow=follow, tail=tail)


def lifecycle(ctx: Delivery, verb: str, wanted: list[str]) -> int:
    if verb not in ("start", "stop", "restart"):
        raise DeliveryError(f"no manage verb '{verb}'")
    ctx.run(ctx.compose(verb, *_ids(ctx, wanted)))
    return 0


def rebuild(ctx: Delivery, wanted: list[str]) -> int:
    svc = [s for s in running.find(ctx, wanted) if s.kind == "build" and running.current_release(ctx, s)]
    if not svc:
        raise DeliveryError("nothing to rebuild: no selected service runs a built release")
    ids = [s.id for s in svc]
    ctx.run(ctx.compose("build", "--no-cache", *ids))
    ctx.run(ctx.compose("up", "-d", *ids))
    failed = [] if ctx.plan else running.wait_healthy(ctx, svc)
    return 6 if failed else 0


def _owned(ctx: Delivery) -> None:
    if not preflight.owned(ctx):
        raise DeliveryError(f"refused: {ctx.places.project_dir} carries no ownership marker of {ctx.project!r} -- "
                            f"nothing is removed from a directory this project has not claimed", 3)


def rm(ctx: Delivery, wanted: list[str]) -> int:
    if not wanted:
        raise DeliveryError("rm names what it removes (a service, module or tier); the whole environment is `nuke`")
    _owned(ctx)
    svc = running.find(ctx, wanted)
    ids = [s.id for s in svc]
    ctx.run(ctx.compose("rm", "-s", "-f", *ids), check=False)
    for s in svc:
        running.set_mode(ctx, s, None)
        if s.module is not None:
            unit = ctx.places.of("unit", s)
            if ctx.transport.exists(unit):
                ctx.transport.remove(unit)
            env = ctx.places.of("stackEnv", s)
            if ctx.transport.exists(env):
                ctx.transport.remove(env)
    running.regenerate(ctx)
    ctx.out(f"[ops] removed {', '.join(ids)} from {ctx.environment}")
    return 0


def nuke(ctx: Delivery) -> int:
    _owned(ctx)
    env_dir = ctx.places.environment_dir
    compose_file = ctx.places.of("stackCompose")
    if ctx.transport.exists(compose_file):
        ctx.run(ctx.compose("down", "-v", "--remove-orphans"), check=False)
    for net in stack.networks_of({}, ctx.project, ctx.environment):
        ctx.run(ctx.engine("network", "rm", net), check=False)
    if ctx.transport.exists(env_dir):
        ctx.transport.remove(env_dir, confine=ctx.places.project_dir)
    ctx.out(f"[ops] {naming.remote_compose_project(ctx.project, ctx.environment)} removed: {env_dir}")
    return 0
