#!/usr/bin/env python3
"""Migrate the project manifest toward v2 conventions (roles, credentials hints)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from lib.identity import MANIFEST_FILENAME, find_manifest
from lib.manifest_defaults import CI_SCRIPT_FIELDS
from lib.modules import driver_accepts_global_credentials, driver_default_role
from lib.project_context import ProjectContext, find_project_root, load_manifest


def _infer_role(cfg: dict[str, Any]) -> str:
    """A module's role: declared on the module, else the role its DRIVER declares."""
    role = (cfg.get("role") or "").lower()
    if role:
        return role
    return driver_default_role(str(cfg.get("type", ""))) or "other"


#: Module fields one former consumer's tools read and the kit never did: carried into the module's
#: `extensions`, under the same name, so nothing the host wrote is lost (ADR-001 amendment 7).
MODULE_EXTENSION_FIELDS = ("catalog", "derivation")
#: `ci` fields that are the kit's own; any other string under `ci` is a host script, by its name.
CI_KIT_FIELDS = frozenset(CI_SCRIPT_FIELDS) | {"scripts", "healthModules", "workflow"}


def carry_host_shapes(manifest: dict[str, Any], *, apply: bool = False) -> list[str]:
    """A host's own names the schema once spelled are carried to the agnostic homes: a former
    `ci.<name>` script path to `ci.scripts.<name>`, a module's `catalog`/`derivation` to its
    `extensions`. A key already in its new home is never overwritten -- that is a conflict, named."""
    changes: list[str] = []
    ci = manifest.get("ci")
    if isinstance(ci, dict):
        for key in [k for k in ci if k not in CI_KIT_FIELDS and isinstance(ci[k], str)]:
            scripts = ci.get("scripts") if isinstance(ci.get("scripts"), dict) else {}
            if key in scripts:
                changes.append(f"ci.{key}: CONFLICT -- ci.scripts.{key} already set; resolve by hand")
                continue
            changes.append(f"ci.{key} -> ci.scripts.{key}")
            if apply:
                ci["scripts"] = {**scripts, key: ci.pop(key)}
    for mid, cfg in (manifest.get("modules") or {}).items():
        if not isinstance(cfg, dict):
            continue
        for key in [k for k in MODULE_EXTENSION_FIELDS if k in cfg]:
            ext = cfg.get("extensions") if isinstance(cfg.get("extensions"), dict) else {}
            if key in ext:
                changes.append(f"modules.{mid}.{key}: CONFLICT -- extensions.{key} already set; resolve by hand")
                continue
            changes.append(f"modules.{mid}.{key} -> modules.{mid}.extensions.{key}")
            if apply:
                cfg["extensions"] = {**ext, key: cfg.pop(key)}
    return changes


#: Where `migrate` declares a host's targets: beside ops/, never under the secrets root (which ignores
#: everything it does not whitelist -- a targets file is reviewable configuration, so it is tracked).
TARGETS_FILE = "ops/deploy/targets.json"
TARGET_NAME = "prod"


def carry_deploy_targets(root: Path, secrets_root: Path, manifest: dict[str, Any], *,
                         apply: bool = False) -> tuple[list[str], dict[str, Any] | None]:
    """deploy.env's server, base and ssh settings, declared as one target (ADR-001 amendment 9).
    Nothing is invented: a base that was inferred is written as what it was, and said; a value that
    looks like a key or a password is refused and named, never written. The env files are not edited."""
    import re as _re

    from lib import envfile, targets

    if targets.declared_file(manifest):
        return [], None
    deploy = envfile.parse(secrets_root / "deploy.env")
    server = deploy.get("DEPLOY_SERVER", "")
    if not server:
        return [], None
    changes: list[str] = []
    m = _re.match(r"^(?:ssh://)?([^@]+)@([^:/]+)(?::(\d+))?$", server)
    if not m:
        return [f"deploy.env DEPLOY_SERVER: not user@host -- declare {TARGETS_FILE} by hand"], None
    user, host, port = m.group(1), m.group(2), int(m.group(3) or 22)
    target: dict[str, Any] = {"runtime": "docker-compose", "host": host, "user": user}
    if port != 22:
        target["port"] = port
    if deploy.get("DEPLOY_SERVER_BASE"):
        target["root"] = deploy["DEPLOY_SERVER_BASE"].rstrip("/")
    else:
        target["root"] = f"/home/{user}"
        changes.append(f"targets.{TARGET_NAME}.root: /home/{user} -- was INFERRED from DEPLOY_SERVER's user; "
                       f"the kit infers no more: confirm or correct it")
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
        changes.append(f"deploy.env DEPLOY_SSH_OPTIONS: '{tok}' is not `-o Key=Value` -- carry it by hand")
        i += 1
    if options:
        ssh["options"] = options
    if ssh:
        target["ssh"] = ssh
    if targets._SECRET_TEXT.search(json.dumps(target)):
        return [f"deploy.env: a value looks like private key material -- refused, nothing written"], None
    for secretish in sorted(k for k in deploy if _re.search(r"(?i)PASS|SECRET|TOKEN|PRIVATE", k) and k.startswith("DEPLOY_SSH")):
        changes.append(f"deploy.env {secretish}: a secret is never a target value -- not carried; keep it in "
                       f"the secret store and reference it (ssh.identity env:VAR)")
    for folder in sorted({str(c.get("secretsModule") or mid) for mid, c in (manifest.get("modules") or {}).items()
                          if isinstance(c, dict)}):
        explicit = envfile.merged(envfile.folder_files(secrets_root, folder)).get("DEPLOY_PATH", "")
        if explicit:
            changes.append(f"{folder}: DEPLOY_PATH={explicit} -- a target places every module under "
                           f"{{root}}/{{project}}/{{environment}}/modules/; move what is deployed there, or "
                           f"override targets.{TARGET_NAME}.layout (inside the project's directory) by hand")
        layout = envfile.merged(envfile.folder_files(secrets_root, folder)).get("DEPLOY_LAYOUT", "")
        if layout and layout != "structured":
            changes.append(f"{folder}: DEPLOY_LAYOUT={layout} -- declare it as targets.{TARGET_NAME}.layout "
                           f"(e.g. \"runtime\": \"{{module}}/{{container}}\") by hand")
    document = {"schema": 1, "defaults": {"prod": TARGET_NAME, "dev": TARGET_NAME}, "targets": {TARGET_NAME: target}}
    changes.insert(0, f"deploy.targets: (add) -> {TARGETS_FILE}  (target '{TARGET_NAME}': {user}@{host}:"
                      f"{target.get('port', 22)}, from deploy.env)")
    if apply:
        manifest.setdefault("deploy", {})["targets"] = TARGETS_FILE
        out = root / TARGETS_FILE
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists():
            out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
    changes.append("deploy.env DEPLOY_SERVER / DEPLOY_SERVER_BASE / DEPLOY_SSH_* are ignored once the target "
                   "is declared -- remove them (migrate does not edit env files)")
    return changes, document


