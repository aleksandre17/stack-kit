"""The project's verbs that run one kit tool each -- the tool keeps its own argv and exit code."""
from __future__ import annotations

from lib.cli import tools
from lib.cli.registry import Args, Option, Verb


def _py(rel: str):
    return lambda a: tools.python_script(rel, a.raw)


def _init(a: Args) -> int:
    if "--plan" in a.raw or "--approve" in a.raw:  # `init --plan` is `extend module`: the draft from the tree
        code = tools.python_script("lib/draft.py", a.raw)
        if code or "--plan" in a.raw:
            return code
    return tools.powershell_script("toolkit/init/Invoke-ProjectInit.ps1", ["-PackageRoot", str(tools.KIT), *a.raw])


def _stack(a: Args) -> int:
    """The local development stack: compose-gen's files under stack.composeDir, every module
    folder's env files of the environment, run by this machine's declared compose invocation."""
    import subprocess

    from lib import catalogs, envfile, naming, targets
    from lib.project_context import ProjectContext
    from lib.stack_endpoints import stack_endpoint_lines

    ctx = ProjectContext.discover()
    prod = "--prod" in a.raw or "-Prod" in a.raw or a.value("--env") == "prod"
    env = "prod" if prod else (a.value("--env") or "dev")
    rest = [x for x in a.positional if x not in ("--prod", "-Prod")]
    compose_dir = ctx.root / str((ctx.manifest.get("stack") or {}).get("composeDir") or "ops/compose/stack")
    files: list[str] = []
    for folder in ctx.list_secrets_module_folders():
        for f in envfile.folder_files(ctx.secrets_root, folder, env, catalogs.ids("environments", ctx.manifest)):
            if str(f) not in files:
                files.append(str(f))
    cmd = targets.local_commands(ctx.manifest)["compose"]
    if not cmd:
        print("  [stack] no target runtime is declared `local` (catalogs.targetRuntimes)")
        return 2
    print(f"\n  {naming.project_slug(ctx.manifest, ctx.root)} stack ({env})")
    for line in stack_endpoint_lines(ctx):
        print(f"  {line}")
    argv = [*cmd, *(x for f in files for x in ("--env-file", f)),
            "-f", "docker-compose.prod.yml" if prod else "docker-compose.yml", *rest]
    return subprocess.run(argv, cwd=str(compose_dir)).returncode


def _infra(a: Args) -> int:
    from lib.cli import remote
    from lib.delivery import infra

    mode = a.positional[0] if a.positional else "help"
    if mode == "remote" and len(a.positional) > 1:
        action = a.positional[1]
        return remote.run(a, f"infra {action}", lambda ctx: infra.act(ctx, action),
                          destructive=action == "purge", plan_first=action != "status")
    if mode == "tunnel":
        return remote.run(a, "infra tunnel", infra.tunnel, plan_first=False)
    rest = [x for x in a.raw if x not in ("--prod",)] + (["-Prod"] if "--prod" in a.raw or a.value("--env") == "prod" else [])
    return tools.powershell_script("toolkit/infra/Invoke-Infra.ps1", [x for x in rest if x not in ("--env", "prod", "dev")])


def _hybrid(a: Args) -> int:
    from lib.cli.verbs.mod import alias

    if len(a.positional) < 2 or a.positional[0] != "boot":
        print("  Usage: hybrid boot <alias|module> [--env <environment>]")
        return 2
    module = alias(a.positional[1]) or a.positional[1]
    env = a.value("--env") or "dev"
    return tools.powershell_script("toolkit/hybrid/Invoke-HybridRun.ps1", ["-ModuleId", module, "-Environment", env],
                                   {"STACK_KIT_MODULE_ID": module})


