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
COLUMNS = "compose_service|module|type|dockerfile|enabled"


def _owner(manifest: dict) -> tuple[dict, dict]:
    """The first module whose driver declares ops modules, and that declaration."""
    from manifest_compose import ops_modules_declaration

    for m in (manifest.get("modules") or {}).values():
        decl = ops_modules_declaration(str(m.get("type") or "")) if isinstance(m, dict) else {}
        if decl:
            return m, decl
    return {}, {}


def _shared_module_line(root: Path, manifest: dict) -> str | None:
    """The shared build module's row, as the driver declares it (`opsModules.shared`: a `marker` file
    under the module and the `row`), only when the module still carries the marker."""
    module, decl = _owner(manifest)
    shared = decl.get("shared") if isinstance(decl.get("shared"), dict) else {}
    if shared.get("marker") and module.get("path") and (root / module["path"] / shared["marker"]).is_file():
        return str(shared.get("row") or "").rstrip() or None
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
    lines = [HEADER.rstrip(), "# Format: " + str(_owner(manifest)[1].get("columns") or COLUMNS)]
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
