#!/usr/bin/env python3
"""Generate the host's CI workflow from its manifest (ADR-001 amendment 8).

One job per module, in parallel: check out (with submodules when the host has any), set up the
toolchain the module's DRIVER declares (`drivers/registry.json` `ci.setup`, its version from the
module's `toolchain.version`), then the lifecycle steps the driver has -- `lint`, `build`, `test` --
each through the host launcher, so CI runs exactly what a developer runs. Every action is pinned by
the full commit SHA in `lib/ci-actions.json`; the generator names no driver and no action version.

    ci_gen.py            write the workflow if it is missing
    ci_gen.py --force    write it over the existing one
    ci_gen.py --check    exit 1 when the committed workflow is not what the manifest generates
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

if __name__ == "__main__":  # run as a file: the kit root, not lib/, is what `lib.` resolves from
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.identity import KIT_NAME, MANIFEST_FILENAME  # noqa: E402
from lib.manifest_defaults import default_field  # noqa: E402
from lib.modules import driver_capability, driver_commands, lifecycle_steps  # noqa: E402
from lib.project_context import ProjectContext  # noqa: E402

DEFAULT_WORKFLOW = ".github/workflows/ci.yml"
PINS = Path(__file__).resolve().parent / "ci-actions.json"
_FIELD = re.compile(r"\{([A-Za-z0-9_.]+)\|([^}]*)\}")


class UnpinnedAction(ValueError):
    """A driver asks for an action the kit has not pinned by SHA."""


_SHA = re.compile(r"^[0-9a-f]{40}$")


def _pins(ctx: ProjectContext | None = None) -> dict[str, dict[str, str]]:
    """The kit's pins with the host's over them (`ci.actions`: a file of the same shape), every one a
    full commit SHA: a project adds `actions/setup-python` without touching the kit, never a tag."""
    pins = dict(json.loads(PINS.read_text(encoding="utf-8"))["actions"])
    rel = ((ctx.manifest.get("ci") or {}).get("actions") if ctx is not None else None)
    if rel:
        path = ctx.root / str(rel)
        if not path.is_file():
            raise UnpinnedAction(f"ci.actions: {rel} is not there")
        own = json.loads(path.read_text(encoding="utf-8")).get("actions") or {}
        for action, pin in own.items():
            if not isinstance(pin, dict) or not _SHA.match(str(pin.get("sha") or "")) or not pin.get("version"):
                raise UnpinnedAction(f"ci.actions: {action} must be pinned by a full 40-hex commit sha with its version")
        pins.update(own)
    return pins


def _uses(action: str, pins: dict[str, dict[str, str]]) -> str:
    pin = pins.get(action)
    if not pin:
        raise UnpinnedAction(f"{action} is not pinned in lib/ci-actions.json; pin it by SHA first")
    return f"{action}@{pin['sha']} # {pin['version']}"


def _module_value(module: dict[str, Any], template: str) -> str:
    """`{toolchain.version|22}` -> the module's field, else the default after the bar."""
    def one(m: re.Match[str]) -> str:
        cur: Any = module
        for part in m.group(1).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        return str(cur) if cur not in (None, "") else m.group(2)
    return _FIELD.sub(one, template)


def _q(value: str) -> str:
    """A YAML scalar, single-quoted (the one quoting with no escapes but a doubled quote)."""
    return "'" + str(value).replace("'", "''") + "'"


def launcher(manifest: dict[str, Any]) -> str:
    """The host launcher a developer runs: the manifest's, else the convention's."""
    return str((manifest.get("vscode") or {}).get("cliScript") or default_field("vscode.cliScript"))


DEFAULT_BRANCH_PUSH = "github.event_name == 'push' && github.ref == format('refs/heads/{0}', github.event.repository.default_branch)"


def _secret_name(*parts: str) -> str:
    return "_".join(re.sub(r"[^A-Za-z0-9]", "_", p).upper() for p in parts)


def _setup_steps(typ: str, module: dict[str, Any], pins: dict[str, dict[str, str]]) -> list[str]:
    out: list[str] = []
    for setup in (driver_capability(typ, "ci", {}) or {}).get("setup", []):
        if "uses" in setup:
            out.append(f"      - uses: {_uses(str(setup['uses']), pins)}")
            if setup.get("with"):
                out.append("        with:")
                out += [f"          {k}: {_q(_module_value(module, str(v)))}" for k, v in setup["with"].items()]
        elif "run" in setup:
            out.append(f"      - run: {_q(str(setup['run']))}")
    return out


def _checkout(pins: dict[str, dict[str, str]], submodules: bool) -> list[str]:
    out = [f"      - uses: {_uses('actions/checkout', pins)}"]
    if submodules:
        out += ["        with:", "          submodules: recursive"]
    return out


