#!/usr/bin/env python3
"""Resolve CLI alias → module id (stdout). Used by stack-kit.sh when PowerShell unavailable."""
from __future__ import annotations

import sys

from lib.project_context import ProjectContext


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    try:
        ctx = ProjectContext.discover()
        target = ctx.resolve_alias(sys.argv[1])
    except FileNotFoundError:
        from lib.manifest_defaults import resolve_cli_alias

        target = resolve_cli_alias(sys.argv[1])
    if target:
        print(target)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