def run_env_notices(secrets_root: Path, manifest: dict[str, Any]) -> list[str]:
    """What a development run no longer fills from `.env.prod` (amendment 8), per secrets folder, by
    key NAME. Not a change `migrate` can make: the development values are the owner's to write."""
    from lib import envfile

    folders: list[str] = []
    for mid, cfg in (manifest.get("modules") or {}).items():
        if isinstance(cfg, dict) and str(cfg.get("secretsModule") or mid) not in folders:
            folders.append(str(cfg.get("secretsModule") or mid))
    out = []
    for folder in folders:
        lost = envfile.dev_run_loses(secrets_root, folder)
        if lost:
            out.append(f"{folder}: a development run no longer reads {', '.join(lost)} from .env.prod -- "
                       f"set development values in .env.dev (non-secret shared ones in .env); "
                       f".env.prod is read only with --env prod")
    return out


def migrate_manifest(manifest: dict[str, Any], *, apply: bool = False) -> list[str]:
    changes: list[str] = []
    ver = manifest.get("version", 1)
    if ver < 2:
        changes.append(f"version: {ver} -> 2")
        if apply:
            manifest["version"] = 2

    mods = manifest.setdefault("modules", {})
    if not isinstance(mods, dict):
        return ["modules: invalid — manual fix required"]

    for mid, cfg in list(mods.items()):
        if not isinstance(cfg, dict):
            continue
        if not cfg.get("role"):
            role = _infer_role(cfg)
            changes.append(f"modules.{mid}.role: (add) -> {role}")
            if apply:
                cfg["role"] = role
        if not cfg.get("secretsModule"):
            changes.append(f"modules.{mid}.secretsModule: (add) -> {mid}")
            if apply:
                cfg["secretsModule"] = mid

    feats = manifest.get("features") or {}
    if feats.get("gcpCredentials") and not any(
        isinstance(c, dict) and c.get("credentials")
        for c in mods.values()
        if isinstance(c, dict)
    ):
        gcp = (manifest.get("adapters") or {}).get("gcp") or {}
        fn = gcp.get("credentialsFile", "google-credentials.json") if isinstance(gcp, dict) else "google-credentials.json"
        for mid, cfg in mods.items():
            if not isinstance(cfg, dict) or not driver_accepts_global_credentials(
                str(cfg.get("type") or "")
            ):
                continue
            if cfg.get("role") not in ("api", "worker"):
                continue
            changes.append(
                f"modules.{mid}.credentials: (optional) add explicit GCP profile for '{fn}'"
            )
            break

    return changes


def main() -> int:
    apply = "--apply" in sys.argv
    try:
        root = find_project_root()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    mf = find_manifest(root) or (root / MANIFEST_FILENAME)
    manifest = load_manifest(root)
    # The kit's former names first: a host on them is carried to the current ones (ADR-001).
    from lib.migrate_identity import TwoHomes, host_words, migrate_identity

    try:
        changes, moved_to = migrate_identity(root, manifest, apply=apply)
    except TwoHomes as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if moved_to is not None and apply:
        mf = moved_to
    changes += migrate_manifest(manifest, apply=apply)
    changes += carry_host_shapes(manifest, apply=apply)
    carried, _document = carry_deploy_targets(root, ProjectContext.discover(root).secrets_root, manifest, apply=apply)
    changes += carried
    words = host_words(root, skip={mf, root / MANIFEST_FILENAME})
    for line in words:
        print(f"  restate (yours to edit): {line}")
    for line in run_env_notices(ProjectContext.discover(root).secrets_root, manifest):
        print(f"  env (yours to set): {line}")
    if not changes:
        print("[migrate] manifest already v2-ready")
        return 0
    for line in changes:
        print(f"  {line}")
    if apply:
        mf.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"[migrate] wrote {mf}")
    else:
        print("[migrate] dry-run — pass --apply to write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
