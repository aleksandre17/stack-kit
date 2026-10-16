#!/usr/bin/env python3
"""Prepare minimal ops/config files for CI — manifest-driven, no hardcoded modules."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from lib.credentials import module_credentials
from lib.project_context import ProjectContext


def _seed_env_example(target: Path, example: Path, fallback_line: str | None = None) -> None:
    if target.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if example.is_file():
        target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    elif fallback_line:
        target.write_text(fallback_line + "\n", encoding="utf-8")


def prepare(ctx: ProjectContext) -> None:
    ctx.secrets_root.mkdir(parents=True, exist_ok=True)
    ctx.stack_compose_dir.mkdir(parents=True, exist_ok=True)

    seen_dirs: set[Path] = set()
    for _mid, sdir in ctx.secrets_module_dirs().items():
        if sdir in seen_dirs:
            continue
        seen_dirs.add(sdir)
        sdir.mkdir(parents=True, exist_ok=True)
        ex = sdir / ".env.example"
        for name in (".env.dev", ".env.prod"):
            _seed_env_example(sdir / name, ex)

    seeded_cred: set[tuple[Path, str]] = set()
    for mid in (ctx.manifest.get("modules") or {}):
        sdir = ctx.secrets_module_dir(str(mid))
        for cred in module_credentials(ctx.manifest, str(mid)):
            fn = cred["file"]
            key = (sdir, fn)
            if key in seeded_cred:
                continue
            seeded_cred.add(key)
            target = sdir / fn
            if target.is_file():
                continue
            ex = sdir / f"{fn}.example"
            if ex.is_file():
                target.write_text(ex.read_text(encoding="utf-8"), encoding="utf-8")
            elif fn.endswith(".json"):
                target.write_text("{}\n", encoding="utf-8")

    print(f"[ci] Integration env ready under {ctx.secrets_root.relative_to(ctx.root)}/")


def main() -> int:
    try:
        ctx = ProjectContext.discover()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    prepare(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
