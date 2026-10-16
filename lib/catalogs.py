"""The kit's catalogs -- roles, environments, lifecycle steps, deploy-target runtimes -- declared once
in config/catalogs/ and extended by a host in its manifest (`catalogs.<kind>`), so adding `staging` or
`typecheck` touches no code (ADR-001 amendment 12).

An entry is `{id, ...attributes}`. A host entry with a kit id overrides that entry's attributes; a new
id is inserted after the id it names (`after`), else appended. A leaf module: it reads JSON, and the
current project's manifest only when a caller gives none (as the driver registry does).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOGS = Path(__file__).resolve().parent.parent / "config" / "catalogs"
KINDS = ("roles", "environments", "lifecycle", "targetRuntimes", "tiers")


class CatalogError(ValueError):
    """A catalog or its host overlay that cannot be read honestly, named."""


@lru_cache(maxsize=None)
def _kit(kind: str) -> tuple[dict[str, Any], ...]:
    if kind not in KINDS:
        raise CatalogError(f"no catalog '{kind}' (catalogs: {', '.join(KINDS)})")
    path = CATALOGS / f"{kind}.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
    except (OSError, ValueError, KeyError) as e:
        raise CatalogError(f"config/catalogs/{kind}.json: unreadable ({e})") from e
    return tuple(entries)


def _current_manifest() -> dict[str, Any]:
    """The project's manifest the process is running for, or {} -- for a caller that has none."""
    try:
        from lib.project_context import find_project_root, load_manifest

        return load_manifest(find_project_root())
    except (FileNotFoundError, ValueError, OSError):
        return {}


def entries(kind: str, manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The kit's entries with the host's over them, in declared order."""
    manifest = _current_manifest() if manifest is None else manifest
    out = [dict(e) for e in _kit(kind)]
    overlay = ((manifest.get("catalogs") or {}).get(kind) or []) if isinstance(manifest, dict) else []
    for own in overlay:
        if not isinstance(own, dict) or not own.get("id"):
            raise CatalogError(f"catalogs.{kind}: an entry without an id ({own!r})")
        at = next((i for i, e in enumerate(out) if e["id"] == own["id"]), None)
        if at is not None:
            out[at] = {**out[at], **own}
            continue
        after = own.get("after")
        pos = next((i + 1 for i, e in enumerate(out) if e["id"] == after), None) if after else None
        if after and pos is None:
            raise CatalogError(f"catalogs.{kind}: '{own['id']}' is to follow '{after}', which is not an entry")
        out.insert(pos if pos is not None else len(out), dict(own))
    return out


def ids(kind: str, manifest: dict[str, Any] | None = None) -> list[str]:
    return [e["id"] for e in entries(kind, manifest)]


def entry(kind: str, ident: str, manifest: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return next((e for e in entries(kind, manifest) if e["id"] == ident), None)


def ordered(kind: str, attribute: str, manifest: dict[str, Any] | None = None) -> list[str]:
    """The ids that carry `attribute`, sorted by it (e.g. roles by deployOrder)."""
    have = [e for e in entries(kind, manifest) if e.get(attribute) is not None]
    return [e["id"] for e in sorted(have, key=lambda e: e[attribute])]


def flagged(kind: str, attribute: str, manifest: dict[str, Any] | None = None) -> list[str]:
    return [e["id"] for e in entries(kind, manifest) if e.get(attribute)]


def default_environment(use: str, manifest: dict[str, Any] | None = None) -> str:
    """The environment a host run (`run`) or a deploy (`deploy`) means when none is asked for."""
    found = flagged("environments", f"{use}Default", manifest)
    if not found:
        raise CatalogError(f"catalogs.environments: no entry carries {use}Default")
    return found[0]


def require(kind: str, ident: str, manifest: dict[str, Any] | None = None, *, what: str = "") -> str:
    """`ident`, if the catalog declares it; else refused, naming the declared ones."""
    known = ids(kind, manifest)
    if ident not in known:
        raise CatalogError(f"{what or kind}: '{ident}' is not declared (catalog {kind}: {', '.join(known)}); "
                           f"a host adds one in `catalogs.{kind}`")
    return ident