def _config(a: Args) -> int:
    """The env-value policy of the configuration catalogue against this machine's env files."""
    from lib import catalogs, config_policy, envfile
    from lib.project_context import ProjectContext

    ctx = ProjectContext.discover()
    catalogue = config_policy.catalogue_of(ctx.root, ctx.manifest)
    if not catalogue:
        print("  [config] no configuration catalogue is declared (manifest `config.keys`)")
        return 0
    envs = [a.value("--env")] if a.value("--env") else catalogs.ids("environments", ctx.manifest)
    folders = a.positional[1:] or ctx.list_secrets_module_folders()
    found = []
    for env in envs:
        for folder in folders:
            values = envfile.merged(envfile.run_files(ctx.secrets_root, folder, env, catalogs.ids("environments", ctx.manifest)))
            found += config_policy.problems(catalogue, values, folder=folder, environment=env)
    for line in found:
        print(f"  {line}")
    print(f"  [config] {len(found)} finding(s) over {', '.join(envs)}" if found else f"  [config] the policy holds ({', '.join(envs)})")
    return 1 if found else 0


def _migrations(a: Args) -> int:
    from lib import migrations_gate
    from lib.project_context import ProjectContext

    ctx = ProjectContext.discover()
    if a.positional[:1] == ["lock"]:
        added = migrations_gate.lock(ctx.root, ctx.manifest)
        for rel in added:
            print(f"  recorded {rel}")
        print(f"  [migrations] {len(added)} new migration(s) recorded in {migrations_gate.LEDGER}")
        return 0
    found = migrations_gate.ledger_problems(ctx.root, ctx.manifest) + migrations_gate.check(ctx.root, ctx.manifest)
    for line in found:
        print(f"  {line}")
    print("  [migrations] " + (f"{len(found)} finding(s)" if found else "structure only, and every recorded one unchanged"))
    return 1 if found else 0


def _render(a: Args) -> int:
    """The generated projections: each module's effective container recipe, each environment's stack compose."""
    from lib import projections
    from lib.project_context import ProjectContext

    ctx = ProjectContext.discover()
    if a.has("--check"):
        errors, notices = projections.drift(ctx.root, ctx.manifest)
        for line in [*errors, *notices]:
            print(f"  {line}")
        print(f"  [render] {len(errors)} stale projection(s)" if errors else "  [render] every rendered projection is current")
        return 1 if errors else 0
    for line in projections.write(ctx.root, ctx.manifest, plan=a.has("--plan")):
        print(f"  {line}")
    return 0


def _scan(a: Args) -> int:
    from lib import secret_scan
    from lib.project_context import ProjectContext

    if a.positional[:1] != ["secrets"]:
        print("  Usage: scan secrets [--history]")
        return 2
    ctx = ProjectContext.discover()
    try:
        lines = secret_scan.main_lines(ctx.root, ctx.manifest, a.has("--history"))
    except secret_scan.ScanError as e:
        print(f"  [scan] NOT RUN: {e}")
        return 2
    for line in lines:
        print(f"  {line}")
    print("  [scan] " + (f"{len(lines)} finding(s) -- values are never printed; allow one by path and rule with its reason "
                         f"(security.allow), or rotate it and list its fingerprint (security.knownLeaks)" if lines
                         else "no credential-shaped value" + (" in the tree or its history" if a.has("--history") else " in the tree")))
    return 1 if lines else 0


