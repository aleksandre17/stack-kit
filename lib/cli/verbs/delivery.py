"""Deploy and operate: package, deploy, release, ops, targets, layout -- each a plan before it acts."""
from __future__ import annotations

import sys
from pathlib import Path

from lib import catalogs, identity
from lib.cli import remote, tools
from lib.cli.registry import Args, Option, Verb
from lib.cli.remote import PLAN, YES


def _manifest() -> dict:
    from lib.project_context import load_manifest

    return load_manifest(tools.project_root())


def _modules(words: list[str], manifest: dict) -> list[str]:
    """Module ids in deploy order (catalogs.roles `deployOrder`): the named ones, or `all` deployable."""
    from lib.cli.verbs.mod import alias
    from lib.delivery.model import deployable
    from lib.modules import module_role

    every = [m for m, c in (manifest.get("modules") or {}).items() if isinstance(c, dict) and deployable(manifest, m)]
    if not words or words == ["all"]:
        chosen = every
    else:
        chosen = []
        for w in words:
            m = alias(w) or w
            if m not in every:
                raise ValueError(f"'{w}' is no deployable module ({', '.join(every) or 'none'})")
            chosen.append(m)
    order = catalogs.ordered("roles", "deployOrder", manifest)
    rank = lambda m: order.index(module_role(manifest, m)) if module_role(manifest, m) in order else len(order)
    return sorted(chosen, key=lambda m: (rank(m), every.index(m)))


# ── package ─────────────────────────────────────────────────────────────────

def package_module(module: str) -> Path:
    """The driver's declared package step, recorded, then the one archive of this commit."""
    from lib import package

    root = tools.project_root()
    manifest = _manifest()
    p = package.plan(root, manifest, module)
    print(f"[package] {module}: {p['command']} {' '.join(p['args'])}".rstrip())
    code = tools.recorded("package", "package", module, lambda: tools.driver_command(module, p["command"], p["args"]))
    if code:
        raise package.PackageError(f"{module}: the package step failed (exit {code})")
    archive = package.pack(root, manifest, module)
    print(f"[package] {module}: {archive.relative_to(root).as_posix()}")
    return archive


def _package(a: Args) -> int:
    from lib import package

    if not a.positional:
        print(f"  Usage: {identity.KIT_NAME} package <module> [<module> ...]", file=sys.stderr)
        return 2
    try:
        for m in _modules(a.positional, _manifest()):
            package_module(m)
    except (package.PackageError, ValueError) as e:
        print(f"  [package] ERROR: {e}", file=sys.stderr)
        return 1
    return 0


# ── deploy ──────────────────────────────────────────────────────────────────

def _deploy(a: Args) -> int:
    from lib import package
    from lib.delivery import release

    manifest = _manifest()
    root = tools.project_root()
    try:
        modules = _modules(a.positional, manifest)
    except ValueError as e:
        print(f"  [deploy] {e}", file=sys.stderr)
        return 2
    if not modules:
        print("  [deploy] nothing deployable in this project", file=sys.stderr)
        return 2
    env = a.value("--env") or identity.env("ENVIRONMENT") or catalogs.default_environment("deploy", manifest)
    # The checkout it packages carries no credential-shaped value -- known before any target is opened.
    from lib import secret_scan

    try:
        leaks = [] if a.value("--artifact") else secret_scan.tree(root, manifest)
    except secret_scan.ScanError as e:
        print(f"  [deploy] NOT RUN: {e}", file=sys.stderr)
        return 2
    if leaks:
        print(f"  [deploy] refused: the checkout carries {len(leaks)} credential-shaped value(s) -- "
              f"`scan secrets` names them (values are never printed)", file=sys.stderr)
        return 5
    # The target first: a pending or unselectable one refuses before anything is built.
    from lib.delivery.context import DeliveryError

    try:
        remote.context(a, out=lambda s: None).close()
    except DeliveryError as e:
        print(f"  [deploy] NOT RUN: {e}", file=sys.stderr)
        return e.code
    clean = (catalogs.entry("environments", env, manifest) or {}).get("requireClean")
    artifact = a.value("--artifact")
    if artifact and len(modules) > 1:
        print("  [deploy] --artifact names one module's archive: deploy one module with it", file=sys.stderr)
        return 2
    archives: dict[str, Path | None] = {}
    try:
        prov = package.provenance(root)
        if clean and prov["dirty"] and not artifact:
            print(f"  [deploy] refused: the checkout is dirty ({prov['revision']}); {env} takes a release of a clean "
                  f"commit only -- commit first", file=sys.stderr)
            return 5
        for m in modules:
            if artifact:
                archives[m] = Path(artifact).resolve()
            elif a.has("--plan") and not package.latest(root, m):
                archives[m] = None  # planned as the package of this commit; nothing is built to plan
            else:
                archives[m] = package.latest(root, m) or package_module(m)
    except package.PackageError as e:
        print(f"  [deploy] ERROR: {e}", file=sys.stderr)
        return 5 if "provenance" in str(e) or "commit" in str(e) else 1
    for m in modules:
        if archives[m] is None:
            print(f"[deploy] {m}: not packaged yet -- a deploy packages it first (`package {m}`), then:")
        code = remote.run(a, f"deploy {m}", lambda ctx, m=m: release.release(ctx, m, archives[m]), module=m)
        if code:
            return code
    return 0


