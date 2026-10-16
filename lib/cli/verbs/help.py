"""`help`: the verbs, the project's modules and aliases -- or, `--markdown`, the operator documentation."""
from __future__ import annotations

from lib import identity
from lib.cli import registry, tools
from lib.cli.registry import Args, Option, Verb


def _help(a: Args) -> int:
    verbs = registry.discover()
    kit = identity.KIT_NAME
    if a.has("--markdown"):
        print(registry.markdown(verbs, kit), end="")
        return 0
    if a.positional and a.positional[0] in verbs:
        print(registry.help_text(verbs[a.positional[0]], kit), end="")
        return 0
    print(f"\n  {kit} -- one CLI for a project's modules, in a terminal and in CI\n")
    for group, title in registry.GROUPS:
        print(f"  {title}:")
        for v in sorted((v for v in verbs.values() if v.group == group), key=lambda v: v.name):
            print(f"    {v.name:<14} {v.summary}")
        print()
    print(f"  `{kit} <verb> --help` for a verb's usage, options, exit codes and examples;"
          f" `{kit} help --markdown` for the operator documentation.\n")
    try:
        from lib.modules import driver_commands, infer_cli_aliases
        from lib.project_context import load_manifest

        manifest = load_manifest(tools.project_root())
    except FileNotFoundError:
        return 0
    print("  Project modules:")
    for mid, cfg in (manifest.get("modules") or {}).items():
        if isinstance(cfg, dict):
            typ = str(cfg.get("type") or "")
            print(f"    {mid}  role={cfg.get('role', '')}  type={typ}  [{', '.join(sorted(driver_commands(typ)))}]")
    aliases = infer_cli_aliases(manifest)
    if aliases:
        print("\n  CLI aliases: " + ", ".join(f"{k}->{v}" for k, v in sorted(aliases.items())))
    print()
    return 0


VERB = Verb("help", "the verbs, or one verb's help, or the generated operator documentation",
            ["help [verb]", "help --markdown"], _help, options=[Option("--markdown", "the operator documentation (OPERATIONS.md)")],
            exits=(0,))
