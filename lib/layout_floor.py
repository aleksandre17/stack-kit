"""The host's product and ops tree as a DECLARED layout, held as a floor (ADR-001 decision 3).

A row is the agent kit's layout row (`path`, `kind`, and the records-map fields `holds`, `writer`,
`read_when`, `lifecycle`; `pending` for a place not built yet) -- one handwriting across both kits,
over disjoint places: the agent kit draws `.agents/` and its own; this kit draws what its manifest
knows of. Two sources of rows:

* **Derived** -- every place the manifest DECLARES explicitly is a place that must exist: the
  vendored kit, each module's directory, the secrets root, a declared compose catalog, declared CI
  scripts, the infra compose directory once infra services are declared, a declared nginx
  template, the config-key catalogue, the editor launcher. A default the host never wrote is not a
  row: a host that uses no compose is not failed for lacking a catalog.
* **Declared** -- `layout.entries` in the manifest: whatever else the host says its tree holds.

`layout.closed` names directories the declaration is EXHAUSTIVE at: every tracked child of one must
be covered by a row (or lie under one), or it is undeclared -- the agent kit's `closed`, the same
word for the same rule.

The gate fails on a declared place that is missing and is not `pending`, and on an undeclared child
of a closed directory. A pending place is printed, never hidden.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib.manifest_defaults import declared_ci_scripts, read_nested


@dataclass
class Floor:
    failures: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)


def _row(path: str, kind: str, holds: str, declared_by: str) -> dict[str, Any]:
    return {"path": path.rstrip("/") + ("/" if kind == "dir" else ""), "kind": kind, "holds": holds,
            "declared_by": declared_by}


def derived_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """The places the manifest itself declares, each naming the field that declares it."""
    rows: list[dict[str, Any]] = []

    def declared(dotted: str) -> str:
        return read_nested(manifest, dotted, "")

    if declared("package"):
        rows.append(_row(declared("package"), "dir", "kit", "package"))
    if declared("secrets"):
        rows.append(_row(declared("secrets"), "dir", "configuration", "secrets"))
    for mid, cfg in (manifest.get("modules") or {}).items():
        if isinstance(cfg, dict) and cfg.get("path"):
            rows.append(_row(str(cfg["path"]), "dir", "module-source", f"modules.{mid}.path"))
    if declared("compose.catalog"):
        rows.append(_row(declared("compose.catalog"), "file", "compose", "compose.catalog"))
    for dotted, rel in declared_ci_scripts(manifest):
        rows.append(_row(rel, "file", "ci", dotted))
    infra = (manifest.get("stack") or {}).get("infra") or {}
    if isinstance(infra, dict) and infra.get("services"):
        rel = declared("stack.infraComposeDir") or "ops/compose/infra"
        rows.append(_row(rel, "dir", "infra", "stack.infra.services"))
    if declared("drivers.registry"):
        rows.append(_row(declared("drivers.registry"), "file", "drivers", "drivers.registry"))
    if declared("adapters.nginx.template"):
        rows.append(_row(declared("adapters.nginx.template"), "file", "module-source",
                         "adapters.nginx.template"))
    if declared("config.keys"):
        rows.append(_row(declared("config.keys"), "file", "configuration", "config.keys"))
    if declared("vscode.cliScript"):
        rows.append(_row(declared("vscode.cliScript"), "file", "launcher", "vscode.cliScript"))
    return rows


def _tracked(root: Path) -> list[str] | None:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return [p for p in out.decode("utf-8").split("\0") if p]


def _children(root: Path, directory: str, tracked: list[str] | None) -> set[str]:
    """The immediate children of `directory` that hold something: tracked ones in a repository,
    what is on disk otherwise. A directory child is spelled with its trailing '/'."""
    prefix = "" if directory in (".", "./") else directory.rstrip("/") + "/"
    if tracked is not None:
        found = set()
        for rel in tracked:
            if rel.startswith(prefix):
                rest = rel[len(prefix):]
                head, sep, _ = rest.partition("/")
                found.add(prefix + head + ("/" if sep else ""))
        return found
    base = root / prefix if prefix else root
    if not base.is_dir():
        return set()
    return {prefix + p.name + ("/" if p.is_dir() else "") for p in base.iterdir() if p.name != ".git"}


def _covered(child: str, rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        path = row["path"]
        if child == path or (path.endswith("/") and child.startswith(path)):
            return True
        if child.endswith("/") and path.startswith(child):
            return True  # a declared place lies below this child
    return False


def evaluate(root: Path, manifest: dict[str, Any]) -> Floor:
    layout = manifest.get("layout") or {}
    rows = derived_rows(manifest) + [dict(r) for r in (layout.get("entries") or []) if isinstance(r, dict)]
    floor = Floor(rows=rows)
    for row in rows:
        path = row["path"]
        target = root / path.rstrip("/")
        present = target.is_dir() if row.get("kind") == "dir" else target.is_file()
        if present:
            continue
        origin = f" (declared by {row['declared_by']})" if row.get("declared_by") else ""
        if row.get("pending"):
            floor.pending.append(f"{path}: pending {row['pending']}{origin}")
        else:
            floor.failures.append(f"{path}: declared {row.get('kind', 'dir')} is missing{origin}")
    closed = [c for c in (layout.get("closed") or []) if isinstance(c, str)]
    if closed:
        tracked = _tracked(root)
        for directory in closed:
            for child in sorted(_children(root, directory, tracked)):
                if not _covered(child, rows):
                    floor.failures.append(f"{child}: in {directory!r}, which the layout declares closed, "
                                          "and no row covers it -- declare it under layout.entries or move it")
    return floor
