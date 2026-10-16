"""Carry a host from the kit's former names to its current ones (ADR-001 decision 1).

Part of `stack-kit migrate`, and held to the same contract: a dry run by default, `--apply` to write.
What the kit owns it moves -- the manifest's file name and the manifest fields the kit renamed. What
the host wrote it never touches: every line of the host's own files that still spells a former name
is PRINTED with its replacement, because rewriting a host's words is a decision only its owner makes.
Both manifest names present is two homes, and is refused whole.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from lib.identity import (
    ENV_PREFIX,
    KIT_NAME,
    LEGACY_ENV_PREFIX,
    LEGACY_MANIFEST_FIELDS,
    LEGACY_MANIFEST_FILENAMES,
    MANIFEST_FILENAME,
)
from lib import identity

#: Directories a host's own words are never looked for in.
_NOT_HOST_WORDS = {".git", "node_modules", "bin", "obj", "dist", "build", "__pycache__", ".venv"}


class TwoHomes(RuntimeError):
    pass


def rename_fields(manifest: dict[str, Any], *, apply: bool) -> list[str]:
    """Every renamed manifest field still under its former name, moved (when applying)."""
    changes = []
    for old, new in LEGACY_MANIFEST_FIELDS.items():
        *oparent, oleaf = old.split(".")
        cur = identity._dig(manifest, ".".join(oparent)) if oparent else manifest
        if not isinstance(cur, dict) or oleaf not in cur:
            continue
        if identity._dig(manifest, new) is not None:
            raise TwoHomes(f"{MANIFEST_FILENAME} holds both {old} and {new}; keep one")
        changes.append(f"field: {old} -> {new}")
        if apply:
            value = cur.pop(oleaf)
            *nparent, nleaf = new.split(".")
            target = manifest
            for part in nparent:
                target = target.setdefault(part, {})
            target[nleaf] = value
    return changes


def manifest_move(root: Path) -> tuple[Path, Path] | None:
    """(former manifest, current manifest) when the host still holds its manifest under a former name."""
    current = root / MANIFEST_FILENAME
    for name in LEGACY_MANIFEST_FILENAMES:
        former = root / name
        if former.is_file():
            if current.is_file():
                raise TwoHomes(f"{root} holds both {name} and {MANIFEST_FILENAME}; keep one")
            return former, current
    return None


def _host_files(root: Path) -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
        found = [root / p for p in out.decode("utf-8").split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        found = [p for p in root.rglob("*") if p.is_file()]
    return [p for p in found
            if p.is_file() and not (_NOT_HOST_WORDS & set(p.relative_to(root).parts))]


def _replacements() -> list[tuple[str, str]]:
    pairs = [(name, MANIFEST_FILENAME) for name in LEGACY_MANIFEST_FILENAMES]
    pairs += list(LEGACY_MANIFEST_FIELDS.items())
    if identity.LEGACY_DEPLOY_MARKER:
        pairs.append((identity.LEGACY_DEPLOY_MARKER, identity.DEPLOY_MARKER))
    pairs += list(zip(identity.LEGACY_VENDOR_DIRS, identity.VENDOR_DIRS))
    legacy_kit = identity._DECLARATION.get("legacyKitName") or ""
    if legacy_kit:
        pairs += [(f"cli/{legacy_kit}.{ext}", f"cli/{KIT_NAME}.{ext}") for ext in ("ps1", "sh")]
    if LEGACY_ENV_PREFIX:
        pairs.append((f"{LEGACY_ENV_PREFIX}_", f"{ENV_PREFIX}_"))
    return pairs


def host_words(root: Path, skip: set[Path]) -> list[str]:
    """`path:line: former -> current` for every line of the host's own files spelling a former name."""
    pairs = _replacements()
    found = []
    for path in _host_files(root):
        if path in skip:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            hits = [f"{old} -> {new}" for old, new in pairs if old in line]
            if hits:
                found.append(f"{path.relative_to(root).as_posix()}:{n}: " + "; ".join(hits))
    return found


def migrate_identity(root: Path, manifest: dict[str, Any], *, apply: bool) -> tuple[list[str], Path | None]:
    """(what changes, the manifest path to write to). Raises TwoHomes before anything is written."""
    changes = rename_fields(manifest, apply=False)
    move = manifest_move(root)
    if move:
        changes.insert(0, f"manifest: {move[0].name} -> {move[1].name}")
    if apply:
        rename_fields(manifest, apply=True)
        if move:
            move[0].rename(move[1])
    return changes, (move[1] if move else None)
