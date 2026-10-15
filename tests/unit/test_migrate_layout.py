"""P6-migrate — preflight and migrate script smoke."""
from __future__ import annotations

from pathlib import Path

import pytest

from lib.migrate_layout_preflight import check_structured_layout, migration_targets
from lib.project_context import ProjectContext


@pytest.fixture
def ctx(repo_root: Path, pkg_root: Path) -> ProjectContext:
    import os

    os.environ["STACK_KIT_PROJECT_ROOT"] = str(repo_root)
    os.environ["STACK_KIT_KIT_ROOT"] = str(pkg_root)
    return ProjectContext.discover(repo_root)


def test_migrate_scripts_exist(pkg_root: Path) -> None:
    deploy = pkg_root / "toolkit" / "deploy"
    assert (deploy / "migrate-backend-layout.sh").is_file()
    assert (deploy / "migrate-frontend-layout.sh").is_file()
    assert (deploy / "migrate-layout.sh").is_file()


def test_preflight_structured_layout(ctx: ProjectContext) -> None:
    issues = check_structured_layout(ctx)
    assert issues == [], issues


def test_migration_targets_include_api_and_ui(ctx: ProjectContext) -> None:
    rows = migration_targets(ctx)
    modules = {r["module"] for r in rows}
    assert "api" in modules
    assert "web" in modules
    be = next(r for r in rows if r["module"] == "api")
    fe = next(r for r in rows if r["module"] == "web")
    assert be["kind"] == "runtime"
    assert "/runtime/" in be["target"]
    assert fe["kind"] == "static"
    assert "/static/" in fe["target"]


def test_legacy_rename_map(ctx: ProjectContext) -> None:
    from lib.migrate_layout_names import (
        migration_rename_map,
        migration_source_dirs,
        pairs_arg,
        pairs_arg_for_role,
    )

    mapping = migration_rename_map(ctx)
    assert mapping.get("legacy-api") == "golden-consumer-api"
    assert mapping.get("legacy-app") == "golden-consumer-app"
    pairs = pairs_arg(mapping)
    assert "legacy-api:golden-consumer-api" in pairs

    api_pairs = pairs_arg_for_role(mapping, ctx, "api")
    assert api_pairs == "legacy-api:golden-consumer-api"
    assert "legacy-app" not in api_pairs

    ui_pairs = pairs_arg_for_role(mapping, ctx, "ui")
    assert "legacy-app:golden-consumer-app" in ui_pairs
    assert "legacy-api" not in ui_pairs

    api_sources = migration_source_dirs(ctx, "api")
    assert api_sources == frozenset({"legacy-api"})
    assert "golden-consumer-api" not in api_sources
    assert "mobile" not in api_sources

    ui_sources = migration_source_dirs(ctx, "ui")
    assert "legacy-app" in ui_sources
    assert "legacy-ui" in ui_sources
    assert "golden-consumer-app" not in ui_sources
    assert "stack-kit-system-app" not in ui_sources
