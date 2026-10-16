"""Single source of convention defaults: the scaffold manifest (not inline dicts)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from lib.identity import MANIFEST_FILENAME

_PKG = Path(__file__).resolve().parents[1]
_SCAFFOLD = _PKG / "scaffold" / MANIFEST_FILENAME


@lru_cache(maxsize=1)
def load_scaffold_manifest() -> dict[str, Any]:
    if not _SCAFFOLD.is_file():
        return {}
    return json.loads(_SCAFFOLD.read_text(encoding="utf-8"))


def read_nested(data: dict[str, Any], dotted: str, default: str = "") -> str:
    # A field renamed by the kit is still read under its old name, with a notice (ADR-001).
    from lib.identity import manifest_field

    cur = manifest_field(data, dotted)
    return str(cur) if cur is not None else default


@lru_cache(maxsize=1)
def flatten_defaults() -> dict[str, str]:
    m = load_scaffold_manifest()
    # DECLARED, not "every field of the template": the template also holds sample modules, aliases
    # and stores, and a host module named like a sample would silently inherit the sample's values.
    out = {dotted: read_nested(m, dotted) for dotted in CONVENTION_DEFAULTS}
    return {k: v for k, v in out.items() if v}


#: The fields whose absence means "the convention" -- the only template fields read as defaults.
CONVENTION_DEFAULTS = (
    "package",
    "secrets",
    "compose.catalog",
    "compose.syncModules",
    "stack.composeDir",
    "stack.infraComposeDir",
    "stack.networkName",
    "adapters.gcp.credentialsFile",
    "adapters.gcp.containerMount",
    "adapters.nginx.template",
    "adapters.nginx.output",
    "adapters.nginx.envExample",
    "adapters.nginx.env",
    "adapters.embed.envExample",
    "ci.integration",
    "ci.prepareEnv",
    "ci.waitHealth",
    "ci.waitStackHealth",
    "vscode.folder",
    "vscode.cliScript",
)


#: The CI scripts the kit itself runs, by field. A host's further scripts are `ci.scripts`, by its
#: own names -- the kit checks each exists and names none of them.
CI_SCRIPT_FIELDS = ("integration", "prepareEnv", "waitHealth", "waitStackHealth")


def declared_ci_scripts(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    """(field, path) for every CI script the manifest declares explicitly, kit-run and host-named."""
    ci = manifest.get("ci") or {}
    if not isinstance(ci, dict):
        return []
    out = [(f"ci.{key}", str(ci[key])) for key in CI_SCRIPT_FIELDS if ci.get(key)]
    scripts = ci.get("scripts") or {}
    if isinstance(scripts, dict):
        out += [(f"ci.scripts.{name}", str(rel)) for name, rel in scripts.items() if rel]
    return out


def default_field(dotted: str) -> str:
    return flatten_defaults().get(dotted, "")


def cli_aliases(manifest: dict[str, Any] | None = None) -> dict[str, str]:
    from lib.modules import infer_cli_aliases

    m = manifest if manifest is not None else load_scaffold_manifest()
    return infer_cli_aliases(m)


def resolve_cli_alias(alias: str, manifest: dict[str, Any] | None = None) -> str | None:
    from lib.modules import resolve_cli_alias as _resolve

    m = manifest if manifest is not None else load_scaffold_manifest()
    return _resolve(alias, m)


def module_ids(manifest: dict[str, Any]) -> list[str]:
    return [str(k) for k in (manifest.get("modules") or {})]


def module_by_type(manifest: dict[str, Any], driver_type: str) -> str | None:
    from lib.modules import module_by_type as _one

    return _one(manifest, driver_type, 0)


def legacy_root_discovery_enabled() -> bool:
    from lib.project_root import legacy_root_discovery_enabled as one

    return one()