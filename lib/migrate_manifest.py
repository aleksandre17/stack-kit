#!/usr/bin/env python3
"""Migrate the project manifest toward v2 conventions (roles, credentials hints)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from lib.identity import MANIFEST_FILENAME, find_manifest
from lib.modules import driver_accepts_global_credentials, driver_default_role
from lib.project_context import ProjectContext, find_project_root, load_manifest


def _infer_role(cfg: dict[str, Any]) -> str:
    """A module's role: declared on the module, else the role its DRIVER declares."""
    role = (cfg.get("role") or "").lower()
    if role:
        return role
    return driver_default_role(str(cfg.get("type", ""))) or "other"


def migrate_manifest(manifest: dict[str, Any], *, apply: bool = False) -> list[str]:
    changes: list[str] = []
    ver = manifest.get("version", 1)
    if ver < 2:
        changes.append(f"version: {ver} -> 2")
        if apply:
            manifest["version"] = 2

    mods = manifest.setdefault("modules", {})
    if not isinstance(mods, dict):
        return ["modules: invalid — manual fix required"]

    for mid, cfg in list(mods.items()):
        if not isinstance(cfg, dict):
            continue
        if not cfg.get("role"):
            role = _infer_role(cfg)
            changes.append(f"modules.{mid}.role: (add) -> {role}")
            if apply:
                cfg["role"] = role
        if not cfg.get("secretsModule"):
            changes.append(f"modules.{mid}.secretsModule: (add) -> {mid}")
            if apply:
                cfg["secretsModule"] = mid

    feats = manifest.get("features") or {}
    if feats.get("gcpCredentials") and not any(
        isinstance(c, dict) and c.get("credentials")
        for c in mods.values()
        if isinstance(c, dict)
    ):
        gcp = (manifest.get("adapters") or {}).get("gcp") or {}
        fn = gcp.get("credentialsFile", "google-credentials.json") if isinstance(gcp, dict) else "google-credentials.json"
        for mid, cfg in mods.items():
            if not isinstance(cfg, dict) or not driver_accepts_global_credentials(
                str(cfg.get("type") or "")
            ):
                continue
            if cfg.get("role") not in ("api", "worker"):
                continue
            changes.append(
                f"modules.{mid}.credentials: (optional) add explicit GCP profile for '{fn}'"
            )
            break

    return changes


def main() -> int:
    apply = "--apply" in sys.argv
    try:
        root = find_project_root()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    mf = find_manifest(root) or (root / MANIFEST_FILENAME)
    manifest = load_manifest(root)
    # The kit's former names first: a host on them is carried to the current ones (ADR-001).
    from lib.migrate_identity import TwoHomes, host_words, migrate_identity

    try:
        changes, moved_to = migrate_identity(root, manifest, apply=apply)
    except TwoHomes as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if moved_to is not None and apply:
        mf = moved_to
    changes += migrate_manifest(manifest, apply=apply)
    words = host_words(root, skip={mf, root / MANIFEST_FILENAME})
    for line in words:
        print(f"  restate (yours to edit): {line}")
    if not changes:
        print("[migrate] manifest already v2-ready")
        return 0
    for line in changes:
        print(f"  {line}")
    if apply:
        mf.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"[migrate] wrote {mf}")
    else:
        print("[migrate] dry-run — pass --apply to write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
