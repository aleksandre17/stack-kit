"""Scaffold must not embed this repo's brands or container names."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import PKG

BANNED = (
    "stack-kit-chat",
    "stack_kit_chat",
    "stack-kit-chat-bot",
    "GEMINI_API",
    "STACK_KIT_SEARCH",
    "ELEVENLABS",
)

SCAFFOLD = PKG / "scaffold"


@pytest.mark.parametrize("path", list(SCAFFOLD.rglob("*")), ids=lambda p: str(p.relative_to(SCAFFOLD)))
def test_scaffold_files_contain_no_branded_names(path: Path) -> None:
    if not path.is_file():
        pytest.skip("directory")
    if path.suffix not in {".md", ".json", ".example", ".ps1", ".sh", ".env", ""} and path.name not in {
        "ops.config.ps1",
        "ops.config.sh",
    }:
        pytest.skip("binary or unrelated")
    text = path.read_text(encoding="utf-8", errors="ignore")
    for token in BANNED:
        assert token.lower() not in text.lower(), f"{path}: contains banned token {token!r}"


def test_catalog_uses_placeholder_service_keys() -> None:
    cat = json.loads((SCAFFOLD / "ops" / "compose" / "catalog.full.json").read_text(encoding="utf-8"))
    blob = json.dumps(cat["templates"])
    assert "{api_service}" in blob
    assert "{app_service}" in blob
    assert "stack-kit-chat" not in blob.lower()
