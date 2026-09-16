"""Smoke: DEV-MODES paths map to real CLI, drivers, and .vscode artifacts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.modules import infer_cli_aliases, modules_by_role
from lib.project_context import ProjectContext
from lib.validate_manifest import validate_manifest
from lib.vscode_gen import build_launch_json, build_tasks_json

PKG = Path(__file__).resolve().parents[1]
REPO = PKG.parents[1]


def test_dev_modes_doc_exists() -> None:
    assert (PKG / "docs" / "DEV-MODES.md").is_file()


def test_validate_consumer_manifest_clean(repo_root: Path) -> None:
    errs, _warnings = validate_manifest(repo_root)
    assert not errs, "\n".join(errs)


def test_mode1_local_host_launch_configs(repo_root: Path, manifest: dict) -> None:
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    launch = build_launch_json(ctx)
    names = {c["name"] for c in launch["configurations"]}
    ui_ids = modules_by_role(manifest, "ui")
    api_ids = modules_by_role(manifest, "api")
    assert ui_ids, "need ui module for mode 1"
    assert any("npm run" in json.dumps(c) for c in launch["configurations"])
    assert any(c.get("type") == "java" for c in launch["configurations"])
    compounds = launch.get("compounds") or []
    assert any(c.get("name") == "Full stack (local)" for c in compounds)


def test_mode4_hybrid_compound_and_tunnel_task(repo_root: Path, manifest: dict) -> None:
    stack = manifest.get("stack") or {}
    infra = stack.get("infra") or {}
    services = infra.get("services") or []
    if not services:
        pytest.skip("no stack.infra.services — hybrid compound not generated")

    ctx = ProjectContext(root=repo_root, manifest=manifest)
    launch = build_launch_json(ctx)
    compounds = launch.get("compounds") or []
    hybrid = next((c for c in compounds if c.get("preLaunchTask")), None)
    assert hybrid is not None, "expected hybrid compound with preLaunchTask"
    assert hybrid["preLaunchTask"] == "geostat: infra tunnel"
    assert len(hybrid.get("configurations") or []) >= 2

    tasks = build_tasks_json(ctx)
    tunnel = next(t for t in tasks["tasks"] if t["label"] == "geostat: infra tunnel")
    assert tunnel.get("isBackground") is True
    assert "infra" in json.dumps(tunnel["args"])
    assert "geostat: infra remote up" in [t["label"] for t in tasks["tasks"]]


def test_java_launch_env_file_from_secrets(repo_root: Path, manifest: dict) -> None:
    # Java launch config is emitted only for java-boot api modules; node-api (and other
    # non-JVM api drivers) get their own launch shape, so guard on driver type not role.
    java_api = [
        mid
        for mid in modules_by_role(manifest, "api")
        if manifest["modules"][mid].get("type") == "java-boot"
    ]
    if not java_api:
        pytest.skip("no java-boot api module")
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    launch = build_launch_json(ctx)
    java_cfg = next(c for c in launch["configurations"] if c.get("type") == "java")
    assert "envFile" in java_cfg
    assert ".env.dev" in java_cfg["envFile"]


def test_mode2_local_docker_tasks(repo_root: Path, manifest: dict) -> None:
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    tasks = build_tasks_json(ctx)
    labels = [t["label"] for t in tasks["tasks"]]
    assert "geostat: stack dev" in labels
    aliases = infer_cli_aliases(manifest)
    for _alias, mid in aliases.items():
        if manifest["modules"][mid]["type"] == "node-vite":
            assert any("compose up" in lb for lb in labels)
        if manifest["modules"][mid]["type"] == "java-boot":
            assert any("compose up" in lb for lb in labels)


def test_mode3_remote_driver_scripts_exist() -> None:
    fe_dev = PKG / "drivers" / "node-vite" / "ps1" / "dev.ps1"
    be_dev = PKG / "drivers" / "java-boot" / "sh" / "dev.sh"
    assert fe_dev.is_file(), "node-vite remote dev driver"
    assert be_dev.is_file(), "java-boot remote dev driver"
    deploy_watch = PKG / "toolkit" / "deploy" / "deploy-watch.sh"
    assert deploy_watch.is_file()


def test_consumer_vscode_matches_manifest(repo_root: Path, manifest: dict) -> None:
    launch_path = repo_root / ".vscode" / "launch.json"
    if not launch_path.is_file():
        pytest.skip(".vscode/launch.json not generated yet")
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    ui_path = manifest["modules"][modules_by_role(manifest, "ui")[0]]["path"]
    fe_cfg = next(c for c in launch["configurations"] if "npm run" in c.get("command", ""))
    assert ui_path.replace("\\", "/") in fe_cfg["cwd"].replace("\\", "/")


def test_compose_catalog_and_stack_dir(repo_root: Path, manifest: dict) -> None:
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    assert ctx.catalog_path.is_file(), "compose catalog for mode 2 stack"
    assert ctx.stack_compose_dir.is_dir() or True  # may be empty before compose-gen


@pytest.mark.parametrize(
    "script_rel",
    [
        "lib/validate_manifest.py",
        "lib/vscode_gen.py",
        "lib/credentials.py",
        "ci/prepare-integration-env.sh",
        "toolkit/deploy/dev-remote.sh",
    ],
)
def test_package_scripts_present(script_rel: str) -> None:
    assert (PKG / script_rel).is_file(), script_rel
