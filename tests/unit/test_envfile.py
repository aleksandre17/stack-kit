"""Env files have one home (lib/envfile.py, ADR-001 decision 2), including what a run reads."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PKG
from lib import envfile


def _folder(tmp_path: Path, shared: str = "", **files: str) -> Path:
    d = tmp_path / "secrets" / "api"
    d.mkdir(parents=True)
    for profile, text in files.items():
        (d / f".env.{profile}").write_text(text, encoding="utf-8")
    if shared:
        (d / ".env").write_text(shared, encoding="utf-8")
    return tmp_path / "secrets"


def test_a_development_run_never_reads_a_production_value(tmp_path):
    # 12-factor III (amendment 8): the shared .env, then .env.dev over it -- .env.prod is not read.
    root = _folder(tmp_path, shared="S=shared\nA=shared\n", prod="A=prod\nB=prod\nC=prod\n", dev="A=dev\nB=\n# C=dev\n")
    assert envfile.merged(envfile.run_files(root, "api")) == {"S": "shared", "A": "dev"}


def test_a_production_run_reads_production_only_when_asked(tmp_path):
    root = _folder(tmp_path, shared="S=shared\n", prod="A=prod\n", dev="A=dev\nD=dev\n")
    assert envfile.merged(envfile.run_files(root, "api", "prod")) == {"S": "shared", "A": "prod"}


def test_a_run_environment_is_declared_never_improvised(tmp_path):
    with pytest.raises(ValueError):
        envfile.run_files(_folder(tmp_path), "api", "staging")


def test_what_a_development_run_no_longer_fills_from_production_is_named_never_valued(tmp_path):
    root = _folder(tmp_path, shared="S=x\n", prod="A=secret\nB=secret\nS=prod\n", dev="A=dev\n")
    assert envfile.dev_run_loses(root, "api") == ["B"]


def test_a_compose_profile_keeps_its_own_order(tmp_path):
    root = _folder(tmp_path, prod="A=prod\n", dev="A=dev\n")
    assert envfile.merged(envfile.folder_files(root, "api")) == {"A": "prod"}


def test_the_resolver_answers_a_run_as_one_json_object(tmp_path):
    from conftest import WORKING_ROOT
    from lib import identity

    manifest = json.loads((WORKING_ROOT / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    folder = next(iter(manifest["modules"].values()))["secretsModule"]
    env = {"PYTHONPATH": str(PKG), "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
           identity.env_name("PROJECT_ROOT"): str(WORKING_ROOT)}
    for extra in ([], ["prod"]):
        ran = subprocess.run([sys.executable, "-B", str(PKG / "lib" / "resolve_cli.py"), "run-env", folder, *extra],
                             capture_output=True, text=True, env=env, cwd=WORKING_ROOT)
        assert ran.returncode == 0, ran.stderr
        assert isinstance(json.loads(ran.stdout), dict)