def delivery_plan(ctx: ProjectContext) -> tuple[dict[str, str], list[str], list[str]]:
    """({environment: target}, modules CD deploys, reasons) -- CD is generated where every environment
    has a reachable declared target and a module packages once (its driver's `package`) and releases
    through the kit (`release` rung `via: release`); every other case is CI only, and the reasons say why."""
    from lib import catalogs, targets as deploy_targets
    from lib.modules import driver_delivery

    reasons: list[str] = []
    try:
        data = deploy_targets.load(ctx.root, ctx.manifest)
    except deploy_targets.TargetError as e:
        return {}, [], [f"the targets file cannot be read: {e}"]
    chosen: dict[str, str] = {}
    if data is None:
        reasons.append("no deploy targets are declared (manifest `deploy.targets`)")
    else:
        for env in catalogs.ids("environments", ctx.manifest):
            name = (data.get("defaults") or {}).get(env)
            target = (data.get("targets") or {}).get(name or "", {})
            pending = (catalogs.entry("targetRuntimes", str(target.get("runtime") or ""), ctx.manifest) or {}).get("pending")
            if not name:
                reasons.append(f"no `defaults.{env}` target")
            elif target.get("pending"):
                reasons.append(f"target {name} ({env}) is pending: {target['pending']}")
            elif pending:
                reasons.append(f"target {name} ({env}): runtime {target.get('runtime')} is pending: {pending}")
            else:
                chosen[env] = name
    promoted = []
    for mid, module in (ctx.manifest.get("modules") or {}).items():
        typ = str((module or {}).get("type") or "")
        spec = driver_capability(typ, "package", None) or {}
        release = driver_delivery(typ).get("release") or {}
        if spec.get("pending"):
            reasons.append(f"{mid} ({typ}): packaging is pending -- {spec['pending']}")
        elif not spec.get("command"):
            reasons.append(f"{mid} ({typ}): its driver declares no package step")
        elif release.get("pending") or release.get("via") != "release":
            reasons.append(f"{mid} ({typ}): its release is {'pending -- ' + release['pending'] if release.get('pending') else 'not the kit release'}")
        else:
            promoted.append(mid)
    if len(chosen) < len(catalogs.ids("environments", ctx.manifest)):
        return chosen, [], reasons
    return chosen, promoted, reasons


RELEASE_EVENT = f"({DEFAULT_BRANCH_PUSH}) || github.event_name == 'workflow_dispatch'"


def _database(manifest: dict[str, Any], mid: str) -> dict[str, Any]:
    """The CI test database a module's job runs beside (`ci.database`), or {}."""
    db = (manifest.get("ci") or {}).get("database") or {}
    if not db or (db.get("modules") and mid not in db["modules"]):
        return {}
    return db


def _db_service(db: dict[str, Any]) -> list[str]:
    """A service container with health options: the job's steps start once the database is healthy."""
    if not db:
        return []
    out = ["    services:", "      db:", f"        image: {_q(db['image'])}"]
    if db.get("env"):
        out += ["        env:"] + [f"          {k}: {_q(str(v))}" for k, v in sorted(db["env"].items())]
    out += ["        ports:", f"          - {_q(str(db.get('port', 5432)) + ':' + str(db.get('port', 5432)))}"]
    if db.get("health"):
        opts = f"--health-cmd {_shell_q(db['health'])} --health-interval 5s --health-timeout 5s --health-retries 20"
        out += [f"        options: {_q(opts)}"]
    return out


