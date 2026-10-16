#!/usr/bin/env python3
"""Generate .vscode/launch.json and tasks.json from the project manifest (manifest-driven).

A module's launch configuration is its driver's DECLARATION (`vscode` in its registry entry), never
a builder here (ADR-001 amendment 16): `launch` is the configuration as data, every string rendered
by the kit's one template grammar (lib/templating.py) over the module's manifest entry and these
values -- `{module}`, `{path}` (the module's folder under `${workspaceFolder}`), `{label}`,
`{script}`, `{envFile}` (the module's run-default env file) and each value the driver declares under
`values`. A value is the first of its sources that yields one:

    {"field": "a.b"}                 the module's manifest entry; `"exists": true` -- a module file,
                                     and a declared one that is missing is an absence, never a fallthrough
    {"driver": "a.b"}                the driver's own registry entry
    {"value": "x"}                   a literal
    {"glob": "p/**/*.x", ...}        module files: `single` (exactly one, else none) or the shortest
                                     path; `as: "dotted"` with `under` gives the dotted name below it
    {"file": ["a", "b"], "capture": "re"}  the first group of `re` in the first of the files that has it

`label` is the module's `debug.label`, else the driver's `label` rendered, else the module id. A key
listed in `optional` is dropped when it has no value; any other missing value is an honest absence
of the launch, not a guess. The kit names no debugger and no tool.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib import templating
from lib.manifest_defaults import default_field, read_nested
from lib.modules import driver_package_scripts, driver_registry, infer_cli_aliases, modules_by_role
from lib.project_context import ProjectContext


def _posix_rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _stack_kit_script_rel(ctx: ProjectContext) -> str:
    custom = read_nested(ctx.manifest, "vscode.cliScript", "")
    if custom:
        return custom.replace("\\", "/")
    return default_field("vscode.cliScript") or "tools/stack-kit.ps1"


def _stack_infra_services(ctx: ProjectContext) -> list[str]:
    stack = ctx.manifest.get("stack") if isinstance(ctx.manifest.get("stack"), dict) else {}
    infra = stack.get("infra") if isinstance(stack.get("infra"), dict) else {}
    services = infra.get("services")
    if isinstance(services, list):
        return [str(s) for s in services if s]
    return []


def _vscode_hybrid_cfg(ctx: ProjectContext) -> dict[str, Any]:
    vscode = ctx.manifest.get("vscode")
    if isinstance(vscode, dict):
        hybrid = vscode.get("hybrid")
        if isinstance(hybrid, dict):
            return hybrid
    return {}


def _pick_module_by_role(ctx: ProjectContext, role: str, override: str = "") -> str | None:
    if override and read_nested(ctx.manifest, f"modules.{override}.path", ""):
        return override
    ids = modules_by_role(ctx.manifest, role)
    return ids[0] if ids else None


TUNNEL_TASK_LABEL = "stack-kit: infra tunnel"
TUNNEL_READY_PATTERN = "Set INFRA_HOST=127.0.0.1"


def _infra_tunnel_task(ctx: ProjectContext) -> dict[str, Any]:
    gs = _stack_kit_script_rel(ctx)
    wf = "${workspaceFolder}"
    return {
        "label": TUNNEL_TASK_LABEL,
        "type": "shell",
        "command": "powershell",
        "args": [
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            f"{wf}/{gs}",
            "infra",
            "tunnel",
        ],
        "options": {"cwd": wf},
        "isBackground": True,
        "presentation": {"reveal": "silent", "panel": "dedicated", "focus": False},
        "problemMatcher": {
            "owner": "stack-kit-infra-tunnel",
            "pattern": {"regexp": "^.*$"},
            "background": {
                "activeOnStart": True,
                "beginsPattern": "\\[infra\\]",
                "endsPattern": TUNNEL_READY_PATTERN.replace(".", "\\."),
            },
        },
    }


def _module_entry(ctx: ProjectContext, module_id: str) -> dict[str, Any]:
    cfg = (ctx.manifest.get("modules") or {}).get(module_id) or {}
    return cfg if isinstance(cfg, dict) else {}


def _module_debug_cfg(manifest: dict[str, Any], module_id: str) -> dict[str, Any]:
    cfg = (manifest.get("modules") or {}).get(module_id) or {}
    dbg = cfg.get("debug") if isinstance(cfg, dict) else None
    return dbg if isinstance(dbg, dict) else {}


def _driver_vscode(driver_id: str) -> dict[str, Any]:
    entry = driver_registry().get(driver_id) or {}
    vs = entry.get("vscode")
    return vs if isinstance(vs, dict) else {}


class _Absent(Exception):
    """A declared value whose authoritative source is missing: no fallthrough to the next source."""


def _source(src: dict[str, Any], module_dir: Path, module: dict[str, Any], driver: dict[str, Any]) -> str | None:
    if "value" in src:
        return str(src["value"])
    if "field" in src or "driver" in src:
        found = templating.lookup(module, str(src["field"])) if "field" in src else templating.lookup(driver, str(src["driver"]))
        if found in (None, ""):
            return None
        if src.get("exists") and not (module_dir / str(found)).is_file():
            raise _Absent(str(src.get("field")))
        return str(found)
    if "glob" in src:
        hits = sorted((p for p in module_dir.glob(str(src["glob"])) if p.is_file()),
                      key=lambda p: (len(p.relative_to(module_dir).parts), p.name))
        if src.get("single"):
            hits = hits if len(hits) == 1 else []
        if not hits:
            return None
        rel = hits[0].relative_to(module_dir)
        if src.get("as") == "dotted":
            return ".".join(rel.relative_to(str(src.get("under") or ".")).with_suffix("").parts)
        return rel.as_posix()
    if "file" in src:
        names = src["file"] if isinstance(src["file"], list) else [src["file"]]
        for name in names:
            f = module_dir / str(name)
            text = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""
            m = re.search(str(src.get("capture") or "(.+)"), text)
            if m:
                return m.group(1)
        return None
    raise ValueError(f"vscode.values: a source is one of value, field, driver, glob, file -- not {sorted(src)}")


def _values(declared: dict[str, Any], module_dir: Path, module: dict[str, Any], driver: dict[str, Any]) -> dict[str, str]:
    """Each declared value: the first of its sources that yields one (an absent value is left out)."""
    out: dict[str, str] = {}
    for name, sources in declared.items():
        try:
            for src in sources if isinstance(sources, list) else [sources]:
                found = _source(src, module_dir, module, driver)
                if found not in (None, ""):
                    out[str(name)] = found
                    break
        except _Absent:
            continue
    return out


def build_launch(ctx: ProjectContext, module_id: str) -> dict[str, Any] | None:
    """The module's launch configuration as its driver declares it (`vscode.launch` data), or None:
    a driver that declares none, or a required value with no source, is an honest absence."""
    module = _module_entry(ctx, module_id)
    typ = str(module.get("type") or "")
    driver = driver_registry().get(typ) or {}
    vs = _driver_vscode(typ)
    template = vs.get("launch")
    if not isinstance(template, dict):
        return None
    module_dir = ctx.module_path(module_id)
    dbg = _module_debug_cfg(ctx.manifest, module_id)
    env_file = dbg.get("envFile")
    env_rel = str(env_file).replace("\\", "/") if env_file else _posix_rel(ctx.root, ctx.secrets_module_dir(module_id) / ".env.dev")
    extra: dict[str, str] = {
        "module": module_id,
        "path": "${workspaceFolder}/" + _posix_rel(ctx.root, module_dir),
        "script": str(dbg.get("npmScript") or dbg.get("script") or driver_package_scripts(typ).get("start") or ""),
        "envFile": "${workspaceFolder}/" + env_rel,
    }
    declared = vs.get("values") if isinstance(vs.get("values"), dict) else {}
    extra.update(_values(declared, module_dir, module, driver))
    try:
        label = str(dbg.get("label") or (templating.render(str(vs["label"]), module, extra) if vs.get("label") else module_id))
    except ValueError:
        return None
    extra["label"] = label
    optional = {str(k) for k in vs.get("optional") or []}
    cfg: dict[str, Any] = {}
    for key, value in template.items():
        try:
            cfg[key] = templating.render_tree(value, module, extra)
        except ValueError:
            if key not in optional:
                return None
    cfg.setdefault("name", label)
    return cfg


def _driver_watch_tasks(driver_id: str) -> dict[str, list[str]]:
    """Tasks a driver declares (`tasks`), and -- when it declares remote dev (`dev`) -- its dev watch."""
    entry = driver_registry().get(driver_id) or {}
    tasks = entry.get("tasks") if isinstance(entry.get("tasks"), dict) else {}
    out: dict[str, list[str]] = {str(n): [str(a) for a in argv] for n, argv in tasks.items() if isinstance(argv, list) and argv}
    if entry.get("dev"):
        out.setdefault("devWatch", ["dev", "watch"])
    return out


def _kit_launch(ctx: ProjectContext, name: str, command: str) -> dict[str, Any]:
    """A launch that runs one kit command in the debug terminal; its type is the manifest's
    `vscode.terminalLaunchType`, else the convention's (the scaffold manifest)."""
    kind = read_nested(ctx.manifest, "vscode.terminalLaunchType", "") or default_field("vscode.terminalLaunchType")
    return {"name": name, "type": kind, "request": "launch", "command": command, "cwd": "${workspaceFolder}"}


