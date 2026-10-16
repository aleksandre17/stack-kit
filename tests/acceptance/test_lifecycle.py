"""Every module builds, tests and lints through its driver, and `stack-kit build|test|lint` runs the
step across the modules, fail-fast, with the step's exit code (ADR-001 amendment 8).

The Node family is proven with real `npm run` over package.json scripts that are `node -e` one-liners
(no dependency, no network); java-boot with a stand-in Gradle wrapper that echoes its argv; dotnet
with a real `dotnet build` of a dependency-free class library when the SDK is on this machine.
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
from lib import identity

PWSH = shutil.which("pwsh") or shutil.which("powershell")
NPM = shutil.which("npm")
pytestmark = pytest.mark.skipif(PWSH is None or NPM is None, reason="needs PowerShell and npm")


def _package(scripts: dict[str, str]) -> str:
    return json.dumps({"name": "fixture", "version": "1.0.0", "private": True, "scripts": scripts})


def _spa(root: Path, mid: str, scripts: dict[str, str]) -> dict:
    d = root / "fx" / mid
    d.mkdir(parents=True)
    (d / "package.json").write_text(_package(scripts), encoding="utf-8")
    (d / "node_modules").mkdir()  # installed: the step runs, it does not fetch
    return {"type": "node-spa", "role": "ui", "path": f"fx/{mid}", "secretsModule": mid}


def _host(tmp_path: Path, modules: dict) -> Path:
    root = tmp_path / "lifecycle-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["modules"] = {mid: build(root, mid) for mid, build in modules.items()}
    for section in ("stack", "stackDeploy", "cli", "vscode"):
        manifest.pop(section, None)
    mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(identity.ENV_PREFIX + "_")}
    env[identity.env_name("PROJECT_ROOT")] = str(root)
    return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(PKG / "cli" / f"{identity.KIT_NAME}.ps1"),
                           *args], cwd=root, env=env, capture_output=True, text=True)


def _records(root: Path) -> list[dict]:
    runs = root / identity.RUNS_DIR / "runs.jsonl"
    return [json.loads(line) for line in runs.read_text(encoding="utf-8").splitlines() if line.strip()]


OK = {"build": "node -e \"console.log('built '+process.cwd().split(/[\\\\/]/).pop())\"",
      "test": "node -e \"console.log('tested')\"", "start": "node -e \"console.log('started')\""}
FAILS = {**OK, "build": "node -e \"process.exit(3)\""}


@pytest.fixture(scope="module")
def spa_host(tmp_path_factory) -> Path:
    return _host(tmp_path_factory.mktemp("spa"), {
        "web": lambda r, m: _spa(r, m, OK),
        "admin": lambda r, m: {**_spa(r, m, {**OK, "build": "node -e \"console.log('built admin')\""}),
                               "node": {"scripts": {"test": ""}}},
    })


def test_a_spa_module_builds_and_tests_by_its_package_scripts(spa_host):
    ran = _cli(spa_host, "mod", "web", "build")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "built web" in ran.stdout
    ran = _cli(spa_host, "mod", "web", "test")
    assert ran.returncode == 0 and "tested" in ran.stdout, ran.stdout + ran.stderr


def test_a_lint_the_package_lacks_is_skipped_and_said(spa_host):
    ran = _cli(spa_host, "lint")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "skipped: package.json has no 'lint' script" in ran.stdout


def test_build_runs_every_module_and_records_each_step(spa_host):
    ran = _cli(spa_host, "build")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "built web" in ran.stdout and "built admin" in ran.stdout and "build OK (2 module(s))" in ran.stdout
    steps = [r for r in _records(spa_host) if r["kind"] == "step" and r["step"] == "build"]
    assert {r["module"] for r in steps} >= {"web", "admin"} and all(r["exit"] == 0 for r in steps)
    assert all(r["startedAt"] <= r["endedAt"] and "gitSha" in r for r in steps)
    top = spa_host / identity.RUNS_DIR.split("/")[0]
    assert (top / ".gitignore").read_text(encoding="utf-8").strip() == "*"


def test_a_module_that_declares_no_tests_says_so_and_passes(spa_host):
    ran = _cli(spa_host, "test", "admin")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "declared none" in ran.stdout


def test_the_host_run_is_the_package_start_script(spa_host):
    ran = _cli(spa_host, "mod", "web", "run")
    assert ran.returncode == 0 and "started" in ran.stdout, ran.stdout + ran.stderr


def test_build_stops_at_the_first_failure_with_its_exit_code(tmp_path):
    root = _host(tmp_path, {
        "first": lambda r, m: _spa(r, m, OK),
        "broken": lambda r, m: _spa(r, m, FAILS),
        "never": lambda r, m: _spa(r, m, {**OK, "build": "node -e \"console.log('built never')\""}),
    })
    ran = _cli(root, "build")
    assert ran.returncode == 3, ran.stdout + ran.stderr
    assert "built first" in ran.stdout and "built never" not in ran.stdout
    assert "[broken build] FAILED (exit 3)" in ran.stdout
    assert [r["exit"] for r in _records(root) if r["module"] == "broken"] == [3]


def test_a_missing_required_script_fails_naming_the_remedy(tmp_path):
    root = _host(tmp_path, {"web": lambda r, m: _spa(r, m, {"build": OK["build"]})})
    ran = _cli(root, "test")
    assert ran.returncode == 1
    assert "package.json has no 'test' script" in ran.stdout and "node.scripts.test" in ran.stdout


def _gradle_module(root: Path, mid: str) -> dict:
    d = root / "fx" / mid
    d.mkdir(parents=True)
    (d / "gradlew.bat").write_text("@echo gradle %*\r\n", encoding="utf-8")
    (d / "gradlew").write_text("#!/bin/sh\necho gradle \"$@\"\n", encoding="utf-8")
    os.chmod(d / "gradlew", 0o755)
    return {"type": "java-boot", "role": "api", "path": f"fx/{mid}", "secretsModule": mid,
            "hybrid": {"gradleProject": "app"}}


def test_a_gradle_module_builds_without_tests_and_tests_through_its_wrapper(tmp_path):
    root = _host(tmp_path, {"api": _gradle_module})
    ran = _cli(root, "mod", "api", "build")
    assert ran.returncode == 0 and "gradle :app:build -x test" in ran.stdout, ran.stdout + ran.stderr
    ran = _cli(root, "mod", "api", "test")
    assert ran.returncode == 0 and "gradle :app:test" in ran.stdout, ran.stdout + ran.stderr


CLASSLIB = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net{v}.0</TargetFramework></PropertyGroup>
</Project>
"""


