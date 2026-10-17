"""A module's build tool is its driver's, read from its files, and validate names what a build would
lack before it fails (found adopting a foreign project: a Gradle API with no wrapper passed validate and
threw at build; a Maven API was not known at all)."""
from __future__ import annotations

from pathlib import Path

from lib import build_tools
from lib.modules import driver_registry


def _host(tmp_path: Path, files: dict) -> Path:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path


def _manifest(**cfg) -> dict:
    return {"modules": {"api": {"type": "java-boot", "role": "api", "path": ".", **cfg}}}


def test_a_maven_module_without_its_wrapper_is_named_and_one_with_it_is_not(tmp_path):
    root = _host(tmp_path, {"pom.xml": "<project/>"})
    errors, warnings = build_tools.problems(root, _manifest(), driver_registry())
    assert errors == [] and len(warnings) == 1 and "a maven build with no wrapper" in warnings[0] and "`mvn`" in warnings[0]
    (root / "mvnw").write_text("#!/bin/sh", encoding="utf-8")
    assert build_tools.problems(root, _manifest(), driver_registry()) == ([], [])


def test_a_gradle_module_without_its_wrapper_is_named(tmp_path):
    root = _host(tmp_path, {"build.gradle": "plugins { id 'org.springframework.boot' }"})
    errors, warnings = build_tools.problems(root, _manifest(), driver_registry())
    assert errors == [] and "a gradle build with no wrapper" in warnings[0]


def test_a_module_with_no_build_file_is_refused(tmp_path):
    root = _host(tmp_path, {"README.md": "x"})
    errors, _ = build_tools.problems(root, _manifest(), driver_registry())
    assert len(errors) == 1 and "no build file its driver knows" in errors[0]


def test_the_release_artifact_follows_the_build_tool():
    from lib import templating

    entry = driver_registry()["java-boot"]
    pattern = entry["container"]["artifact"]
    assert templating.render(pattern, {"java": {"artifact": "target/*.jar"}}) == "target/*.jar"
    assert templating.render(pattern, {}) == "build/libs/*.jar"
    assert "target/" in entry["outputs"] and "target/*.jar" in entry["package"]["artifacts"]


def _resolve(module_dir: Path) -> "subprocess.CompletedProcess":
    import shutil
    import subprocess

    import pytest

    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("no pwsh on this machine")
    script = Path(__file__).resolve().parents[2] / "drivers" / "java-boot" / "ps1" / "_build-tool.ps1"
    body = ("function Get-ModuleField { param($m, $f) return $null }; "
            f". '{script.as_posix()}'; "
            "$env:PATH = ''; "
            f"try {{ $t = Resolve-JvmBuildTool -ModuleId api -ModPath '{module_dir.as_posix()}' -Root '{module_dir.as_posix()}'; "
            "'KIND=' + $t.Kind + ' EXE=' + (Split-Path $t.Exe -Leaf); "
            "'ARGS=' + ((Get-JvmStepArgs -ModuleId api -Kind $t.Kind -Step build) -join ' ') } "
            "catch { 'REFUSED: ' + $_.Exception.Message }")
    return subprocess.run([pwsh, "-NoProfile", "-Command", body], capture_output=True, text=True)


def test_the_build_script_takes_the_maven_wrapper_and_refuses_by_name_without_one(tmp_path):
    root = _host(tmp_path, {"pom.xml": "<project/>"})
    refused = _resolve(root).stdout
    assert "REFUSED" in refused and "a maven build, with no mvnw" in refused and "no mvn on the PATH" in refused
    import os
    wrapper = "mvnw.cmd" if os.name == "nt" else "mvnw"
    (root / wrapper).write_text("@echo off", encoding="utf-8")
    took = _resolve(root).stdout
    assert f"KIND=maven EXE={wrapper}" in took and "ARGS=-q package -DskipTests" in took, took