def build_launch_json(ctx: ProjectContext) -> dict[str, Any]:
    from lib import catalogs

    compound_roles = catalogs.flagged("roles", "launchCompound", ctx.manifest)
    boot = _boot_order(ctx)
    aliases = infer_cli_aliases(ctx.manifest)
    configs: list[dict[str, Any]] = []
    launch_of: dict[str, str] = {}
    by_role: dict[str, list[str]] = {}

    for mid in ctx.list_module_ids():
        cfg = build_launch(ctx, mid)
        if not cfg:
            continue  # the driver declares no launch, or a value it needs has no source
        configs.append(cfg)
        launch_of[mid] = cfg["name"]
        role = read_nested(ctx.manifest, f"modules.{mid}.role", "")
        if role in compound_roles:
            by_role.setdefault(role, []).append(cfg["name"])

    gs = _stack_kit_script_rel(ctx)
    run = f'powershell -ExecutionPolicy Bypass -File "${{workspaceFolder}}/{gs}"'
    configs.append(_kit_launch(ctx, "stack-kit: stack (compose dev)", f"{run} stack up -d --build"))
    for alias, _target in sorted(aliases.items()):
        configs.append(_kit_launch(ctx, f"stack-kit: {alias} check", f"{run} {alias} check"))

    out: dict[str, Any] = {"version": "0.2.0", "configurations": configs}
    if sum(len(v) for v in by_role.values()) >= 2:
        # the first launch of each compounded role, in the roles catalog's boot order
        order = sorted(by_role, key=lambda r: (boot.get(r, len(boot) + 1), r))
        out["compounds"] = [{"name": "Full stack (local)", "configurations": [by_role[r][0] for r in order],
                             "stopAll": True}]

    if _stack_infra_services(ctx):
        hybrid = _vscode_hybrid_cfg(ctx)
        api_id = _pick_module_by_role(ctx, "api", str(hybrid.get("apiModule") or ""))
        ui_id = _pick_module_by_role(ctx, "ui", str(hybrid.get("uiModule") or ""))
        if api_id in launch_of and ui_id in launch_of:
            out.setdefault("compounds", []).append({
                "name": str(hybrid.get("compoundName") or "Hybrid: infra tunnel + API + UI"),
                "configurations": [launch_of[api_id], launch_of[ui_id]],
                "preLaunchTask": str(hybrid.get("preLaunchTask") or TUNNEL_TASK_LABEL),
                "stopAll": True,
            })
    return out