# ── release ─────────────────────────────────────────────────────────────────

def _release(a: Args) -> int:
    from lib.delivery import release

    sub = a.positional[0] if a.positional else "list"
    rest = a.positional[1:]
    if sub == "list":
        def show(ctx):
            if not ctx.plan:
                for line in release.listing(ctx, rest):
                    print(line)
            return 0
        return remote.run(a, "release list", show, plan_first=False, read_only=True)
    if sub == "rollback":
        to = a.value("--to")
        return remote.run(a, f"rollback {' '.join(rest) or 'all'}{' to ' + to if to else ''}",
                          lambda ctx: release.rollback(ctx, rest, to))
    print(f"  Usage: {identity.KIT_NAME} release list|rollback [module ...] [--to <id>] --env <id>", file=sys.stderr)
    return 2


# ── ops ─────────────────────────────────────────────────────────────────────

def _ops(a: Args) -> int:
    from lib.delivery import manage

    sub = a.positional[0] if a.positional else ""
    rest = a.positional[1:]
    if sub == "status":
        def show(ctx):
            if not ctx.plan:
                for line in manage.status(ctx, rest):
                    print(line)
            return 0
        return remote.run(a, "status", show, plan_first=False, read_only=True)
    if sub == "logs":
        return remote.run(a, "logs", lambda ctx: 0 if ctx.plan else manage.logs(ctx, rest, follow=a.has("--follow"),
                                                                               tail=int(a.value("--tail", "200"))),
                          plan_first=False, read_only=True)
    if sub in ("start", "stop", "restart"):
        return remote.run(a, f"{sub} {' '.join(rest) or 'all'}", lambda ctx: manage.lifecycle(ctx, sub, rest))
    if sub == "restart-check":
        def check(ctx):
            failures = manage.restart_check(ctx, rest)
            for f in failures:
                print(f"  [ops] FAILED {f}")
            return 6 if failures else 0
        return remote.run(a, f"restart-check {' '.join(rest) or 'all'}", check)
    if sub == "prune":
        if a.has("--schedule"):
            return remote.run(a, "schedule the safe prune", lambda ctx: manage.schedule_prune(ctx, a.value("--at") or manage.CRON_DEFAULT))
        return remote.run(a, "safe prune", manage.prune)
    if sub == "rebuild":
        return remote.run(a, f"rebuild {' '.join(rest) or 'all'}", lambda ctx: manage.rebuild(ctx, rest))
    if sub == "rm":
        return remote.run(a, f"rm {' '.join(rest)}", lambda ctx: manage.rm(ctx, rest), destructive=True)
    if sub == "nuke":
        return remote.run(a, "nuke the environment", manage.nuke, destructive=True)
    print(f"  Usage: {identity.KIT_NAME} ops status|logs|start|stop|restart|rebuild|rm|nuke [module|service|tier ...] --env <id>",
          file=sys.stderr)
    return 2


# ── targets ─────────────────────────────────────────────────────────────────

def _targets(a: Args) -> int:
    from lib import targets
    from lib.delivery import tree

    root = tools.project_root()
    manifest = _manifest()
    if a.has("--init"):
        return remote.run(a, "init the tree", lambda ctx: _say(tree.init(ctx)))
    if a.has("--verify"):
        def check(ctx):
            if ctx.plan:
                return 0
            drift = tree.verify(ctx)
            for line in drift:
                print(f"  {line}")
            print(f"[verify] {ctx.places.project_dir}: " + (f"{len(drift)} drift(s)" if drift else "matches the declared tree"))
            return 1 if drift else 0
        return remote.run(a, "verify", check, plan_first=False, read_only=True)
    try:
        data = targets.load(root, manifest)
    except targets.TargetError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if data is None:
        print("[targets] none declared (manifest `deploy.targets`)")
        return 0
    if a.has("--health"):
        env = a.value("--env") or catalogs.default_environment("deploy", manifest)
        try:
            name, t = targets.select(data, a.value("--target"), env, manifest)
            targets.reachable(name, t)
        except targets.TargetError as e:
            print(f"[health] NOT VERIFIED: {e}")
            return 2
        urls = targets.health_urls(t, env)
        if not urls:
            print(f"[health] target {name} ({env}) declares no health endpoint -- nothing checked (targets.{name}.health.{env})")
            return 0
        failed = targets.check_health_urls(urls, attempts=int(a.value("--attempts", "12")), pause=float(a.value("--pause", "5")))
        oidc = ((t.get("oidc") or {}).get(env)) or {}
        if oidc.get("issuer"):
            ca = str(root / oidc["caFile"]) if oidc.get("caFile") else ""
            found = targets.check_oidc(str(oidc["issuer"]), ca_file=ca)
            failed += [f"oidc {f}" for f in found]
            if not found:
                print(f"[health] oidc {oidc['issuer']}: discovery and JWKS ready")
        for f in failed:
            print(f"[health] FAILED {f}")
        return 1 if failed else 0
    return _list_targets(root, manifest, data, plan=a.has("--plan"), env_only=a.value("--env"))


