"""Deploy targets: declared configuration, never a value the kit holds (ADR-001 amendments 9, 13).

A host names a tracked, non-secret file in its manifest (`deploy.targets`); a gitignored
`<name>.local.json` beside it is merged over it, per machine. Each named target says where a deploy
goes (`host`, `user`, `port`, an absolute `root` -- a directory the platform shares between
projects, never acted on itself), what runs it there (`runtime`), how ssh reaches it (`ssh`: an
identity REFERENCE, pinned host keys, options), the host ports each service publishes, and where
each place lives (`layout`, over the kit's one default). The kit infers nothing.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import lib.targets.layout as layout

KIT = Path(__file__).resolve().parents[2]
SCHEMA = KIT / "config" / "deploy-targets.schema.json"
#: What may never be a value of a targets file: a key's armour, or a field that names a secret.
_SECRET_TEXT = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|PRIVATE KEY")
_SECRET_FIELD = re.compile(r"(?i)^(password|passphrase|secret|token|private_?key|key)$")
#: ssh options host-key checking owns; a target sets them through `hostKeys`, never `options`.
_HOST_KEY_OPTIONS = {"stricthostkeychecking", "userknownhostsfile", "globalknownhostsfile"}


class TargetError(ValueError):
    """A target could not be selected or resolved; the message names the field or the choice."""


def environments(manifest: dict[str, Any] | None = None) -> list[str]:
    from lib import catalogs

    return catalogs.ids("environments", manifest)


def declared_file(manifest: dict[str, Any]) -> str | None:
    deploy = manifest.get("deploy")
    return (deploy.get("targets") or None) if isinstance(deploy, dict) else None


def local_file(path: Path) -> Path:
    return path.with_name(path.name[: -len(".json")] + ".local.json") if path.name.endswith(".json") else path.with_name(path.name + ".local")


def _merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = _merge(base.get(k), v) if k in base else v
        return out
    return over


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise TargetError(f"{path.name}: not JSON ({e})") from e
    return data if isinstance(data, dict) else {}


def load(root: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    """The declared targets merged with this machine's override, or None when none is declared."""
    rel = declared_file(manifest)
    if not rel:
        return None
    path = root / rel
    if not path.is_file():
        raise TargetError(f"deploy.targets: {rel} is not there")
    data = _read(path)
    local = local_file(path)
    if local.is_file():
        data = _merge(data, _read(local))
    return data


def select(data: dict[str, Any], name: str = "", environment: str = "",
           manifest: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """The target asked for (`--target`), else the environment's default, else the only one."""
    targets = data.get("targets") or {}
    if not environment:
        from lib import catalogs

        environment = catalogs.default_environment("deploy", manifest)
    chosen = name or (data.get("defaults") or {}).get(environment) or (next(iter(targets)) if len(targets) == 1 else "")
    if not chosen:
        raise TargetError(f"no target for '{environment}': pass --target <{'|'.join(targets) or 'name'}> "
                          f"or declare defaults.{environment}")
    if chosen not in targets:
        raise TargetError(f"no target '{chosen}' (declared: {', '.join(targets) or 'none'})")
    return chosen, targets[chosen]


def reachable(name: str, target: dict[str, Any]) -> dict[str, Any]:
    """The target, if a deploy may go to it; a pending one is refused with its reason."""
    if target.get("pending"):
        raise TargetError(f"target {name} is pending: {target['pending']}")
    for field in ("host", "user", "root"):
        if not target.get(field):
            raise TargetError(f"target {name}: {field} is not declared")
    return target


def server(name: str, target: dict[str, Any]) -> str:
    t = reachable(name, target)
    return f"{t['user']}@{t['host']}"


def keep(target: dict[str, Any]) -> int:
    from lib.delivery.model import defaults

    return int(target.get("keep") or defaults()["keep"])


def _ports(data: dict[str, Any]) -> list[tuple[str, str, str, str, int]]:
    """(host, target, environment, service, port) for every declared host port."""
    out = []
    for name, t in (data.get("targets") or {}).items():
        if isinstance(t, dict):
            for env, services in (t.get("ports") or {}).items():
                for service, ports in (services or {}).items():
                    out += [(str(t.get("host") or name), name, env, service, int(p)) for p in ports or []]
    return out


def _fields(cur: Any, path: str = "") -> list[tuple[str, str]]:
    out = []
    if isinstance(cur, dict):
        for k, v in cur.items():
            here = f"{path}.{k}" if path else str(k)
            parent = path.rsplit(".", 1)[-1] if path else ""
            if parent not in ("targets", "paths", "defaults", "units"):  # names chosen by the host, not fields
                out.append((str(k), here))
            out += _fields(v, here)
    return out


def tracked(root: Path, rel: str) -> bool:
    try:
        ran = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", rel],
                             capture_output=True, text=True)
    except OSError:
        return False
    return ran.returncode == 0


