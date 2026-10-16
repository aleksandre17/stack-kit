"""The context: what the manifest says, as one flat map (ADR-001 decision 2; split from the
resolver in amendment 13).

The one resolver (ADR-001 decision 2).

Before this module the same resolution lived three times -- Python, `lib/project.sh` + `lib/env.sh`
and `lib/project.ps1` + `lib/env.ps1` -- and the copies had drifted apart where nobody could see it:
bash inferred a module's role from two driver names spelled inline while Python read the registry;
PowerShell fell back to ANY field of the scaffold template, so a host module named like a template
sample silently inherited the sample's values; a module env value was the FIRST file's in bash and
the LAST file's in PowerShell; a deploy value preferred the file in bash and the process environment
in PowerShell; each runtime searched for the project in its own order.

Here each rule has one home, and the shells hold none: they ask this module, through
`lib/resolve_cli.py`, and read the answer.

Two kinds of answer, kept apart on purpose:

* **The context** -- what the MANIFEST says: the project root, every scalar field and list, the
  declared convention defaults, the modules with their type, role, paths and credentials, roles,
  types, aliases. A pure function of the manifest and the kit, so a shell may cache it for its
  lifetime. It is FLAT: one map of `kind:key` to text, identical in every runtime, so parity
  between runtimes is a comparison of two maps.
* **The environment's answers** -- env files, env values, slugs, the server base, deploy paths.
  They read env files and the process environment, which change during a run, so they are asked
  for each time and never cached.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterator

from lib import envfile, identity
from lib.credentials import module_credentials
from lib.manifest_defaults import flatten_defaults
from lib.modules import (
    driver_command_runtimes,
    driver_commands,
    driver_default_role,
    driver_delivery,
    driver_home,
    driver_package_scripts,
    driver_registry,
    infer_cli_aliases,
    module_role,
)
from lib.project_context import find_project_root, load_manifest

KIT_ROOT = Path(__file__).resolve().parents[2]



# ── the context: what the manifest says ─────────────────────────────────────


def _leaves(data: dict[str, Any], prefix: str = "") -> Iterator[tuple[str, Any]]:
    for key, value in data.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _leaves(value, dotted + ".")
        else:
            yield dotted, value


def _text(value: Any) -> str:
    return str(value)


def _normalized(manifest: dict[str, Any]) -> dict[str, Any]:
    """The manifest with every field the kit renamed under its current name (the former noticed)."""
    return identity.with_current_fields(manifest)


def _lines(items) -> str:
    return "\n".join(str(i) for i in items)


def _root(start: Path | None) -> Path | None:
    try:
        return find_project_root(start)
    except FileNotFoundError:
        return None


def context(start: Path | None = None) -> dict[str, str]:
    """Everything the manifest says, as one flat map of `kind:key` to text.

    Kinds: `identity:` the kit's declared names; `root`, `manifest`, `kitRoot`, `packageRoot`,
    `monorepoRoot`, `secretsRoot`; `path:` derived project paths; `field:` every scalar leaf;
    `list:` every list of scalars (newline-joined); `default:` the declared convention defaults;
    `feature:` true/false; `module:<id>:<attr>`; `modules`, `role:<role>`, `type:<type>`,
    `secretsFolders` (newline-joined ids); `alias:<alias>`.
    """
    out: dict[str, str] = {f"identity:{k}": v for k, v in identity._DECLARATION.items()
                           if isinstance(v, str) and not k.startswith("$")}
    out["kitRoot"] = str(KIT_ROOT)
    out["packageRoot"] = os.environ.get("OPS_PACKAGE_ROOT") or str(KIT_ROOT)
    for dotted, value in flatten_defaults().items():
        out[f"default:{dotted}"] = value
    out.update(_drivers())
    root = _root(start)
    if root is None:
        return out
    found = identity.find_manifest(root)
    manifest = _normalized(load_manifest(root))
    out["root"] = str(root)
    out["manifest"] = str(found) if found else ""
    out["monorepoRoot"] = monorepo_root(root)

    for dotted, value in _leaves(manifest):
        if isinstance(value, list):
            if all(not isinstance(i, (dict, list)) for i in value):
                out[f"list:{dotted}"] = _lines(str(i).strip() for i in value
                                               if i is not None and str(i).strip())
        elif value is not None:
            out[f"field:{dotted}"] = _text(value)

    def field(dotted: str) -> str:
        return out.get(f"field:{dotted}") or out.get(f"default:{dotted}", "")

    secrets_root = root / field("secrets")
    out["secretsRoot"] = str(secrets_root)
    out["secretsRel"] = field("secrets").replace("\\", "/")
    out["path:stackComposeDir"] = str(root / field("stack.composeDir"))
    out["path:infraComposeDir"] = str(root / (field("stack.infraComposeDir") or "ops/compose/infra"))
    out["path:composeCatalog"] = str(root / field("compose.catalog"))
    out["path:syncModules"] = str(root / field("compose.syncModules"))

    for name, value in (manifest.get("features") or {}).items():
        out[f"feature:{name}"] = "true" if value is True else "false"

    modules = {str(k): v for k, v in (manifest.get("modules") or {}).items() if isinstance(v, dict)}
    roles: dict[str, list[str]] = {}
    types: dict[str, list[str]] = {}
    folders: list[str] = []
    for mid, cfg in modules.items():
        typ = str(cfg.get("type") or "")
        role = module_role(manifest, mid)
        folder = str(cfg.get("secretsModule") or mid)
        out[f"module:{mid}:type"] = typ
        out[f"module:{mid}:role"] = role
        out[f"module:{mid}:path"] = str(root / cfg["path"]) if cfg.get("path") else ""
        out[f"module:{mid}:secretsFolder"] = folder
        out[f"module:{mid}:secretsDir"] = str(secrets_root / folder)
        out[f"module:{mid}:credentials"] = _lines(
            "\t".join((c["file"], c["mount"], c.get("envVar", ""))) for c in module_credentials(manifest, mid))
        out[f"module:{mid}:driverRoot"] = str(driver_home(typ)) if typ else ""
        out[f"module:{mid}:json"] = json.dumps(cfg, sort_keys=True)
        if role:
            roles.setdefault(role, []).append(mid)
        if typ:
            types.setdefault(typ, []).append(mid)
        if folder not in folders:
            folders.append(folder)
    out["modules"] = _lines(modules)
    out.update({f"role:{r}": _lines(ids) for r, ids in roles.items()})
    out.update({f"type:{t}": _lines(ids) for t, ids in types.items()})
    out["secretsFolders"] = _lines(folders)
    out.update({f"alias:{a}": mid for a, mid in infer_cli_aliases(manifest).items()})
    return out


def _drivers() -> dict[str, str]:
    """What each registered driver declares: its commands (and their scripts), its default role,
    its watch tasks, its host-run script, its layout simulator -- the registry, read once."""
    out: dict[str, str] = {}
    registry = {k: v for k, v in driver_registry().items() if isinstance(v, dict)}
    out["drivers"] = _lines(sorted(registry))
    from lib import catalogs
    from lib.modules import lifecycle_steps, optional_steps

    out["lifecycle:steps"] = _lines(lifecycle_steps())
    out["lifecycle:optional"] = _lines(optional_steps())
    out["environments"] = _lines(catalogs.ids("environments"))
    out["environment:run"] = catalogs.default_environment("run")
    out["environment:deploy"] = catalogs.default_environment("deploy")
    out["roles"] = _lines(catalogs.ids("roles"))
    out["roles:bootOrder"] = _lines(catalogs.ordered("roles", "bootOrder"))
    from lib.modules import script_runtimes

    runtimes = script_runtimes()
    out["runtimes"] = _lines(runtimes)
    for rid, spec in runtimes.items():
        out[f"runtime:{rid}:match"] = _lines(spec.get("match") or [])
        if spec.get("inSession"):
            out[f"runtime:{rid}:inSession"] = "true"
        if spec.get("argv"):
            out[f"runtime:{rid}:argv"] = json.dumps(spec["argv"])
    for typ, entry in registry.items():
        home = driver_home(typ)
        commands = driver_commands(typ)
        out[f"driver:{typ}:commands"] = _lines(sorted(commands))
        for name, path in commands.items():
            out[f"driver:{typ}:command:{name}"] = str(path)
        for name, runtime in driver_command_runtimes(typ).items():
            out[f"driver:{typ}:commandRuntime:{name}"] = runtime
        out[f"driver:{typ}:defaultRole"] = driver_default_role(typ)
        for name, argv in (entry.get("tasks") or {}).items():
            if isinstance(argv, list):
                out[f"driver:{typ}:task:{name}"] = _lines(argv)
        for step, name in driver_package_scripts(typ).items():
            out[f"driver:{typ}:packageScript:{step}"] = name
        script = (entry.get("hybrid") or {}).get("script")
        if script:
            out[f"driver:{typ}:hybridScript"] = str(home / script)
        ladder = driver_delivery(typ)
        out[f"driver:{typ}:rungs"] = _lines(ladder)
        for rung, how in ladder.items():
            out[f"driver:{typ}:rung:{rung}"] = json.dumps(how, sort_keys=True)
        for word, rewrite in (entry.get("operands") or {}).items():
            if isinstance(rewrite, dict) and isinstance(rewrite.get("to"), list):
                out[f"driver:{typ}:operand:{word}"] = json.dumps(rewrite, sort_keys=True)
    return out


def monorepo_root(root: Path) -> str:
    return (os.environ.get("OPS_MONOREPO_ROOT") or identity.env("MONOREPO_ROOT") or str(root))


def slugify(text: str) -> str:
    from lib.naming import slugify as one

    return one(text)
