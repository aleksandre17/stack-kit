"""Manifest-driven project context — no hardcoded consumer paths."""
from __future__ import annotations

import json

import pytest

from lib.project_context import ProjectContext


def test_discover_paths_from_manifest(repo_root: Path, manifest: dict) -> None:
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    assert ctx.secrets_root == repo_root / "ops" / "config"
    assert ctx.module_path("api") == repo_root / "apps" / "api"
    assert ctx.secrets_module_dir("web") == repo_root / "ops" / "config" / "web"
    assert ctx.stack_compose_dir == repo_root / "ops" / "compose" / "stack"


def test_gcp_optional_by_feature(repo_root: Path, manifest: dict) -> None:
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    assert ctx.feature_enabled("gcpCredentials") is True
    assert ctx.gcp_credentials_filename() == "google-credentials.json"
    # `worker` declares no credentials list -> the global GCP fallback applies.
    backend_creds = ctx.module_credentials_list("worker")
    assert backend_creds and backend_creds[0]["file"] == "google-credentials.json"

    off = {**manifest, "features": {"gcpCredentials": False}}
    ctx2 = ProjectContext(root=repo_root, manifest=off)
    assert ctx2.gcp_credentials_filename() is None


def test_compose_service_names_from_manifest(repo_root: Path, manifest: dict) -> None:
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    names = ctx.compose_service_names()
    assert names["modules"]["api"].endswith("-api")
    assert names["modules"]["search"].endswith("-search")
    assert names["modules"]["worker"].endswith("-worker")
    assert names["worker"] == names["modules"]["worker"]
    # No consumer brand may leak: every service name derives from the compose slug.
    assert all(v.startswith(names["compose_slug"]) for v in names["modules"].values())


def test_list_secrets_module_folders(repo_root: Path, manifest: dict) -> None:
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    folders = ctx.list_secrets_module_folders()
    assert "api" in folders
    assert "web" in folders


def test_default_remote_deploy_base_uses_secrets_folder(tmp_path: Path) -> None:
    mf = tmp_path / "geostat.ops.json"
    mf.write_text(
        '{"secrets":"ops/config","modules":{"web":{"secretsModule":"web"}}}',
        encoding="utf-8",
    )
    ctx = ProjectContext(root=tmp_path, manifest=json.loads(mf.read_text(encoding="utf-8")))
    base = ctx.default_remote_deploy_base("web", server_base="/home/u", project_slug="my-app")
    assert base == "/home/u/my-app/web"
