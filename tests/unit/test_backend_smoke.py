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


def test_devtools_in_root_gradle(manifest: dict, repo_root: Path) -> None:
    _mid, _folder = _api_module(manifest)
    rel = manifest["modules"][_mid]["path"]
    gpath = repo_root.joinpath(*rel.split("/")) / "build.gradle.kts"
    if not gpath.is_file():
        gpath = repo_root.joinpath(*rel.split("/")) / "build.gradle"
    g = gpath.read_text(encoding="utf-8")
    assert "spring-boot-devtools" in g


def test_backend_layout_simulation_doc(repo_root: Path) -> None:
    p = repo_root / "docs" / "BACKEND-LAYOUT-SIMULATION-FULL.md"
    if not p.is_file():
        return
    text = p.read_text(encoding="utf-8")
    assert "runtime/" in text
    assert "workspace/" in text
