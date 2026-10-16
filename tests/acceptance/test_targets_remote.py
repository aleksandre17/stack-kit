"""The server side of a declared target, proven against a local directory standing in for the server
(ADR-001 amendment 9): the preflight claims a project's directory or refuses another's, a foreign
compose project on a declared port is refused, and `targets --verify` reports drift, read-only.

What this does NOT prove: a real sshd, a real docker daemon's port labels, and GNU vs busybox `find`
on a real server. The scripts use only POSIX sh, `find -path/-prune/-print` and `docker ps --filter
publish= --format`, and the stand-ins answer in those forms.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PKG, WORKING_ROOT
from lib import identity, targets

BASH = shutil.which("bash")
PWSH = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")


def _bin(tmp_path: Path, name: str, body: str) -> Path:
    """A stand-in command on PATH (a .bat beside a sh script, so Windows and POSIX both find it)."""
    d = tmp_path / "bin"
    d.mkdir(parents=True, exist_ok=True)
    sh = d / name
    sh.write_text("#!/bin/bash\n" + body, encoding="utf-8", newline="\n")
    os.chmod(sh, 0o755)
    if os.name == "nt":
        (d / f"{name}.bat").write_text(f'@"{BASH}" "{sh.as_posix()}" %*\r\n', encoding="utf-8")
    return d


def _run(script: str, path_dir: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if path_dir is not None:
        env["PATH"] = str(path_dir) + os.pathsep + env["PATH"]
    return subprocess.run([BASH, "-s"], input=script, capture_output=True, text=True, env=env)


def _target(server: Path, **extra) -> dict:
    return {"runtime": "docker-compose", "host": "h", "user": "u", "root": server.as_posix(), **extra}


# ── apply: the preflight before any write ────────────────────────────────────

def test_the_first_deploy_claims_the_project_directory_and_another_project_is_refused(tmp_path):
    server = tmp_path / "srv"
    server.mkdir()
    t = _target(server)
    mine = targets.preflight(t, project="geo", environment="prod", repository="github.com/o/geo", services=[])
    assert _run(mine).returncode == 0
    marker = json.loads((server / "geo" / targets.MARKER).read_text(encoding="utf-8"))
    assert marker == {"project": "geo", "repository": "github.com/o/geo"}
    assert _run(mine).returncode == 0, "the owner's own second deploy was refused"
    # A different repository that happens to choose the same slug never writes into it.
    other = targets.preflight(t, project="geo", environment="prod", repository="github.com/x/geo", services=[])
    ran = _run(other)
    assert ran.returncode == 3 and "belongs to project 'geo' (github.com/o/geo)" in ran.stderr, ran.stderr
    assert json.loads((server / "geo" / targets.MARKER).read_text(encoding="utf-8")) == marker


def test_a_declared_port_another_compose_project_publishes_is_refused_naming_it(tmp_path):
    server = tmp_path / "srv"
    server.mkdir()
    t = _target(server, ports={"prod": {"api": [8080]}})
    script = targets.preflight(t, project="geo", environment="prod", repository="", services=["api"])
    foreign = _bin(tmp_path / "a", "docker", 'echo "shop-prod"\n')
    ran = _run(script, foreign)
    assert ran.returncode == 4 and "port 8080 is published by compose project 'shop-prod', not geo-prod" in ran.stderr
    own = _bin(tmp_path / "b", "docker", 'echo "geo-prod"\n')
    assert _run(script, own).returncode == 0


# ── verify: what is there against what is declared ───────────────────────────

def _tree(server: Path) -> dict:
    return targets.declared_tree(_target(server), project="geo", services=["api", "web"],
                                 environments=["dev", "prod"])


def _verify(server: Path, *, repository: str = "github.com/o/geo") -> list[str]:
    tree = _tree(server)
    ran = _run(targets.verify_script(tree))
    assert ran.returncode == 0, ran.stderr
    return targets.verify_report(tree, ran.stdout, project="geo", repository=repository, keep_limit=3)


def _deploy(server: Path, *envs: str) -> Path:
    project = server / "geo"
    project.mkdir(parents=True, exist_ok=True)
    (project / targets.MARKER).write_text(json.dumps({"project": "geo", "repository": "github.com/o/geo"}) + "\n",
                                          encoding="utf-8")
    for env in envs:
        for svc in ("api", "web"):
            unit = project / env / "modules" / svc
            (unit / "logs").mkdir(parents=True)
            (unit / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
    return project


def test_a_server_that_holds_the_declared_tree_matches(tmp_path):
    _deploy(tmp_path / "srv", "dev", "prod")
    assert _verify(tmp_path / "srv") == []


def test_drift_is_named_and_nothing_is_deleted(tmp_path):
    server = tmp_path / "srv"
    project = _deploy(server, "prod")
    (project / "stray.tar.gz").write_text("x", encoding="utf-8")
    (project / "prod" / "scratch").mkdir()
    versions = project / "prod" / "modules" / "api" / "versions"
    versions.mkdir()
    for i in range(5):
        (versions / f"app-{i}.jar").write_text("j", encoding="utf-8")
    drift = _verify(server)
    joined = "\n".join(drift)
    assert f"undeclared: {(project / 'stray.tar.gz').as_posix()}" in joined
    assert f"undeclared: {(project / 'prod' / 'scratch').as_posix()} (directory" in joined
    assert "missing: " + (project / "dev" / "modules" / "api").as_posix() in joined and "not deployed" in joined
    assert "keeps 5 versioned artifacts" in joined and "the limit is 3" in joined
    assert (project / "stray.tar.gz").exists(), "verify deleted a file"


def test_a_marker_that_is_absent_or_another_projects_is_drift(tmp_path):
    server = tmp_path / "srv"
    project = _deploy(server, "dev", "prod")
    (project / targets.MARKER).unlink()
    assert any(d.startswith("marker absent") for d in _verify(server))
    (project / targets.MARKER).write_text(json.dumps({"project": "shop", "repository": "github.com/x/shop"}), encoding="utf-8")
    assert any("marker names another project: 'shop'" in d for d in _verify(server))


def test_a_current_that_points_at_nothing_is_drift(tmp_path):
    server = tmp_path / "srv"
    project = _deploy(server, "dev", "prod")
    try:
        os.symlink(project / "prod" / "modules" / "api" / "releases" / "gone",
                   project / "prod" / "modules" / "api" / "current", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this machine cannot create a symlink")
    assert any(d.startswith("current points at nothing") for d in _verify(server))


def test_a_project_never_deployed_is_one_missing_directory(tmp_path):
    (tmp_path / "srv").mkdir()
    assert _verify(tmp_path / "srv") == [f"missing: {(tmp_path / 'srv' / 'geo').as_posix()} (the project's directory -- nothing is deployed here)"]


# ── the verb, through a stand-in ssh ─────────────────────────────────────────

def _host(tmp_path: Path, server: Path, **target_extra) -> Path:
    root = tmp_path / "verify-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    (root / "ops" / "deploy").mkdir(parents=True, exist_ok=True)
    doc = {"schema": 1, "targets": {"prod": {**_target(server), **target_extra}}}
    (root / "ops" / "deploy" / "targets.json").write_text(json.dumps(doc), encoding="utf-8")
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["deploy"] = {"targets": "ops/deploy/targets.json"}
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _verb(root: Path, path_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(identity.ENV_PREFIX + "_")}
    env[identity.env_name("PROJECT_ROOT")] = str(root)
    env["PYTHONPATH"] = str(PKG)
    env["PATH"] = str(path_dir) + os.pathsep + env["PATH"]
    return subprocess.run([sys.executable, "-B", str(PKG / "lib" / "targets.py"), "--verify", *args],
                          cwd=root, env=env, capture_output=True, text=True)


def test_verify_exits_one_on_drift_and_two_when_nothing_could_be_verified(tmp_path):
    server = tmp_path / "srv"
    server.mkdir()
    root = _host(tmp_path, server)
    reachable = _bin(tmp_path / "ok", "ssh", "exec bash -s\n")
    ran = _verb(root, reachable)
    assert ran.returncode == 1 and "missing:" in ran.stdout, ran.stdout + ran.stderr
    unreachable = _bin(tmp_path / "down", "ssh", 'echo "ssh: connect to host h port 22: Connection refused" >&2; exit 255\n')
    ran = _verb(root, unreachable)
    assert ran.returncode == 2 and "NOT VERIFIED" in ran.stdout and "unreachable" in ran.stdout
    pending = _host(tmp_path / "p", server, pending="no host yet")
    ran = _verb(pending, reachable)
    assert ran.returncode == 2 and "NOT VERIFIED" in ran.stdout and "pending: no host yet" in ran.stdout