def _say(lines: list[str]) -> int:
    for line in lines:
        print(f"  {line}")
    return 0


def _list_targets(root: Path, manifest: dict, data: dict, *, plan: bool, env_only: str) -> int:
    from lib import naming, targets
    from lib.delivery.model import all_services

    defaults = data.get("defaults") or {}
    project = naming.project_slug(manifest, root)
    for name, t in (data.get("targets") or {}).items():
        marks = [env for env, n in defaults.items() if n == name]
        head = f"{name}{' (default: ' + ', '.join(marks) + ')' if marks else ''}  runtime={t.get('runtime')}"
        if t.get("pending"):
            print(f"{head}  PENDING: {t['pending']}")
            continue
        ssh = t.get("ssh") or {}
        cmds = targets.runtime_commands(t, manifest)
        print(f"{head}  {t.get('user')}@{t.get('host')}:{t.get('port', 22)}  root={targets.declared_root(t)}  "
              f"identity={targets.identity_kind(t)}  hostKeys={ssh.get('hostKeys', 'pinned')}"
              + (f"  compose={' '.join(cmds['compose'])}" if cmds["compose"] else ""))
        if not plan:
            continue
        envs = catalogs.ids("environments", manifest)
        services = all_services(manifest)
        first = targets.Places(t, project=project, environment=envs[0], environments=envs)
        print(f"  {first.project_dir}                  the project's own directory (never the root)")
        print(f"    {targets.MARKER}            ownership: {{\"project\": \"{project}\", \"repository\": \"{targets.repository_identity(root)}\"}}")
        for env in envs:
            if env_only and env != env_only:
                continue
            p = targets.Places(t, project=project, environment=env, environments=envs)
            print(f"    {p.environment_dir}       compose project {naming.remote_compose_project(project, env)}, "
                  f"network {naming.remote_network(project, env)}")
            print(f"      stack        {p.of('stackCompose')}")
            print(f"      state        {p.of('stackState')}")
            print(f"      infra        {p.of('infra')}")
            print(f"      backups      {p.of('backups')}")
            for s in services:
                ports = ((t.get("ports") or {}).get(env) or {}).get(s.id) or []
                if s.module is None:
                    print(f"      service {s.id} ({s.tier}, stack image {s.spec.get('image')})"
                          + (f"  ports {','.join(map(str, ports))}" if ports else ""))
                    continue
                print(f"      {s.tier}/{s.id}  module {s.module} ({s.kind}): {p.of('unit', s)}"
                      + (f"  ports {','.join(map(str, ports))}" if ports else ""))
                kinds = ["releases", "current", "logs", "runtime", "stackEnv"]
                if env in catalogs.flagged("environments", "workspace", manifest):
                    kinds.append("workspace")
                for kind in kinds:
                    print(f"        {kind:<10} {p.of(kind, s)}")
        if targets.unproven():
            print(f"  unproven: {targets.unproven()}")
    return 0


# ── layout migrate ──────────────────────────────────────────────────────────

def _layout(a: Args) -> int:
    from lib.delivery import legacy_layout

    if a.positional[:1] != ["migrate"]:
        print(f"  Usage: {identity.KIT_NAME} layout migrate --target <t> --env <id> [--approve]", file=sys.stderr)
        return 2

    def act(ctx):
        moves = legacy_layout.plan(ctx)
        for line in legacy_layout.report(moves):
            print(f"  {line}")
        if not a.has("--approve") or ctx.plan:
            if not ctx.plan:
                return 0
            return 0
        legacy_layout.apply(ctx, moves)
        for line in legacy_layout.report(moves):
            print(f"  {line}")
        return 0
    if not a.has("--approve"):
        return remote.run(a, "layout migrate (plan; --approve applies)", act, plan_first=False)
    return remote.run(a, "layout migrate", act, destructive=True)


