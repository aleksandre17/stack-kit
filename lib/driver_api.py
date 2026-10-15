#!/usr/bin/env python3
"""
Driver resolution — single source for manifest + drivers/registry.json.
Used by Bash (drivers.sh), stack-remote, and optionally PowerShell wrappers.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from lib.identity import MANIFEST_FILENAME, env, find_manifest


def _root() -> Path:
    r = env("PROJECT_ROOT").strip()
    if not r:
        raise SystemExit("STACK_KIT_PROJECT_ROOT not set")
    return Path(r)


def _pkg() -> Path:
    p = env("KIT_ROOT").strip()
    if not p:
        raise SystemExit("STACK_KIT_KIT_ROOT not set")
    return Path(p)


def load_manifest(root: Path | None = None) -> dict[str, Any]:
    root = root or _root()
    path = find_manifest(root)
    if path is None:
        raise SystemExit(f"{MANIFEST_FILENAME} not found under {root}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_registry(pkg: Path | None = None) -> dict[str, Any]:
    pkg = pkg or _pkg()
    path = pkg / "drivers" / "registry.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def module_ids(manifest: dict[str, Any]) -> list[str]:
    return list(manifest.get("modules", {}).keys())


def module_entry(manifest: dict[str, Any], module_id: str) -> dict[str, Any]:
    mods = manifest.get("modules", {})
    if module_id not in mods:
        raise SystemExit(f"Unknown module '{module_id}' — add modules.{module_id} in {MANIFEST_FILENAME}")
    return mods[module_id]


def module_type(manifest: dict[str, Any], module_id: str) -> str:
    entry = module_entry(manifest, module_id)
    typ = (entry.get("type") or "").strip()
    if not typ:
        raise SystemExit(
            f"modules.{module_id}.type is required (driver id from drivers/registry.json, e.g. java-boot, node-api)"
        )
    return typ


def registry_entry(registry: dict[str, Any], typ: str) -> dict[str, Any]:
    if typ not in registry:
        known = ", ".join(sorted(registry.keys()))
        raise SystemExit(
            f"Unknown driver type '{typ}' — implement kits/stack-kit/drivers/{typ}/ and register it. Known: {known}"
        )
    return registry[typ]


def driver_capabilities(registry: dict[str, Any], typ: str) -> list[str]:
    entry = registry_entry(registry, typ)
    return sorted(entry.get("commands", {}).keys())


def command_path(root: Path, pkg: Path, manifest: dict[str, Any], registry: dict[str, Any], module_id: str, command: str) -> Path:
    typ = module_type(manifest, module_id)
    entry = registry_entry(registry, typ)
    rel = entry.get("commands", {}).get(command)
    if not rel:
        caps = ", ".join(driver_capabilities(registry, typ))
        raise SystemExit(f"Driver '{typ}' has no command '{command}' (available: {caps})")
    path = pkg / "drivers" / typ / rel
    if not path.is_file():
        raise SystemExit(f"Driver script missing: {path}")
    return path


def cli_aliases(manifest: dict[str, Any]) -> dict[str, str]:
    from lib.modules import infer_cli_aliases

    return infer_cli_aliases(manifest)


def resolve_alias(manifest: dict[str, Any], alias: str) -> str | None:
    from lib.modules import resolve_cli_alias as _resolve

    return _resolve(alias, manifest)


def resolve_module_id(manifest: dict[str, Any], module_or_alias: str) -> str:
    target = resolve_alias(manifest, module_or_alias)
    if not target:
        raise SystemExit(
            f"Unknown module or alias '{module_or_alias}' — add modules.{module_or_alias} or cli.aliases in {MANIFEST_FILENAME}"
        )
    return target


def default_stack_deploy_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    from lib.modules import default_stack_deploy_steps as _default

    return _default(manifest)


def stack_deploy_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    from lib.stack_deploy import stack_deploy_steps as _steps

    return _steps(manifest)


def substitute_stack_args(args: list[Any], environment: str) -> list[str]:
    out: list[str] = []
    for a in args:
        s = str(a)
        out.append(s.replace("{environment}", environment).replace("{env}", environment))
    return out


def _cmd_type(root: Path, pkg: Path, module_id: str) -> None:
    m = load_manifest(root)
    print(module_type(m, resolve_module_id(m, module_id)))


def _cmd_path(root: Path, pkg: Path, module_id: str, command: str) -> None:
    m = load_manifest(root)
    r = load_registry(pkg)
    print(command_path(root, pkg, m, r, resolve_module_id(m, module_id), command))


def _cmd_caps(root: Path, pkg: Path, module_id: str) -> None:
    m = load_manifest(root)
    r = load_registry(pkg)
    typ = module_type(m, resolve_module_id(m, module_id))
    print(" ".join(driver_capabilities(r, typ)))


def _cmd_alias(root: Path, alias: str) -> None:
    m = load_manifest(root)
    target = resolve_alias(m, alias)
    if not target:
        raise SystemExit(f"Unknown CLI alias '{alias}'")
    print(target)


def _cmd_stack_steps(root: Path, env: str) -> None:
    m = load_manifest(root)
    for step in stack_deploy_steps(m):
        mod = step["module"]
        cmd = step["command"]
        args = substitute_stack_args(step.get("args", []), env)
        line = "\t".join([mod, cmd, *args])
        print(line)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: driver_api.py <type|path|caps|alias|stack-steps> ...")
    root = _root()
    pkg = _pkg()
    op = sys.argv[1]
    if op == "type":
        _cmd_type(root, pkg, sys.argv[2])
    elif op == "path":
        _cmd_path(root, pkg, sys.argv[2], sys.argv[3])
    elif op == "caps":
        _cmd_caps(root, pkg, sys.argv[2])
    elif op == "alias":
        _cmd_alias(root, sys.argv[2])
    elif op == "stack-steps":
        env = "prod"
        if "--dev" in sys.argv:
            env = "dev"
        _cmd_stack_steps(root, env)
    elif op == "list-types":
        r = load_registry(pkg)
        for tid, ent in sorted(r.items()):
            roles = ",".join(ent.get("roles", ["any"]))
            print(f"{tid}\t{roles}\t{ent.get('label', '')}")
    else:
        raise SystemExit(f"unknown op: {op}")


if __name__ == "__main__":
    main()
