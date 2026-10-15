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
    out: dict[str, str] = {
        "package": read_nested(m, "package"),
        "secrets": read_nested(m, "secrets"),
        "compose.catalog": read_nested(m, "compose.catalog"),
        "compose.syncModules": read_nested(m, "compose.syncModules"),
        "stack.composeDir": read_nested(m, "stack.composeDir"),
        "stack.infraComposeDir": read_nested(m, "stack.infraComposeDir"),
        "stack.networkName": read_nested(m, "stack.networkName"),
    }
    return {k: v for k, v in out.items() if v}


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
    from lib.identity import env

    v = env("LEGACY_ROOT_DISCOVERY").strip().lower()
    return v in ("1", "true", "yes", "on")
