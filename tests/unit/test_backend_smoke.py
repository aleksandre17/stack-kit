"""API-role module smoke — paths from manifest (no hardcoded module folder names)."""
from __future__ import annotations

import re
from pathlib import Path

from lib.modules import modules_by_role


def _api_module(manifest: dict) -> tuple[str, str]:
    ids = modules_by_role(manifest, "api")
    assert ids, "manifest needs modules.*.role=api"
    mid = ids[0]
    folder = manifest["modules"][mid]["secretsModule"]
    return mid, folder


def test_api_env_deploy_exists_and_structured(secrets_root: Path, manifest: dict) -> None:
    _mid, folder = _api_module(manifest)
    p = secrets_root / folder / ".env.deploy"
    assert p.is_file(), f"{p} missing — copy from .env.deploy.example"
    text = p.read_text(encoding="utf-8")
    assert "DEPLOY_LAYOUT=structured" in text
    assert "DEPLOY_PATH=" in text


def test_api_env_deploy_matches_deploy_env(secrets_root: Path, manifest: dict) -> None:
    _mid, folder = _api_module(manifest)
    deploy = secrets_root / "deploy.env"
    be = secrets_root / folder / ".env.deploy"
    if not deploy.is_file():
        return
    proj = None
    for line in deploy.read_text(encoding="utf-8").splitlines():
        if line.startswith("DEPLOY_PROJECT="):
            proj = line.split("=", 1)[1].strip()
            break
    if proj:
        assert proj in be.read_text(encoding="utf-8")


def test_migrate_script_exists(pkg_root: Path) -> None:
    deploy = pkg_root / "toolkit" / "deploy"
    assert (deploy / "migrate-backend-layout.sh").is_file()
    assert (deploy / "migrate-frontend-layout.sh").is_file()
    assert (deploy / "migrate-layout.sh").is_file()


def test_devtools_in_root_gradle(manifest: dict, repo_root: Path) -> None:
    _mid, _folder = _api_module(manifest)
    rel = manifest["modules"][_mid]["path"]
    gpath = repo_root.joinpath(*rel.split("/")) / "build.gradle.kts"
    if not gpath.is_file():
        gpath = repo_root.joinpath(*rel.split("/")) / "build.gradle"
    g = gpath.read_text(encoding="utf-8")
    assert "spring-boot-devtools" in g


def test_simulate_backend_layout_script(pkg_root: Path) -> None:
    assert (pkg_root / "toolkit" / "layout" / "simulate-backend-layout.ps1").is_file()


def test_backend_layout_simulation_doc(repo_root: Path) -> None:
    p = repo_root / "docs" / "BACKEND-LAYOUT-SIMULATION-FULL.md"
    if not p.is_file():
        return
    text = p.read_text(encoding="utf-8")
    assert "runtime/" in text
    assert "workspace/" in text