def _boot_order(ctx: ProjectContext) -> dict[str, int]:
    from lib import catalogs

    return {r: i for i, r in enumerate(catalogs.ordered("roles", "bootOrder", ctx.manifest))}


def build_tasks_json(ctx: ProjectContext) -> dict[str, Any]:
    gs = _stack_kit_script_rel(ctx)
    wf = "${workspaceFolder}"
    ps = "powershell"
    aliases = infer_cli_aliases(ctx.manifest)

    def _task(label: str, args: list[str]) -> dict[str, Any]:
        return {
            "label": label,
            "type": "shell",
            "command": ps,
            "args": ["-ExecutionPolicy", "Bypass", "-File", f"{wf}/{gs}", *args],
            "options": {"cwd": wf},
            "problemMatcher": [],
        }

    tasks: list[dict[str, Any]] = [
        _task("stack-kit: stack dev", ["stack", "up", "-d", "--build"]),
        _task("stack-kit: stack prod", ["stack", "-Prod", "up", "-d", "--build"]),
        _task("stack-kit: stack down", ["stack", "down"]),
        _task("stack-kit: compose-gen", ["compose-gen"]),
        _task("stack-kit: validate", ["validate"]),
    ]
    if _stack_infra_services(ctx):
        tasks.append(_infra_tunnel_task(ctx))
        tasks.append(_task("stack-kit: infra remote up", ["infra", "remote", "up", "--env", "dev"]))
        tasks.append(_task("stack-kit: infra remote status", ["infra", "remote", "status", "--env", "dev"]))
    for alias in sorted(set(aliases.values()), key=lambda x: aliases.get(x, x)):
        short = next((k for k, v in aliases.items() if v == alias), alias)
        # Watch tasks are DECLARED per driver in drivers/registry.json — a driver that
        # declares none simply gets none, and a new driver needs no generator edit.
        driver_id = read_nested(ctx.manifest, f"modules.{alias}.type", "")
        from lib.modules import driver_commands, lifecycle_steps

        for step in [s for s in lifecycle_steps(ctx.manifest) if s in driver_commands(driver_id)]:
            tasks.append(_task(f"stack-kit: {short} {step}", [step, short]))
        for _name, argv in sorted(_driver_watch_tasks(driver_id).items()):
            # a kit verb over the module (`dev watch <module>`), never a driver script
            tasks.append(_task(f"stack-kit: {' '.join(argv)} {short}", [*argv, short]))

    return {"version": "2.0.0", "tasks": tasks}


def write_vscode(ctx: ProjectContext, *, force: bool = False) -> list[str]:
    folder = read_nested(ctx.manifest, "vscode.folder", "") or default_field("vscode.folder") or ".vscode"
    out_dir = ctx.root / folder.replace("\\", "/")
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, builder in (("launch.json", build_launch_json), ("tasks.json", build_tasks_json)):
        path = out_dir / name
        if path.is_file() and not force:
            continue
        data = builder(ctx)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        written.append(_posix_rel(ctx.root, path))
    return written


def main() -> int:
    import sys

    force = "--force" in sys.argv
    ctx = ProjectContext.discover()
    paths = write_vscode(ctx, force=force)
    if not paths:
        print("[vscode-gen] .vscode files exist (use --force to overwrite)")
        return 0
    for p in paths:
        print(f"[vscode-gen] wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