TARGET_OPTS = [PLAN, YES]
VERBS = [
    Verb("package", "build once: the driver's package step, then one archive of this commit with its provenance",
         ["package <module|all> [...]"], _package, group="delivery", exits=(0, 1, 2),
         examples=["package api"],
         details="The archive is `.stack-kit/artifacts/<module>-<commit>[-dirty].tgz` with its sha256 beside it; "
                 "`release.json` inside it carries the commit, `git describe --tags --always --dirty` and the services."),
    Verb("deploy", "build -> package -> ship -> up -> health, for a module or all, to one environment",
         ["deploy <module|all> --env <id> [--target <t>] [--plan] [--yes] [--artifact <archive>]"],
         _deploy, options=[*TARGET_OPTS, Option("--artifact", "deploy this archive (CI: the one packaged earlier)", "archive")],
         group="delivery", exits=(0, 1, 2, 3, 4, 5, 6),
         examples=["deploy api --env dev --plan", "deploy all --env prod --yes"],
         details="An environment that requires a clean checkout refuses a dirty one; one that asks first (`confirm`) asks "
                 "on a terminal and refuses without one unless --yes. A commit already packaged is not rebuilt. A failed "
                 "health rolls back where the environment declares it."),
    Verb("release", "a unit's releases, and moving `current` back", ["release list [module ...] --env <id>",
                                                                    "release rollback [module ...] [--to <id>] --env <id>"],
         _release, options=[*TARGET_OPTS, Option("--to", "the release to roll back to (default: the one before current)", "id")],
         group="delivery", exits=(0, 1, 2, 3, 5, 6), examples=["release list --env prod", "release rollback api --env prod --yes"],
         details="`list` marks `current` with `*` and, with `!` and why, a release that cannot run as its service is "
                 "declared now. `rollback` is a transaction: such a release is refused (exit 5) with nothing changed and "
                 "the remedy (deploy that commit); otherwise the stack is brought up on the release -- its image built "
                 "when missing -- and `current` moves only once each service is healthy on that release's image. Any "
                 "failure brings the previous release back up, `current` never having left it, and exits 6 naming the "
                 "failure and the build log."),
    Verb("ops", "operate a deployed environment, per service, module or tier (or all)",
         ["ops status|logs|start|stop|restart|rebuild [module|service|tier ...] --env <id>",
          "ops restart-check [module|service|tier ...] --env <id>   (restart is idempotent: healthy, same image, no drift)",
          "ops rm <module|service|tier ...> --env <id> [--yes]", "ops nuke --env <id> [--yes]",
          "ops prune [--schedule [--at '<cron>']] --env <id>   (builder cache and dangling images only)"],
         _ops, options=[*TARGET_OPTS, Option("--follow", "logs: keep following"), Option("--tail", "logs: lines (default 200)", "n"),
                        Option("--schedule", "prune: install it in the target user's crontab, once per host"),
                        Option("--at", "prune --schedule: the cron schedule (default weekly)", "cron")],
         group="delivery", exits=(0, 1, 2, 3, 6), examples=["ops status --env prod", "ops logs api --env dev --follow"],
         details="rm and nuke ask first and act only inside the project's own environment directory, which must carry "
                 "this project's ownership marker; never at the target's root."),
    Verb("targets", "the declared deploy targets: list, plan the tree, create it, verify it, check health",
         ["targets [--plan] [--env <id>]", "targets --init --target <t> --env <id> [--plan]",
          "targets --verify --target <t> --env <id>", "targets --health --target <t> --env <id>"],
         _targets, options=[PLAN, YES, Option("--init", "create the project's tree with its ownership marker (idempotent)"),
                            Option("--verify", "read-only: marker, tree, current, prune limit, runtime, ports, disk"),
                            Option("--health", "the target's declared health URLs answer below 400, and its OIDC provider is ready (discovery, JWKS)"),
                            Option("--attempts", "health: attempts per URL (default 12)", "n"),
                            Option("--pause", "health: seconds between attempts (default 5)", "s")],
         group="delivery", exits=(0, 1, 2, 3, 4), examples=["targets --plan", "targets --init --target linux --env dev"],
         details="--init refuses a non-empty directory without this project's marker; --verify reads the declared state "
                 "(places, marker, compose file, env and runtime config digests, each service's running release, runtime, "
                 "ports, disk) against the host, read-only, and exits 1 on drift, 2 when nothing could be verified; a drift is "
                 "undone by the verb that owns it (deploy, release rollback)."),
    Verb("layout", "move this project's services out of a tree laid out before the layout",
         ["layout migrate --target <t> --env <id> [--approve] [--yes]"], _layout,
         options=[PLAN, YES, Option("--approve", "apply the planned moves (never automatic)")],
         group="delivery", exits=(0, 1, 2, 3),
         details="Only what the target declares as this project's (`legacyLayout`) moves, never a folder a listing finds; "
                 "a direct child of the shared root is never moved."),
]
