"""VS Code launch/tasks generation from manifest."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from lib.project_context import ProjectContext
from lib.vscode_gen import build_launch_json, build_tasks_json, write_vscode
from conftest import PKG


def test_launch_paths_use_manifest_modules(repo_root: Path, manifest: dict) -> None:
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    launch = build_launch_json(ctx)
    names = {c["name"]: c for c in launch["configurations"]}
    fe = next(c for c in launch["configurations"] if "npm run" in c.get("command", ""))
    assert fe["cwd"].endswith("apps/web")
    java = next(c for c in launch["configurations"] if c.get("type") == "java")
    assert java["cwd"].endswith("apps/api")
    assert java["mainClass"] == "com.example.app.AppApplication"
    assert "/frontend" not in fe["cwd"].replace("apps/frontend", "")


def test_tasks_include_validate(repo_root: Path, manifest: dict) -> None:
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    tasks = build_tasks_json(ctx)
    labels = [t["label"] for t in tasks["tasks"]]
    assert "stack-kit: validate" in labels
    # Per-module check tasks are labelled by the manifest cli alias, not by any
    # consumer vocabulary: the fixture declares w -> web, a -> api.
    assert any("w build" in lb or "a build" in lb for lb in labels)


def test_write_vscode_tmp(tmp_path: Path) -> None:
    import os
    from pathlib import Path

    manifest = {
        "version": 2,
        "package": ".",
        "secrets": "ops/config",
        "compose": {"catalog": "ops/compose/catalog.json"},
        "modules": {
            "web": {
                "role": "ui",
                "type": "node-vite",
                "path": "apps/web",
                "secretsModule": "web",
            }
        },
        "vscode": {"folder": ".vscode", "cliScript": "tools/stack-kit.ps1"},
    }
    (tmp_path / "stack-kit.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "apps" / "web").mkdir(parents=True)
    pkg = PKG
    manifest["package"] = os.path.relpath(pkg, tmp_path).replace("\\", "/")
    (tmp_path / "stack-kit.json").write_text(json.dumps(manifest), encoding="utf-8")
    ctx = ProjectContext(root=tmp_path, manifest=manifest)
    paths = write_vscode(ctx, force=True)
    assert any(p.endswith("launch.json") for p in paths)
    launch = json.loads((tmp_path / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    assert launch["configurations"][0]["cwd"].endswith("apps/web")


# ── a launch is the driver's declaration (ADR-001 amendment 16) ──────────────

def _java_host(tmp_path: Path, **module_extra) -> ProjectContext:
    mod = tmp_path / "apps" / "api"
    (mod / "src" / "main" / "java" / "org" / "demo").mkdir(parents=True, exist_ok=True)
    (mod / "src" / "main" / "java" / "org" / "demo" / "DemoApplication.java").write_text("class X {}", encoding="utf-8")
    (mod / "settings.gradle.kts").write_text('rootProject.name = "demo-api"\n', encoding="utf-8")
    module = {"type": "java-boot", "role": "api", "path": "apps/api", "secretsModule": "api", **module_extra}
    return ProjectContext(root=tmp_path, manifest={"version": 2, "package": ".", "secrets": "ops/config",
                                                   "modules": {"api": module}})


def test_a_java_launch_is_read_from_the_drivers_declared_values(tmp_path: Path) -> None:
    from lib.vscode_gen import build_launch

    assert build_launch(_java_host(tmp_path), "api") == {
        "name": "api: Spring Boot", "type": "java", "request": "launch", "mainClass": "org.demo.DemoApplication",
        "cwd": "${workspaceFolder}/apps/api", "projectName": "demo-api",
        "envFile": "${workspaceFolder}/ops/config/api/.env.dev"}
    cfg = build_launch(_java_host(tmp_path, hybrid={"springProfiles": "dev,local"},
                                  debug={"java": {"mainClass": "a.B"}, "label": "mine"}), "api")
    assert cfg["mainClass"] == "a.B" and cfg["name"] == "mine" and cfg["env"] == {"SPRING_PROFILES_ACTIVE": "dev,local"}


def test_a_required_value_with_no_source_is_an_honest_absence(tmp_path: Path) -> None:
    from lib.vscode_gen import build_launch

    ctx = _java_host(tmp_path)
    (tmp_path / "apps" / "api" / "src" / "main" / "java" / "org" / "demo" / "DemoApplication.java").unlink()
    assert build_launch(ctx, "api") is None


def test_a_declared_file_that_is_missing_never_falls_through(tmp_path: Path) -> None:
    from lib.vscode_gen import build_launch

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Only.csproj").write_text("<Project />", encoding="utf-8")
    manifest = {"version": 2, "package": ".", "secrets": "ops/config", "modules": {"api": {
        "type": "dotnet-aspnet", "role": "api", "path": "src", "secretsModule": "api",
        "dotnet": {"project": "Gone.csproj", "launchProfile": "http"}}}}
    assert build_launch(ProjectContext(root=tmp_path, manifest=manifest), "api") is None
    manifest["modules"]["api"]["dotnet"]["project"] = "Only.csproj"
    cfg = build_launch(ProjectContext(root=tmp_path, manifest=manifest), "api")
    assert cfg["projectPath"] == "${workspaceFolder}/src/Only.csproj"
    assert cfg["launchConfigurationId"] == "TargetFramework=;http"


def test_a_project_driver_declares_its_values_with_the_kit_untouched(tmp_path: Path, monkeypatch) -> None:
    """Open/Closed: a driver the kit does not ship reads a file capture and a single glob."""
    from lib import identity
    from lib.vscode_gen import build_launch_json

    registry = {"py-svc": {"label": "x", "roles": ["api"], "commands": {}, "vscode": {
        "label": "{module}: {app}",
        "values": {"app": [{"file": ["pyproject.toml"], "capture": r'name\s*=\s*"([^"]+)"'}],
                   "entry": [{"glob": "*/main.py", "single": True}]},
        "launch": {"type": "debugpy", "request": "launch", "program": "{path}/{entry}", "args": ["--app", "{app}"]}}}}
    (tmp_path / "ops" / "drivers").mkdir(parents=True)
    (tmp_path / "ops" / "drivers" / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    (tmp_path / "svc" / "pkg").mkdir(parents=True)
    (tmp_path / "svc" / "pyproject.toml").write_text('[project]\nname = "orders"\n', encoding="utf-8")
    (tmp_path / "svc" / "pkg" / "main.py").write_text("", encoding="utf-8")
    manifest = {"version": 2, "package": os.path.relpath(PKG, tmp_path).replace("\\", "/"), "secrets": "ops/config",
                "drivers": {"registry": "ops/drivers/registry.json"},
                "modules": {"svc": {"type": "py-svc", "role": "api", "path": "svc", "secretsModule": "svc"}}}
    (tmp_path / identity.MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(tmp_path))
    cfg = build_launch_json(ProjectContext.discover(tmp_path))["configurations"][0]
    assert cfg == {"type": "debugpy", "request": "launch", "program": "${workspaceFolder}/svc/pkg/main.py",
                   "args": ["--app", "orders"], "name": "svc: orders"}


def test_the_full_stack_compound_takes_one_launch_per_role_in_boot_order(repo_root: Path, manifest: dict) -> None:
    launch = build_launch_json(ProjectContext(root=repo_root, manifest=manifest))
    names = {c["name"]: c for c in launch["configurations"]}
    full = next(c for c in launch.get("compounds", []) if c["name"] == "Full stack (local)")
    roles = [next(m["role"] for mid, m in manifest["modules"].items()
                  if names[n]["cwd"].endswith(m["path"].replace("\\", "/"))) for n in full["configurations"]]
    assert roles == sorted(set(roles), key=["api", "worker", "ui"].index)
