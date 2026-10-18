"""Through the real CLI, a project extends the kit by declaration alone (ADR-001 amendment 12): a
driver whose commands are Python scripts (a `-Flag` operand included), a script runtime of its own, a
lifecycle step (`typecheck`) that becomes a verb, and an environment (`staging`) a host run reads."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import PKG, WORKING_ROOT
from lib import identity

PWSH = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(PWSH is None, reason="needs PowerShell")

BUILD = "import sys\nprint('python build', *sys.argv[1:])\n"
TEST = "import sys\nprint('python test')\nsys.exit(int(sys.argv[1]) if len(sys.argv) > 1 else 0)\n"
TYPECHECK = "print('python typecheck')\n"
HYBRID = '"run in $Environment where=$env:WHERE"\n'


@pytest.fixture(scope="module")
def host(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("ext") / "ext-cli-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    reg = root / "ops" / "drivers"
    d = reg / "py-svc"
    d.mkdir(parents=True)
    (d / "build.py").write_text(BUILD, encoding="utf-8")
    (d / "test.py").write_text(TEST, encoding="utf-8")
    (d / "typecheck.tc").write_text(TYPECHECK, encoding="utf-8")
    (d / "hybrid.ps1").write_text(HYBRID, encoding="utf-8")
    (reg / "registry.json").write_text(json.dumps({"py-svc": {
        "label": "a Python service", "roles": ["api"],
        "commands": {"build": "build.py", "test": {"script": "test.py", "runtime": "python"}, "typecheck": "typecheck.tc"},
        "hybrid": {"script": "hybrid.ps1"}}}), encoding="utf-8")
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["drivers"] = {"registry": "ops/drivers/registry.json"}
    manifest["modules"] = {"svc": {"type": "py-svc", "role": "api", "path": "apps/svc", "secretsModule": "svc"}}
    manifest["catalogs"] = {"lifecycle": [{"id": "typecheck", "after": "lint"}], "environments": [{"id": "staging", "after": "dev"}]}
    # A runtime of the project's own: `*.tc` files run under Python, through a one-line launcher.
    manifest["runtimes"] = {"typecheck-files": {"match": ["*.tc"], "argv": ["{python}", "{script}", "{operands}"]}}
    for section in ("stack", "stackDeploy", "cli", "vscode"):
        manifest.pop(section, None)
    mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (root / "apps" / "svc").mkdir(parents=True, exist_ok=True)
    secrets = root / manifest["secrets"] / "svc"
    secrets.mkdir(parents=True, exist_ok=True)
    (secrets / ".env.staging").write_text("WHERE=staging\n", encoding="utf-8")
    (secrets / ".env.dev").write_text("WHERE=dev\n", encoding="utf-8")
    return root


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(identity.ENV_PREFIX + "_")}
    env[identity.env_name("PROJECT_ROOT")] = str(root)
    return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(PKG / "cli" / f"{identity.KIT_NAME}.ps1"),
                           *args], cwd=root, env=env, capture_output=True, text=True)


def test_a_python_command_runs_with_its_operands_a_flag_included(host):
    ran = _cli(host, "mod", "svc", "build", "-Fast", "now")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "python build -Fast now" in ran.stdout


def test_a_python_command_s_exit_code_is_the_steps(host):
    ran = _cli(host, "mod", "svc", "test", "3")
    assert ran.returncode == 3, ran.stdout + ran.stderr


def test_the_lifecycle_verb_runs_a_python_driver_across_modules(host):
    ran = _cli(host, "build")
    assert ran.returncode == 0 and "python build" in ran.stdout and "build OK (1 module(s) ran)" in ran.stdout, ran.stdout + ran.stderr


def test_a_host_declared_step_is_a_verb_and_runs_under_a_host_declared_runtime(host):
    ran = _cli(host, "typecheck")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "python typecheck" in ran.stdout and "typecheck OK (1 module(s) ran)" in ran.stdout


def test_a_host_declared_environment_is_one_a_host_run_reads(host):
    ran = _cli(host, "hybrid", "boot", "svc", "--env", "staging")
    assert ran.returncode == 0 and "run in staging where=staging" in ran.stdout, ran.stdout + ran.stderr
    refused = _cli(host, "hybrid", "boot", "svc", "--env", "qa")
    assert refused.returncode != 0 and "not a declared environment" in (refused.stdout + refused.stderr)
