#!/usr/bin/env python3
"""Sync ops.modules from manifest modules + catalog features."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "compose"))
from build import find_project_root, global_fmt, load_catalog  # noqa: E402
from manifest_compose import ops_modules_lines  # noqa: E402

HEADER = "# GENERATED — do not edit. Run: stack-kit compose-gen\n"
SHARED = "|shared|library||yes\n"


def _shared_module_line(root: Path, manifest: dict) -> str | None:
    """Emit shared Gradle submodule row only when the consumer still has apps/backend/shared."""
    modules = manifest.get("modules") or {}
    # The module that may carry a shared build module: the first whose driver declares ops modules.
    from manifest_compose import _ops_modules_kind

    jvm = next((m for m in modules.values() if isinstance(m, dict) and _ops_modules_kind(str(m.get("type") or ""))), {})
    rel = jvm.get("path") or "apps/backend"
    if (root / rel / "shared" / "build.gradle.kts").is_file():
        return SHARED.rstrip()
    return None


def main() -> int:
    root = find_project_root()
    from lib.project_context import load_manifest

    manifest = load_manifest(root)
    out_rel = manifest.get("compose", {}).get("syncModules", "apps/backend/ops.modules")
    out = root / out_rel

    from lib.project_context import ProjectContext

    ctx = ProjectContext(root=root, manifest=manifest)
    fmt = global_fmt(root)
    _, _, catalog_features = load_catalog(root)
    from lib.compose_identity import effective_compose_features

    features = effective_compose_features(manifest, catalog_features)
    lines = [HEADER.rstrip(), "# Format: compose_service|gradle_module|type|dockerfile|enabled"]
    lines.extend(ops_modules_lines(ctx, fmt, features))
    shared_line = _shared_module_line(root, manifest)
    if shared_line:
        lines.append(shared_line)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"  wrote {out.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
