"""Compose naming — manifest modules, optional deploy.env legacy overrides."""
from __future__ import annotations

from pathlib import Path

from lib.compose_identity import (
    build_global_fmt,
    compose_service_names,
    load_deploy_env,
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


def test_default_names_from_manifest_without_compose_env(tmp_path: Path) -> None:
    manifest = _manifest()
    deploy: dict[str, str] = {}
    names = compose_service_names(manifest, deploy, "my-app")
    assert names["api"] == "my-app-api"
    assert names["app"] == "my-app-app"
    assert names["worker"] == "my-app-ingestion"
    assert names["modules"]["retrieval"] == "my-app-retrieval"


def test_deploy_project_does_not_change_compose_slug() -> None:
    manifest = _manifest()
    deploy = {"DEPLOY_PROJECT": "geostat"}
    names = compose_service_names(manifest, deploy, "my-app")
    assert names["compose_slug"] == "my-app"
    assert names["api"] == "my-app-api"


def test_legacy_override_primary_api_only(tmp_path: Path) -> None:
    manifest = _manifest()
    deploy = {"COMPOSE_API_SERVICE": "legacy-api"}
    assert resolve_module_service_name("backend", manifest, deploy, "my-app") == "legacy-api"
    assert resolve_module_service_name("retrieval", manifest, deploy, "my-app") == "my-app-retrieval"


def test_build_global_fmt_matches_compose_gen_keys(tmp_path: Path) -> None:
    manifest = _manifest()
    secrets = tmp_path / "ops" / "config"
    secrets.mkdir(parents=True)
    (secrets / "deploy.env").write_text("DOCKER_NETWORK=custom-net\n", encoding="utf-8")
    deploy = load_deploy_env(secrets)
    fmt = build_global_fmt(manifest=manifest, deploy=deploy, repo_name="my-app")
    assert fmt["api_service"] == "my-app-api"
    assert fmt["app_service"] == "my-app-app"
    assert fmt["network_name"] == "custom-net"


def test_project_context_compose_names(repo_root: Path) -> None:
    from lib.project_context import ProjectContext

    ctx = ProjectContext.discover(repo_root)
    names = ctx.compose_service_names()
    slug = repo_root.name
    assert "modules" in names
    assert names.get("compose_slug") == slug
    assert names.get("api") == f"{slug}-api"
    assert names.get("app") == f"{slug}-app"
    assert names["modules"].get("search", "").endswith("-search")
    assert names["modules"]["search"] == f"{slug}-search"
