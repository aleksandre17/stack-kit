"""What the CLI runs on this machine: a driver's command by the runtime that declares it, a kit
script, and the run record of each step (ADR-001 amendments 8, 12).

A command runs by the runtime it names ({script, runtime}), else the first declared runtime whose
`match` fits its file name (config/runtimes.json, the host's `runtimes`): an argv template with
{script}, {operands}, {bash}, {python}, {pwsh}. The `inSession` runtime (PowerShell) runs the
script with `-File`, so its `-Name value` operands bind to the parameters it declares.
"""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from lib import identity

KIT = Path(__file__).resolve().parents[2]


def project_root() -> Path:
    from lib.project_context import find_project_root

    return find_project_root()


def pwsh() -> str:
    found = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")
    if not found:
        raise RuntimeError("PowerShell is required for this command (pwsh 7+ on any OS; Windows PowerShell 5.1)")
    return found


def bash() -> str:
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),):
            for rel in (r"Git\bin\bash.exe", r"Git\usr\bin\bash.exe"):
                cand = Path(base) / rel
                if cand.is_file():
                    return str(cand)
    found = shutil.which("bash")
    if not found or "system32" in found.lower():
        raise RuntimeError("bash is required for this command (Git Bash on Windows)")
    return found


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(KIT), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])])
    env["PYTHONUTF8"] = "1"
    env[identity.env_name("KIT_ROOT")] = str(KIT)
    try:
        env.setdefault(identity.env_name("PROJECT_ROOT"), str(project_root()))
    except FileNotFoundError:
        pass
    env.update(extra or {})
    return env


def python_script(rel: str, args: list[str]) -> int:
    """A kit script (lib/validate_manifest.py, ...) in its own process: its argv and exit are its own."""
    return subprocess.run([sys.executable, "-B", str(KIT / rel), *args], env=child_env()).returncode


def powershell_script(rel: str, args: list[str], extra: dict[str, str] | None = None) -> int:
    return subprocess.run([pwsh(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(KIT / rel), *args],
                          env=child_env(extra)).returncode


def runtime_of(script: Path, declared: str = "") -> str:
    from lib.modules import script_runtimes

    if declared:
        return declared
    for rid, spec in script_runtimes().items():
        if any(fnmatch.fnmatch(script.name, g) for g in spec.get("match") or []):
            return rid
    raise RuntimeError(f"no declared runtime runs {script.name}: declare one (manifest `runtimes`) or the "
                       f"command's own {{script, runtime}}")


def argv_of(script: Path, operands: list[str], declared: str = "") -> list[str]:
    from lib.modules import script_runtimes

    rid = runtime_of(script, declared)
    spec = script_runtimes()[rid]
    if spec.get("inSession"):
        return [pwsh(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *operands]
    if not spec.get("argv"):
        raise RuntimeError(f"runtime '{rid}' declares neither argv nor inSession")
    out: list[str] = []
    for token in spec["argv"]:
        if token == "{script}":
            out.append(str(script))
        elif token == "{operands}":
            out += operands
        elif token == "{bash}":
            out.append(bash())
        elif token == "{python}":
            out.append(sys.executable)
        elif token == "{pwsh}":
            out.append(pwsh())
        else:
            out.append(str(token))
    return out


def driver_command(module_id: str, command: str, operands: list[str]) -> int:
    """One command a module's driver declares, run by its runtime, in its own process."""
    from lib.modules import driver_command_runtimes, driver_commands
    from lib.project_context import load_manifest

    root = project_root()
    typ = str(((load_manifest(root).get("modules") or {}).get(module_id) or {}).get("type") or "")
    commands = driver_commands(typ)
    if command not in commands:
        print(f"  [{module_id}] driver '{typ}' declares no command '{command}' (declared: {', '.join(sorted(commands)) or 'none'})",
              file=sys.stderr)
        return 1
    argv = argv_of(commands[command], operands, driver_command_runtimes(typ).get(command, ""))
    env = child_env({identity.env_name("MODULE_ID"): module_id, identity.env_name("COMMAND"): command,
                     identity.env_name("PROJECT_ROOT"): str(root)})
    return subprocess.run(argv, env=env, cwd=str(root)).returncode


# ── the run record (DORA): one JSON line per step that ran, never failing the step ──

def _git(root: Path, *args: str) -> str:
    ran = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return ran.stdout.strip() if ran.returncode == 0 else ""


def runs_file(root: Path) -> Path:
    d = root / identity.RUNS_DIR
    d.mkdir(parents=True, exist_ok=True)
    ignore = root / identity.RUNS_DIR.split("/")[0] / ".gitignore"
    if not ignore.is_file():
        ignore.write_text("*\n", encoding="utf-8")
    return d / "runs.jsonl"


def recorded(kind: str, step: str, module: str, action: Callable[[], int], environment: str = "",
             target: str = "") -> int:
    try:
        root = project_root()
    except FileNotFoundError:
        return action()
    sha = _git(root, "rev-parse", "HEAD") or None
    dirty = bool(_git(root, "status", "--porcelain", "--untracked-files=no")) if sha else None
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    code = 1
    try:
        code = int(action() or 0)
    finally:
        ended = datetime.now(timezone.utc)
        record = {"schema": 1, "kind": kind, "step": step, "module": module, "environment": environment or None,
                  "target": target or None, "startedAt": started.isoformat(), "endedAt": ended.isoformat(),
                  "durationMs": int((time.monotonic() - t0) * 1000), "exit": code, "gitSha": sha, "gitDirty": dirty}
        try:
            with runs_file(root).open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            print(f"  [run record] not written: {e}", file=sys.stderr)
    return code
