"""Manifest-driven compose-gen — N modules (retrieval, ingestion, …)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import PKG
from lib.project_context import ProjectContext

COMPOSE_PKG = PKG / "compose"
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
    assert resolve_module_service_name("backend", manifest, Path("x")) == "x-api"
    assert resolve_module_service_name("retrieval", manifest, Path("x")) == "x-retrieval"
    assert resolve_module_service_name("ingestion", manifest, Path("x")) == "x-ingestion"


def test_the_ops_modules_rows_are_the_drivers_declaration(tmp_path: Path) -> None:
    """The registry rows' kind, header, embedded worker and shared build module are declared by the
    driver (`compose.opsModules`); a driver that declares none gets none (ADR-001 amendment 16)."""
    from compose.manifest_compose import ops_modules_declaration
    from compose.sync_ops_modules import _owner, _shared_module_line

    decl = ops_modules_declaration("java-boot")
    assert decl["kind"] and decl["embeddedWorker"] and decl["shared"]["marker"]
    assert ops_modules_declaration("node-vite") == {}
    manifest = {"modules": {"web": {"type": "node-vite", "path": "web"}, "api": {"type": "java-boot", "path": "api"}}}
    assert _owner(manifest)[0]["path"] == "api"
    assert _shared_module_line(tmp_path, manifest) is None
    marker = tmp_path / "api" / decl["shared"]["marker"]
    marker.parent.mkdir(parents=True)
    marker.write_text("", encoding="utf-8")
    assert _shared_module_line(tmp_path, manifest) == decl["shared"]["row"]


def test_a_module_without_its_local_recipe_is_not_composed_and_says_why(tmp_path):
    # Found adopting a foreign project: a root Spring module's compose built from `src/Dockerfile.dev`,
    # which the project never had.
    from manifest_compose import missing_recipe
    from lib.project_context import ProjectContext

    manifest = {"version": 2, "modules": {"app": {"type": "java-boot", "role": "api", "path": "."},
                                          "web": {"type": "node-vite", "role": "ui", "path": "web"}}}
    ctx = ProjectContext(root=tmp_path, manifest=manifest)
    why = missing_recipe(ctx, "app", "dev")
    assert "has no Dockerfile.dev" in why and "compose.fromRelease" in why
    assert missing_recipe(ctx, "web", "dev") == "", "a module run from its release image builds from the staged tree"
    (tmp_path / "Dockerfile.dev").write_text("FROM x", encoding="utf-8")
    assert missing_recipe(ctx, "app", "dev") == ""


def test_a_modules_own_port_and_health_path_win_over_the_roles(mini_project: ProjectContext) -> None:
    # Read from the app by the draft (Spring's server.port, actuator): the compose asks what the app serves.
    manifest = _fixture_manifest()
    manifest["modules"]["retrieval"]["container"] = {"port": 8181, "healthPath": "/actuator/health"}
    ctx = ProjectContext(root=mini_project.root, manifest=manifest)
    fmt = {"compose_slug": "demo", "api_service": "demo-api", "app_service": "demo-app", "worker_service": "demo-worker",
           "worker_image": "demo-worker", "network_key": "demo-net", "network_name": "demo-net",
           "health_interval": "15s", "health_retries": "5", "health_start": "60s"}
    from compose.manifest_compose import build_single_module_compose

    body = build_single_module_compose(ctx=ctx, module_id="retrieval", profile="dev",
                                       compose_dir=mini_project.root / "apps" / "retrieval-service",
                                       fmt_global=fmt, fmt_extra={})
    assert "/actuator/health" in body and ":-8181}" in body, body


def test_a_driver_with_no_local_template_is_skipped_with_its_reason_never_a_crash(tmp_path):
    # Found by an audit: dotnet-aspnet and node-api declare no compose templates, so a module of theirs
    # with a Dockerfile.dev made compose-gen raise "no template".
    from manifest_compose import build_manifest_stack_services, missing_recipe

    manifest = {"version": 2, "modules": {"api": {"type": "dotnet-aspnet", "role": "api", "path": "api"},
                                          "edge": {"type": "node-api", "role": "api", "path": "edge"}}}
    for mid in ("api", "edge"):
        (tmp_path / mid).mkdir()
        (tmp_path / mid / "Dockerfile.dev").write_text("FROM x", encoding="utf-8")
    ctx = ProjectContext(root=tmp_path, manifest=manifest)
    for mid in ("api", "edge"):
        why = missing_recipe(ctx, mid, "dev")
        assert "declares no compose template for role api" in why and f"dev up {mid}" in why, why
    fmt = {"compose_slug": "demo", "network_key": "demo-net", "network_name": "demo-net",
           "health_interval": "15s", "health_retries": "5", "health_start": "60s"}
    body = build_manifest_stack_services(ctx=ctx, profile="dev", compose_dir=tmp_path, fmt_global=fmt,
                                         fmt_extra={}, features={}, compose_cat={"templates": {}}, stack_cat={})
    assert "Dockerfile.dev" not in body, "both are skipped, and composing the stack never raises"
