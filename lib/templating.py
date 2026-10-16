"""The one template grammar of the kit's declarations (ADR-001 amendment 13).

    {path}                 a value from the module (dotted path into its manifest entry), or a value
                           the caller supplies (`artifact`, `entry`, ...)
    {path|default}         ... else the default
    {path|default|:f}      ... then the filter f: `stem` (a file name without its extension),
                           `majorminor` (8.0.x -> 8.0, 17 -> 17)

A `${...}` is never a placeholder (a shell's or a recipe's own variable).

Drivers use it for what only they know (a base image from the module's toolchain version, an
entry point from its project file) so the kit names no tool and no version.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

_FIELD = re.compile(r"(?<!\$)\{([A-Za-z0-9_.@]+)((?:\|[^}|]*)*)\}")


def _filter(value: str, name: str) -> str:
    if name == "stem":
        return PurePosixPath(value.replace("\\", "/")).stem
    if name == "majorminor":
        parts = [p for p in value.split(".") if p and p.lower() != "x"]
        return ".".join(parts[:2])
    raise ValueError(f"template filter ':{name}' is not one of :stem, :majorminor")


def _lookup(cur: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def render(template: str, module: dict[str, Any], extra: dict[str, str] | None = None) -> str:
    """Fill every placeholder; an unknown one with no default is refused by name."""
    extra = extra or {}

    def one(m: re.Match[str]) -> str:
        path, rest = m.group(1), m.group(2)
        parts = rest.split("|")[1:] if rest else []
        filters = [p[1:] for p in parts if p.startswith(":")]
        defaults = [p for p in parts if not p.startswith(":")]
        value = extra.get(path)
        if value in (None, ""):
            found = _lookup(module, path)
            value = str(found) if found not in (None, "") else None
        if value in (None, ""):
            if not defaults:
                raise ValueError(f"template: {{{path}}} has no value and no default")
            value = defaults[0]
        for f in filters:
            value = _filter(str(value), f)
        return str(value)

    return _FIELD.sub(one, template)


def render_tree(cur: Any, module: dict[str, Any], extra: dict[str, str] | None = None) -> Any:
    """Every string inside a declaration, rendered."""
    if isinstance(cur, str):
        return render(cur, module, extra)
    if isinstance(cur, list):
        return [render_tree(n, module, extra) for n in cur]
    if isinstance(cur, dict):
        return {k: render_tree(v, module, extra) for k, v in cur.items()}
    return cur
