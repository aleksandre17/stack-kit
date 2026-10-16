"""Bash and PowerShell reach the selected deploy target only through the resolver (ADR-001 amendment 9),
the CLI's --target never outlives its run, and a deploy carries its provenance."""
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
BASH = shutil.which("bash")
TARGETS = {"schema": 1, "defaults": {"prod": "prod", "dev": "stage"}, "targets": {
    "prod": {"runtime": "docker-compose", "host": "prod.example.test", "user": "svc", "port": 2201,
             "root": "/srv/prod", "ssh": {"knownHosts": "ops/deploy/known_hosts"}},
    "stage": {"runtime": "docker-compose", "host": "stage.example.test", "user": "svc", "root": "/srv/stage"}}}


@pytest.fixture(scope="module")
def host(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("shells") / "targets-shell-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    (root / "ops" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / "ops" / "deploy" / "known_hosts").write_text("# pinned\n", encoding="utf-8")
    (root / "ops" / "deploy" / "targets.json").write_text(json.dumps(TARGETS), encoding="utf-8")
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["deploy"] = {"targets": "ops/deploy/targets.json"}
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _env(host: Path, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(identity.ENV_PREFIX + "_")}
    env[identity.env_name("PROJECT_ROOT")] = str(host)
    env.update({identity.env_name(k): v for k, v in extra.items()})
    return env


@pytest.mark.skipif(BASH is None, reason="no bash")
def test_bash_reads_the_server_and_ssh_options_of_the_selected_target(host):
    lib = (PKG / "lib").as_posix()
    script = (f'source "{lib}/project.sh"; source "{lib}/env.sh"; source "{lib}/ssh.sh"; '
              'stack_kit_deploy_env_value DEPLOY_SERVER; stack_kit_ssh_extra_args')
    out = subprocess.run([BASH, "-c", script], env=_env(host), capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "svc@prod.example.test" in out.stdout and "Port=2201" in out.stdout
    assert "StrictHostKeyChecking=yes" in out.stdout
    out = subprocess.run([BASH, "-c", script], env=_env(host, ENVIRONMENT="dev"), capture_output=True, text=True)
    assert "svc@stage.example.test" in out.stdout


@pytest.mark.skipif(PWSH is None, reason="no PowerShell")
def test_powershell_reads_the_target_and_its_layout(host):
    lib = PKG / "lib"
    script = (f". '{lib / 'project.ps1'}'; . '{lib / 'env.ps1'}'; . '{lib / 'ssh.ps1'}'; "
              f". '{PKG / 'toolkit' / 'powershell' / 'Deploy-Path.ps1'}'; $OpsSecretsModule = 'web'; "
              "(Get-StackKitSshExtraArgs) -join ' '; Resolve-ModuleDeployPath -ContainerName c -Kind compose-dev")
    out = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", script], env=_env(host, TARGET="stage"),
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "StrictHostKeyChecking=yes" in out.stdout
    assert "/srv/stage/golden-consumer/dev/modules/c" in out.stdout


@pytest.mark.skipif(PWSH is None, reason="no PowerShell")
def test_the_targets_verb_prints_every_target_and_module_path(host):
    out = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(PKG / "cli" / f"{identity.KIT_NAME}.ps1"),
                          "targets", "--plan"], env=_env(host), cwd=host, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "prod (default: prod)" in out.stdout and "svc@prod.example.test:2201" in out.stdout
    assert "/srv/prod/golden-consumer/prod/modules/" in out.stdout and "identity=agent" in out.stdout
    assert "compose project golden-consumer-dev" in out.stdout and "(declared; pending:" in out.stdout


@pytest.mark.skipif(PWSH is None, reason="no PowerShell")
def test_a_target_chosen_by_flag_does_not_outlive_its_run(host):
    cli = PKG / "cli" / f"{identity.KIT_NAME}.ps1"
    script = (f"& '{cli}' targets --target stage | Out-Null; $first = $env:STACK_KIT_TARGET; "
              f"& '{cli}' targets | Out-Null; \"first=$first after=$env:STACK_KIT_TARGET\"")
    out = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", script], env=_env(host), cwd=host,
                         capture_output=True, text=True)
    assert "first=stage after=" in out.stdout and "after=stage" not in out.stdout, out.stdout + out.stderr


@pytest.mark.skipif(BASH is None or shutil.which("git") is None, reason="needs bash and git")
def test_a_production_deploy_needs_a_clean_checkout_and_carries_its_revision(tmp_path):
    repo = tmp_path / "prov"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    (repo / "a.txt").write_text("1\n", encoding="utf-8")
    subprocess.run([*git, "add", "a.txt"], check=True)
    subprocess.run([*git, "commit", "-qm", "c"], check=True)
    prov = (PKG / "toolkit" / "deploy" / "provenance.sh").as_posix()
    run = lambda env: subprocess.run([BASH, "-c", f'source "{prov}"; deploy_require_provenance {env} && echo "rev=$IMAGE_REVISION"'],
                                     env={**_env(repo)}, capture_output=True, text=True)
    clean = run("prod")
    assert clean.returncode == 0 and "rev=" in clean.stdout and "dirty" not in clean.stdout, clean.stderr
    (repo / "a.txt").write_text("2\n", encoding="utf-8")
    dirty = run("prod")
    assert dirty.returncode != 0 and "clean checkout" in dirty.stderr
    dev = run("dev")
    assert dev.returncode == 0 and "-dirty" in dev.stdout
    subprocess.run([*git, "checkout", "-q", "--", "a.txt"], check=True)
    (repo / "New.java").write_text("class New {}\n", encoding="utf-8")  # untracked: it would be built in
    assert run("prod").returncode != 0
