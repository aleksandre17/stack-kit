"""Build output is never tracked (ADR-001 amendment 16.12).

What a toolchain writes has one home: its driver's `outputs` -- gitignore-style patterns relative to
the module path (`bin/` a directory of that name at any depth, the remote-dev sync's own matcher). A
host adds what its own build writes with `modules.<id>.outputs` -- an extension, never a removal (a
`!` pattern is refused by the schema, and nothing here subtracts). validate lists what git tracks
under each module (a file under a nested module is that module's alone) and refuses every tracked
file an output matches: one error per output found, with its file count and the fix. Outside a
repository nothing is tracked, so nothing is refused.

A project of a toolchain the host uses that lies outside every module -- a test project beside the
app -- writes the same outputs: there an output is the toolchain's only beside one of its project
files (the files its driver's `detect` names), so a `bin/` of scripts is never one. What an editor
writes for one machine or one user is never tracked either (`config/editor-state.json`, from the
github/gitignore templates).
"""
from __future__ import annotations

import fnmatch
import json
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


EDITOR_STATE = Path(__file__).resolve().parents[1] / "config" / "editor-state.json"


def _markers(entry: dict[str, Any]) -> list[str]:
    """The project files a driver's detection names at a project's top -- beside them, its outputs are written."""
    out: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            name = item.get("file")
            if isinstance(name, str) and "/" not in name:
                out.append(name)
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(entry.get("detect") or {})
    return list(dict.fromkeys(out))


def outside_modules(files: list[str], bases: dict[str, str], types: dict[str, str],
                    registry: dict[str, Any]) -> list[str]:
    """Every output a project outside every module tracks: a directory a used toolchain writes, beside one
    of that toolchain's project files."""
    toolchains = [(typ, [o for o in (registry.get(typ) or {}).get("outputs") or [] if o.endswith("/")],
                   _markers(registry.get(typ) or {})) for typ in sorted(set(types.values()))]
    names: dict[str, set[str]] = {}
    for rel in files:
        parent, _, name = rel.rpartition("/")
        names.setdefault(parent, set()).add(name)
    hits: dict[tuple[str, str], int] = {}
    for rel in files:
        if _owner(rel, bases) is not None:
            continue
        parts = rel.split("/")
        for k in range(len(parts) - 1):
            parent = "/".join(parts[:k])
            found = next((typ for typ, outputs, markers in toolchains if parts[k] + "/" in outputs
                          and any(fnmatch.fnmatch(n, m) for m in markers for n in names.get(parent, ()))), None)
            if found:
                where = "/".join(parts[:k + 1])
                hits[(where, found)] = hits.get((where, found), 0) + 1
                break
    return [f"{where}/: {count} tracked {'file' if count == 1 else 'files'} in the build output of a {typ} project "
            f"outside every module -- untrack: git rm -r --cached {where}; ignore: add '{where}/' to .gitignore"
            for (where, typ), count in sorted(hits.items())]


def editor_state(files: list[str]) -> list[str]:
    """Every tracked file an editor writes for one machine or one user, grouped by its editor directory."""
    declared = json.loads(EDITOR_STATE.read_text(encoding="utf-8"))
    hits: dict[str, list[str]] = {}
    for rel in files:
        parts = rel.split("/")
        where = ""
        for k in range(len(parts) - 2, -1, -1):  # the innermost editor directory holding it
            inside = declared["under"].get(parts[k])
            if inside is not None:
                inner = "/".join(parts[k + 1:])
                if any(fnmatch.fnmatch(inner, p) for p in inside) \
                        and not any(fnmatch.fnmatch(inner, p) for p in (declared.get("shared") or {}).get(parts[k], [])):
                    where = "/".join(parts[:k + 1])
                break
        if not where and any(fnmatch.fnmatch(parts[-1], p) for p in declared["names"]):
            where = rel
        if where:
            hits.setdefault(where, []).append(rel)
    return [f"{where}: {len(held)} tracked editor-state {'file' if len(held) == 1 else 'files'} (one machine's or "
            f"one user's, never shared: {', '.join(sorted(h.rsplit('/', 1)[-1] for h in held)[:4])}"
            f"{', ...' if len(held) > 4 else ''}) -- untrack: git rm --cached <each>; ignore them in .gitignore"
            for where, held in sorted(hits.items())]


def problems(root: Path, manifest: dict[str, Any], registry: dict[str, Any],
             files: list[str] | None = None) -> list[str]:
    """Every output a module -- or a project outside them -- tracks, and every editor-state file, each
    named with its file count and the fix."""
    files = tracked(root) if files is None else files
    if not files:
        return []
    modules = {str(m): c for m, c in (manifest.get("modules") or {}).items() if isinstance(c, dict) and c.get("path")}
    if not modules:
        return editor_state(files)
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
    types = {mid: str(cfg.get("type") or "") for mid, cfg in modules.items()}
    return out + outside_modules(files, bases, types, registry) + editor_state(files)
