"""`dev`: remote dev on the target (up, down, sync, watch, logs, status, shell, tunnel), and the local
modes of `dev up` (hybrid, local, docker) on this machine."""
from __future__ import annotations

import sys

from lib import identity
from lib.cli import remote, tools
from lib.cli.registry import Args, Option, Verb
from lib.cli.remote import PLAN, YES

LOCAL_MODES = ("hybrid", "local", "docker")


def _dev(a: Args) -> int:
    from lib.delivery import dev, running

    sub = a.positional[0] if a.positional else "help"
    rest = a.positional[1:]
    mode = a.value("--mode")
    if not a.value("--env") and not identity.env("ENVIRONMENT"):
        from lib import catalogs

        workspace = catalogs.flagged("environments", "workspace")
        if workspace:
            a.flags["--env"] = workspace[0]  # remote dev's environment unless one is asked for
    if sub == "up" and mode in LOCAL_MODES:
        extra = [f for f in ("--no-infra", "--no-tunnel") if a.has(f)]
        return tools.powershell_script("toolkit/dev/Invoke-DevUp.ps1", ["up", *rest, "--mode", mode, *extra])
    if sub == "up":
        return remote.run(a, f"dev up {' '.join(rest) or 'all'}", lambda ctx: dev.up(ctx, rest))
    if sub == "down":
        return remote.run(a, f"dev down {' '.join(rest) or 'all'}", lambda ctx: dev.down(ctx, rest))
    if sub == "sync":
        def one(ctx):
            dev._require_workspace(ctx)
            for s in dev.dev_services(ctx, rest):
                dev.sync_one(ctx, s, full=a.has("--full"))
            return 0
        return remote.run(a, f"dev sync {' '.join(rest) or 'all'}", one)
    if sub == "watch":
        return remote.run(a, f"dev watch {' '.join(rest) or 'all'}",
                          lambda ctx: 0 if ctx.plan else dev.watch(ctx, rest), plan_first=False)
    if sub == "logs":
        return remote.run(a, "dev logs", lambda ctx: 0 if ctx.plan else dev.logs(ctx, rest, follow=a.has("--follow")),
                          plan_first=False)
    if sub == "status":
        def show(ctx):
            if not ctx.plan:
                for line in dev.status(ctx, rest):
                    print(line)
            return 0
        return remote.run(a, "dev status", show, plan_first=False)
    if sub == "shell":
        if len(rest) != 1:
            print(f"  Usage: {identity.KIT_NAME} dev shell <module>", file=sys.stderr)
            return 2
        return remote.run(a, f"dev shell {rest[0]}", lambda ctx: dev.shell(ctx, running.find(ctx, rest)[0]),
                          plan_first=False)
    if sub == "tunnel":
        return remote.run(a, f"dev tunnel {' '.join(rest) or 'all'}", lambda ctx: dev.tunnel(ctx, rest), plan_first=False)
    print(f"  Usage: {identity.KIT_NAME} dev up|down|sync|watch|logs|status|shell|tunnel [module ...] [--target <t>]",
          file=sys.stderr)
    return 2


VERB = Verb(
    "dev", "remote dev: the module's source synced into its workspace and run by its driver's dev container",
    ["dev up <module|all> [--target <t>] [--plan]", "dev up <module|all> --mode hybrid|local|docker   (this machine)",
     "dev sync <module> [--full]", "dev watch <module|all>", "dev down <module|all>", "dev logs <module> [--follow]",
     "dev status", "dev shell <module>", "dev tunnel <module>"],
    _dev, options=[PLAN, YES, Option("--mode", "up: a local mode instead (hybrid, local, docker)", "mode"),
                   Option("--full", "sync: compare every file again (after a lost connection)"),
                   Option("--no-infra", "up --mode hybrid: the infra stack is running already"),
                   Option("--no-tunnel", "up --mode hybrid: open no tunnel"),
                   Option("--follow", "logs: keep following")],
    group="dev", exits=(0, 1, 2, 3, 4, 6),
    examples=["dev up api --target linux --plan", "dev watch api", "dev tunnel api"],
    details="The workspace is the layout's ({root}/{project}/dev/{tier}/{service}/workspace). A sync uses rsync when "
            "both ends have it, else the built-in index + tar stream over ssh; env files, keys and credential files are "
            "never sent. `watch` polls (no extra dependency), debounces, syncs, and reacts as the driver declares: "
            "hot-reload, restart, or rebuild; a lost connection is retried and followed by a full sync.")
