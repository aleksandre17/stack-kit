"""Manifest-driven compose-gen — N modules (retrieval, ingestion, …)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.project_context import ProjectContext

COMPOSE_PKG = Path(__file__).resolve().parents[1] / "compose"
from compose.manifest_compose import (  # noqa: E402
    build_manifest_stack_services,
    load_compose_catalog,
    ops_modules_lines,
    stack_compose_module_ids,
)
from lib.compose_identity import resolve_module_service_name  # noqa: E402


def _fixture_manifest() -> dict:
    return {
        "version": 2,
        "package": "kits/stack-kit",
        "secrets": "ops/config",
        "stack": {
            "composeModules": ["backend", "retrieval", "ingestion", "frontend"],
        },
        "features": {"gcpCredentials": True, "worker": True},
        "modules": {
            "backend": {
                "role": "api",
                "type": "java-boot",
                "path": "apps/backend",
                "secretsModule": "backend",
                "target": "backend",
                "credentials": [{"file": "google-credentials.json", "mount": "/app/google-credentials.json"}],
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
    }


@pytest.fixture()
def mini_project(tmp_path: Path) -> ProjectContext:
    root = tmp_path / "proj"
    (root / "kits" / "stack-kit").mkdir(parents=True)
    (root / "stack-kit.json").write_text(json.dumps(_fixture_manifest()), encoding="utf-8")
    for mid, sub in [
        ("backend", "apps/backend"),
        ("retrieval", "apps/retrieval-service"),
        ("ingestion", "apps/ingestion-service"),
        ("frontend", "apps/frontend"),
    ]:
        d = root / sub
        d.mkdir(parents=True)
        if "retrieval" in sub or "ingestion" in sub:
            (d / "Dockerfile.dev").write_text("FROM scratch\n", encoding="utf-8")
        (root / "ops" / "config" / _fixture_manifest()["modules"][mid]["secretsModule"]).mkdir(
            parents=True
        )
        sm = _fixture_manifest()["modules"][mid]["secretsModule"]
        env_lines = {
            "backend": "API_PORT=8090\nWORKER_PORT=8091\n",
            "retrieval": "RETRIEVAL_PORT=8092\n",
            "ingestion": "INGESTION_PORT=8093\n",
            "frontend": "DEPLOY_HOST_PORT=5177\n",
        }
        (root / "ops" / "config" / sm / ".env.dev").write_text(
            env_lines.get(sm, ""), encoding="utf-8"
        )
    stack_dir = root / "ops" / "compose" / "stack"
    stack_dir.mkdir(parents=True)
    return ProjectContext(root=root, manifest=_fixture_manifest())


def test_stack_includes_retrieval_and_ingestion(mini_project: ProjectContext) -> None:
    fmt = {
        "compose_slug": "demo",
        "api_service": "demo-api",
        "app_service": "demo-app",
        "worker_service": "demo-worker",
        "worker_image": "demo-worker",
        "network_key": "demo-net",
        "network_name": "demo-net",
    }
    body = build_manifest_stack_services(
        ctx=mini_project,
        profile="dev",
        compose_dir=mini_project.root / "ops" / "compose" / "stack",
        fmt_global=fmt,
        fmt_extra={"health_interval": "15s", "health_retries": "5", "health_start": "60s"},
        features={"worker": True},
        compose_cat=load_compose_catalog(),
    )
    slug = mini_project.root.name
    assert f"{slug}-retrieval:" in body
    assert f"{slug}-ingestion:" in body
    assert "RETRIEVAL_PORT" in body
    assert "${RETRIEVAL_PORT:-8092}" in body
    assert "${INGESTION_PORT:-8093}" in body
    assert "apps/retrieval-service" in body or "retrieval-service" in body


def test_compose_modules_filter(tmp_path: Path) -> None:
    manifest = _fixture_manifest()
    manifest["stack"]["composeModules"] = ["retrieval"]
    assert stack_compose_module_ids(manifest) == ["retrieval"]


def test_ops_modules_lists_all_java_services(mini_project: ProjectContext) -> None:
    slug = mini_project.root.name
    fmt = {
        "compose_slug": slug,
        "api_service": f"{slug}-api",
        "app_service": f"{slug}-app",
        "worker_service": f"{slug}-worker",
    }
    lines = ops_modules_lines(mini_project, fmt, {"worker": True})
    joined = "\n".join(lines)
    assert f"{slug}-api" in joined
    assert f"{slug}-retrieval" in joined
    assert f"{slug}-ingestion" in joined
    assert f"{slug}-worker" in joined  # embedded backend worker (features.worker)


def test_resolve_service_names() -> None:
    manifest = _fixture_manifest()
    deploy: dict[str, str] = {}
    assert resolve_module_service_name("backend", manifest, deploy, "x") == "x-api"
    assert resolve_module_service_name("retrieval", manifest, deploy, "x") == "x-retrieval"
    assert resolve_module_service_name("ingestion", manifest, deploy, "x") == "x-ingestion"