VERBS = [
    Verb("init", "bootstrap a host, or draft its manifest from the tree", ["init", "init --plan", "init --approve <who>"],
         _init, passthrough=True, examples=["init --plan"],
         details="`--plan` drafts the manifest from the evidence each driver declares (declared fields always win); "
                 "`--approve <who>` writes the draft."),
    Verb("validate", "validate the manifest, its declarations and the deploy targets", ["validate [--stages]"],
         _py("lib/validate_manifest.py"), passthrough=True, exits=(0, 1)),
    Verb("migrate", "carry a host's older declarations into their current homes", ["migrate [--apply]"],
         _py("lib/migrate_manifest.py"), passthrough=True, exits=(0, 1),
         details="Without --apply it lists what would change. It is the only reader of the legacy homes "
                 "(deploy.env, .env.deploy, DEPLOY_*/COMPOSE_* keys): it moves their values into the manifest and "
                 "the targets file, and removes them."),
    Verb("config", "the configuration catalogue's env-value policy against this machine's env files (names, never values)",
         ["config check [module ...] [--env <id>]"], _config, exits=(0, 1),
         examples=["config check --env prod"],
         details="The same policy every release runs before it writes an env file: required (or required only in an "
                 "environment), no placeholder, a minimum length, a format (positive-int, url, https-url without "
                 "localhost), values an environment forbids (a wildcard CORS origin in prod), keys another requires."),
    Verb("migrations", "the migrations' ledger: a recorded one is never edited or removed; each is structure only",
         ["migrations check", "migrations lock"], _migrations, exits=(0, 1),
         details="`lock` records every migration the drivers' declarations find (sha256, line endings normalised) in "
                 "ops/stack-kit/migrations.lock.json; validate then refuses a recorded migration that changed or is gone."),
    Verb("render", "write what a deploy runs into the host as generated projections: each module's container recipe, each environment's stack compose",
         ["render [--plan]", "render --check"], _render,
         options=[Option("--plan", "say what would be written"), Option("--check", "report a projection its sources no longer render")],
         exits=(0, 1),
         details="Each file carries a header naming its sources -- edit those, not it. The release id and the packaged "
                 "artifact's name are written symbolically ({release}, the driver's artifact glob). validate reports a stale "
                 "projection; a release refuses one (exit 5). Paths: manifest `projections.containers` "
                 "(default ops/containers/{module}/Dockerfile) and `projections.stack` (default ops/compose/stack/{environment}/compose.yml)."),
    Verb("scan", "the secret boundary: credential-shaped values in the tracked tree (and, --history, every commit)",
         ["scan secrets [--history]"], _scan, options=[Option("--history", "every line any commit added, too")], exits=(0, 1, 2),
         details="JWTs, passwords in URLs, connection-string passwords, private keys, committed env files, binaries in the "
                 "tooling directories, and values the operator lists as leaked (security.knownLeaks: sha256 fingerprints). "
                 "Placeholders are not values; a file the configuration catalogue tracks (knownExposures) is not failed twice."),
    Verb("vscode-gen", "generate .vscode launch and tasks from the manifest", ["vscode-gen [--force]"],
         _py("lib/vscode_gen.py"), passthrough=True, group="generate"),
    Verb("config-gen", "generate module config from the manifest", ["config-gen [--all|--check|--dry-run] [module]"],
         _py("lib/config_gen.py"), passthrough=True, group="generate"),
    Verb("ci-gen", "generate the CI/CD workflow from the manifest and the targets", ["ci-gen [--force|--check]"],
         _py("lib/ci_gen.py"), passthrough=True, group="generate",
         details="CD calls this same CLI (`deploy --yes`), never deploy logic of its own: a manual dispatch with an "
                 "environment choice, and each environment gated by its GitHub Environment (give production required "
                 "reviewers in the repository settings)."),
    Verb("compose-gen", "generate the local development compose files", ["compose-gen"], _py("compose/build.py"),
         passthrough=True, group="generate"),
    Verb("nginx-gen", "render the UI module's nginx config", ["nginx-gen"], _py("adapters/render_nginx.py"),
         passthrough=True, group="generate"),
    Verb("stack", "the local development stack, run by this machine's declared compose invocation",
         ["stack <up|down|ps|logs> ... [--env dev|prod]"], _stack, passthrough=True),
    Verb("infra", "the infra stack: on this machine, or on the target in its layout's infra place",
         ["infra local up|down|status [--prod]", "infra remote sync|up|down|status|purge --env <id> [--target <t>] [--plan] [--yes]",
          "infra tunnel --env <id> [--target <t>]"], _infra, passthrough=True, group="delivery",
         options=[Option("--plan", "print the plan and stop; nothing is written"), Option("--yes", "answer the confirmation (CI)")], exits=(0, 1, 2, 3, 4),
         examples=["infra remote up --env dev --plan", "infra tunnel --env dev"]),
    Verb("hybrid", "run a module on this machine with its environment's env files", ["hybrid boot <module> [--env dev]"],
         _hybrid, options=[Option("--env", "the environment whose env files the run reads (default dev)", "id")],
         examples=["hybrid boot api"]),
]
