"""A new project gets a working system from one command (ADR-001 amendment 8).

`init` in an empty repository, with the kit vendored at the convention's place, has to leave a
project that `validate` passes, that declares its command lines (`commands`), whose CI workflow is
generated, and whose secrets are ignored while their examples are tracked. It once failed at its
first Python call (`& @py`) and nothing noticed, because nothing ran it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import PKG
from lib import identity

PWSH = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(PWSH is None or shutil.which("git") is None, reason="needs PowerShell and git")


def _run(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(identity.ENV_PREFIX + "_")}
    return subprocess.run(list(argv), cwd=cwd, env=env, capture_output=True, text=True)


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("new") / "my-app"
    kit = root / identity.VENDOR_DIRS[0]
    tracked = _run(PKG, "git", "ls-files", "-co", "--exclude-standard").stdout.splitlines()
    for rel in (r for r in tracked if not r.startswith("tests/") and (PKG / r).is_file()):
        (kit / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PKG / rel, kit / rel)
    _run(root, "git", "init", "-q", ".")
    ran = _run(root, PWSH, "-NoProfile", "-NonInteractive", "-File", str(kit / "cli" / f"{identity.KIT_NAME}.ps1"), "init")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "not recognized" not in ran.stdout + ran.stderr, ran.stdout + ran.stderr
    return root


def test_the_new_project_validates(project):
    ran = _run(project, PWSH, "-NoProfile", "-NonInteractive", "-File", "ops/cli/stack-kit.ps1", "validate")
    assert ran.returncode == 0, ran.stdout + ran.stderr


def test_it_declares_its_command_lines_through_its_launcher(project):
    manifest = json.loads((project / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["commands"]["test"] == "pwsh ops/cli/stack-kit.ps1 test"
    assert (project / "ops" / "cli" / "stack-kit.ps1").is_file()


def test_its_ci_workflow_is_generated_and_current(project):
    assert (project / ".github" / "workflows" / "ci.yml").is_file()
    ran = _run(project, PWSH, "-NoProfile", "-NonInteractive", "-File", "ops/cli/stack-kit.ps1", "ci-gen", "--check")
    assert ran.returncode == 0, ran.stdout + ran.stderr


def test_its_secrets_are_ignored_and_their_examples_are_not(project):
    ignored = _run(project, "git", "check-ignore", "ops/config/backend/.env.dev", "ops/config/deploy.env").stdout
    assert "ops/config/backend/.env.dev" in ignored and "ops/config/deploy.env" in ignored
    kept = _run(project, "git", "check-ignore", "ops/config/backend/.env.example")
    assert kept.returncode == 1, "a secrets example is ignored"
