"""Env files: how one is read, which ones a secrets folder has, and how several combine.

The one home of these three rules (ADR-001 decision 2) -- before it, Python alone parsed env files
three ways (`compose_identity`, `config_gen`, `stack_endpoints`) and listed a folder's files twice,
and the shells each had their own copy of all of it. A leaf module: it imports nothing of the kit,
so anything may use it.
"""
from __future__ import annotations

import re
from pathlib import Path

_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")

#: The order a folder's files are read in; a later file's value wins, as it does when the same files
#: are handed to compose with repeated --env-file.
PROFILES = ("dev", "prod", "deploy")


def parse(path: Path) -> dict[str, str]:
    """KEY=value lines; comments, blank lines and empty values are not values."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        value = m.group(2).strip().strip('"').strip("'")
        if value:
            out[m.group(1)] = value
    return out


def merged(paths: list[Path]) -> dict[str, str]:
    """Several files read in order, a later file's value winning."""
    out: dict[str, str] = {}
    for path in paths:
        out.update(parse(path))
    return out


def folder_files(secrets_root: Path, folder: str, profile: str = "all") -> list[Path]:
    """The env files of one secrets folder that exist: .env.dev, .env.prod, then the shared
    deploy.env and the folder's .env.deploy -- or only one profile's."""
    d = secrets_root / folder
    wanted = PROFILES if profile == "all" else (profile,)
    files: list[Path] = []
    for p in PROFILES:
        if p not in wanted:
            continue
        if p == "deploy":
            files += [secrets_root / "deploy.env", d / ".env.deploy"]
        else:
            files.append(d / f".env.{p}")
    return [f for f in files if f.is_file()]
