"""Manifest-driven project paths — package boundary (no app brands or fixed tree)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.credentials import global_gcp_credentials, module_credentials
from lib.identity import (
    LEGACY_VENDOR_DIRS,
    MANIFEST_FILENAME,
    VENDOR_DIRS,
    env,
    env_name,
    find_manifest,
    has_manifest,
)
from lib.manifest_defaults import (
    default_field,
    legacy_root_discovery_enabled,
    load_scaffold_manifest,
    read_nested,
    resolve_cli_alias,
)
from lib.modules import (
    infer_cli_aliases,
    module_by_role,
    module_by_type,
    module_ids,
    modules_by_role,
    modules_by_type,
    module_role,
)


def _read_nested(data: dict[str, Any], dotted: str, default: str = "") -> str:
    return read_nested(data, dotted, default)


def find_project_root(start: Path | None = None) -> Path:
    """The ONE discovery every runtime uses (ADR-001 decision 2).

    An explicit `start` is walked up from. Otherwise: the declared root (`<prefix>_PROJECT_ROOT`)
    is authoritative -- an operator's explicit answer is never overridden by a guess; then the
    working directory and its parents; then, only when asked for, pre-v2 trees. (Not the
    directories above the running kit: a kit checked out inside some other repository would then
    resolve that repository from anywhere -- a guess, made silently.)
    """
    if start is None and env("PROJECT_ROOT"):
        return Path(env("PROJECT_ROOT")).resolve()
    start = (start or Path.cwd()).resolve()
    for p in [start, *start.parents]:
        if has_manifest(p):
            return p
    if legacy_root_discovery_enabled():
        for p in [start, *start.parents]:
            if (p / "ops" / "config").is_dir() or (p / "secrets").is_dir():
                if any((p / d).is_dir() for d in (*VENDOR_DIRS, *LEGACY_VENDOR_DIRS)):
                    return p
    raise FileNotFoundError(
        f"project root not found ({MANIFEST_FILENAME} required; "
        f"set {env_name('LEGACY_ROOT_DISCOVERY')}=1 for pre-v2 trees)"
    )


def load_manifest(root: Path) -> dict[str, Any]:
    mf = find_manifest(root)
    if mf is not None:
        return json.loads(mf.read_text(encoding="utf-8"))
    return {}


@dataclass(frozen=True)
class ProjectContext:
    root: Path
    manifest: dict[str, Any]

    @classmethod
    def discover(cls, start: Path | None = None) -> ProjectContext:
        root = find_project_root(start)
        return cls(root=root, manifest=load_manifest(root))

    @classmethod
    def scaffold_defaults(cls) -> dict[str, Any]:
        return load_scaffold_manifest()

    def field(self, dotted: str, default: str | None = None) -> str:
        d = default if default is not None else default_field(dotted)
        return _read_nested(self.manifest, dotted, d)

    def resolve_alias(self, alias: str) -> str | None:
        return resolve_cli_alias(alias, self.manifest)

    def cli_aliases(self) -> dict[str, str]:
        return infer_cli_aliases(self.manifest)

    def module_id_for_role(self, role: str, index: int = 0) -> str | None:
        return module_by_role(self.manifest, role, index)

    def module_ids_for_role(self, role: str) -> list[str]:
        return modules_by_role(self.manifest, role)

    def module_id_for_type(self, driver_type: str, index: int = 0) -> str | None:
        return module_by_type(self.manifest, driver_type, index)

    def module_ids_for_type(self, driver_type: str) -> list[str]:
        return modules_by_type(self.manifest, driver_type)

    def get_module_role(self, module_id: str) -> str:
        return module_role(self.manifest, module_id)

    def list_module_ids(self) -> list[str]:
        return module_ids(self.manifest)

    @property
    def secrets_root(self) -> Path:
        return self.root / self.field("secrets")

    @property
    def package_root(self) -> Path:
        return (self.root / self.field("package")).resolve()

    def module_path(self, module_id: str) -> Path:
        rel = _read_nested(self.manifest, f"modules.{module_id}.path", "")
        if not rel:
            raise KeyError(f"manifest modules.{module_id}.path missing")
        return self.root / rel

    def secrets_module_dir(self, module_id: str) -> Path:
        sm = _read_nested(self.manifest, f"modules.{module_id}.secretsModule", module_id)
        return self.secrets_root / sm

    def secrets_folder_path(self, secrets_folder: str) -> Path:
        """Path under secrets root by folder name (modules.*.secretsModule)."""
        return self.secrets_root / secrets_folder

    def secrets_module_dirs(self) -> dict[str, Path]:
        mods = self.manifest.get("modules") or {}
        out: dict[str, Path] = {}
        for mid, cfg in mods.items():
            if isinstance(cfg, dict):
                sm = str(cfg.get("secretsModule", mid))
                out[mid] = self.secrets_root / sm
        return out

    @property
    def stack_compose_dir(self) -> Path:
        return self.root / self.field("stack.composeDir")

    @property
    def catalog_path(self) -> Path:
        return self.root / self.field("compose.catalog")

    def feature_enabled(self, name: str) -> bool:
        feats = self.manifest.get("features") or {}
        val = feats.get(name)
        if isinstance(val, bool):
            return val
        return False

    def gcp_credentials_filename(self) -> str | None:
        creds = global_gcp_credentials(self.manifest)
        return creds[0]["file"] if creds else None

    def module_credentials_list(self, module_id: str) -> list[dict[str, str]]:
        return module_credentials(self.manifest, module_id)

    def secrets_module_folder(self, module_id: str) -> str:
        cfg = (self.manifest.get("modules") or {}).get(module_id)
        if isinstance(cfg, dict) and cfg.get("secretsModule"):
            return str(cfg["secretsModule"])
        return module_id

    def list_secrets_module_folders(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for mid in (self.manifest.get("modules") or {}):
            folder = self.secrets_module_folder(str(mid))
            if folder not in seen:
                seen.add(folder)
                out.append(folder)
        return out

    def compose_service_names(self) -> dict[str, Any]:
        from lib.compose_identity import compose_service_names as resolve_names

        return resolve_names(self.manifest, self.root)