def _dotnet_major() -> int | None:
    dotnet = shutil.which("dotnet")
    if not dotnet:
        return None
    ran = subprocess.run([dotnet, "--version"], capture_output=True, text=True)
    return int(ran.stdout.split(".")[0]) if ran.returncode == 0 and ran.stdout[:1].isdigit() else None


@pytest.mark.skipif(_dotnet_major() is None, reason="no dotnet SDK on this machine")
def test_a_dotnet_module_builds_its_project_and_declares_its_tests(tmp_path):
    def module(root: Path, mid: str) -> dict:
        d = root / "fx" / mid
        d.mkdir(parents=True)
        (d / "Lib.csproj").write_text(CLASSLIB.format(v=_dotnet_major()), encoding="utf-8")
        (d / "Lib.cs").write_text("namespace Lib; public static class Answer { public const int Value = 42; }\n",
                                  encoding="utf-8")
        return {"type": "dotnet-aspnet", "role": "api", "path": f"fx/{mid}", "secretsModule": mid,
                "dotnet": {"configuration": "Debug", "test": ""}}

    root = _host(tmp_path, {"api": module})
    ran = _cli(root, "build")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert (root / "fx" / "api" / "bin" / "Debug").is_dir()
    ran = _cli(root, "test")
    assert ran.returncode == 0 and "declared none" in ran.stdout, ran.stdout + ran.stderr


