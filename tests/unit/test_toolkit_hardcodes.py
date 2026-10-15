"""Toolkit/runtime must not hardcode legacy paths or brand names."""
from __future__ import annotations

import re
from pathlib import Path
from conftest import PKG


FORBIDDEN_IN_RUNTIME = (
    re.compile(r"packages/stack-kit"),
    re.compile(r"deploy/compose"),
    re.compile(r"\.\./secrets/"),
    re.compile(r"stack-kit-chat-bot", re.I),
    re.compile(r"Hybrid\s*[④4]", re.I),
    re.compile(r"\bfe\s*\|\s*be\s*\|\s*ret\s*\|\s*ing\b", re.I),
)

HARDCODED_SECRET_SUBDIR = re.compile(
    r"ops/config/(?:frontend|backend)(?!['\"]?\s*\+)",
)

HARDCODED_GCP_FILE = re.compile(r"google-credentials\.json")

SCAN_DIRS = ("toolkit", "drivers", "lib", "cli", "compose", "adapters", "scripts")
def _scan_file(path: Path) -> list[str]:
    if path.suffix not in {".py", ".sh", ".ps1"}:
        return []
    rel = path.relative_to(PKG).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    issues: list[str] = []
    for pat in FORBIDDEN_IN_RUNTIME:
        if pat.search(text) and not (
            pat.pattern == "packages/stack-kit" and "STACK_KIT_LEGACY" in text
        ):
            issues.append(f"{rel}: legacy pattern {pat.pattern}")
    if "layout/simulate-" in rel:
        return issues
    if HARDCODED_SECRET_SUBDIR.search(text.replace("\\", "/")):
        if "Get-ModuleEnvPathLabels" in text or "Get-ScaffoldManifestField" in text:
            return issues
        issues.append(f"{rel}: hardcoded ops/config/frontend|backend")
    if "toolkit/deploy/" in rel and HARDCODED_GCP_FILE.search(text):
        if "stack_kit_module_credentials" not in text and "stack_kit_gcp_" not in text:
            issues.append(f"{rel}: hardcoded google-credentials.json (use manifest credentials)")
    return issues


def test_runtime_tree_has_no_legacy_patterns() -> None:
    hits: list[str] = []
    for sub in SCAN_DIRS:
        root = PKG / sub
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                hits.extend(_scan_file(path))
    assert not hits, "legacy/hardcoded paths in package runtime:\n  " + "\n  ".join(hits)
