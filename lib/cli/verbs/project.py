"""The project's verbs that run one kit tool each -- the tool keeps its own argv and exit code."""
from __future__ import annotations

from lib.cli import tools
from lib.cli.registry import Args, Option, Verb


def _py(rel: str):
    return lambda a: tools.python_script(rel, a.raw)


def _init(a: Args) -> int:
    if "--plan" in a.raw or "--approve" in a.raw:
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