def _shell_q(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"'


def _package_steps(mid: str, module: dict[str, Any], cli: str, pins: dict[str, dict[str, str]]) -> list[str]:
    archive = f".stack-kit/artifacts/{mid}-*.tgz"
    return [
        "      - name: package (build once: one archive per commit)",
        f"        if: ${{{{ {RELEASE_EVENT} }}}}",
        f"        run: {_q(f'pwsh {cli} package {mid}')}",
        "      - name: sbom",
        f"        if: ${{{{ {RELEASE_EVENT} }}}}",
        f"        uses: {_uses('anchore/sbom-action', pins)}",
        "        with:",
        f"          path: {_q(module['path'])}",
        "          format: spdx-json",
        f"          output-file: {_q(f'.stack-kit/artifacts/{mid}.spdx.json')}",
        "          upload-artifact: false",
        "      - name: build provenance",
        f"        if: ${{{{ {RELEASE_EVENT} }}}}",
        f"        uses: {_uses('actions/attest-build-provenance', pins)}",
        "        with:",
        f"          subject-path: {_q(archive)}",
        f"      - if: ${{{{ {RELEASE_EVENT} }}}}",
        f"        uses: {_uses('actions/upload-artifact', pins)}",
        "        with:",
        f"          name: package-{mid}",
        "          path: |",
        f"            {archive}",
        f"            {archive}.sha256",
        f"            .stack-kit/artifacts/{mid}.spdx.json",
        "          if-no-files-found: error",
    ]


def _runs_upload(name: str, pins: dict[str, dict[str, str]]) -> list[str]:
    return [
        "      - name: run records (DORA)",
        "        if: always()",
        f"        uses: {_uses('actions/upload-artifact', pins)}",
        "        with:",
        f"          name: stack-kit-runs-{name}",
        "          path: .stack-kit/runs/runs.jsonl",
        "          if-no-files-found: ignore",
    ]


def render(ctx: ProjectContext) -> str:
    pins = _pins(ctx)
    manifest = ctx.manifest
    cli = launcher(manifest)
    submodules = (ctx.root / ".gitmodules").is_file()
    chosen, promoted, reasons = delivery_plan(ctx)
    modules = {m: c for m, c in (manifest.get("modules") or {}).items() if isinstance(c, dict)}
    packaged = [m for m, c in modules.items()
                if (driver_capability(str(c.get("type") or ""), "package", None) or {}).get("command")]
    out = [
        f"# Generated by `{KIT_NAME} ci-gen` from {MANIFEST_FILENAME} and its deploy targets: regenerate, never",
        f"# edit (`{KIT_NAME} ci-gen --check` fails when this file and the declarations disagree).",
        "# Every step runs the command a developer runs locally; the workflow only sequences them.",
    ]
    if promoted:
        from lib import catalogs

        chain = " -> ".join(f"{chosen[e]} ({e})" for e in catalogs.ids("environments", manifest))
        out.append(f"# CD: {', '.join(promoted)} -> {chain}, on the default branch, each gated by its GitHub "
                   f"Environment; the same packaged bytes throughout.")
    else:
        out.append("# CD: none -- CI and packaging only, because:")
    out += [f"#   - {r}" for r in reasons]
    out += [
        "name: ci",
        "on:",
        "  push:",
        "  pull_request:",
        *_dispatch(manifest, bool(promoted)),
        "permissions:",
        "  contents: read",
        "concurrency:",
        "  group: ci-${{ github.ref }}",
        "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
        "jobs:",
    ]
    out += ["  secrets:", "    name: 'secret scan (tree and history)'", "    runs-on: ubuntu-latest", "    timeout-minutes: 10",
            "    steps:", f"      - uses: {_uses('actions/checkout', pins)}", "        with:", "          fetch-depth: 0",
            f"      - run: {_q(f'pwsh {cli} scan secrets --history')}"]
    for mid, module in modules.items():
        typ = str(module.get("type") or "")
        steps = [s for s in lifecycle_steps(manifest) if s in driver_commands(typ)]
        job = re.sub(r"[^A-Za-z0-9_-]", "-", mid)
        runner = (driver_capability(typ, "ci", {}) or {}).get("runsOn") or "ubuntu-latest"
        out += [f"  {job}:", f"    name: {_q(f'{mid} ({typ})')}", f"    runs-on: {runner}", "    timeout-minutes: 30"]
        if mid in packaged:
            out += ["    permissions:", "      contents: read", "      id-token: write", "      attestations: write"]
        db = _database(manifest, mid)
        out += _db_service(db)
        out += ["    steps:", *_checkout(pins, submodules), *_setup_steps(typ, module, pins)]
        if db.get("migrate"):
            out += ["      - name: migrate (the test database, before the tests)", "        env:",
                    f"          DATABASE_URL: {_q(db['url'])}", f"        run: {_q(db['migrate'])}"]
        for step in steps:
            out += [f"      - name: {step}"]
            if db:  # the DB tests run instead of skipping
                out += ["        env:", f"          DATABASE_URL: {_q(db['url'])}"]
            out += [f"        run: {_q(f'pwsh {cli} mod {mid} {step}')}"]
        if not steps:
            out.append(f"      - run: {_q(f'echo driver {typ} declares no lifecycle step')}")
        if mid in packaged:
            out += _package_steps(mid, module, cli, pins) + _runs_upload(f"package-{job}", pins)
    if promoted:
        from lib import catalogs, targets as deploy_targets

        data = deploy_targets.load(ctx.root, manifest) or {}
        secrets_root = str(manifest.get("secrets") or "ops/config").rstrip("/")
        # the first deploy waits for the secret scan too -- the later ones wait for it through it
        previous: list[str] = ["secrets", *(re.sub(r"[^A-Za-z0-9_-]", "-", m) for m in promoted)]
        for env in catalogs.ids("environments", manifest):
            name = chosen[env]
            target = data["targets"][name]
            job = f"deploy-{env}"
            gate = (f"!failure() && !cancelled() && (({DEFAULT_BRANCH_PUSH}) || "
                    f"(github.event_name == 'workflow_dispatch' && inputs.environment == '{env}'))")
            out += [
                f"  {job}:",
                f"    name: {_q(f'deploy {env} -> {name}')}",
                f"    needs: [{', '.join(previous)}]",
                f"    if: ${{{{ {gate} }}}}",
                f"    runs-on: {target.get('runner') or 'ubuntu-latest'}",
                "    timeout-minutes: 45",
                f"    environment: {_q(env)}",
                "    concurrency:",
                f"      group: {_q(f'deploy-{name}-{env}')}",
                "      cancel-in-progress: false",
                "    steps:",
                *_checkout(pins, submodules),
            ]
            for mid in promoted:
                out += [f"      - uses: {_uses('actions/download-artifact', pins)}", "        with:",
                        f"          name: package-{mid}", "          path: .stack-kit/artifacts"]
            identity_ref = str((target.get("ssh") or {}).get("identity") or "agent")
            key_secret = _secret_name("STACK_KIT_SSH_KEY", name)
            out += [
                f"      - name: ssh key from the secret store into ssh-agent ({key_secret})",
                "        env:",
                f"          KEY: ${{{{ secrets.{key_secret} }}}}",
                "        run: |",
                '          eval "$(ssh-agent -s)"',
                '          echo "SSH_AUTH_SOCK=$SSH_AUTH_SOCK" >> "$GITHUB_ENV"',
                "          printf '%s\\n' \"$KEY\" | ssh-add -",
            ]
            if identity_ref != "agent":
                out.append(f"      # targets.{name}.ssh.identity is {identity_ref}: in CI the agent holds the key instead")
            for mid in promoted:
                folder = str(modules[mid].get("secretsModule") or mid)
                env_secret = _secret_name("STACK_KIT_ENV", folder, env)
                from lib.envfile import injected_name

                var = injected_name(folder, env)
                out += [
                    f"      - name: {folder} .env.{env} from the secret store ({env_secret}), outside the checkout",
                    "        env:",
                    f"          VALUES: ${{{{ secrets.{env_secret} }}}}",
                    "        run: |",
                    "          umask 077",
                    f"          f=\"$RUNNER_TEMP/{folder}.env.{env}\"",
                    "          if [ -n \"$VALUES\" ]; then printf '%s\\n' \"$VALUES\" > \"$f\"; "
                    f"echo \"{var}=$f\" >> \"$GITHUB_ENV\"; fi",
                ]
            for mid in promoted:
                archive = f".stack-kit/artifacts/{mid}-*.tgz"
                out += [f"      - name: deploy {mid} ({env}) -- the bytes packaged above; nothing is rebuilt",
                        f"        run: {_q(f'pwsh {cli} deploy {mid} --env {env} --target {name} --yes --artifact $(ls {archive})')}"]
            out += [
                "      - name: verify -- the declared health endpoints",
                f"        run: {_q(f'pwsh {cli} targets --health --target {name} --env {env}')}",
                "      - name: verify -- the server holds the declared tree",
                f"        run: {_q(f'pwsh {cli} targets --verify --target {name} --env {env}')}",
                "      # A release whose health fails is rolled back by the deploy itself where the environment",
                "      # declares rollbackOnFailure; `release rollback` moves `current` back by hand.",
                *_runs_upload(f"deploy-{env}", pins),
            ]
            previous = [job]
    return "\n".join(out) + "\n"


def _dispatch(manifest: dict[str, Any], cd: bool) -> list[str]:
    """A manual run that deploys to one chosen environment (the GitHub Environment of the same name
    gates it; give production required reviewers there)."""
    if not cd:
        return []
    from lib import catalogs

    envs = catalogs.ids("environments", manifest)
    return ["  workflow_dispatch:", "    inputs:", "      environment:", "        description: 'the environment to deploy'",
            "        type: choice", f"        default: {_q(envs[0])}", "        options:", *(f"          - {_q(e)}" for e in envs)]


def target(ctx: ProjectContext) -> Path:
    return ctx.root / str((ctx.manifest.get("ci") or {}).get("workflow") or DEFAULT_WORKFLOW)


def main(argv: list[str]) -> int:
    ctx = ProjectContext.discover()
    path = target(ctx)
    try:
        text = render(ctx)
    except UnpinnedAction as e:
        print(f"[ci-gen] ERROR: {e}", file=sys.stderr)
        return 1
    rel = path.relative_to(ctx.root).as_posix()
    if "--check" in argv:
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            print(f"[ci-gen] {rel} is not what {MANIFEST_FILENAME} generates (run: {KIT_NAME} ci-gen --force)")
            return 1
        print(f"[ci-gen] {rel} matches {MANIFEST_FILENAME}")
        return 0
    if path.is_file() and "--force" not in argv:
        print(f"[ci-gen] {rel} exists (use --force to overwrite, --check to compare)")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"[ci-gen] wrote {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
