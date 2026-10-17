"""The env-value policy a release must pass, driven by the configuration catalogue (`config.keys`,
each key's `policy`) -- ADR-001 amendment 14. A value is never printed: a finding names the key, the
folder, the environment and the rule.

    policy.required      true, or the environments it is required in ("required only in prod")
    policy.modules       the secrets folders the key belongs to (required-ness applies there only)
    policy.minLength     a minimum length (a JWT signing key: 32)
    policy.format        positive-int | url | https-url (https-url: also never localhost)
    policy.forbid        {environment: [glob, ...]} values refused there (CORS `*` in prod: `[*]`, a glob's literal star)
    policy.requires      keys that must be set whenever this one is ("if X then Y")
    policy.generate      {bytes}: made on the server, once, never read back (lib/delivery/running.py)

A placeholder is never a value: empty, `CHANGE_ME`, `changeme`, `TODO`, `__NAME__`, `${...}`,
`<...>`, `xxx`.
"""
from __future__ import annotations

import fnmatch
import re
from typing import Any

PLACEHOLDER = re.compile(r"^(|change[_-]?me|todo|tbd|xxx+|__[A-Z0-9_]+__|\$\{[^}]*\}|<[^>]*>|your[_-].*)$", re.I)
PENDING = re.compile(r"<<pending:\s*([^>]*)>>")  # an answer only the host gives (lib/envgen.py writes it)
_LOCAL = re.compile(r"^https?://(localhost|127\.|0\.0\.0\.0|\[::1\])", re.I)


def generate_bytes(row: dict[str, Any]) -> int:
    """The bytes of randomness a key is generated with (0: not generated) -- one reader of both spellings."""
    policy = row.get("policy") if isinstance(row.get("policy"), dict) else {}
    if isinstance(policy.get("generate"), dict):
        return int(policy["generate"].get("bytes") or 32)
    m = re.fullmatch(r"random:(\d+)", str(row.get("generate") or ""))
    return int(m.group(1)) if m else 0


def generated_rows(catalogue: dict[str, Any], folder: str, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """The catalogue keys generated for one secrets folder: each that names it (`policy.modules`), and an
    unscoped one only in a project with one secrets folder (the catalogue check refuses it otherwise) --
    never every module. The one reader: what is made, handed over and checked for reach is the same set."""
    from lib.config_keys import secrets_folders

    single = len(secrets_folders(manifest)) <= 1
    out = []
    for row in catalogue.get("keys") or []:
        if not isinstance(row, dict) or not generate_bytes(row):
            continue
        policy = row.get("policy") if isinstance(row.get("policy"), dict) else {}
        named = policy.get("modules") or []
        if folder in named or (not named and single):
            out.append(row)
    return out


def env_name(row: dict[str, Any]) -> str:
    """The one environment spelling a key is given by: its first declared `env`, else `A__B` of `A:B`."""
    import re as _re

    declared = [str(n) for n in row.get("env") or []]
    return declared[0] if declared else _re.sub(r"[^A-Za-z0-9_]", "_", str(row["key"]).replace(":", "__"))


def _names(row: dict[str, Any]) -> list[str]:
    from lib.config_keys import env_names

    return sorted(env_names(row))


def _value(values: dict[str, str], row: dict[str, Any]) -> tuple[str, str] | None:
    for name in _names(row):
        if name in values:
            return name, values[name]
    return None


def _applies(policy: dict[str, Any], folder: str) -> bool:
    mods = policy.get("modules")
    return not mods or folder in mods


def _required(policy: dict[str, Any], environment: str) -> bool:
    req = policy.get("required")
    return environment in req if isinstance(req, list) else bool(req)


def problems(catalogue: dict[str, Any], values: dict[str, str], *, folder: str, environment: str) -> list[str]:
    out: list[str] = [f"{folder} ({environment}): {name} is pending -- {m.group(1).strip()}"
                      for name, value in sorted(values.items()) if (m := PENDING.search(value))]
    rows = [r for r in catalogue.get("keys") or [] if isinstance(r, dict) and isinstance(r.get("policy"), dict)]
    by_key = {str(r["key"]): r for r in rows}
    where = f"{folder} ({environment})"
    for row in rows:
        policy = row["policy"]
        if not _applies(policy, folder):
            continue
        key = str(row["key"])
        found = _value(values, row)
        if found is None or PLACEHOLDER.match(found[1].strip()) or PENDING.search(found[1]):
            if _required(policy, environment) and not generate_bytes(row) and not (found and PENDING.search(found[1])):
                out.append(f"{where}: {key} is required{' in ' + environment if isinstance(policy.get('required'), list) else ''}"
                           f" and {'is a placeholder' if found else 'is not set'}")
            continue
        name, value = found
        value = value.strip()
        if policy.get("minLength") and len(value) < int(policy["minLength"]):
            out.append(f"{where}: {key} is shorter than {int(policy['minLength'])} characters")
        fmt = policy.get("format")
        if fmt == "positive-int" and not re.fullmatch(r"[1-9]\d*", value):
            out.append(f"{where}: {key} is not a positive integer")
        if fmt in ("url", "https-url") and not re.match(r"^https?://[^\s/]+", value):
            out.append(f"{where}: {key} is not a URL")
        if fmt == "https-url" and re.match(r"^https?://", value):
            if not value.lower().startswith("https://"):
                out.append(f"{where}: {key} is not https")
            if _LOCAL.match(value):
                out.append(f"{where}: {key} points at this machine (localhost)")
        for glob in (policy.get("forbid") or {}).get(environment) or []:
            parts = [p.strip() for p in value.split(",")] if "," in value else [value]
            if any(fnmatch.fnmatch(p, str(glob)) for p in parts):
                out.append(f"{where}: {key} holds a value {environment} forbids ({glob})")
                break
        for other in policy.get("requires") or []:
            row2 = by_key.get(str(other)) or {"key": str(other)}
            got = _value(values, row2)
            if got is None or PLACEHOLDER.match(got[1].strip()):
                out.append(f"{where}: {key} is set, so {other} is required too")
    return out


def catalogue_of(root, manifest: dict[str, Any]) -> dict[str, Any]:
    import json

    rel = (manifest.get("config") or {}).get("keys")
    path = root / str(rel) if rel else None
    if not path or not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))
