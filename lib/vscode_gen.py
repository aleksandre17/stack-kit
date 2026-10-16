#!/usr/bin/env python3
"""Generate .vscode/launch.json and tasks.json from the project manifest (manifest-driven)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib.manifest_defaults import default_field, read_nested
from lib.modules import driver_package_scripts, driver_registry, infer_cli_aliases, modules_by_role
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
    # The module's debug script, else the start script its driver declares, else `dev`.
    typ = str(((ctx.manifest.get("modules") or {}).get(module_id) or {}).get("type") or "")
    declared = driver_package_scripts(typ).get("start")
    script = str(dbg.get("npmScript") or dbg.get("script") or declared or "dev")
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


def _dotnet_project_file(module_dir: Path, declared: str | None) -> Path | None:
    """The project file a module DECLARES (dotnet.project), else its single *.csproj."""
    if declared:
        candidate = module_dir / declared
        return candidate if candidate.is_file() else None
    found = sorted(module_dir.glob("*.csproj"))
    return found[0] if len(found) == 1 else None


def _launch_dotnet(
    ctx: ProjectContext, module_id: str, aliases: dict[str, str]
) -> dict[str, Any] | None:
    """C# Dev Kit launch ("type": "dotnet") for an SDK-style project."""
    mod_dir = ctx.module_path(module_id)
    declared = read_nested(ctx.manifest, f"modules.{module_id}.dotnet.project", "")
    project = _dotnet_project_file(mod_dir, str(declared) if declared else None)
    if project is None:
        return None
    dbg = _module_debug_cfg(ctx.manifest, module_id)
    label = str(dbg.get("label") or f"{module_id}: dotnet run")
    cfg: dict[str, Any] = {
        "name": label,
        "type": "dotnet",
        "request": "launch",
        "projectPath": "${workspaceFolder}/" + _posix_rel(ctx.root, project),
    }
    profile = read_nested(ctx.manifest, f"modules.{module_id}.dotnet.launchProfile", "")
    if profile:
        cfg["launchConfigurationId"] = f"TargetFramework=;{profile}"
    return cfg


# Launch builders are keyed by the launch KIND a driver DECLARES in
# drivers/registry.json ("vscode": {"launch": ...}). A new driver becomes debuggable by
# declaring a kind it already supports; the generator holds no driver name of its own.
LAUNCH_BUILDERS = {
    "node-terminal": _launch_node_terminal,
    "java": _launch_java,
    "dotnet": _launch_dotnet,
}


def _driver_vscode(driver_id: str) -> dict[str, Any]:
    entry = driver_registry().get(driver_id) or {}
    vs = entry.get("vscode")
    return vs if isinstance(vs, dict) else {}


def _launch_kind(driver_id: str) -> str:
    launch = _driver_vscode(driver_id).get("launch")
    return launch if isinstance(launch, str) else ("data" if isinstance(launch, dict) else "")


def _launch_from_data(ctx: ProjectContext, module_id: str, aliases: dict[str, str]) -> dict[str, Any] | None:
    """A launch configuration the driver declares as data (`vscode.launch` an object): every string in
    it has {module}, {path}, {label} and {script} filled for the module. A new driver needs no builder."""
    typ = str(((ctx.manifest.get("modules") or {}).get(module_id) or {}).get("type") or "")
    template = _driver_vscode(typ).get("launch")
    dbg = _module_debug_cfg(ctx.manifest, module_id)
    values = {"module": module_id, "path": "${workspaceFolder}/" + _posix_rel(ctx.root, ctx.module_path(module_id)),
              "label": str(dbg.get("label") or module_id),
              "script": str(dbg.get("npmScript") or dbg.get("script") or driver_package_scripts(typ).get("start") or "")}

    def fill(node: Any) -> Any:
        if isinstance(node, str):
            for k, v in values.items():
                node = node.replace("{" + k + "}", v)
            return node
        if isinstance(node, list):
            return [fill(n) for n in node]
        if isinstance(node, dict):
            return {k: fill(v) for k, v in node.items()}
        return node

    cfg = fill(template)
    cfg.setdefault("name", values["label"])
    return cfg


LAUNCH_BUILDERS["data"] = _launch_from_data


def _driver_watch_tasks(driver_id: str) -> dict[str, list[str]]:
    """Tasks a driver declares (`tasks`), and -- when it declares remote dev (`dev`) -- its dev watch."""
    entry = driver_registry().get(driver_id) or {}
    tasks = entry.get("tasks") if isinstance(entry.get("tasks"), dict) else {}
    out: dict[str, list[str]] = {str(n): [str(a) for a in argv] for n, argv in tasks.items() if isinstance(argv, list) and argv}
    if entry.get("dev"):
        out.setdefault("devWatch", ["dev", "watch"])
    return out


def build_launch_json(ctx: ProjectContext) -> dict[str, Any]:
    from lib import catalogs

    compound_roles = catalogs.flagged("roles", "launchCompound", ctx.manifest)
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
        if read_nested(ctx.manifest, f"modules.{mid}.role", "") in compound_roles:
            compounds_members.append(cfg["name"])

    gs = _stack_kit_script_rel(ctx)
    configs.extend(
        [
            {
                "name": "stack-kit: stack (compose dev)",
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
                "name": f"stack-kit: {alias} check",
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
