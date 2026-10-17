"""Remote dev: a module's source in its unit's workspace, run by its driver's dev container
(ADR-001 amendment 13). Everything is the environment's own: the workspace is the layout's
`workspace` of a workspace environment (catalogs.environments `workspace`), the container is in the
environment's one compose file (the unit's state says `workspace`), caches are named volumes
{project}-{environment}-{service}-{cache}.

    up       preflight (marker, runtime, the dev ports) -> sync -> env file -> workspace mode -> up -> health
    down     back to the unit's release when it has one, else the container removed
    sync     one incremental sync (lib/delivery/sync.py)
    watch    poll the source (debounced), sync each change, then the driver's declared reaction:
             hot-reload (nothing), restart (the container), rebuild (its declared `dev.build` in the
             container); a dropped connection is retried with backoff and followed by a full sync
    logs, status, shell, tunnel
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from lib import catalogs, identity, naming
from lib.delivery import preflight, running, stack, sync
from lib.delivery.context import Delivery, DeliveryError
from lib.delivery.model import Service
from lib.delivery.transport import TransportError


def _require_workspace(ctx: Delivery) -> None:
    if ctx.environment not in catalogs.flagged("environments", "workspace", ctx.manifest):
        envs = ", ".join(catalogs.flagged("environments", "workspace", ctx.manifest)) or "none"
        raise DeliveryError(f"remote dev runs in a workspace environment ({envs}), not {ctx.environment}", 2)


def module_dir(ctx: Delivery, service: Service) -> Path:
    return ctx.root / str(ctx.manifest["modules"][service.module]["path"])


def _cache(ctx: Delivery, service: Service) -> Path:
    return ctx.root / identity.RUNS_DIR.split("/")[0] / "dev" / f"{ctx.target_name}-{ctx.environment}-{service.id}.json"


def dev_services(ctx: Delivery, wanted: list[str]) -> list[Service]:
    svc = [s for s in running.find(ctx, wanted) if s.module is not None]
    lacking = [s.id for s in svc if not (s.dev.get("image") and s.dev.get("command"))]
    if lacking:
        raise DeliveryError(f"no remote dev declared for {', '.join(lacking)} (driver or module `dev.image`, `dev.command`)")
    return svc


def sync_one(ctx: Delivery, service: Service, *, full: bool = False) -> sync.SyncResult:
    src = module_dir(ctx, service)
    ws = ctx.places.of("workspace", service)
    result = sync.sync(ctx.transport, src, ws, sync.excludes(service, src), cache=_cache(ctx, service), full=full)
    ctx.out(f"[dev] {service.id}: {result.summary()} -> {ws}")
    return result


def up(ctx: Delivery, wanted: list[str]) -> int:
    _require_workspace(ctx)
    svc = dev_services(ctx, wanted)
    for line in preflight.all_checks(ctx, [s.id for s in svc]):
        ctx.out(f"[preflight] {line}")
    for s in svc:
        unit = ctx.places.unit(s)
        for kind in ("logs", "runtime", "workspace"):
            ctx.transport.mkdir(unit[kind])
        sync_one(ctx, s, full=True)
        running.place_files(ctx, s)
        running.set_mode(ctx, s, "workspace")
    running.regenerate(ctx)
    running.up(ctx, [s.id for s in svc])
    failed = [] if ctx.plan else running.wait_healthy(ctx, svc)
    if failed:
        ctx.out(f"[dev] not running: {'; '.join(failed)} (see: dev logs)")
        return 6
    for s in svc:
        ports = stack.host_ports(s, ctx.target, ctx.environment)
        ctx.out(f"[dev] {s.id} runs its workspace{' on host port(s) ' + ', '.join(map(str, ports)) if ports else ''}")
    return 0


def down(ctx: Delivery, wanted: list[str]) -> int:
    _require_workspace(ctx)
    svc = dev_services(ctx, wanted)
    for s in svc:
        running.set_mode(ctx, s, None)
    running.regenerate(ctx)
    back = [s.id for s in svc if running.current_release(ctx, s)]
    gone = [s.id for s in svc if s.id not in back]
    if back:
        for s in svc:
            if s.id in back:
                running.hand_over_secrets(ctx, [s], str(running.current_release(ctx, s)))
        running.up(ctx, back)
        ctx.out(f"[dev] {', '.join(back)}: back to their release")
    if gone:
        ctx.run(ctx.compose("rm", "-s", "-f", *gone), check=False)
        for sid in gone:
            ctx.run(ctx.engine("rm", "-f", naming.remote_container(ctx.project, ctx.environment, sid)), check=False)
        ctx.out(f"[dev] {', '.join(gone)}: stopped (no release to return to)")
    return 0


def logs(ctx: Delivery, wanted: list[str], follow: bool = False, tail: int = 200) -> int:
    ids = [s.id for s in running.find(ctx, wanted)]
    return ctx.transport.exec(ctx.compose("logs", "--tail", str(tail), *(["-f"] if follow else []), *ids),
                              stream=True, readonly=True).code


def status(ctx: Delivery, wanted: list[str]) -> list[str]:
    st = running.states(ctx)
    lines = []
    for s in running.find(ctx, wanted):
        state = st.get(s.id) or stack.State()
        mode = "workspace" if state.workspace else (f"release {state.release}" if state.release else
                                                     ("image" if s.module is None else "nothing"))
        lines.append(f"{s.id:<16} {s.tier:<10} {mode:<28} {running.health_of(ctx, s)}")
    return lines


def shell(ctx: Delivery, service: Service, command: list[str] | None = None) -> int:
    name = naming.remote_container(ctx.project, ctx.environment, service.id)
    return ctx.transport.interactive(ctx.engine("exec", "-it", name, *(command or ["sh"])))


def tunnel(ctx: Delivery, wanted: list[str]) -> int:
    forwards: list[tuple[int, int]] = []
    for s in running.find(ctx, wanted):
        forwards += [(p, p) for p in stack.host_ports(s, ctx.target, ctx.environment)]
        if s.dev.get("debugPort"):
            forwards.append((int(s.dev["debugPort"]), int(s.dev["debugPort"])))
    if not forwards:
        raise DeliveryError(f"nothing to forward: no host port declared for {', '.join(wanted) or 'any service'} in "
                            f"targets.{ctx.target_name}.ports.{ctx.environment}, and no dev.debugPort")
    ctx.out("[dev] tunnel " + ", ".join(f"localhost:{a} -> {ctx.target_name}:{b}" for a, b in forwards) + " (Ctrl-C stops)")
    return ctx.transport.tunnel(forwards)


def react(ctx: Delivery, service: Service, changed: list[str]) -> str:
    what = sync.reaction(changed, service.dev.get("reactions") or [])
    if what == "restart":
        ctx.run(ctx.compose("restart", service.id))
    elif what == "rebuild":
        if not service.dev.get("build"):
            raise DeliveryError(f"{service.id}: a rebuild reaction needs the driver's or module's `dev.build`")
        ctx.run(ctx.compose("exec", "-T", service.id, *service.dev["build"]))
    ctx.out(f"[dev] {service.id}: {len(changed)} change(s) -> {what}")
    return what


def watch(ctx: Delivery, wanted: list[str], *, poll: float = 0.5, stop: Callable[[], bool] | None = None,
          reconnect: Callable[[], None] | None = None, max_backoff: float = 30.0) -> int:
    """Until Ctrl-C (or `stop()`): poll, debounce, sync, react. A dropped connection is retried with
    backoff (`reconnect` reopens it) and followed by a full sync of every watched service."""
    _require_workspace(ctx)
    svc = dev_services(ctx, wanted)
    srcs = {s.id: module_dir(ctx, s) for s in svc}
    pats = {s.id: sync.excludes(s, srcs[s.id]) for s in svc}
    seen = {s.id: sync.snapshot(srcs[s.id], pats[s.id]) for s in svc}
    for s in svc:
        sync_one(ctx, s)
    ctx.out(f"[dev] watching {', '.join(s.id for s in svc)} (Ctrl-C stops)")
    backoff, pending_full = 1.0, False
    try:
        while not (stop and stop()):
            ctx.sleep(poll)
            try:
                if pending_full:
                    if reconnect:
                        reconnect()
                    for s in svc:
                        sync_one(ctx, s, full=True)
                    pending_full, backoff = False, 1.0
                    ctx.out("[dev] reconnected; full sync done")
                for s in svc:
                    now = sync.snapshot(srcs[s.id], pats[s.id])
                    if now == seen[s.id]:
                        continue
                    debounce = float(s.dev.get("debounceMs") or 800) / 1000.0
                    while True:  # settle: a burst of saves is one change
                        ctx.sleep(debounce)
                        later = sync.snapshot(srcs[s.id], pats[s.id])
                        if later == now:
                            break
                        now = later
                    seen[s.id] = now
                    result = sync_one(ctx, s)
                    if result.changed() or result.way == "rsync":
                        react(ctx, s, result.changed() or sorted(set(now) ^ set(seen[s.id])) or ["*"])
            except TransportError as e:
                ctx.out(f"[dev] connection lost ({e}); retrying in {backoff:.0f}s")
                ctx.sleep(backoff)
                backoff, pending_full = min(backoff * 2, max_backoff), True
    except KeyboardInterrupt:
        ctx.out("[dev] watch stopped")
    return 0


def now() -> float:
    return time.time()
