"""Migrations are structure-only (ADR-001 decision 4).

What the prior system proved: schema migrations that only shape the database, and demo or
production data loaded through the same pipeline production uses (the `ingest` stage) -- so a
migration run from nothing yields an empty, correctly shaped store, and data has one way in.

Which files are a driver's migrations, and what a data statement looks like in its technology, is
the DRIVER's declaration (`drivers/registry.json` `migrations`: `globs` relative to the module,
`exclude` file-name patterns, `data` line patterns); this module names no technology. A module may
point at its migration directories elsewhere (`modules.<id>.migrations.paths`, project-relative --
for a solution whose migrations sit beside the module that runs them), and may declare a file that
legitimately carries reference data, with its reason (`modules.<id>.migrations.allowData:
[{path, reason}]`).
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from lib.modules import driver_capability


def _bases(root: Path, cfg: dict[str, Any], declared: dict[str, Any]) -> list[tuple[Path, list[str]]]:
    """(directory, globs) to search: the module's own tree with the driver's globs, or each
    declared migrations directory with the globs' file-name part."""
    globs = [str(g) for g in declared.get("globs") or []]
    paths = (cfg.get("migrations") or {}).get("paths")
    if paths:
        names = sorted({g.split("/")[-1] for g in globs})
        return [(root / str(p), names) for p in paths]
    if cfg.get("path"):
        return [(root / str(cfg["path"]), globs)]
    return []


def check(root: Path, manifest: dict[str, Any]) -> list[str]:
    """`path:line: why` for the first data statement of each migration no allowData covers."""
    findings: list[str] = []
    for mid, cfg in (manifest.get("modules") or {}).items():
        if not isinstance(cfg, dict):
            continue
        declared = driver_capability(str(cfg.get("type") or ""), "migrations")
        if not isinstance(declared, dict):
            continue
        allowed = {str(a.get("path", "")).replace("\\", "/")
                   for a in (cfg.get("migrations") or {}).get("allowData") or []
                   if isinstance(a, dict) and a.get("reason")}
        exclude = [str(e).split("/")[-1] for e in declared.get("exclude") or []]
        patterns = [re.compile(p) for p in declared.get("data") or []]
        files: set[Path] = set()
        for base, globs in _bases(root, cfg, declared):
            if base.is_dir():
                for g in globs:
                    files.update(p for p in base.glob(g) if p.is_file())
        for f in sorted(files):
            rel = f.relative_to(root).as_posix()
            if rel in allowed or any(fnmatch.fnmatch(f.name, e) for e in exclude):
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for n, line in enumerate(lines, 1):
                if any(p.search(line) for p in patterns):
                    findings.append(f"{rel}:{n}: a migration carries data (module '{mid}') -- load it through "
                                    f"the ingest stage, or declare the file under "
                                    f"modules.{mid}.migrations.allowData with its reason")
                    break
    return findings


# ── the applied-checksum ledger: an edited or removed migration is refused ─────

LEDGER = "ops/stack-kit/migrations.lock.json"


def migration_files(root: Path, manifest: dict[str, Any]) -> list[Path]:
    """Every migration file the drivers' declarations find, data or not."""
    found: set[Path] = set()
    for _mid, cfg in (manifest.get("modules") or {}).items():
        if not isinstance(cfg, dict):
            continue
        declared = driver_capability(str(cfg.get("type") or ""), "migrations")
        if not isinstance(declared, dict):
            continue
        exclude = [str(e).split("/")[-1] for e in declared.get("exclude") or []]
        for base, globs in _bases(root, cfg, declared):
            if base.is_dir():
                for g in globs:
                    found.update(p for p in base.glob(g) if p.is_file() and not any(fnmatch.fnmatch(p.name, e) for e in exclude))
    return sorted(found)


def _digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def ledger_problems(root: Path, manifest: dict[str, Any]) -> list[str]:
    """A recorded migration that changed or is gone (a migration once run is never edited: a new one
    corrects it). A new, unrecorded one is not a problem until `stack-kit migrations lock` records it."""
    import json

    path = root / LEDGER
    if not path.is_file():
        return []
    recorded = json.loads(path.read_text(encoding="utf-8")).get("files") or {}
    out = []
    for rel, digest in sorted(recorded.items()):
        f = root / rel
        if not f.is_file():
            out.append(f"{rel}: a recorded migration is gone -- a migration once applied is never removed")
        elif _digest(f) != digest:
            out.append(f"{rel}: a recorded migration was edited -- it is never edited once applied; add a new one")
    return out


def lock(root: Path, manifest: dict[str, Any]) -> list[str]:
    """Record every migration not yet in the ledger (the ones already recorded are never rewritten)."""
    import json

    path = root / LEDGER
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema": 1, "files": {}}
    added = []
    for f in migration_files(root, manifest):
        rel = f.relative_to(root).as_posix()
        if rel not in data["files"]:
            data["files"][rel] = _digest(f)
            added.append(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return added
