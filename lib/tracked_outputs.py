"""Build output is never tracked (ADR-001 amendment 16.12).

What a toolchain writes has one home: its driver's `outputs` -- gitignore-style patterns relative to
the module path (`bin/` a directory of that name at any depth, the remote-dev sync's own matcher). A
host adds what its own build writes with `modules.<id>.outputs` -- an extension, never a removal (a
`!` pattern is refused by the schema, and nothing here subtracts). validate lists what git tracks
under each module (a file under a nested module is that module's alone) and refuses every tracked
file an output matches: one error per output found, with its file count and the fix. Outside a
repository nothing is tracked, so nothing is refused.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def tracked(root: Path) -> list[str] | None:
    """What git tracks under `root`, posix and relative to it -- None outside a repository."""
    try:
        ran = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True)
    except OSError:
        return None
    if ran.returncode != 0:
        return None
    return [p for p in ran.stdout.decode("utf-8", errors="replace").split("\0") if p]


def module_outputs(cfg: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    """A module's outputs: its driver's, then its own -- deduplicated, never fewer than the driver's."""
    entry = registry.get(str(cfg.get("type") or "")) or {}
    declared = [*(entry.get("outputs") or []), *(cfg.get("outputs") or [])]
    return list(dict.fromkeys(str(p) for p in declared if str(p).strip() and not str(p).startswith("!")))


def _base(path: Any) -> str:
    rel = str(path or "").replace("\\", "/").strip("/")
    return "" if rel in ("", ".") else rel


def _owner(rel: str, bases: dict[str, str]) -> str | None:
    """The module a tracked file belongs to: the deepest module path that holds it."""
    best, depth = None, -1
    for mid, base in bases.items():
        if (not base or rel.startswith(base + "/")) and len(base) > depth:
            best, depth = mid, len(base)
    return best


def _found(rel: str, pattern: str) -> tuple[str, bool] | None:
    """(the output a module-relative file is inside -- the matching directory, else the file -- is it
    a directory), or None when the pattern does not match the file."""
    from lib.delivery.sync import excluded

    if not excluded(rel, [pattern]):
        return None
    parts = rel.split("/")
    for k in range(1, len(parts)):
        if excluded("/".join(parts[:k]) + "/_", [pattern]):
            return "/".join(parts[:k]), True
    return rel, False


def problems(root: Path, manifest: dict[str, Any], registry: dict[str, Any],
             files: list[str] | None = None) -> list[str]:
    """Every output a module tracks, named with its file count and the fix."""
    modules = {str(m): c for m, c in (manifest.get("modules") or {}).items() if isinstance(c, dict) and c.get("path")}
    if not modules:
        return []
    files = tracked(root) if files is None else files
    if not files:
        return []
    bases = {mid: _base(cfg["path"]) for mid, cfg in modules.items()}
    patterns = {mid: module_outputs(cfg, registry) for mid, cfg in modules.items()}
    hits: dict[tuple[str, str, str, bool], int] = {}
    for rel in files:
        mid = _owner(rel, bases)
        if mid is None or not patterns[mid]:
            continue
        base = bases[mid]
        inner = rel[len(base) + 1:] if base else rel
        for pattern in patterns[mid]:
            found = _found(inner, pattern)
            if found:
                hits[(mid, pattern, found[0], found[1])] = hits.get((mid, pattern, found[0], found[1]), 0) + 1
                break
    out = []
    for (mid, pattern, where, is_dir), count in sorted(hits.items(), key=lambda kv: (kv[0][0], kv[0][2])):
        path = f"{bases[mid]}/{where}" if bases[mid] else where
        typ = str(modules[mid].get("type") or "")
        owner = f"driver {typ}" if pattern in ((registry.get(typ) or {}).get("outputs") or []) else f"modules.{mid}.outputs"
        line = pattern if "/" in pattern.rstrip("/") or pattern.startswith("/") else f"**/{pattern}"
        ignore = f"{bases[mid]}/{line.lstrip('/')}" if bases[mid] else line
        noun = "file" if count == 1 else "files"
        out.append(f"modules.{mid}: {count} tracked {noun} in build output {path}{'/' if is_dir else ''} "
                   f"('{pattern}', {owner}) -- untrack: git rm -r --cached {path}; ignore: add '{ignore}' to .gitignore")
    return out
