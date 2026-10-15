"""Scaffold is the single source of convention defaults."""
from __future__ import annotations

from pathlib import Path

from lib.manifest_defaults import (
    cli_aliases,
    default_field,
    flatten_defaults,
    load_scaffold_manifest,
    resolve_cli_alias,
)
from lib.project_context import ProjectContext
from conftest import PKG

SCAFFOLD = PKG / "scaffold" / "stack-kit.json"


def test_scaffold_manifest_loads() -> None:
    m = load_scaffold_manifest()
    assert m.get("version") == 2
    assert m.get("secrets") == "ops/config"


def test_flatten_defaults_match_scaffold() -> None:
    d = flatten_defaults()
    assert d["package"] == "kits/stack-kit"
    assert d["secrets"] == "ops/config"
    assert "catalog.json" in d["compose.catalog"]


def test_cli_aliases_from_scaffold() -> None:
    a = cli_aliases()
    assert a.get("fe") == "frontend"
    assert a.get("be") == "backend"
    assert resolve_cli_alias("fe") == "frontend"


def test_project_context_uses_scaffold_defaults(tmp_path: Path) -> None:
    mf = tmp_path / "stack-kit.json"
    mf.write_text('{"version":2,"secrets":"custom/config","modules":{}}', encoding="utf-8")
    ctx = ProjectContext(root=tmp_path, manifest={"version": 2, "secrets": "custom/config", "modules": {}})
    assert ctx.field("package") == "kits/stack-kit"
    assert ctx.field("secrets") == "custom/config"