def test_package_builds_once_and_leaves_one_archive_per_commit(tmp_path):
    def module(root: Path, mid: str) -> dict:
        d = root / "fx" / mid
        d.mkdir(parents=True)
        jar = "build/libs/app-boot.jar"
        (d / "gradlew.bat").write_text(f"@mkdir build{chr(92)}libs 2>nul\r\n@echo jar> {jar.replace('/', chr(92))}\r\n", encoding="utf-8")
        (d / "gradlew").write_text(f"#!/bin/sh\nmkdir -p build/libs && echo jar > {jar}\n", encoding="utf-8")
        os.chmod(d / "gradlew", 0o755)
        return {"type": "java-boot", "role": "api", "path": f"fx/{mid}", "secretsModule": mid}

    root = _host(tmp_path, {"api": module})
    git = ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "c"], check=True)
    ran = _cli(root, "package", "api")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    archives = list((root / ".stack-kit" / "artifacts").glob("api-*.tgz"))
    assert len(archives) == 1 and archives[0].with_suffix(".tgz.sha256").is_file()
    assert [r["kind"] for r in _records(root) if r["module"] == "api"] == ["package"]


PENDING_TARGETS = {"schema": 1, "defaults": {"dev": "linux", "prod": "linux"}, "targets": {
    "iis": {"runtime": "iis", "pending": "Windows/IIS delivery is not built"},
    "linux": {"runtime": "docker-compose", "pending": "the platform's host is not known yet"}}}


def test_a_host_whose_every_target_is_pending_builds_tests_and_runs_but_never_deploys(tmp_path):
    # A local step never resolves a deploy target (ADR-001 amendment 9): a pending one refuses the
    # deploy, naming why, and nothing else. (It once failed `build` through a toolkit reading
    # DEPLOY_SERVER at load.)
    def dotnet_module(root: Path, mid: str) -> dict:
        d = root / "fx" / mid
        d.mkdir(parents=True)
        major = _dotnet_major()
        if major is not None:
            (d / "Lib.csproj").write_text(CLASSLIB.format(v=major), encoding="utf-8")
            (d / "Lib.cs").write_text("namespace Lib; public static class A { public const int V = 1; }\n", encoding="utf-8")
        return {"type": "dotnet-aspnet", "role": "api", "path": f"fx/{mid}", "secretsModule": mid,
                "dotnet": {"configuration": "Debug", "test": ""}}

    modules = {"web": lambda r, m: _spa(r, m, OK)}
    if _dotnet_major() is not None:
        modules["api"] = dotnet_module
    root = _host(tmp_path, modules)
    (root / "ops" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / "ops" / "deploy" / "targets.json").write_text(json.dumps(PENDING_TARGETS), encoding="utf-8")
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["deploy"] = {"targets": "ops/deploy/targets.json"}
    mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for step in ("build", "test"):
        ran = _cli(root, step)
        assert ran.returncode == 0, ran.stdout + ran.stderr
        assert f"{step} OK ({len(modules)} module(s))" in ran.stdout and "pending" not in ran.stdout + ran.stderr
    ran = _cli(root, "mod", "web", "run")
    assert ran.returncode == 0 and "started" in ran.stdout, ran.stdout + ran.stderr

    # Every remote verb opens its target first; a pending one is refused, naming the reason.
    for argv in (["deploy", "web", "--plan"], ["targets", "--verify"], ["release", "list"], ["ops", "status"]):
        ran = _cli(root, *argv)
        assert ran.returncode == 2 and "pending: the platform's host is not known yet" in ran.stdout + ran.stderr, (argv, ran.stdout + ran.stderr)