def problems(root: Path, manifest: dict[str, Any]) -> list[str]:
    """What `validate` refuses in the declaration: its shape, a missing root, a secret value, a
    host-key option outside `hostKeys`, an unknown placeholder, a tracked override or key file, an
    undeclared runtime or environment, a host port declared twice, a legacy mapping that would reach
    outside the root."""
    from lib import catalogs
    from lib.schema_check import validate as schema_validate

    rel = declared_file(manifest)
    if not rel:
        return []
    out: list[str] = []
    path = root / rel
    try:
        data = load(root, manifest)
    except TargetError as e:
        return [str(e)]
    for f in (path, local_file(path)):
        if f.is_file() and _SECRET_TEXT.search(f.read_text(encoding="utf-8")):
            out.append(f"{f.relative_to(root).as_posix()}: holds private key material -- a target names an identity, never carries one")
    out += [f"{rel}: {e}" for e in schema_validate(data, json.loads(SCHEMA.read_text(encoding="utf-8")))]
    envs = environments(manifest)
    for name, t in (data.get("targets") or {}).items():
        if not isinstance(t, dict):
            continue
        where = f"{rel}: targets.{name}"
        if not t.get("pending"):
            for field in ("host", "user", "root"):
                if not t.get(field):
                    out.append(f"{where}.{field}: required (or declare the target `pending` with its reason)")
        for opt in (t.get("ssh") or {}).get("options") or []:
            if str(opt).split("=", 1)[0].lower() in _HOST_KEY_OPTIONS:
                out.append(f"{where}.ssh.options: {opt.split('=', 1)[0]} is `hostKeys`' to set (pinned | accept-new)")
        out += [f"{where}.{p}" for p in layout.problems(t, envs)]
        if t.get("root"):
            out += [f"{where}.{p}" for p in layout.isolation_problems(t, envs)]
        identity_ref = str((t.get("ssh") or {}).get("identity") or "")
        if identity_ref.startswith("file:") and tracked(root, identity_ref[5:]):
            out.append(f"{where}.ssh.identity: {identity_ref[5:]} is tracked by git -- a key file is never committed")
        known = (t.get("ssh") or {}).get("knownHosts")
        if known and not (root / known).is_file():
            out.append(f"{where}.ssh.knownHosts: {known} is not there (pin the host key, verified out of band)")
        legacy = t.get("legacyLayout") or {}
        if legacy and legacy.get("environment") and legacy["environment"] not in envs:
            out.append(f"{where}.legacyLayout.environment: '{legacy['environment']}' is not a declared environment")
    for walk_key, walk_path in _fields(data):
        if _SECRET_FIELD.match(walk_key):
            out.append(f"{rel}: {walk_path} names a secret -- secrets live in secret files or the store")
    if local_file(path).is_file() and tracked(root, local_file(path).relative_to(root).as_posix()):
        out.append(f"{local_file(path).relative_to(root).as_posix()}: tracked by git -- the per-machine override is ignored by design")
    runtimes = catalogs.ids("targetRuntimes", manifest)
    for env, name in (data.get("defaults") or {}).items():
        if env not in envs:
            out.append(f"{rel}: defaults.{env}: '{env}' is not a declared environment ({', '.join(envs)})")
        if name not in (data.get("targets") or {}):
            out.append(f"{rel}: defaults.{env} names '{name}', which is not a target")
    for name, t in (data.get("targets") or {}).items():
        if isinstance(t, dict) and t.get("runtime") not in runtimes:
            out.append(f"{rel}: targets.{name}.runtime: '{t.get('runtime')}' is not a declared target runtime "
                       f"({', '.join(runtimes)}; a host adds one in catalogs.targetRuntimes)")
        for field in ("ports", "health", "oidc"):
            for env in (t.get(field) or {}) if isinstance(t, dict) else {}:
                if env not in envs:
                    out.append(f"{rel}: targets.{name}.{field}.{env}: '{env}' is not a declared environment")
    seen: dict[tuple[str, int], str] = {}
    for host, name, env, service, port in _ports(data):
        here = f"targets.{name}.ports.{env}.{service}"
        if (host, port) in seen and seen[(host, port)] != here:
            out.append(f"{rel}: {here}: host port {port} on {host} is already {seen[(host, port)]}'s")
        seen.setdefault((host, port), here)
    return out


def notices(root: Path, manifest: dict[str, Any]) -> list[str]:
    """What `validate` prints but does not refuse: pending targets, unpinned host keys, trust on first use."""
    try:
        data = load(root, manifest)
    except TargetError:
        return []
    if data is None:
        return []
    out = []
    for name, t in (data.get("targets") or {}).items():
        if not isinstance(t, dict):
            continue
        if t.get("pending"):
            out.append(f"target {name}: pending -- {t['pending']}")
            continue
        ssh = t.get("ssh") or {}
        if ssh.get("hostKeys") == "accept-new":
            out.append(f"target {name}: hostKeys accept-new -- the first host key seen is trusted (declared)")
        elif not ssh.get("knownHosts"):
            out.append(f"target {name}: host key not pinned in the repository (strict against this machine's known_hosts)")
    return out
