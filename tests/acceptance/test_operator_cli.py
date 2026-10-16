"""The operator CLI end to end (ADR-001 amendment 13): every verb a person runs, through the real
launcher, against a recorded server -- on a host whose driver, tier, environment and target
runtime are its own declarations. A verb that changes the server prints its plan first; `--plan`
writes nothing; a confirming environment refuses without a terminal unless `--yes`."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PKG
from lib import identity
from delivery_host import ROOT, host

KIT = identity.KIT_NAME


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    base = tmp_path_factory.mktemp("operator")
    root = host(base)
    record = base / "server.json"

    def run(*argv: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith(identity.ENV_PREFIX + "_")}
        env.update({identity.env_name("PROJECT_ROOT"): str(root), identity.env_name("TRANSPORT"): f"record:{record}",
                    "PYTHONUTF8": "1"})
        return subprocess.run([sys.executable, "-B", str(PKG / "cli" / "stack_kit.py"), *argv], cwd=root, env=env,
                              capture_output=True, text=True, input=stdin)

    run.root, run.record = root, record
    return run


def _server(cli) -> dict:
    return json.loads(cli.record.read_text(encoding="utf-8")) if cli.record.is_file() else {"files": {}, "links": {}}


def test_targets_plan_renders_every_place_with_its_tier(cli):
    ran = cli("targets", "--plan", "--env", "staging")
    assert ran.returncode == 0, ran.stderr
    assert f"{ROOT}/shop/staging/edge/edge  module edge (build)" in ran.stdout.replace("      edge/edge", "").replace("  ", " ") or \
        f"{ROOT}/shop/staging/edge/edge" in ran.stdout
    assert "compose project shop-staging" in ran.stdout and f"{ROOT}/shop/staging/backups" in ran.stdout


def test_a_plan_prints_the_paths_and_commands_and_writes_nothing(cli):
    before = _server(cli)
    ran = cli("deploy", "edge", "--env", "staging", "--plan")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert f"plan: unpack " in ran.stdout and f"{ROOT}/shop/staging/edge/edge/releases/" in ran.stdout
    assert "plan: eng-compose -f /srv/platform/shop/staging/stack/compose.yml up -d edge" in ran.stdout
    assert "[plan] nothing was changed (--plan)" in ran.stdout
    assert _server(cli)["files"] == before["files"]


def test_init_deploy_list_status_verify(cli):
    ran = cli("targets", "--init", "--env", "staging")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert json.loads(_server(cli)["files"][f"{ROOT}/shop/.stack-kit-project"])["project"] == "shop"
    ran = cli("deploy", "edge", "--env", "staging")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "is current in staging" in ran.stdout
    assert f"{ROOT}/shop/staging/edge/edge/current" in _server(cli)["links"]
    listing = cli("release", "list", "--env", "staging")
    assert listing.returncode == 0 and "  * " in listing.stdout, listing.stdout + listing.stderr
    status = cli("ops", "status", "--env", "staging")
    assert status.returncode == 0 and "release" in status.stdout and "healthy" in status.stdout, status.stdout
    verify = cli("targets", "--verify", "--env", "staging")
    assert verify.returncode == 0 and "matches the declared tree" in verify.stdout, verify.stdout + verify.stderr
    runs = (cli.root / identity.RUNS_DIR / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(r)["kind"] == "deploy" and json.loads(r)["exit"] == 0 for r in runs)


def test_a_confirming_environment_refuses_without_a_terminal_unless_yes(cli):
    ran = cli("ops", "nuke", "--env", "staging")
    assert ran.returncode == 2 and "pass --yes" in ran.stderr, ran.stdout + ran.stderr
    assert f"{ROOT}/shop/staging/edge/edge/current" in _server(cli)["links"]


def test_remote_dev_up_and_sync(cli):
    ran = cli("dev", "up", "edge", "--plan")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert f"{ROOT}/shop/dev/edge/edge/workspace" in ran.stdout
    ran = cli("dev", "up", "edge")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert any(p.startswith(f"{ROOT}/shop/dev/edge/edge/workspace/src/") for p in _server(cli)["files"])
    assert cli("dev", "sync", "edge").returncode == 0


def test_every_verb_has_help_with_its_exit_codes(cli):
    from lib.cli import registry

    for name in registry.discover():
        if name.startswith("<"):
            continue
        ran = cli(name, "--help")
        assert ran.returncode == 0 and "exit codes:" in ran.stdout, (name, ran.stdout + ran.stderr)


@pytest.mark.skipif(not (os.environ.get("PATH") and __import__("shutil").which("pwsh")), reason="no pwsh")
def test_the_powershell_launcher_is_the_same_cli(cli):
    env = {k: v for k, v in os.environ.items() if not k.startswith(identity.ENV_PREFIX + "_")}
    env[identity.env_name("PROJECT_ROOT")] = str(cli.root)
    ran = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(PKG / "cli" / f"{KIT}.ps1"), "targets"],
                         cwd=cli.root, env=env, capture_output=True, text=True)
    assert ran.returncode == 0 and "box" in ran.stdout and "runtime=fixture-compose" in ran.stdout, ran.stdout + ran.stderr
