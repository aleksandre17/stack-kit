"""`migrate`'s carrying of the homes removed in 2.0.0 (lib/legacy.py names them): each value into its
one home, then out of where it was (ADR-001 amendment 13). Nothing is invented: a root that was
inferred is written as what it was, and said; a value that looks like a key or a password is
refused and named, never written; a key with no home now is named and dropped.

    DEPLOY_SERVER, _SERVER_BASE, _SSH_*      -> a target in the targets file (when none is declared)
    DEPLOY_PROJECT (else COMPOSE_PROJECT_NAME) -> the manifest's `project`
    <folder> DEPLOY_HOST_PORT                -> targets.<t>.ports.<deploy environment>.<service>
    <folder> DEPLOY_PATH                     -> targets.<t>.legacyLayout.units.<service> (plan its move:
                                                `layout migrate`, applied only with --approve)
    COMPOSE_*_SERVICE, DOCKER_NETWORK,       -> dropped: derived from `project` (lib/naming.py)
    INFRA_SLUG, DEPLOY_LAYOUT, _PATH_MODE
    stack.networkName, stack.deployBaseSecretsModule, stackDeploy, catalogs.roles serviceOverride
                                             -> removed from the manifest
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib import envfile, legacy

TARGETS_FILE = "ops/deploy/targets.json"
TARGET_NAME = "prod"
DROPPED = re.compile(r"^(COMPOSE_[A-Z0-9]+_SERVICE|DOCKER_NETWORK|STACK_KIT_DOCKER_NETWORK|INFRA_SLUG|DEPLOY_LAYOUT|"
                     r"DEPLOY_PATH_MODE)$")


def _legacy_values(secrets_root: Path, manifest: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """(the shared deploy values, {folder: its own legacy keys}) -- names and values, never printed."""
    shared = {k: v for k, v in envfile.parse(secrets_root / "deploy.env").items() if legacy.KEY.match(k)}
    per: dict[str, dict[str, str]] = {}
    for folder in legacy.folders(secrets_root, manifest):
        d = secrets_root / folder
        files = [d / ".env.deploy", *(sorted(d.glob(".env*")) if d.is_dir() else [])]
        vals: dict[str, str] = {}
        for f in dict.fromkeys(files):
            if f.is_file() and not f.name.endswith(".example"):
                vals.update({k: v for k, v in envfile.parse(f).items() if legacy.KEY.match(k)})
        if vals:
            per[folder] = vals
    return shared, per


def _target(deploy: dict[str, str], changes: list[str]) -> dict[str, Any] | None:
    from lib.targets.declaration import _SECRET_TEXT

    server = deploy.get("DEPLOY_SERVER", "")
    m = re.match(r"^(?:ssh://)?([^@]+)@([^:/]+)(?::(\d+))?$", server)
    if not m:
        changes.append(f"DEPLOY_SERVER: not user@host -- declare {TARGETS_FILE} by hand")
        return None
    user, host, port = m.group(1), m.group(2), int(m.group(3) or 22)
    target: dict[str, Any] = {"runtime": "docker-compose", "host": host, "user": user}
    if port != 22:
        target["port"] = port
    if deploy.get("DEPLOY_SERVER_BASE"):
        target["root"] = deploy["DEPLOY_SERVER_BASE"].rstrip("/")
    else:
        target["root"] = f"/home/{user}"
        changes.append(f"targets.{TARGET_NAME}.root: /home/{user} -- was INFERRED from DEPLOY_SERVER's user; the kit "
                       f"infers no more: confirm it, or name the platform's shared directory under it")
    ssh: dict[str, Any] = {}
    if deploy.get("DEPLOY_SSH_IDENTITY_FILE"):
        ssh["identity"] = f"file:{deploy['DEPLOY_SSH_IDENTITY_FILE']}"
    if deploy.get("DEPLOY_SSH_CONFIG_FILE"):
        ssh["config"] = deploy["DEPLOY_SSH_CONFIG_FILE"]
    tokens = deploy.get("DEPLOY_SSH_OPTIONS", "").split()
    options, i = [], 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-o", "-p") and i + 1 < len(tokens):
            value, i = tokens[i + 1], i + 2
            if tok == "-p":
                target["port"] = int(value)
                continue
            key, _, val = value.partition("=")
            if key.lower() == "stricthostkeychecking":
                if val.lower() in ("accept-new", "no", "off"):
                    ssh["hostKeys"] = "accept-new"
                    changes.append(f"targets.{TARGET_NAME}.ssh.hostKeys: accept-new (was StrictHostKeyChecking={val}) "
                                   f"-- trust on first use, now declared; pin the key in ssh.knownHosts to remove it")
            elif key.lower() == "userknownhostsfile":
                ssh["knownHosts"] = val
            elif key.lower() == "port":
                target["port"] = int(val)
            else:
                options.append(value)
            continue
        changes.append(f"DEPLOY_SSH_OPTIONS: '{tok}' is not `-o Key=Value` -- carry it by hand")
        i += 1
    if options:
        ssh["options"] = options
    if ssh:
        target["ssh"] = ssh
    if _SECRET_TEXT.search(json.dumps(target)):
        changes.append("deploy.env: a value looks like private key material -- refused, nothing written")
        return None
    return target


def _service_of(manifest: dict[str, Any], folder: str) -> str | None:
    from lib import naming

    for mid, cfg in (manifest.get("modules") or {}).items():
        if isinstance(cfg, dict) and str(cfg.get("secretsModule") or mid) == folder:
            return naming.service_id(manifest, mid)
    return None


def _strip(path: Path) -> bool:
    """The file without its legacy keys (comments and other keys kept); deleted when nothing is left.
    True when it changed."""
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if not (re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", ln)
                                       and legacy.KEY.match(re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)", ln).group(1)))]
    if kept == lines and path.name not in legacy.FILES:
        return False
    if not envfile.parse(path) or all(legacy.KEY.match(k) for k in envfile.parse(path)):
        if path.name in legacy.FILES or not [ln for ln in kept if ln.strip() and not ln.lstrip().startswith("#")]:
            path.unlink()
            return True
    path.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
    return True


def carry(root: Path, secrets_root: Path, manifest: dict[str, Any], *, apply: bool = False) -> list[str]:
    from lib import catalogs, naming, targets

    changes: list[str] = []
    shared, per = _legacy_values(secrets_root, manifest)
    every = {**shared, **{k: v for vals in per.values() for k, v in vals.items() if k.startswith("DEPLOY_SERVER") or k.startswith("DEPLOY_SSH")}}
    rel = targets.declared_file(manifest)
    # The tracked file itself, never merged with this machine's override: that is not written back.
    data = json.loads((root / rel).read_text(encoding="utf-8")) if rel and (root / rel).is_file() else None
    name = TARGET_NAME
    target: dict[str, Any] | None = None
    if data is None and every.get("DEPLOY_SERVER"):
        target = _target(every, changes)
        if target is not None:
            data = {"schema": 1, "defaults": {e: name for e in catalogs.ids("environments", manifest)}, "targets": {name: target}}
            changes.insert(0, f"deploy.targets: (add) -> {TARGETS_FILE} (target '{name}': {target['user']}@{target['host']})")
    elif data is not None:
        env = catalogs.default_environment("deploy", manifest)
        name = (data.get("defaults") or {}).get(env) or next(iter(data.get("targets") or {}), TARGET_NAME)
        target = (data.get("targets") or {}).get(name)
    project = shared.get("DEPLOY_PROJECT") or shared.get("COMPOSE_PROJECT_NAME")
    if project and not manifest.get("project"):
        changes.append(f"project: (add) -> {naming.slugify(project)} (from {'DEPLOY_PROJECT' if shared.get('DEPLOY_PROJECT') else 'COMPOSE_PROJECT_NAME'})")
        if apply:
            manifest["project"] = naming.slugify(project)
    if shared.get("COMPOSE_PROJECT_NAME") and shared.get("DEPLOY_PROJECT") and \
            naming.slugify(shared["COMPOSE_PROJECT_NAME"]) != naming.slugify(shared["DEPLOY_PROJECT"]):
        changes.append(f"COMPOSE_PROJECT_NAME differed from DEPLOY_PROJECT -- one name now: the manifest's `project`")
    env = catalogs.default_environment("deploy", manifest)
    for folder, vals in sorted(per.items()):
        service = _service_of(manifest, folder)
        if vals.get("DEPLOY_HOST_PORT") and service and target is not None and vals["DEPLOY_HOST_PORT"].isdigit():
            ports = target.setdefault("ports", {}).setdefault(env, {})
            if service not in ports:
                ports[service] = [int(vals["DEPLOY_HOST_PORT"])]
                changes.append(f"targets.{name}.ports.{env}.{service}: (add) -> [{vals['DEPLOY_HOST_PORT']}] (from {folder} DEPLOY_HOST_PORT)")
        path = vals.get("DEPLOY_PATH", "").rstrip("/")
        if path and service and target is not None and target.get("root"):
            base = str(target["root"]).rstrip("/")
            if path.startswith(base + "/"):
                units = target.setdefault("legacyLayout", {"environment": env}).setdefault("units", {})
                units.setdefault(service, "{root}" + path[len(base):])
                changes.append(f"targets.{name}.legacyLayout.units.{service}: (add) -> {{root}}{path[len(base):]} "
                               f"(from {folder} DEPLOY_PATH; plan its move: `layout migrate`, apply with --approve)")
            else:
                changes.append(f"{folder} DEPLOY_PATH: {path} is not under the target's root -- move it by hand")
    for key in sorted({k for vals in [shared, *per.values()] for k in vals if DROPPED.match(k)}):
        changes.append(f"{key}: dropped -- derived from the manifest's `project` now (lib/naming.py)")
    for field in legacy.FIELDS:
        if legacy._dig(manifest, field) is not None:
            changes.append(f"{field}: removed -- {legacy.FIELDS[field]}")
            if apply:
                *parent, leaf = field.split(".")
                holder = legacy._dig(manifest, ".".join(parent)) if parent else manifest
                holder.pop(leaf, None)
    for role in ((manifest.get("catalogs") or {}).get("roles") or []):
        if isinstance(role, dict) and role.pop("serviceOverride", None) is not None:
            changes.append(f"catalogs.roles[{role.get('id')}].serviceOverride: removed")
    stripped = []
    for path in legacy.env_files(secrets_root, manifest):
        if any(legacy.KEY.match(k) for k in envfile.parse(path)) or path.name in legacy.FILES:
            stripped.append(path)
    for path in stripped:
        changes.append(f"{path.relative_to(secrets_root).as_posix()}: its legacy keys removed"
                       + (" (the file goes when nothing else is left in it)" if path.name in legacy.FILES else ""))
    if apply:
        if data is not None and target is not None:
            if not targets.declared_file(manifest):
                manifest.setdefault("deploy", {})["targets"] = TARGETS_FILE
            out = root / (targets.declared_file(manifest) or TARGETS_FILE)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
        for path in stripped:
            _strip(path)
    return changes
