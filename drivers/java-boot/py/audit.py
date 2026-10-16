#!/usr/bin/env python3
"""java-boot - audit: the module's locked dependency graph against the OSV database (OpenSSF), by
OSV-Scanner over Gradle's dependency lockfiles. Any known vulnerability fails the step; a waiver is
OSV-Scanner's own `osv-scanner.toml` beside the lockfile (`[[IgnoredVulns]]` with an id and a
reason), reviewed like code (ADR-001 amendment 16.2).

Every fact is this driver's declaration (`audit` in its registry entry), a module's `audit` over it:
`scanner` (the binary, used when it is on PATH), `image` (the scanner's image, run through the local
engine -- the target runtime flagged `local` -- when the binary is absent: CI runners carry an
engine, so CI needs no install), `args` (before the lockfiles), `lockfiles` (globs under the module)
and `unlocked` (what to do when the module locks nothing). A module that locks nothing is refused:
an unlocked graph resolves differently tomorrow, so passing it would prove nothing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

if __name__ == "__main__":
    sys.path.insert(0, os.environ.get("STACK_KIT_KIT_ROOT") or str(Path(__file__).resolve().parents[3]))

DRIVER = "java-boot"
#: OSV-Scanner's exit codes that are not a tool failure: 1 -- vulnerabilities found; 128 -- no package found.
FOUND, NO_PACKAGES = 1, 128


class Refused(Exception):
    pass


def declaration(module: dict[str, Any]) -> dict[str, Any]:
    from lib.modules import driver_capability

    decl = dict(driver_capability(DRIVER, "audit", {}) or {})
    decl.update({k: v for k, v in (module.get("audit") or {}).items() if v not in (None, "", [])})
    return decl


def lockfiles(module_dir: Path, globs: list[str]) -> list[str]:
    found = {p.relative_to(module_dir).as_posix() for g in globs for p in module_dir.glob(g) if p.is_file()}
    return sorted(found)


def plan(module_dir: Path, decl: dict[str, Any], *, which: Callable[[str], str | None] = shutil.which,
         engine: list[str] | None = None) -> list[str]:
    """The scanner's command line for this module, or Refused (nothing locked, no scanner, no engine)."""
    locks = lockfiles(module_dir, [str(g) for g in decl.get("lockfiles") or []])
    if not locks:
        raise Refused(f"no dependency lockfile under {module_dir.as_posix()} (looked for "
                      f"{', '.join(decl.get('lockfiles') or [])}): {decl.get('unlocked') or 'lock the dependency graph'}")
    args = [str(a) for a in decl.get("args") or []]
    binary = which(str(decl.get("scanner") or "")) if decl.get("scanner") else None
    if binary:
        return [binary, *args, *(t for f in locks for t in ("--lockfile", str(module_dir / f)))]
    if decl.get("image") and engine:
        return [*engine, "run", "--rm", "-v", f"{module_dir}:/src:ro", str(decl["image"]), *args,
                *(t for f in locks for t in ("--lockfile", f"/src/{f}"))]
    raise Refused(f"neither '{decl.get('scanner')}' on PATH nor a local container engine to run {decl.get('image')}")


def run(module_id: str, root: Path, manifest: dict[str, Any], *,
        which: Callable[[str], str | None] = shutil.which,
        execute: Callable[[list[str]], int] = lambda argv: subprocess.run(argv).returncode) -> int:
    from lib.targets.remote import local_commands

    module = (manifest.get("modules") or {}).get(module_id) or {}
    module_dir = root / str(module.get("path") or ".")
    try:
        argv = plan(module_dir, declaration(module), which=which, engine=local_commands(manifest)["engine"])
    except Refused as e:
        print(f"  [{module_id} audit] refused: {e}", file=sys.stderr)
        return 1
    print(f"  [{module_id} audit] {' '.join(argv)}", flush=True)
    code = execute(argv)
    if code == FOUND:
        print(f"  [{module_id} audit] a known vulnerability -- upgrade it, or waive it in osv-scanner.toml with a reason",
              file=sys.stderr)
    elif code == NO_PACKAGES:
        print(f"  [{module_id} audit] the lockfiles hold no package -- regenerate them", file=sys.stderr)
    return code


def main() -> int:
    from lib import identity
    from lib.project_context import load_manifest

    root = Path(identity.env("PROJECT_ROOT") or os.getcwd())
    return run(identity.env("MODULE_ID"), root, load_manifest(root))


if __name__ == "__main__":
    raise SystemExit(main())
