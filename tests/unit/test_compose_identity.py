"""Compose naming -- every name from lib/naming.py: the manifest `project`, else the folder."""
from __future__ import annotations

from pathlib import Path

from lib.compose_identity import (
    build_global_fmt,
    compose_service_names,
    resolve_module_service_name,
)


def _manifest() -> dict:
    return {
        "version": 2,
        "modules": {
            "backend": {
                "role": "api",
                "type": "java-boot",
                "path": "apps/backend",
                "secretsModule": "backend",
                "target": "backend",
            },
            "retrieval": {
                "role": "api",
                "type": "java-boot",
                "path": "apps/retrieval-service",
                "secretsModule": "retrieval",
                "target": "retrieval",
            },
            "ingestion": {
                "role": "worker",
                "type": "java-boot",
                "path": "apps/ingestion-service",
                "secretsModule": "ingestion",
                "target": "ingestion",
            },
            "frontend": {
                "role": "ui",
                "type": "node-vite",
                "path": "apps/frontend",
                "secretsModule": "frontend",
                "target": "frontend",
            },
        },
        "stack": {"composeModules": ["backend", "retrieval", "ingestion", "frontend"]},
    }


def test_default_names_from_the_folder_without_a_declared_project(tmp_path: Path) -> None:
    names = compose_service_names(_manifest(), tmp_path / "my-app")
    assert names["api"] == "my-app-api"
    assert names["app"] == "my-app-app"
    assert names["worker"] == "my-app-ingestion"
    assert names["modules"]["retrieval"] == "my-app-retrieval"


def test_the_declared_project_names_everything(tmp_path: Path) -> None:
    manifest = {**_manifest(), "project": "shop"}
    assert compose_service_names(manifest, tmp_path / "my-app")["compose_slug"] == "shop"
    assert resolve_module_service_name("backend", manifest, tmp_path / "my-app") == "shop-api"
    assert resolve_module_service_name("retrieval", manifest, tmp_path / "my-app") == "shop-retrieval"


def test_build_global_fmt_matches_compose_gen_keys(tmp_path: Path) -> None:
    fmt = build_global_fmt(manifest=_manifest(), root=tmp_path / "my-app")
    assert fmt["api_service"] == "my-app-api"
    assert fmt["app_service"] == "my-app-app"
    assert fmt["network_name"] == "my-app-net"


def test_project_context_compose_names(repo_root: Path) -> None:
    from lib.project_context import ProjectContext

    ctx = ProjectContext.discover(repo_root)
    names = ctx.compose_service_names()
    slug = "golden-consumer"  # the fixture's declared `project`
    assert "modules" in names
    assert names.get("compose_slug") == slug
    assert names.get("api") == f"{slug}-api"
    assert names.get("app") == f"{slug}-app"
    assert names["modules"].get("search", "").endswith("-search")
    assert names["modules"]["search"] == f"{slug}-search"
