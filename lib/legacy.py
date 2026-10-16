"""The homes a value had before 2.0.0 -- the one place that knows them (ADR-001 amendment 13).

Nothing reads them any more: `validate` refuses each one present, naming `migrate`, and `migrate
--apply` is their only reader -- it carries each value into its one home (the manifest, the targets
file) and removes it from where it was.

    deploy.env, <folder>/.env.deploy          files
    DEPLOY_*, COMPOSE_PROJECT_NAME,           keys, in any env file of the secrets folders
    COMPOSE_<ROLE>_SERVICE, DOCKER_NETWORK,
    STACK_KIT_DOCKER_NETWORK, INFRA_SLUG
    stack.networkName, stack.deployBaseSecretsModule, stackDeploy,
    catalogs.roles[].serviceOverride          manifest fields
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lib import envfile, identity

FILES = envfile.LEGACY_FILES
KEY = re.compile(r"^(DEPLOY_[A-Z0-9_]+|COMPOSE_PROJECT_NAME|COMPOSE_[A-Z0-9]+_SERVICE|DOCKER_NETWORK|"
                 r"STACK_KIT_DOCKER_NETWORK|INFRA_SLUG)$")
#: field -> where its value lives now
FIELDS = {"stack.networkName": "derived: {project}-net (the manifest `project` names it)",
          "stack.deployBaseSecretsModule": "gone: a target places every service by the layout",
          "stackDeploy": "gone: `deploy all` orders the modules by catalogs.roles deployOrder"}


def _dig(data: Any, dotted: str) -> Any:
    cur = data
    for part in dotted.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def folders(secrets_root: Path, manifest: dict[str, Any]) -> list[str]:
    out = {str(c.get("secretsModule") or m) for m, c in (manifest.get("modules") or {}).items() if isinstance(c, dict)}
    out.add("infra")
    if secrets_root.is_dir():
        out |= {p.name for p in secrets_root.iterdir() if p.is_dir()}
    return sorted(out)


def env_files(secrets_root: Path, manifest: dict[str, Any]) -> list[Path]:
    """Every env file of the secrets folders, the legacy ones included."""
    out = [secrets_root / "deploy.env"]
    for f in folders(secrets_root, manifest):
        d = secrets_root / f
        out += sorted(p for p in d.glob(".env*") if p.is_file() and not p.name.endswith(".example")) if d.is_dir() else []
    return [p for p in out if p.is_file()]


def found(secrets_root: Path, manifest: dict[str, Any]) -> dict[str, list[str]]:
    """{where: [what]} -- every legacy file, key (by NAME, never its value) and field present."""
    out: dict[str, list[str]] = {}
    for path in env_files(secrets_root, manifest):
        rel = path.relative_to(secrets_root).as_posix()
        if path.name in FILES:
            out.setdefault(rel, []).append("the file itself")
        keys = sorted(k for k in envfile.parse(path) if KEY.match(k))
        if keys:
            out.setdefault(rel, []).extend(keys)
    for field, home in FIELDS.items():
        if _dig(manifest, field) is not None:
            out.setdefault(identity.MANIFEST_FILENAME, []).append(f"{field} ({home})")
    for role in ((manifest.get("catalogs") or {}).get("roles") or []):
        if isinstance(role, dict) and role.get("serviceOverride"):
            out.setdefault(identity.MANIFEST_FILENAME, []).append(
                f"catalogs.roles[{role.get('id')}].serviceOverride (a service id is the role's primaryService)")
    return out


def problems(root: Path, secrets_root: Path, manifest: dict[str, Any]) -> list[str]:
    out = [f"{where}: {', '.join(what)} -- a former home (removed in 2.0.0); run `{identity.KIT_NAME} migrate "
           f"--apply` to carry it into the manifest and the targets file" for where, what in found(secrets_root, manifest).items()]
    out += [f"{p} -- run `{identity.KIT_NAME} migrate --apply`" for p in identity.legacy_names_in(root, manifest)]
    return out
