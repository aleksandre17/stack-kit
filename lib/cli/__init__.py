"""THE operator interface: one CLI, the same in a terminal and in CI (ADR-001 amendment 13).

`cli/stack-kit.ps1` and `cli/stack-kit.sh` (and a host's `ops/cli/stack-kit.*`) are thin launchers
of this entry point. A command is a discovered verb (lib/cli/registry.py), a lifecycle step the
catalog declares (`build`, `test`, ... across the modules), or a module alias (`<alias> <command>`
is `mod <module> <command>`).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from lib import identity


def _environment_flags(argv: list[str]) -> None:
    """`--target` / `--env` (`--dev`, `--prod`, `-Environment`) reach every child process as variables,
    so a driver script resolves the same target and environment as the verb that ran it."""
    for i, a in enumerate(argv):
        if a == "--target" and i + 1 < len(argv):
            os.environ[identity.env_name("TARGET")] = argv[i + 1]
        if a in ("--env", "-Environment") and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            os.environ[identity.env_name("ENVIRONMENT")] = argv[i + 1]
        if a in ("--dev", "--prod"):
            os.environ[identity.env_name("ENVIRONMENT")] = a[2:]


def main(argv: list[str]) -> int:
    from lib.cli import registry

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    os.environ.setdefault(identity.env_name("KIT_ROOT"), str(Path(__file__).resolve().parents[2]))
    command, rest = (argv[0], argv[1:]) if argv else ("help", [])
    if command in ("-h", "--help"):
        command = "help"
    _environment_flags(rest)
    verbs = registry.discover()
    verb = verbs.get(command)
    if verb is None:
        from lib.cli.verbs import mod as mod_verb, step as step_verb

        if command in step_verb.steps():
            verb, rest = step_verb.verb_for(command), rest
        else:
            module = mod_verb.alias(command)
            if module is None:
                print(f"  Unknown command: {command} (run: {identity.KIT_NAME} help)", file=sys.stderr)
                return 2
            verb, rest = verbs["mod"], [module, *rest]
    if "--help" in rest and not verb.passthrough or (verb.passthrough and rest[:1] == ["--help"]):
        print(registry.help_text(verb, identity.KIT_NAME), end="")
        return 0
    try:
        args = registry.parse(verb, rest)
    except registry.UsageError as e:
        print(f"  [usage] {e}", file=sys.stderr)
        return 2
    try:
        return int(verb.run(args) or 0)
    except KeyboardInterrupt:
        print("  interrupted", file=sys.stderr)
        return 130
