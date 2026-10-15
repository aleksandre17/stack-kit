"""Configuration carries its sensitivity (ADR-001 decision 5).

A host declares, in the catalogue its manifest names (`config.keys`), every key its code reads:
how sensitive it is, who owns it, where its value may come from, and -- for a secret -- how it is
rotated. The gate holds three things:

1. the catalogue has the declared shape (`config/config-keys.schema.json`), and every SECRET says
   how it is rotated;
2. no tracked file gives a SECRET a real value -- an env-style line, or the key's path in a JSON or
   YAML file; a placeholder (`__NAME__`), an empty value or a reference to the environment
   (`${NAME}`, `${NAME:default}`) is not a value;
3. an exposure already known is printed with the work that removes it (`knownExposures`), never
   hidden and never failed twice -- rotation comes first, because the value is already in history.

Values are never printed: a finding names the file, the line or path, and the key.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PLACEHOLDER = re.compile(r"^(__[A-Z0-9_]+__|\$\{[^}]*\}|)$")
_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_YAML_LINE = re.compile(r"^(\s*)([A-Za-z0-9_.-]+)\s*:\s*(.*?)\s*$")
_SCHEMA = Path(__file__).resolve().parents[1] / "config" / "config-keys.schema.json"


@dataclass
class Verdict:
    failures: list[str] = field(default_factory=list)
    known: list[str] = field(default_factory=list)


def env_names(row: dict[str, Any]) -> set[str]:
    """Every environment spelling of a catalogued key: declared ones, and the key's own forms."""
    key = str(row["key"])
    names = {str(n) for n in row.get("env") or []}
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        names.add(key)
    names.add(key.replace(":", "__"))
    names.add(re.sub(r"[.:-]", "_", key).upper())
    return {n for n in names if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n)}


def _path(key: str) -> list[str]:
    return [p for p in re.split(r"[:.]", key) if p]


def _clean(value: str) -> str:
    v = value.strip()
    if v[:1] in "\"'" and v[-1:] == v[:1]:
        v = v[1:-1]
    return v


def _is_value(value: Any) -> bool:
    return isinstance(value, str) and not PLACEHOLDER.match(_clean(value))


def _json_at(data: Any, parts: list[str]) -> Any:
    for p in parts:
        if not isinstance(data, dict):
            return None
        match = next((k for k in data if k.lower() == p.lower()), None)  # config keys are case-blind
        if match is None:
            return None
        data = data[match]
    return data


def _yaml_hits(text: str, parts: list[str]) -> list[int]:
    """Line numbers where the nested YAML key `parts` holds an inline scalar (block YAML only)."""
    stack: list[tuple[int, str]] = []
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _YAML_LINE.match(line)
        if not m:
            continue
        indent, name, rest = len(m.group(1)), m.group(2), m.group(3)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        here = [s[1] for s in stack] + name.split(".")
        if [p.lower() for p in here] == [p.lower() for p in parts] and rest and _is_value(rest.split(" #")[0]):
            hits.append(n)
        if not rest:
            stack.append((indent, name))
    return hits


def _tracked(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [p for p in out.decode("utf-8").split("\0") if p]


def _kind(rel: str) -> str | None:
    name = rel.rsplit("/", 1)[-1].lower()
    if name.endswith(".env") or name.startswith(".env") or name in ("deploy.env",) or ".env." in name:
        return "env"
    if name.endswith(".json"):
        return "json"
    if name.endswith((".yml", ".yaml")):
        return "yaml"
    return None


def exposures(root: Path, rows: list[dict[str, Any]], skip: set[str]) -> list[tuple[str, str, str]]:
    """(file, where, key) for every SECRET given a real value in a tracked file."""
    secrets = [r for r in rows if r.get("sensitivity") == "SECRET"]
    if not secrets:
        return []
    by_env = {n: r["key"] for r in secrets for n in env_names(r)}
    found: list[tuple[str, str, str]] = []
    for rel in _tracked(root):
        kind = _kind(rel)
        if kind is None or rel in skip:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        if kind == "env":
            for n, line in enumerate(text.splitlines(), 1):
                m = _ENV_LINE.match(line)
                if m and m.group(1) in by_env and _is_value(m.group(2)):
                    found.append((rel, f"line {n}", by_env[m.group(1)]))
        elif kind == "json":
            try:
                data = json.loads(text)
            except ValueError:
                continue
            for r in secrets:
                if _is_value(_json_at(data, _path(r["key"]))):
                    found.append((rel, ":".join(_path(r["key"])), r["key"]))
        else:
            for r in secrets:
                for n in _yaml_hits(text, _path(r["key"])):
                    found.append((rel, f"line {n}", r["key"]))
    return found


def check(root: Path, manifest: dict[str, Any]) -> Verdict:
    """The catalogue's shape, rotation for every secret, and no committed secret value."""
    verdict = Verdict()
    rel = ((manifest.get("config") or {}).get("keys") or "")
    if not rel:
        return verdict
    path = root / rel
    if not path.is_file():
        verdict.failures.append(f"{rel}: the manifest names a key catalogue that does not exist")
        return verdict
    try:
        catalogue = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        verdict.failures.append(f"{rel}: not JSON ({e})")
        return verdict
    from lib.schema_check import validate

    verdict.failures += [f"{rel}: {e}" for e in validate(catalogue, json.loads(_SCHEMA.read_text(encoding="utf-8")))]
    rows = [r for r in catalogue.get("keys") or [] if isinstance(r, dict) and r.get("key")]
    for r in rows:
        if r.get("sensitivity") == "SECRET" and not r.get("rotation"):
            verdict.failures.append(f"{rel}: {r['key']} is SECRET and declares no rotation")
        if r.get("sensitivity") == "SECRET" and r.get("default") not in (None, ""):
            verdict.failures.append(f"{rel}: {r['key']} is SECRET and declares a default -- a committed secret")
    known = {(str(k.get("key")), str(k.get("file")).replace("\\", "/")): str(k.get("tracking"))
             for k in catalogue.get("knownExposures") or [] if isinstance(k, dict)}
    for file, where, key in exposures(root, rows, skip={rel}):
        tracking = known.get((key, file))
        if tracking:
            verdict.known.append(f"{file} ({where}): SECRET {key} is committed -- known, tracked by {tracking}")
        else:
            verdict.failures.append(f"{file} ({where}): SECRET {key} has a committed value -- rotate it, then "
                                    f"move it to its allowed source; the value is not printed")
    return verdict
