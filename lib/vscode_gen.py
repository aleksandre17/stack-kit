#!/usr/bin/env python3
"""Generate .vscode/launch.json and tasks.json from geostat.ops.json (manifest-driven)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib.manifest_defaults import default_field, read_nested
from lib.modules import driver_registry, infer_cli_aliases, modules_by_role
from lib.project_context import ProjectContext


def _posix_rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _gradle_project_name(module_dir: Path) -> str | None:
    for name in ("settings.gradle.kts", "settings.gradle"):
        f = module_dir / name
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'rootProject\.name\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
    return None


def _detect_spring_main_class(module_dir: Path) -> str | None:
    java_root = module_dir / "src" / "main" / "java"
    if not java_root.is_dir():
        return None
    candidates: list[Path] = []
    for p in java_root.rglob("*Application.java"):
        if p.is_file():
            candidates.append(p)
    if not candidates:
        return None
    # Prefer shortest path / typical Spring Boot entry
    pick = sorted(candidates, key=lambda x: (len(x.parts), x.name))[0]
    rel = pick.relative_to(java_root)
    return ".".join(rel.with_suffix("").parts)


def _module_debug_cfg(manifest: dict[str, Any], module_id: str) -> dict[str, Any]:
    cfg = (manifest.get("modules") or {}).get(module_id) or {}
    if not isinstance(cfg, dict):
        return {}
    dbg = cfg.get("debug")
    return dbg if isinstance(dbg, dict) else {}


def _launch_node_terminal(
    ctx: ProjectContext, module_id: str, aliases: dict[str, str]
) -> dict[str, Any]:
    rel = _posix_rel(ctx.root, ctx.module_path(module_id))
    dbg = _module_debug_cfg(ctx.manifest, module_id)
    script = str(dbg.get("npmScript") or dbg.get("script") or "dev")
    label = str(dbg.get("label") or f"{module_id}: npm run {script}")
    return {
        "name": label,
        "type": "node-terminal",
        "request": "launch",
        "command": f"npm run {script}",
        "cwd": "${workspaceFolder}/" + rel,
    }


def _launch_java(
    ctx: ProjectContext, module_id: str, aliases: dict[str, str]
) -> dict[str, Any] | None:
    mod_dir = ctx.module_path(module_id)
    dbg = _module_debug_cfg(ctx.manifest, module_id)
    java_dbg = dbg.get("java") if isinstance(dbg.get("java"), dict) else dbg
    main = None
    project = None
    if isinstance(java_dbg, dict):
        main = java_dbg.get("mainClass")
        project = java_dbg.get("projectName")
    if not main:
        main = dbg.get("mainClass")
    if not project:
        project = dbg.get("projectName")
    if not main:
        main = _detect_spring_main_class(mod_dir)
    if not project:
        project = _gradle_project_name(mod_dir)
    if not main:
        return None
    rel = _posix_rel(ctx.root, mod_dir)
    label = str(dbg.get("label") or f"{module_id}: Spring Boot")
    cfg: dict[str, Any] = {
        "name": label,
        "type": "java",
        "request": "launch",
        "mainClass": main,
        "cwd": "${workspaceFolder}/" + rel,
    }
    if project:
        cfg["projectName"] = project
    env_file = dbg.get("envFile")
    if env_file:
        cfg["envFile"] = "${workspaceFolder}/" + str(env_file).replace("\\", "/")
    else:
        dev_env = ctx.secrets_module_dir(module_id) / ".env.dev"
        cfg["envFile"] = "${workspaceFolder}/" + _posix_rel(ctx.root, dev_env)
    profiles = read_nested(ctx.manifest, f"modules.{module_id}.hybrid.springProfiles", "")
    if profiles:
        cfg["env"] = {"SPRING_PROFILES_ACTIVE": profiles}
    return cfg


def _geostat_script_rel(ctx: ProjectContext) -> str:
    custom = read_nested(ctx.manifest, "vscode.geostatScript", "")
    if custom:
        return custom.replace("\\", "/")
    return default_field("vscode.geostatScript") or "tools/geostat.ps1"


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


def _find_launch_name_for_module(
    configs: list[dict[str, Any]], module_id: str, ctx: ProjectContext
) -> str | None:
    rel = _posix_rel(ctx.root, ctx.module_path(module_id))
    kind = _launch_kind(read_nested(ctx.manifest, f"modules.{module_id}.type", ""))
    for cfg in configs:
        cwd = str(cfg.get("cwd", "")).replace("\\", "/")
        if not cwd.endswith(rel):
            continue
        if kind and cfg.get("type") == kind:
            return cfg["name"]
    return None


TUNNEL_TASK_LABEL = "geostat: infra tunnel"
TUNNEL_READY_PATTERN = "Set INFRA_HOST=127.0.0.1"


def _infra_tunnel_task(ctx: ProjectContext) -> dict[str, Any]:
    gs = _geostat_script_rel(ctx)
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
            "owner": "geostat-infra-tunnel",
            "pattern": {"regexp": "^.*$"},
            "background": {
                "activeOnStart": True,
                "beginsPattern": "\\[infra\\]",
                "endsPattern": TUNNEL_READY_PATTERN.replace(".", "\\."),
            },
        },
    }


# Launch builders are keyed by the launch KIND a driver DECLARES in
# drivers/registry.json ("vscode": {"launch": ...}). A new driver becomes debuggable by
# declaring a kind it already supports; the generator holds no driver name of its own.
LAUNCH_BUILDERS = {
    "node-terminal": _launch_node_terminal,
    "java": _launch_java,
}


def _driver_vscode(driver_id: str) -> dict[str, Any]:
    entry = driver_registry().get(driver_id) or {}
    vs = entry.get("vscode")
    return vs if isinstance(vs, dict) else {}


def _launch_kind(driver_id: str) -> str:
    return str(_driver_vscode(driver_id).get("launch") or "")


def _driver_watch_tasks(driver_id: str) -> dict[str, list[str]]:
    tasks = (driver_registry().get(driver_id) or {}).get("tasks")
    if not isinstance(tasks, dict):
        return {}
    out: dict[str, list[str]] = {}
    for name, argv in tasks.items():
        if isinstance(argv, list) and argv:
            out[str(name)] = [str(a) for a in argv]
    return out


def build_launch_json(ctx: ProjectContext) -> dict[str, Any]:
    aliases = infer_cli_aliases(ctx.manifest)
    configs: list[dict[str, Any]] = []
    compounds_members: list[str] = []

    for mid in ctx.list_module_ids():
        typ = read_nested(ctx.manifest, f"modules.{mid}.type", "")
        builder = LAUNCH_BUILDERS.get(_launch_kind(typ))
        if builder is None:
            continue  # driver declares no launch kind — an honest absence, not a guess
        cfg = builder(ctx, mid, aliases)
        if not cfg:
            continue
        configs.append(cfg)
        if read_nested(ctx.manifest, f"modules.{mid}.role", "") in ("ui", "api", "worker"):
            compounds_members.append(cfg["name"])

    gs = _geostat_script_rel(ctx)
    configs.extend(
        [
            {
                "name": "geostat: stack (compose dev)",
                "type": "node-terminal",
                "request": "launch",
                "command": f'powershell -ExecutionPolicy Bypass -File "${{workspaceFolder}}/{gs}" stack up -d --build',
                "cwd": "${workspaceFolder}",
            },
        ]
    )
    for alias, _target in sorted(aliases.items()):
        configs.append(
            {
                "name": f"geostat: {alias} check",
                "type": "node-terminal",
                "request": "launch",
                "command": f'powershell -ExecutionPolicy Bypass -File "${{workspaceFolder}}/{gs}" {alias} check',
                "cwd": "${workspaceFolder}",
            }
        )

    out: dict[str, Any] = {"version": "0.2.0", "configurations": configs}
    if len(compounds_members) >= 2:
        ui_names = [
            c["name"]
            for c in configs
            if c.get("type") == "node-terminal" and "npm run" in c.get("command", "")
        ]
        api_names = [
            c["name"]
            for c in configs
            if c.get("type") == "java"
        ]
        pick = (api_names[:1] + ui_names[:1]) or compounds_members[:2]
        out["compounds"] = [
            {
                "name": "Full stack (local)",
                "configurations": pick,
                "stopAll": True,
            }
        ]

    if _stack_infra_services(ctx):
        hybrid = _vscode_hybrid_cfg(ctx)
        api_id = _pick_module_by_role(ctx, "api", str(hybrid.get("apiModule") or ""))
        ui_id = _pick_module_by_role(ctx, "ui", str(hybrid.get("uiModule") or ""))
        if api_id and ui_id:
            api_launch = _find_launch_name_for_module(configs, api_id, ctx)
            ui_launch = _find_launch_name_for_module(configs, ui_id, ctx)
            if api_launch and ui_launch:
                compound_name = str(
                    hybrid.get("compoundName")
                    or "Hybrid: infra tunnel + API + UI"
                )
                pre_launch = str(hybrid.get("preLaunchTask") or TUNNEL_TASK_LABEL)
                hybrid_compound = {
                    "name": compound_name,
                    "configurations": [api_launch, ui_launch],
                    "preLaunchTask": pre_launch,
                    "stopAll": True,
                }
                out.setdefault("compounds", []).append(hybrid_compound)
    return out


def build_tasks_json(ctx: ProjectContext) -> dict[str, Any]:
    gs = _geostat_script_rel(ctx)
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
        _task("geostat: stack dev", ["stack", "up", "-d", "--build"]),
        _task("geostat: stack prod", ["stack", "-Prod", "up", "-d", "--build"]),
        _task("geostat: stack down", ["stack", "down"]),
        _task("geostat: compose-gen", ["compose-gen"]),
        _task("geostat: validate", ["validate"]),
    ]
    if _stack_infra_services(ctx):
        tasks.append(_infra_tunnel_task(ctx))
        tasks.append(_task("geostat: infra remote up", ["infra", "remote", "up"]))
        tasks.append(_task("geostat: infra remote status", ["infra", "remote", "status"]))
    for alias in sorted(set(aliases.values()), key=lambda x: aliases.get(x, x)):
        short = next((k for k, v in aliases.items() if v == alias), alias)
        tasks.append(_task(f"geostat: {short} check", [short, "check"]))
        tasks.append(
            _task(
                f"geostat: {short} compose up",
                [short, "compose", "up", "-d", "--build"],
            )
        )
        # Watch tasks are DECLARED per driver in drivers/registry.json — a driver that
        # declares none simply gets none, and a new driver needs no generator edit.
        driver_id = read_nested(ctx.manifest, f"modules.{alias}.type", "")
        for _name, argv in sorted(_driver_watch_tasks(driver_id).items()):
            tasks.append(_task(f"geostat: {short} {' '.join(argv)}", [short, *argv]))

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
