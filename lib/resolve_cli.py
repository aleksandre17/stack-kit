#!/usr/bin/env python3
"""The resolver's command line -- what `lib/project.sh`, `lib/env.sh`, `lib/project.ps1` and
`lib/env.ps1` ask instead of resolving anything themselves (ADR-001 decision 2).

    resolve_cli.py [--shell bash|pwsh] context
    resolve_cli.py [--shell bash|pwsh] notice <former> <current>
    resolve_cli.py [--shell bash] env-files <folder> [dev|prod|deploy|all]
    resolve_cli.py env-value <folder> <KEY> [default]
    resolve_cli.py run-env <folder> [dev|prod]   (one JSON object: what a run sets; for the process, never a console)
    resolve_cli.py deploy-env-value <KEY> [default]
    resolve_cli.py project-slug | compose-slug | docker-network | server-base | infra-slug
    resolve_cli.py [--shell bash] infra-deploy-path | deploy-base <folder>
    resolve_cli.py infra-services | infra-compose-files | infra-compose-args | infra-sync-paths
    resolve_cli.py infra-tunnel-forwards     (local<TAB>remote<TAB>service<TAB>env per line)
    resolve_cli.py slugify <text>
    resolve_cli.py alias <alias>            (also: resolve_cli.py <alias>, the former form)
    resolve_cli.py driver-types              (id<TAB>roles<TAB>label per line)
    resolve_cli.py remote-path <folder> <kind> <container> [dev|prod] [service]   (kind: module, runtime,
                   workspace, static, compose, compose-dev, compose-prod -- from the selected target)
    resolve_cli.py ssh-args                  (one openssh argument per line, for ssh, scp and rsync -e)
    resolve_cli.py target                    (the selected target's name; empty when none is declared)
    resolve_cli.py compose-project [dev|prod] | target-keep | remote-preflight [service...] | confined <path>
    resolve_cli.py driver-command <module|alias> <command>
    resolve_cli.py stack-steps [dev|prod] [flag...]   (module<TAB>command<TAB>args... per line)
    resolve_cli.py stack-health              (module<TAB>url<TAB>expect per line; expect '-' = status only)
    resolve_cli.py stack-endpoints | compose-names | compose-service <module>

`context` first carries every former-prefixed variable to its current name and then answers; for
bash it prints shell to `eval` (the variables to export and unset, and the context as one
associative array `_SK`), for PowerShell one JSON document. Every other verb prints its answer
and exits 0, or prints why there is none to stderr and exits 1.

With `--shell bash` on Windows, paths are printed as Git Bash spells them (`/c/...`): a drive
colon in a path handed to scp or rsync reads as a host name.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

if __name__ == "__main__":  # run as a file: the kit root, not lib/, is what `lib.` resolves from
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # a shell reads LF; CR would ride in values

from lib import identity  # noqa: E402

VERBS_WITHOUT_A_PROJECT = {"context", "notice", "slugify", "alias"}


def _posix(text: str) -> str:
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", text)
    if not m:
        return text
    return f"/{m.group(1).lower()}/" + m.group(2).replace("\\", "/")


def _bash_quote(text: str) -> str:
    return "$'" + (text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
                   .replace("\t", "\\t").replace("\r", "\\r")) + "'"


#: Context keys whose value is a filesystem path, or lines of paths -- the ones `--shell bash`
#: respells on Windows. Every other key is a name or a value and is never touched.
_PATH_KEYS = ("root", "manifest", "kitRoot", "packageRoot", "monorepoRoot", "secretsRoot")
_PATH_KINDS = ("path:",)
_PATH_ATTRS = (":path", ":secretsDir")


def _is_path(key: str) -> bool:
    return key in _PATH_KEYS or key.startswith(_PATH_KINDS) or key.endswith(_PATH_ATTRS)


def _env_changes(before: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    now = dict(os.environ)
    changed = {k: v for k, v in now.items() if before.get(k) != v}
    removed = [k for k in before if k not in now]
    return changed, removed


def _emit(shell: str, changed: dict[str, str], removed: list[str], ctx: dict[str, str] | None) -> None:
    if shell == "bash":
        posix = os.name == "nt"
        lines = [f"export {k}={_bash_quote(v)}" for k, v in sorted(changed.items())]
        lines += [f"unset {k}" for k in sorted(removed)]
        if ctx is not None:
            pairs = " ".join(f"[{_bash_quote(k)}]={_bash_quote(_posix(v) if posix and _is_path(k) else v)}"
                             for k, v in sorted(ctx.items()))
            lines.append(f"declare -gA _SK=({pairs})")
        print("\n".join(lines))
        return
    print(json.dumps({"env": {"set": changed, "unset": removed}, "context": ctx}, sort_keys=True))


def main(argv: list[str]) -> int:
    shell = "pwsh"
    if len(argv) >= 2 and argv[0] == "--shell":
        shell, argv = argv[1], argv[2:]
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    verb, args = argv[0], argv[1:]

    from lib import resolution

    if verb == "context":
        before = dict(os.environ)
        identity.adopt_legacy_env()
        ctx = resolution.context()
        changed, removed = _env_changes(before)
        _emit(shell, changed, removed, ctx)
        return 0
    if verb == "notice" and len(args) == 2:
        before = dict(os.environ)
        identity.notice(*args)
        _emit(shell, *_env_changes(before), None)
        return 0
    if verb == "slugify" and len(args) == 1:
        print(resolution.slugify(args[0]))
        return 0
    if verb == "alias" or (verb not in VERBS and len(args) == 0):
        return _alias(args[0] if verb == "alias" and args else verb)

    try:
        r = resolution.Resolver()
        answer = _answer(r, verb, args)
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if answer is None:
        print(__doc__, file=sys.stderr)
        return 2
    posix = shell == "bash" and os.name == "nt"
    for line in answer:
        print(_posix(line) if posix and verb in PATH_VERBS else line)
    return 0


#: Verbs whose answer is one path per line.
PATH_VERBS = {"env-files"}

VERBS = {"context", "notice", "slugify", "alias", "env-files", "env-value", "run-env", "deploy-env-value",
         "project-slug", "compose-slug", "docker-network", "server-base", "infra-slug",
         "infra-deploy-path", "deploy-base", "infra-tunnel-forwards", "infra-compose-files",
         "infra-compose-args", "infra-sync-paths", "infra-services",
         "driver-types", "driver-command", "stack-steps", "stack-health", "stack-endpoints",
         "compose-names", "compose-service", "remote-path", "ssh-args", "target",
         "compose-project", "target-keep", "remote-preflight", "confined"}


def _answer(r, verb: str, args: list[str]) -> list[str] | None:
    if verb == "env-files" and 1 <= len(args) <= 2:
        return [str(p) for p in r.env_files(args[0], args[1] if len(args) == 2 else "all")]
    if verb == "env-value" and 2 <= len(args) <= 3:
        return [r.env_value(args[0], args[1], args[2] if len(args) == 3 else "")]
    if verb == "run-env" and 1 <= len(args) <= 2:
        return [json.dumps(r.run_env(args[0], args[1] if len(args) == 2 else ""), ensure_ascii=False)]
    if verb == "deploy-env-value" and 1 <= len(args) <= 2:
        return [r.deploy_env_value(args[0], args[1] if len(args) == 2 else "")]
    if verb == "deploy-base" and len(args) == 1:
        return [r.deploy_base(args[0])]
    if verb == "remote-path" and 3 <= len(args) <= 5:
        return [r.remote_path(args[0], args[1], args[2], args[3] if len(args) > 3 else "",
                              args[4] if len(args) > 4 else "")]
    if verb == "ssh-args" and not args:
        return r.ssh_args()
    if verb == "target" and not args:
        chosen = r.target()
        return [chosen[0] if chosen else ""]
    if verb == "compose-project" and len(args) <= 1:
        return [r.compose_project(args[0] if args else "")]
    if verb == "target-keep" and not args:
        from lib import targets

        try:
            chosen = r.target()
        except targets.TargetError:
            chosen = None
        return [str(targets.keep(chosen[1]) if chosen else 5)]
    if verb == "remote-preflight":
        return [r.remote_preflight(args)]
    if verb == "confined" and len(args) == 1:
        if not r.confined(args[0]):
            raise ValueError(f"{args[0]} is outside this project's directory on the target -- refused")
        return [args[0]]
    if verb == "infra-tunnel-forwards" and not args:
        return ["\t".join((f["local"], f["remote"], f["service"], f["env"])) for f in r.infra_tunnel_forwards()]
    lists = {"infra-compose-files": r.infra_compose_files, "infra-compose-args": r.infra_compose_args,
             "infra-sync-paths": r.infra_sync_paths, "infra-services": r.infra_services}
    if verb in lists and not args:
        return lists[verb]()
    simple = {"project-slug": r.project_slug, "compose-slug": r.compose_slug,
              "docker-network": r.docker_network, "server-base": r.server_base,
              "infra-slug": r.infra_slug, "infra-deploy-path": r.infra_deploy_path}
    if verb in simple and not args:
        return [simple[verb]()]
    return _modules_answer(verb, args)


def _modules_answer(verb: str, args: list[str]) -> list[str] | None:
    """What the drivers and modules answer: the verbs `driver_api.py` and `modules_cli.py` held,
    folded here so one command line speaks for the resolver (ADR-001 amendment 7)."""
    from lib.modules import driver_commands, driver_registry, resolve_cli_alias
    from lib.project_context import ProjectContext

    if verb == "driver-types" and not args:
        return [f"{tid}\t{','.join(ent.get('roles', ['any']))}\t{ent.get('label', '')}"
                for tid, ent in sorted(driver_registry().items())]
    ctx = ProjectContext.discover()
    if verb == "driver-command" and len(args) == 2:
        module_id = resolve_cli_alias(args[0], ctx.manifest) or args[0]
        typ = str((ctx.manifest.get("modules") or {}).get(module_id, {}).get("type") or "")
        if not typ:
            raise ValueError(f"module '{args[0]}' is not declared, or declares no type")
        commands = driver_commands(typ)
        if args[1] not in commands:
            raise ValueError(f"driver '{typ}' has no command '{args[1]}' (available: {', '.join(sorted(commands))})")
        return [str(commands[args[1]])]
    if verb == "stack-steps":
        from lib.stack_deploy import stack_deploy_lines

        from lib import catalogs

        envs = catalogs.ids("environments", ctx.manifest)
        environment = args[0] if args and args[0] in envs else catalogs.default_environment("deploy", ctx.manifest)
        flags = args[1:] if args and args[0] in envs else args
        return stack_deploy_lines(ctx.manifest, environment, flags)
    if verb == "stack-health" and not args:
        from lib.ci_health import stack_health_targets

        return [f"{t.module_id}\t{t.url}\t{t.expect or '-'}" for t in stack_health_targets(ctx)]
    if verb == "stack-endpoints" and not args:
        from lib.stack_endpoints import stack_endpoint_lines

        return list(stack_endpoint_lines(ctx))
    if verb in ("compose-names", "compose-service"):
        from lib.compose_identity import compose_service_names, load_deploy_env, resolve_module_service_name

        deploy = load_deploy_env(ctx.secrets_root)
        if verb == "compose-names" and not args:
            return [json.dumps(compose_service_names(ctx.manifest, deploy, ctx.root.name))]
        if verb == "compose-service" and len(args) == 1:
            return [resolve_module_service_name(args[0], ctx.manifest, deploy, ctx.root.name)]
    return None


def _alias(name: str) -> int:
    from lib.project_context import ProjectContext

    try:
        target = ProjectContext.discover().resolve_alias(name)
    except FileNotFoundError:
        from lib.manifest_defaults import resolve_cli_alias

        target = resolve_cli_alias(name)
    if target:
        print(target)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
