"""A generated compose file never builds from a Dockerfile that is not there (found adopting a foreign
project: a root module's compose named `src/Dockerfile.dev`, which did not exist, and validate passed).
Each `build:` block's context and dockerfile are resolved from the compose file's own directory; a
context inside the local release trees (`stage` writes them) is not judged here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_BUILD = re.compile(r"^(\s*)build:\s*(.*?)\s*$")
_FIELD = re.compile(r"^(\s+)([A-Za-z_][\w-]*):\s*(.*?)\s*$")
_FLOW = re.compile(r"\b(context|dockerfile)\s*:\s*([^,}\s]+)")


def _scalar(text: str) -> str:
    """A YAML scalar's first token, unquoted, without a trailing comment."""
    return (text.split(" #")[0].strip().split() or [""])[0].strip("'\"")


def compose_files(root: Path, manifest: dict[str, Any]) -> list[Path]:
    from lib import extend

    rel = (manifest.get("compose") or {}).get("catalog") or "ops/compose/catalog.json"
    catalog = root / rel
    if not catalog.is_file():
        return []
    try:
        doc = json.loads(catalog.read_text(encoding="utf-8-sig"))
    except ValueError:
        return []
    return [root / extend.placed(key, manifest) for key in (doc.get("targets") or {}) if (root / extend.placed(key, manifest)).is_file()]


def references(text: str) -> list[tuple[str, str]]:
    """(context, dockerfile) of each `build:` -- its block in any field order (args, target, ... beside
    them), a flow mapping, or the short form `build: ./dir` (the context, with its Dockerfile)."""
    out, lines = [], text.splitlines()
    for i, line in enumerate(lines):
        m = _BUILD.match(line)
        if not m:
            continue
        inline = m.group(2)
        if inline and not inline.startswith("#"):
            if inline.startswith("{"):
                flow = dict((k, v.strip("'\"")) for k, v in _FLOW.findall(inline))
                out.append((flow.get("context", "."), flow.get("dockerfile", "Dockerfile")))
            else:
                out.append((_scalar(inline) or ".", "Dockerfile"))
            continue
        found: dict[str, str] = {}
        child = None
        for nxt in lines[i + 1:]:
            if not nxt.strip() or nxt.lstrip().startswith("#"):
                continue
            depth = len(nxt) - len(nxt.lstrip())
            if depth <= len(m.group(1)):
                break
            child = depth if child is None else child
            f = _FIELD.match(nxt)
            if f and depth == child and f.group(2) in ("context", "dockerfile"):
                found[f.group(2)] = _scalar(f.group(3))
        out.append((found.get("context", "."), found.get("dockerfile", "Dockerfile")))
    return out


def problems(root: Path, manifest: dict[str, Any]) -> list[str]:
    from lib import package

    staged = package.local_tree(root, "_").parent.resolve()
    errors = []
    for path in compose_files(root, manifest):
        for context, dockerfile in references(path.read_text(encoding="utf-8", errors="replace")):
            if "${" in context or "${" in dockerfile:
                continue
            base = (path.parent / context).resolve()
            if staged in base.parents or base == staged:
                continue
            if not (base / dockerfile).is_file():
                errors.append(f"{path.relative_to(root).as_posix()}: builds from {context}/{dockerfile}, which is not there "
                              f"-- add the recipe, or re-run compose-gen (it writes no service without one)")
    return errors
