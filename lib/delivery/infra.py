"""The infra stack on a target (`infra remote sync|up|down|status|purge`, `infra tunnel`): its compose
files in the layout's `infra` place of the environment, run as the compose project
{project}-{environment}-infra under the target's declared compose invocation, joined to the
environment's network. It replaces the PowerShell remote infra and the prerequisites script.
"""
from __future__ import annotations

import posixpath

from lib import naming
from lib.delivery.context import Delivery, DeliveryError
from lib.delivery.running import write_if_changed


def _resolver(ctx: Delivery):
    from lib.resolution import Resolver

    return Resolver(ctx.root)


def compose(ctx: Delivery, *args: str) -> list[str]:
    r = _resolver(ctx)
    base = ctx.places.of("infra")
    files = [a for f in r.infra_compose_files() for a in ("-f", posixpath.join(base, f))]
    env = posixpath.join(base, ".env.runtime")
    return [*ctx.commands["compose"], "-p", naming.remote_named_network(ctx.project, ctx.environment, "infra"),
            "--project-directory", base, "--env-file", env, *files, *args]


def sync(ctx: Delivery) -> list[str]:
    r = _resolver(ctx)
    base = ctx.places.of("infra")
    ctx.transport.mkdir(base)
    written = []
    for rel in r.infra_sync_paths():
        if write_if_changed(ctx, posixpath.join(base, rel), (r.infra_compose_dir() / rel).read_bytes()):
            written.append(rel)
    from lib import envfile, catalogs

    values = envfile.merged(envfile.run_files(ctx.secrets_root, "infra", ctx.environment,
                                              catalogs.ids("environments", ctx.manifest)))
    values.setdefault("STACK_KIT_NETWORK", naming.remote_network(ctx.project, ctx.environment))
    values.setdefault("INFRA_PREFIX", naming.remote_compose_project(ctx.project, ctx.environment))
    data = "".join(f"{k}={v}\n" for k, v in sorted(values.items())).encode("utf-8")
    if write_if_changed(ctx, posixpath.join(base, ".env.runtime"), data, "600"):
        written.append(".env.runtime")
    return written


def act(ctx: Delivery, action: str) -> int:
    if not ctx.commands["compose"]:
        raise DeliveryError(f"target {ctx.target_name} runs no compose stack")
    if action in ("sync", "up"):
        for rel in sync(ctx):
            ctx.out(f"[infra] wrote {posixpath.join(ctx.places.of('infra'), rel)}")
    if action == "up":
        net = naming.remote_network(ctx.project, ctx.environment)
        if ctx.transport.exec(ctx.engine("network", "inspect", net), readonly=True).code != 0:
            ctx.run(ctx.engine("network", "create", net))
        ctx.run(compose(ctx, "up", "-d", "--remove-orphans"))
    elif action == "down":
        ctx.run(compose(ctx, "down"))
    elif action == "status":
        return ctx.transport.exec(compose(ctx, "ps"), stream=True, readonly=True).code
    elif action == "purge":
        ctx.run(compose(ctx, "down", "-v"))
    elif action != "sync":
        raise DeliveryError(f"no infra action '{action}' (sync, up, down, status, purge)", 2)
    return 0


def tunnel(ctx: Delivery) -> int:
    forwards = [(int(f["local"]), int(f["remote"])) for f in _resolver(ctx).infra_tunnel_forwards()]
    ctx.out("[infra] tunnel " + ", ".join(f"localhost:{a} -> {ctx.target_name}:{b}" for a, b in forwards))
    return ctx.transport.tunnel(forwards)
