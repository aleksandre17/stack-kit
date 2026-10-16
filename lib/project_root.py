"""Where the project is and what its manifest says -- a leaf every module may use (it imports only
the kit's identity), so nothing has to reach "up" to the project context to find the manifest.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.identity import LEGACY_VENDOR_DIRS, MANIFEST_FILENAME, VENDOR_DIRS, env, env_name, find_manifest, has_manifest


def legacy_root_discovery_enabled() -> bool:
    """Opt-in pre-v2 root discovery (`<prefix>_LEGACY_ROOT_DISCOVERY=1`)."""
    return env("LEGACY_ROOT_DISCOVERY").strip().lower() in ("1", "true", "yes", "on")


def find_project_root(start: Path | None = None) -> Path:
    """The ONE discovery every runtime uses (ADR-001 decision 2).

    An explicit `start` is walked up from. Otherwise: the declared root (`<prefix>_PROJECT_ROOT`)
    is authoritative -- an operator's explicit answer is never overridden by a guess; then the
    working directory and its parents; then, only when asked for, pre-v2 trees. (Not the
    directories above the running kit: a kit checked out inside some other repository would then
    resolve that repository from anywhere -- a guess, made silently.)
    """
    if start is None and env("PROJECT_ROOT"):
        return Path(env("PROJECT_ROOT")).resolve()
    start = (start or Path.cwd()).resolve()
    for p in [start, *start.parents]:
        if has_manifest(p):
            return p
    if legacy_root_discovery_enabled():
        for p in [start, *start.parents]:
            if (p / "ops" / "config").is_dir() or (p / "secrets").is_dir():
                if any((p / d).is_dir() for d in (*VENDOR_DIRS, *LEGACY_VENDOR_DIRS)):
                    return p
    raise FileNotFoundError(
        f"project root not found ({MANIFEST_FILENAME} required; "
        f"set {env_name('LEGACY_ROOT_DISCOVERY')}=1 for pre-v2 trees)"
    )


def load_manifest(root: Path) -> dict[str, Any]:
    mf = find_manifest(root)
    if mf is not None:
        return json.loads(mf.read_text(encoding="utf-8"))
    return {}
