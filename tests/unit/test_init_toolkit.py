"""stack-kit init toolkit — smoke tests."""
from __future__ import annotations

from pathlib import Path


def test_init_scripts_exist(pkg_root: Path) -> None:
    assert (pkg_root / "toolkit" / "init" / "Invoke-ProjectInit.ps1").is_file()
    assert (pkg_root / "toolkit" / "init" / "init.sh").is_file()
    assert (pkg_root / "toolkit" / "init" / "README.md").is_file()


def test_catalog_templates_in_scaffold(pkg_root: Path) -> None:
    compose = pkg_root / "scaffold" / "ops" / "compose"
    assert (compose / "catalog.minimal.json").is_file()
    assert (compose / "catalog.full.json").is_file()
    full = (compose / "catalog.full.json").read_text(encoding="utf-8")
    assert "ops/compose/stack/docker-compose.yml" in full
    assert "apps/backend/docker-compose.dev.yml" in full
    assert "app_stack_dev" in full or "api_dev" in full


def test_cli_documents_init(pkg_root: Path) -> None:
    cli = (pkg_root / "cli" / "stack-kit.ps1").read_text(encoding="utf-8")
    assert "init" in cli
    assert "Invoke-ProjectInit.ps1" in cli
