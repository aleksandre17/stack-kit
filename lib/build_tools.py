"""A module's build tool, read from its driver's declaration (`buildTools`) and the module's files:
the first tool whose build file is in the module is its tool. validate names a module with no build
file its driver knows, and one whose wrapper is not committed -- the build would then depend on
whatever tool this machine happens to have (found adopting a foreign project whose build tool the
driver did not know). No tool is named here: every name is the driver's declaration.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def tool_of(root: Path, cfg: dict[str, Any], entry: dict[str, Any]) -> "dict[str, Any] | None":
    """The first tool whose build file is in the module, else the first whose wrapper is there."""
    base = root / str(cfg.get("path") or ".")
    tools = entry.get("buildTools") or []
    return (next((t for t in tools if any((base / w).is_file() for w in t["when"])), None)
            or next((t for t in tools if any((base / w).is_file() for w in t["wrapper"])), None))


def problems(root: Path, manifest: dict[str, Any], registry: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for mid, cfg in (manifest.get("modules") or {}).items():
        if not isinstance(cfg, dict):
            continue
        entry = registry.get(str(cfg.get("type") or "")) or {}
        if not entry.get("buildTools"):
            continue
        tool = tool_of(root, cfg, entry)
        base = root / str(cfg.get("path") or ".")
        if tool is None:
            known = ", ".join(w for t in entry["buildTools"] for w in t["when"])
            warnings.append(f"modules.{mid}: no build file its driver knows ({known}) in {cfg.get('path') or '.'} yet -- "
                            f"its build will be refused until one is there")
            continue
        if not any((base / w).is_file() for w in tool["wrapper"]):
            warnings.append(f"modules.{mid}: a {tool['id']} build with no wrapper ({' / '.join(tool['wrapper'])}) -- it "
                            f"builds with `{tool['fallback']}` from the PATH, whatever version this machine has; "
                            f"{tool.get('how', 'commit the wrapper')}")
    return errors, warnings
