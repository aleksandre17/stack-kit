"""Environment isolation by data source (ADR-001 amendment 16.6).

Two environments may run apart -- their own compose projects, networks, volumes, ports, secrets --
and still read and write ONE database, so a "dev" deploy runs against production data. The
configuration catalogue (`config.keys`) marks the keys that name a store (`dataSource: true`); each
environment's value of each such key is read where the application reads it -- the module's env
files for that environment (the shared `.env` included) and the runtime config files declared for
it (`modules.<id>.runtimeConfig`) -- and reduced to its IDENTITY: the server (host, port or instance)
and the database name, parsed from a connection string or URL. Only identities are compared; a value
is never printed, and an identity is shown as a short fingerprint.

Two environments that share an identity are refused by a deploy of either, and reported by
`validate`, unless the sharing is declared with its reason -- in the manifest (`config.sharedDataSources`)
or on a target (`sharedDataSources`): `[{key, environments: [a, b], reason}]`. A value whose host is
under `.invalid` (RFC 2606: never resolves) is the kit's sentinel for "no store in this environment"
and is never shared.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

#: The host of the kit's "no store here" sentinel (RFC 2606: a name under .invalid never resolves).
SENTINEL_HOST = "none.invalid"
_LOCAL = {"localhost", "127.0.0.1", "::1", ".", "(local)", "(localdb)"}
_SERVER_KEYS = ("server", "data source", "datasource", "address", "addr", "network address", "host", "hostname")
_DB_KEYS = ("database", "initial catalog", "dbname", "databasename", "db")


def _host(raw: str) -> str:
    h = raw.strip().lower()
    for prefix in ("tcp:", "np:", "lpc:"):
        if h.startswith(prefix):
            h = h[len(prefix):]
    h = h.replace(",", ":")  # ADO.NET spells a port `host,1433`
    name, _, port = h.partition(":") if h.count(":") == 1 else (h, "", "")
    name = "localhost" if name.split("\\")[0] in _LOCAL else name
    return f"{name}:{port}" if port else name


def identity(value: str) -> tuple[str, str] | None:
    """(server, database) of a connection string or URL, or None when it names no server."""
    v = value.strip().strip("\"'")
    if not v:
        return None
    if v.lower().startswith("jdbc:"):
        v = v[5:]
    if "://" in v:
        scheme, rest = v.split("://", 1)
        head, *params = rest.split(";")  # jdbc:sqlserver://host:1433;databaseName=x
        kv = {k.strip().lower(): val.strip() for k, _, val in (p.partition("=") for p in params) if k.strip()}
        u = urlsplit(f"{scheme}://{head}")
        try:
            port = u.port
        except ValueError:
            port = None
        host = (u.hostname or "") + (f":{port}" if port else "")
        db = (u.path.strip("/").split("/")[0] or next((kv[k] for k in _DB_KEYS if kv.get(k)), "")
              or (parse_qs(u.query).get("database") or [""])[0])
        return (_host(host), db.strip().lower()) if u.hostname else None
    pairs = [p for p in (v.split(";") if ";" in v else v.split()) if "=" in p]
    kv = {k.strip().lower(): val.strip() for k, _, val in (p.partition("=") for p in pairs)}
    server = next((kv[k] for k in _SERVER_KEYS if kv.get(k)), "")
    db = next((kv[k] for k in _DB_KEYS if kv.get(k)), "")
    if kv.get("port") and server and ":" not in server and "," not in server:
        server = f"{server}:{kv['port']}"
    return (_host(server), db.strip().lower()) if server else None


def is_sentinel(ident: tuple[str, str]) -> bool:
    """The kit's "no store in this environment" value: a host under .invalid, which never resolves."""
    return ident[0].split(":")[0].endswith(".invalid")


def fingerprint(ident: tuple[str, str]) -> str:
    return hashlib.sha256("/".join(ident).encode("utf-8")).hexdigest()[:8]


