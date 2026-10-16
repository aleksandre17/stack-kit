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

#: The kit's environments when a caller passes none (the catalog's, config/catalogs/environments.json,
#: is what the resolver passes); a folder's files are read in this order, a later file's value winning, as compose does with repeated --env-file.
DEFAULT_ENVIRONMENTS = ("dev", "prod")

#: A run on this machine (`run`, `hybrid boot`) reads ONE environment's configuration (12-factor III):
#: the folder's shared, non-secret `.env`, then that environment's file over it. A development run
#: never reads a production value; production's file is read only when it is asked for (`--env prod`).
#: (ADR-001 amendment 8; until then a host run filled from `.env.prod`.)
SHARED = ".env"


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


def run_files(secrets_root: Path, folder: str, environment: str = "dev",
              environments: tuple[str, ...] | list[str] = DEFAULT_ENVIRONMENTS) -> list[Path]:
    """The env files a run of one environment reads, in the order they are applied."""
    if environment not in environments:
        raise ValueError(f"a run's environment is one of {', '.join(environments)}, not {environment!r}")
    files = [secrets_root / folder / SHARED, secrets_root / folder / f".env.{environment}"]
    return [f for f in files if f.is_file()]


def dev_run_loses(secrets_root: Path, folder: str) -> list[str]:
    """The keys a development run filled from `.env.prod` before amendment 8 and no longer gets:
    set in `.env.prod`, in neither `.env` nor `.env.dev`. Names only -- a value is never read out."""
    prod = parse(secrets_root / folder / ".env.prod")
    dev = merged(run_files(secrets_root, folder, "dev"))
    return sorted(k for k in prod if k not in dev)


def folder_files(secrets_root: Path, folder: str, profile: str = "all",
                 environments: tuple[str, ...] | list[str] = DEFAULT_ENVIRONMENTS) -> list[Path]:
    """The env files of one secrets folder that exist: the shared `.env`, then one per environment in
    catalog order -- or the shared one and one environment's. (Before 2.0.0 a shared deploy.env and a
    folder's .env.deploy were read too; `validate` now refuses them, naming `migrate`.)"""
    d = secrets_root / folder
    wanted = list(environments) if profile == "all" else [profile]
    files = [d / SHARED, *(d / f".env.{p}" for p in wanted)]
    return [f for f in files if f.is_file()]


#: The legacy homes `validate` refuses and `migrate` carries (ADR-001 amendment 13).
LEGACY_FILES = ("deploy.env", ".env.deploy")
