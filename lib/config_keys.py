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
    found: list[tuple[str, str, str]] = []
    for rel in _tracked(root):
        if _kind(rel) is None or rel in skip:
            continue
        found += file_exposures(root, rel, secrets)
    return found


def file_exposures(root: Path, rel: str, secrets: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """(file, where, key) for every SECRET given a real value in one structured file (env, JSON, YAML)."""
    kind = _kind(rel)
    by_env = {n: r["key"] for r in secrets for n in env_names(r)}
    try:
        text = (root / rel).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    found: list[tuple[str, str, str]] = []
    if kind == "env":
        for n, line in enumerate(text.splitlines(), 1):
            m = _ENV_LINE.match(line)
            if m and m.group(1) in by_env and _is_value(m.group(2)):
                found.append((rel, f"line {n}", by_env[m.group(1)]))
    elif kind == "json":
        try:
            data = json.loads(text)
        except ValueError:
            return []
        for r in secrets:
            if _is_value(_json_at(data, _path(r["key"]))):
                found.append((rel, ":".join(_path(r["key"])), r["key"]))
    elif kind == "yaml":
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
    folders = {str(m.get("secretsModule") or name) for name, m in (manifest.get("modules") or {}).items()
               if isinstance(m, dict)}
    for r in rows:
        if r.get("sensitivity") == "SECRET" and not r.get("rotation"):
            verdict.failures.append(f"{rel}: {r['key']} is SECRET and declares no rotation")
        if r.get("sensitivity") == "SECRET" and r.get("default") not in (None, ""):
            verdict.failures.append(f"{rel}: {r['key']} is SECRET and declares a default -- a committed secret")
        per_env = r.get("environments") if isinstance(r.get("environments"), dict) else {}
        if r.get("sensitivity") == "SECRET" and any(v != "none" for v in per_env.values()):
            verdict.failures.append(f"{rel}: {r['key']} is SECRET and declares a per-environment value -- a committed "
                                    f"secret (only `none`, for a data source)")
        if any(v == "none" for v in per_env.values()) and not r.get("dataSource"):
            verdict.failures.append(f"{rel}: {r['key']} declares `none` for an environment but is no `dataSource`")
        scoped = (r.get("policy") or {}).get("modules") if isinstance(r.get("policy"), dict) else None
        if r.get("sensitivity") == "SECRET" and not scoped and len(folders) > 1:
            # Least privilege: a secret reaches the modules that declare they need it, never every module
            # by default -- a signing key the UI container can read is a key one more process can leak.
            verdict.failures.append(f"{rel}: {r['key']} is SECRET and names no module (policy.modules) -- with "
                                    f"{len(folders)} secrets folders ({', '.join(sorted(folders))}) it would reach "
                                    f"every one; name the modules that read it")
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


def runtime_config_problems(root: Path, manifest: dict[str, Any]) -> list[str]:
    """A module's runtime config (`modules.<id>.runtimeConfig`) is a file the application reads, and
    never a secret (ADR-001 amendment 9): its `from` must be there, and it may not carry a catalogued
    SECRET -- a structured file (JSON, YAML, env) is held by the exposure gate like every tracked
    file; any other (env.js, nginx.conf) may not even name one, nor hold key material."""
    out: list[str] = []
    rel = ((manifest.get("config") or {}).get("keys") or "")
    secrets: list[dict[str, Any]] = []
    if rel and (root / rel).is_file():
        try:
            catalogue = json.loads((root / rel).read_text(encoding="utf-8-sig"))
            secrets = [r for r in catalogue.get("keys") or [] if isinstance(r, dict) and r.get("sensitivity") == "SECRET"]
        except ValueError:
            pass
    for mid, cfg in (manifest.get("modules") or {}).items():
        for i, item in enumerate((cfg or {}).get("runtimeConfig") or [] if isinstance(cfg, dict) else []):
            where = f"modules.{mid}.runtimeConfig[{i}]"
            src = root / str(item.get("from") or "")
            if not src.is_file():
                out.append(f"{where}.from: {item.get('from')} is not there")
                continue
            text = src.read_text(encoding="utf-8", errors="replace")
            if "PRIVATE KEY" in text:
                out.append(f"{where}: {item['from']} holds private key material -- a runtime file never carries a secret")
            src_rel = src.relative_to(root).as_posix()
            if _kind(src_rel) is None:
                for row in secrets:
                    names = {row["key"], row["key"].split(":")[-1], *env_names(row)}
                    hit = sorted(n for n in names if n and n in text)
                    if hit:
                        out.append(f"{where}: {item['from']} names SECRET {row['key']} ({', '.join(hit)}) -- "
                                   f"a secret reaches the app through its env file or the store")
            else:
                out += [f"{where}: {item['from']} carries SECRET {key} at {at} -- it reaches the app through its "
                        f"env file or the store" for _rel, at, key in file_exposures(root, src_rel, secrets)]
    return out