def _rows(catalogue: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in catalogue.get("keys") or [] if isinstance(r, dict) and r.get("dataSource")]


def _json_value(path: Path, key: str) -> str | None:
    from lib.config_keys import _json_at, _path

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    found = _json_at(data, _path(key))
    return found if isinstance(found, str) else None


def values_by_environment(root: Path, manifest: dict[str, Any], catalogue: dict[str, Any],
                          environments: list[str]) -> dict[str, dict[str, list[tuple[str, tuple[str, str]]]]]:
    """{environment: {key: [(where, identity)]}} -- every place an environment's value of a data-source
    key is read from, reduced to its identity. An environment whose files are not on this machine
    simply has none (a CI job that holds only its own environment's file compares what it has)."""
    from lib import envfile
    from lib.config_keys import env_names
    from lib.project_context import ProjectContext

    ctx = ProjectContext(root=root, manifest=manifest)
    rows = _rows(catalogue)
    out: dict[str, dict[str, list[tuple[str, tuple[str, str]]]]] = {e: {} for e in environments}
    if not rows:
        return out
    folders = ctx.list_secrets_module_folders()
    for env in environments:
        for folder in folders:
            try:
                files = envfile.run_files(ctx.secrets_root, folder, env, environments)
            except (FileNotFoundError, ValueError):
                continue
            values = envfile.merged(files)
            for row in rows:
                name = next((n for n in sorted(env_names(row)) if n in values), None)
                ident = identity(values[name]) if name else None
                if ident:
                    out[env].setdefault(str(row["key"]), []).append((f"{folder} env files", ident))
        for mid, cfg in (manifest.get("modules") or {}).items():
            for item in (cfg or {}).get("runtimeConfig") or [] if isinstance(cfg, dict) else []:
                if env not in (item.get("environments") or []):
                    continue
                src = root / str(item.get("from") or "")
                for row in rows:
                    value = _json_value(src, str(row["key"])) if src.is_file() else None
                    ident = identity(value) if value else None
                    if ident:
                        out[env].setdefault(str(row["key"]), []).append((str(item["from"]), ident))
    return out


def declared_sharing(manifest: dict[str, Any], targets: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    found = list(((manifest.get("config") or {}).get("sharedDataSources")) or [])
    for t in ((targets or {}).get("targets") or {}).values():
        if isinstance(t, dict):
            found += list(t.get("sharedDataSources") or [])
    return [d for d in found if isinstance(d, dict) and d.get("reason")]


def _declared(sharing: list[dict[str, Any]], key: str, a: str, b: str) -> bool:
    return any(d.get("key") in (key, "*") and {a, b} <= set(d.get("environments") or []) for d in sharing)


def shared(root: Path, manifest: dict[str, Any], catalogue: dict[str, Any], environments: list[str], *,
           only: str = "", targets: dict[str, Any] | None = None) -> list[str]:
    """Each pair of environments that reads one store through a data-source key, undeclared; `only`:
    the pairs that involve that environment (a deploy's). Names and fingerprints, never values."""
    by_env = values_by_environment(root, manifest, catalogue, environments)
    sharing = declared_sharing(manifest, targets)
    out = []
    for i, a in enumerate(environments):
        for b in environments[i + 1:]:
            if only and only not in (a, b):
                continue
            for key in sorted(set(by_env[a]) & set(by_env[b])):
                ids_a = {ident: where for where, ident in by_env[a][key]}
                for where_b, ident in by_env[b][key]:
                    if ident in ids_a and not is_sentinel(ident) and not _declared(sharing, key, a, b):
                        out.append(f"{key}: {a} ({ids_a[ident]}) and {b} ({where_b}) name the same server and database "
                                   f"[{fingerprint(ident)}] -- a {a} deploy would use {b}'s data; give each its own, "
                                   f"or declare the sharing with its reason (config.sharedDataSources)")
                        break
    return out
