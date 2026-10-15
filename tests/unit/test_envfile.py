"""Env files have one home (lib/envfile.py, ADR-001 decision 2), including a host run's order."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import PKG
from lib import envfile


def _folder(tmp_path: Path, **files: str) -> Path:
    d = tmp_path / "secrets" / "api"
    d.mkdir(parents=True)
    for profile, text in files.items():
        (d / f".env.{profile}").write_text(text, encoding="utf-8")
    return tmp_path / "secrets"


def test_a_host_run_takes_dev_over_prod_and_prod_fills_the_rest(tmp_path):
    root = _folder(tmp_path, prod="A=prod\nB=prod\nC=prod\n", dev="A=dev\nB=\n# C=dev\n")
    assert envfile.merged(envfile.host_run_files(root, "api")) == {"A": "dev", "B": "prod", "C": "prod"}


def test_a_compose_profile_keeps_its_own_order(tmp_path):
    root = _folder(tmp_path, prod="A=prod\n", dev="A=dev\n")
    assert envfile.merged(envfile.folder_files(root, "api")) == {"A": "prod"}


def test_the_resolver_answers_a_host_run_as_one_json_object(tmp_path):
    from conftest import WORKING_ROOT
    from lib import identity

    manifest = json.loads((WORKING_ROOT / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    folder = next(iter(manifest["modules"].values()))["secretsModule"]
    env = {"PYTHONPATH": str(PKG), "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
           identity.env_name("PROJECT_ROOT"): str(WORKING_ROOT)}
    ran = subprocess.run([sys.executable, "-B", str(PKG / "lib" / "resolve_cli.py"), "run-env", folder],
                         capture_output=True, text=True, env=env, cwd=WORKING_ROOT)
    assert ran.returncode == 0, ran.stderr
    assert isinstance(json.loads(ran.stdout), dict)
