"""K2 — one resolver: bash and PowerShell answer exactly what Python answers (ADR-001 decision 2).

Before K2 the three runtimes each carried the resolution, and on the reference consumer they
already disagreed: role inference, convention defaults, which env file's value wins, whether the
process environment beats deploy.env, the order the project is searched for. Here every public
getter of `lib/project.sh` + `lib/env.sh` and `lib/project.ps1` + `lib/env.ps1` is asked the same
questions on the same host as `lib/resolution.py`, and the answers are compared one by one -- on a
host built to exercise the rules that had drifted: a field left to its convention default, a
module whose role comes from its driver, one key in two env files, a deploy value the process
environment overrides.

And the shims are held to holding no rule: no manifest field is spelled in them.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PKG, WORKING_ROOT
from lib import identity

SHIMS = ["lib/project.sh", "lib/env.sh", "lib/drivers.sh", "lib/project.ps1", "lib/env.ps1", "lib/drivers.ps1",
         "lib/modules.ps1"]
TOP_LEVEL_FIELDS = list(json.loads((PKG / "manifest.schema.json").read_text(encoding="utf-8"))["properties"])

#: The questions, as (name, bash call, PowerShell call). Python's answer is computed below.
QUESTIONS = [
    ("root", "stack_kit_find_project_root", "Get-ProjectRootFromManifest"),
    ("field.present", "stack_kit_read_manifest_field compose.catalog",
     "Get-ManifestField compose.catalog"),
    ("field.convention", "stack_kit_read_manifest_field secrets", "Get-ManifestField secrets"),
    ("field.explicit-default", "stack_kit_read_manifest_field no.such.field given",
     "Get-ManifestField no.such.field -Default given"),
    ("field.absent", "stack_kit_read_manifest_field no.such.field", "Get-ManifestField no.such.field"),
    ("module.path", "stack_kit_module_path api", "Get-ManifestModulePath api"),
    ("module.secrets", "stack_kit_secrets_module_name worker", "Get-ModuleSecretsFolder worker"),
    ("role.inferred", "stack_kit_module_id_for_role ui", "@(Get-KitContextLines 'role:ui')[0]"),
    ("type.first", "stack_kit_module_id_for_type java-boot", "Get-ModuleIdByDriverType java-boot"),
    ("folders", "stack_kit_list_secrets_module_folders | paste -sd, -",
     "(Get-ListedSecretsModuleFolders) -join ','"),
    ("secrets.root", "stack_kit_secrets_root", "Get-SecretsRoot"),
    ("env.files", "stack_kit_env_files api all | paste -sd, -",
     "(Get-SecretsEnvFiles -Module api -Profile all) -join ','"),
    ("env.last-wins", "stack_kit_env_value api PARITY_KEY none",
     "Get-SecretsEnvValue -Module api -Key PARITY_KEY -Default none"),
    ("deploy.process-env-first", "stack_kit_deploy_env_value DEPLOY_PROJECT",
     "Get-DeployEnvValue DEPLOY_PROJECT"),
    ("slug.project", "stack_kit_project_slug", "Get-ProjectSlug"),
    ("slug.compose", "stack_kit_compose_slug", "Get-ComposeSlug"),
    ("network", "stack_kit_docker_network", "Get-DockerNetworkName"),
    ("server.base", "stack_kit_server_base", "Get-DeployServerBase"),
    ("deploy.base", "stack_kit_default_remote_deploy_base worker", "Get-DefaultRemoteDeployPathBase worker"),
    ("module.type", "stack_kit_module_type web", "Get-ModuleType web"),
    ("driver.command", "stack_kit_driver_command_path api deploy", "Get-DriverCommandPath api deploy"),
    ("alias", "stack_kit_cli_resolve_alias ui", "Resolve-CliAlias ui"),
]

PROCESS_PROJECT = "from-the-environment"


@pytest.fixture(scope="module")
def host(tmp_path_factory) -> Path:
    """The reference consumer, bent to exercise every rule that had drifted between runtimes."""
    root = tmp_path_factory.mktemp("parity") / "parity-host"
    shutil.copytree(WORKING_ROOT, root, ignore=shutil.ignore_patterns("kits"))
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest.pop("secrets", None)                       # a convention default
    web = next(m for m in manifest["modules"].values() if m.get("type") == "node-vite")
    web.pop("role", None)                               # a role its driver declares
    mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    api = root / "ops" / "config" / "api"
    with (api / ".env.dev").open("a", encoding="utf-8") as f:
        f.write("\nPARITY_KEY=from-dev\n")
    with (api / ".env.deploy").open("a", encoding="utf-8") as f:
        f.write("\nPARITY_KEY=from-deploy\n")
    (root / "ops" / "config" / "deploy.env").write_text(
        "DEPLOY_PROJECT=from-the-file\nDEPLOY_SERVER=ops@example.invalid\n", encoding="utf-8")
    return root


def _env(host: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(identity.ENV_PREFIX + "_")}
    env[identity.env_name("PROJECT_ROOT")] = str(host)
    env["DEPLOY_PROJECT"] = PROCESS_PROJECT
    env["PYTHONPATH"] = str(PKG)
    env.pop("OPS_PACKAGE_ROOT", None)
    env.pop("OPS_MONOREPO_ROOT", None)
    return env


def _python_answers(host: Path) -> dict[str, str]:
    probe = (
        "import json, sys\n"
        "from lib.resolution import Resolver\n"
        "r = Resolver(); c = r.ctx\n"
        "def f(d, given=None):\n"
        "    v = c.get('field:' + d)\n"
        "    return v if v else (given if given is not None else c.get('default:' + d, ''))\n"
        "print(json.dumps({\n"
        " 'root': c['root'], 'field.present': f('compose.catalog'), 'field.convention': f('secrets'),\n"
        " 'field.explicit-default': f('no.such.field', 'given'), 'field.absent': f('no.such.field'),\n"
        " 'module.path': c['module:api:path'], 'module.secrets': c['module:worker:secretsFolder'],\n"
        " 'role.inferred': c['role:ui'].split('\\n')[0], 'type.first': c['type:java-boot'].split('\\n')[0],\n"
        " 'folders': c['secretsFolders'].replace('\\n', ','), 'secrets.root': c['secretsRoot'],\n"
        " 'env.files': ','.join(str(p) for p in r.env_files('api')),\n"
        " 'env.last-wins': r.env_value('api', 'PARITY_KEY', 'none'),\n"
        " 'deploy.process-env-first': r.deploy_env_value('DEPLOY_PROJECT'),\n"
        " 'slug.project': r.project_slug(), 'slug.compose': r.compose_slug(),\n"
        " 'network': r.docker_network(), 'server.base': r.server_base(), 'deploy.base': r.deploy_base('worker'),\n"
        " 'module.type': c['module:web:type'], 'alias': c['alias:ui'],\n"
        " 'driver.command': c['driver:' + c['module:api:type'] + ':command:deploy'],\n"
        "}))\n")
    ran = subprocess.run([sys.executable, "-B", "-c", probe], cwd=host, env=_env(host),
                         capture_output=True, text=True)
    assert ran.returncode == 0, ran.stderr
    return json.loads(ran.stdout)


def _same_path(a: str, b: str) -> bool:
    def norm(p: str) -> str:
        m = re.match(r"^/([a-zA-Z])/(.*)$", p)
        if m:
            p = f"{m.group(1)}:/{m.group(2)}"
        return p.replace("\\", "/").rstrip("/").lower()
    return norm(a) == norm(b)


def _agree(expected: dict[str, str], got: dict[str, str]) -> list[str]:
    wrong = []
    for name, want in expected.items():
        have = got.get(name, "<missing>")
        parts_w, parts_h = want.split(","), have.split(",")
        same = len(parts_w) == len(parts_h) and all(
            w == h or _same_path(w, h) for w, h in zip(parts_w, parts_h))
        if not same:
            wrong.append(f"{name}: python={want!r} shell={have!r}")
    return wrong


def _bash() -> str | None:
    found = shutil.which("bash")
    if not found or "system32" in found.lower():
        return None
    return found


def _pwsh() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def test_the_reference_host_exercises_every_rule_that_drifted(host):
    answers = _python_answers(host)
    from lib.manifest_defaults import default_field

    assert answers["field.convention"] == default_field("secrets"), "the convention default was not read"
    assert answers["role.inferred"], "the driver's declared role was not inferred"
    assert answers["env.last-wins"] == "from-deploy", "a later env file's value must win"
    assert answers["deploy.process-env-first"] == PROCESS_PROJECT, "the process environment must win"
    assert answers["server.base"] == "/home/ops"


@pytest.mark.skipif(_bash() is None, reason="no POSIX bash on this machine")
def test_bash_answers_what_python_answers(host):
    script = "".join(f'source "{(PKG / "lib" / name).as_posix()}"\n' for name in ("env.sh", "drivers.sh")) + "".join(
        f'printf "%s\\t%s\\n" {name!r} "$({call} 2>/dev/null)"\n' for name, call, _ in QUESTIONS)
    ran = subprocess.run([_bash(), "-c", script], cwd=host, env=_env(host), capture_output=True, text=True)
    assert ran.returncode == 0, ran.stderr
    got = dict(line.split("\t", 1) for line in ran.stdout.splitlines() if "\t" in line)
    wrong = _agree(_python_answers(host), got)
    assert not wrong, "bash and python disagree:\n  " + "\n  ".join(wrong)


@pytest.mark.skipif(_pwsh() is None, reason="no PowerShell on this machine")
def test_powershell_answers_what_python_answers(host):
    lib = PKG / "lib" / "env.ps1"
    script = f". '{lib}'\n. '{PKG / 'lib' / 'modules.ps1'}'\n" + "".join(
        f"\"{name}`t$({call})\"\n" for name, _, call in QUESTIONS)
    ran = subprocess.run([_pwsh(), "-NoProfile", "-NonInteractive", "-Command", script], cwd=host,
                         env=_env(host), capture_output=True, text=True)
    assert ran.returncode == 0, ran.stderr
    got = dict(line.split("\t", 1) for line in ran.stdout.splitlines() if "\t" in line)
    wrong = _agree(_python_answers(host), got)
    assert not wrong, "PowerShell and python disagree:\n  " + "\n  ".join(wrong)


#: The shims' own field readers: called with a literal, they would be spelling a field.
READERS = r"(?:Get-ManifestField|Get-ManifestList|stack_kit_read_manifest_field|stack_kit_read_manifest_list)"


def _spelled_fields(text: str) -> list[str]:
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    found = []
    for top in TOP_LEVEL_FIELDS:
        # `drivers.ps1` is a file, not the `drivers.` field: a script extension is never a field name.
        for m in re.finditer(rf"(?<![\w.:$/\\-]){re.escape(top)}\.(?!(?:ps1|sh|py|json|md)\b)[A-Za-z]", code):
            found.append(code[m.start():m.start() + 40].split()[0])
    for m in re.finditer(rf"{READERS}\s+[\"']?[A-Za-z]", code):
        found.append(code[m.start():m.end() + 30].split("\n")[0])
    return found


def test_the_shims_spell_no_manifest_field():
    spelled = {rel: _spelled_fields((PKG / rel).read_text(encoding="utf-8")) for rel in SHIMS}
    spelled = {rel: hits for rel, hits in spelled.items() if hits}
    assert not spelled, f"a shim spells a manifest field, i.e. holds a rule: {spelled}"


def test_the_sensor_sees_a_spelled_field():
    assert _spelled_fields('stack_kit_read_manifest_field stack.composeDir\n')
    assert _spelled_fields("Get-ManifestField \"secrets\"\n")
    assert not _spelled_fields("# a comment about stack.composeDir\n")
    assert not _spelled_fields('_stack_kit_ctx path:stackComposeDir\n')
    assert not _spelled_fields('[ValidateSet("dev", "prod")][string]$Environment\n')
    assert not _spelled_fields('. (Join-Path $PSScriptRoot "drivers.ps1")\n')
    assert _spelled_fields('$r = Get-KitContextValue "x"; $p = "drivers.registry"\n')
    assert not _spelled_fields('_stack_kit_ctx "field:$1" && return 0\n')
