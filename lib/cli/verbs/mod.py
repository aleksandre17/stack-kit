"""`mod <module> <command>`: a command the module's driver declares, or a rung of its delivery ladder."""
from __future__ import annotations

import json
import sys

from lib import identity
from lib.cli import tools
from lib.cli.registry import Args, Verb


def _manifest() -> dict:
    from lib.project_context import load_manifest

    return load_manifest(tools.project_root())


def alias(word: str) -> str | None:
    from lib.modules import resolve_cli_alias

    try:
        return resolve_cli_alias(word, _manifest())
    except FileNotFoundError:
        return None


def _deliver(module: str, typ: str, rest: list[str]) -> int:
    from lib.modules import driver_delivery

    ladder = driver_delivery(typ)
    rung = rest[0] if rest else ""
    how = ladder.get(rung)
    if how is None:
        print(f"  Driver '{typ}' declares no delivery rung '{rung}' (declared: {', '.join(ladder)})")
        return 1
    if how.get("pending"):
        print(f"  Rung '{rung}' of driver '{typ}' is declared but not built: {how['pending']}")
        return 1
    extra = rest[1:]
    if how.get("via"):
        from lib.cli import registry

        via = str(how["via"])
        argv = {"hybrid": ["hybrid", "boot", module], "release": ["deploy", module], "dev": ["dev", "up", module]}.get(via, [via, module])
        if "--plan" in extra:
            print(f"  deliver {rung} -> {identity.KIT_NAME} {' '.join(argv)}")
            return 0
        verb = registry.discover()[argv[0]]
        return verb.run(registry.parse(verb, [*argv[1:], *extra]))
    command = str(how["command"])
    env = next((extra[i + 1] for i, a in enumerate(extra[:-1]) if a == "--env"), "prod")
    args = [str(a).replace("{environment}", env) for a in how.get("args") or []]
    if "--plan" in extra:
        from lib.modules import driver_commands

        print(f"  deliver {rung} -> {command} {' '.join(args)}  ({driver_commands(typ).get(command, '?')})")
        return 0
    return tools.recorded("deliver", rung, module, lambda: tools.driver_command(module, command, args), env)


def _run(a: Args) -> int:
    from lib.modules import driver_commands

    if not a.raw:
        print(f"  Usage: {identity.KIT_NAME} mod <module> <command> [operands]", file=sys.stderr)
        return 2
    module = alias(a.raw[0]) or a.raw[0]
    cfg = (_manifest().get("modules") or {}).get(module)
    if not isinstance(cfg, dict):
        print(f"  Unknown module: {a.raw[0]} (modules.* in {identity.MANIFEST_FILENAME})", file=sys.stderr)
        return 1
    typ = str(cfg.get("type") or "")
    sub, rest = (a.raw[1], a.raw[2:]) if len(a.raw) > 1 else ("help", [])
    from lib.modules import driver_capability

    rewrite = (driver_capability(typ, "operands", {}) or {}).get(sub)
    if isinstance(rewrite, dict) and isinstance(rewrite.get("to"), list):
        if rewrite.get("hint"):
            print(f"  Hint: {rewrite['hint']}")
        sub, rest = str(rewrite["to"][0]), [*map(str, rewrite["to"][1:]), *rest]
    if sub == "deliver":
        return _deliver(module, typ, rest)
    commands = driver_commands(typ)
    if sub not in commands:
        from lib.modules import driver_delivery

        print(f"  Unknown subcommand: {sub} (module {module}, type {typ})")
        print(f"  Valid: {' | '.join(sorted(commands))} | deliver <{'|'.join(driver_delivery(typ))}>")
        return 1
    return tools.driver_command(module, sub, rest)


def describe(module: str) -> str:
    from lib.modules import driver_commands, driver_delivery

    cfg = (_manifest().get("modules") or {}).get(module) or {}
    typ = str(cfg.get("type") or "")
    return json.dumps({"commands": sorted(driver_commands(typ)), "rungs": list(driver_delivery(typ))})


VERB = Verb("mod", "a command a module's driver declares, or a rung of its delivery ladder",
            ["mod <module> <command> [operands]", "mod <module> deliver <rung> [--env <id>] [--plan]",
             "<alias> <command> [operands]"],
            _run, passthrough=True, exits=(0, 1, 2), examples=["mod api build", "mod api deliver release --env prod --plan"],
            details="A rung `via` a kit verb runs that verb (release -> deploy, remote-dev -> dev up, hybrid -> hybrid boot).")
