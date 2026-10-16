"""`stack-kit init --plan` drafts a manifest from a tree that has none, and writes nothing (ADR-001
amendment 10)."""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from conftest import PKG
from lib import identity

PWSH = shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.skipif(PWSH is None, reason="no PowerShell")
def test_init_plan_drafts_without_writing(tmp_path):
    root = tmp_path / "fresh"
    (root / "svc").mkdir(parents=True)
    (root / "svc" / "package.json").write_text('{"dependencies": {"fastify": "4"}}', encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(identity.ENV_PREFIX + "_")}
    ran = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(PKG / "cli" / f"{identity.KIT_NAME}.ps1"),
                          "init", "--plan"], cwd=root, env=env, capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert '+ modules.svc: {"type": "node-api"' in ran.stdout, ran.stdout
    assert not (root / identity.MANIFEST_FILENAME).exists()
