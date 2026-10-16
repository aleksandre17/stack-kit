"""K6 — delivery ladders by declaration (ADR-001 decision 6).

Proof owed by the ADR: each declared rung runs on the fixture; an undeclared one is refused by name.
The kit's own rungs end on servers this suite has none of, so each is PLANNED through the real CLI
(`deliver <rung> --plan`) and the plan must name a script the driver declares. A rung is RUN through
a project driver (ADR-001 decision 7) whose commands echo how their operands arrived -- the same
dispatch every kit driver goes through, so binding by name, positional order, the environment
substitution and bash-or-PowerShell by script are all held.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import PKG, WORKING_ROOT
from lib import identity
from lib.modules import _read_registry, driver_commands

KIT = _read_registry(PKG / "drivers" / "registry.json")
PWSH = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(PWSH is None, reason="no PowerShell on this machine")
OWN = "echo-driver"

HYBRID = '"hybrid module=$ModuleId a=$env:SK_ECHO_A b=$env:SK_ECHO_B c=$env:SK_ECHO_C"\n'

PS1 = '''param([Parameter(Position=0)][string]$First = "", [string]$Environment = "none", [switch]$Fast)
"ps1 first=$First env=$Environment fast=$Fast"
'''


def _host(tmp_path: Path) -> Path:
    root = tmp_path / "ladder-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    for typ in KIT:  # one module per kit driver, so every kit ladder is planned
        if typ not in {m.get("type") for m in manifest["modules"].values()}:
            manifest["modules"][f"m-{typ}"] = {"type": typ, "path": f"apps/m-{typ}", "secretsModule": f"m-{typ}",
                                               "role": "api"}
            (root / "apps" / f"m-{typ}").mkdir(parents=True)
    reg = root / "ops" / "drivers"
    (reg / OWN / "ps1").mkdir(parents=True)
    (reg / OWN / "sh").mkdir(parents=True)
    (reg / OWN / "ps1" / "deploy.ps1").write_text(PS1, encoding="utf-8")
    (reg / OWN / "sh" / "check.sh").write_text('echo "sh $*"\n', encoding="utf-8")
    (reg / OWN / "ps1" / "hybrid.ps1").write_text(HYBRID, encoding="utf-8")
    secrets = root / manifest["secrets"] / "echo"
    secrets.mkdir(parents=True, exist_ok=True)
    (secrets / ".env.prod").write_text("SK_ECHO_A=prod\nSK_ECHO_B=prod\n", encoding="utf-8")
    (secrets / ".env.dev").write_text("SK_ECHO_A=dev\nSK_ECHO_B=\n", encoding="utf-8")
    (secrets / ".env").write_text("SK_ECHO_C=shared\n", encoding="utf-8")
    (reg / "registry.json").write_text(json.dumps({OWN: {
        "label": "echoes its operands", "roles": ["worker"],
        "commands": {"deploy": "ps1/deploy.ps1", "check": "sh/check.sh"},
        "hybrid": {"script": "ps1/hybrid.ps1"},
        "delivery": {"hybrid": {"via": "hybrid"}, "release": {"command": "deploy", "args": ["dist", "-Environment", "{environment}"]},
                     "remote-dev": {"command": "check", "args": ["remote"]},
                     "container": {"pending": "not proven yet"}},
        "operands": {"ship": {"to": ["deploy", "now", "-Fast"], "hint": "ship is deploy -Fast"}}}}),
        encoding="utf-8")
    manifest["drivers"] = {"registry": "ops/drivers/registry.json"}
    manifest["modules"]["echo"] = {"type": OWN, "path": "apps/echo", "secretsModule": "echo", "role": "worker"}
    (root / "apps" / "echo").mkdir(parents=True)
    mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def host(tmp_path_factory) -> Path:
    return _host(tmp_path_factory.mktemp("ladder"))


def _cli(host: Path, *args: str) -> subprocess.CompletedProcess[str]:
    import os

    env = {k: v for k, v in os.environ.items() if not k.startswith(identity.ENV_PREFIX + "_")}
    env[identity.env_name("PROJECT_ROOT")] = str(host)
    return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(PKG / "cli" / f"{identity.KIT_NAME}.ps1"),
                           *args], cwd=host, env=env, capture_output=True, text=True)


def _module_of(host: Path, typ: str) -> str:
    manifest = json.loads((host / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    return next(mid for mid, m in manifest["modules"].items() if m.get("type") == typ)


@pytest.mark.parametrize("typ", sorted(KIT))
def test_every_built_rung_of_a_kit_driver_plans_to_a_script_it_declares(host, typ):
    module = _module_of(host, typ)
    for rung, how in KIT[typ]["delivery"].items():
        if "pending" in how:
            continue
        ran = _cli(host, "mod", module, "deliver", rung, "--plan")
        assert ran.returncode == 0, (rung, ran.stdout + ran.stderr)
        if "command" in how:
            script = driver_commands(typ)[how["command"]]
            assert Path(script).name in ran.stdout, (rung, ran.stdout)
        else:
            assert f"{how['via']} boot {module}" in ran.stdout


def test_a_built_rung_runs_binding_operands_by_the_scripts_own_parameters(host):
    ran = _cli(host, "mod", "echo", "deliver", "release", "--env", "dev")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "ps1 first=dist env=dev fast=False" in ran.stdout


def test_a_bash_command_rung_runs_under_bash(host):
    if not shutil.which("bash"):
        pytest.skip("no bash")
    ran = _cli(host, "mod", "echo", "deliver", "remote-dev")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "sh remote" in ran.stdout


def test_an_undeclared_rung_is_refused_naming_the_declared_ones(host):
    ran = _cli(host, "mod", "echo", "deliver", "local")
    assert ran.returncode == 1
    assert "declares no delivery rung 'local'" in ran.stdout and "release" in ran.stdout


def test_a_pending_rung_is_refused_with_its_reason(host):
    ran = _cli(host, "mod", "echo", "deliver", "container")
    assert ran.returncode == 1
    assert "not built: not proven yet" in ran.stdout


def test_a_declared_operand_is_rewritten_and_said(host):
    ran = _cli(host, "mod", "echo", "ship")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "ship is deploy -Fast" in ran.stdout
    assert "ps1 first=now env=none fast=True" in ran.stdout


def test_every_rung_names_a_command_its_driver_declares_or_is_pending():
    for typ, entry in KIT.items():
        for rung, how in entry.get("delivery", {}).items():
            assert ("pending" in how) or ("via" in how) or how.get("command") in driver_commands(typ), (typ, rung)


def test_the_hybrid_rung_runs_the_drivers_declared_launch_step_with_its_run_environment(host):
    # The runner names no driver: the step is the one the registry declares. A development run reads
    # the shared .env and .env.dev only -- never a production value (envfile.run_files, amendment 8).
    ran = _cli(host, "mod", "echo", "deliver", "hybrid")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "hybrid module=echo a=dev b= c=shared" in ran.stdout


def test_production_configuration_is_read_only_when_asked_for(host):
    ran = _cli(host, "mod", "echo", "deliver", "hybrid", "--env", "prod")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "hybrid module=echo a=prod b=prod c=shared" in ran.stdout


def test_a_driver_that_declares_a_launch_step_is_given_the_kits_host_run_as_run(host):
    # No driver ships a `run` script of its own any more (ADR-001 amendment 7): `run` is the kit's
    # one host runner, dispatched as the driver's command, reading the module from the dispatch.
    ran = _cli(host, "mod", "echo", "run")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "hybrid module=echo a=dev b= c=shared" in ran.stdout
