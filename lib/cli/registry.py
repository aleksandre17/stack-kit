"""The verb registry: every CLI verb is one module under lib/cli/verbs/ declaring a `VERB` -- its
name, summary, usage, options, exit codes and examples -- discovered, never listed. The help
screen, each verb's `--help` and the operator documentation (`help --markdown`) are rendered from
these declarations, and nothing else (ADR-001 amendment 13).
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Callable

#: The exit codes every verb shares; a verb's own `exits` names those it can return.
EXIT_CODES = {
    0: "done (or, with --plan, planned)",
    1: "failed: a step or a declaration was wrong; the message names it",
    2: "not run: a usage error, or nothing selectable (no target, a pending one, a non-workspace environment)",
    3: "refused: ownership -- the directory carries another project's marker, or none",
    4: "refused by the preflight: runtime, ports or disk",
    5: "refused: provenance -- a dirty checkout or an archive without release.json where a clean commit is required, "
       "or a release that cannot run as its service is declared now",
    6: "unhealthy: a service did not become healthy (a release in a rolling-back environment was rolled back)",
    130: "interrupted",
}


@dataclass
class Option:
    flag: str
    help: str
    value: str = ""          # the value's name when the option takes one ("" = a switch)


@dataclass
class Verb:
    name: str
    summary: str
    usage: list[str]
    run: Callable[["Args"], int]
    options: list[Option] = field(default_factory=list)
    exits: tuple[int, ...] = (0, 1, 2)
    examples: list[str] = field(default_factory=list)
    details: str = ""
    passthrough: bool = False   # the operands go to a driver or a tool untouched
    group: str = "project"      # project | delivery | dev | generate


@dataclass
class Args:
    verb: str
    positional: list[str]
    flags: dict[str, str | bool]
    raw: list[str]

    def has(self, flag: str) -> bool:
        return bool(self.flags.get(flag))

    def value(self, flag: str, default: str = "") -> str:
        v = self.flags.get(flag)
        return v if isinstance(v, str) else default


class UsageError(ValueError):
    """A command line the verb cannot take, named."""


#: The options every remote verb takes; parsed once, for every verb.
GLOBAL = [Option("--target", "the declared deploy target (default: the environment's)", "name"),
          Option("--env", "the environment (catalogs.environments; --dev / --prod are short for it)", "id"),
          Option("--help", "this verb's help")]


def parse(verb: Verb, argv: list[str]) -> Args:
    declared = {o.flag: o for o in [*GLOBAL, *verb.options]}
    flags: dict[str, str | bool] = {}
    positional: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--dev", "--prod"):
            flags["--env"] = a[2:]
        elif a in declared:
            o = declared[a]
            if o.value:
                if i + 1 >= len(argv):
                    raise UsageError(f"{a} takes a value ({o.value})")
                i += 1
                flags[a] = argv[i]
            else:
                flags[a] = True
        elif a.startswith("--") and not verb.passthrough:
            raise UsageError(f"{verb.name}: no option {a} (see: {verb.name} --help)")
        else:
            positional.append(a)
        i += 1
    return Args(verb.name, positional, flags, argv)


def discover() -> dict[str, Verb]:
    from lib.cli import verbs

    found: dict[str, Verb] = {}
    for info in sorted(pkgutil.iter_modules(verbs.__path__), key=lambda i: i.name):
        mod = importlib.import_module(f"lib.cli.verbs.{info.name}")
        for v in [getattr(mod, "VERB", None), *getattr(mod, "VERBS", [])]:
            if v is None:
                continue
            if v.name in found:
                raise RuntimeError(f"verb {v.name} declared twice ({info.name})")
            found[v.name] = v
    return found


def help_text(v: Verb, kit: str) -> str:
    lines = [f"{kit} {v.name} -- {v.summary}", "", "usage:"]
    lines += [f"  {kit} {u}" for u in v.usage]
    opts = [*v.options, *(GLOBAL if v.group in ("delivery", "dev") else GLOBAL[-1:])]
    if opts:
        lines += ["", "options:"]
        lines += [f"  {(o.flag + (' <' + o.value + '>' if o.value else '')):<24} {o.help}" for o in opts]
    if v.details:
        lines += ["", v.details]
    lines += ["", "exit codes:"] + [f"  {c}  {EXIT_CODES[c]}" for c in v.exits]
    if v.examples:
        lines += ["", "examples:"] + [f"  {kit} {e}" for e in v.examples]
    return "\n".join(lines) + "\n"


GROUPS = [("delivery", "Deploy and operate"), ("dev", "Remote dev"), ("project", "The project"),
          ("generate", "Generated files")]


def markdown(verbs: dict[str, Verb], kit: str) -> str:
    """The operator documentation, from the registry alone (`help --markdown`)."""
    out = [f"# Operating with {kit}", "",
           f"Generated by `{kit} help --markdown` from the verb registry (lib/cli/verbs/); regenerate, never edit.",
           f"Every verb runs the same in a terminal and in CI. A verb that changes a server prints its plan -- the",
           "exact remote paths and commands -- before it acts; `--plan` stops there and writes nothing.", "",
           "## Exit codes", "", "| code | meaning |", "|---|---|"]
    out += [f"| {c} | {m} |" for c, m in EXIT_CODES.items()]
    for group, title in GROUPS:
        members = [v for v in verbs.values() if v.group == group]
        if not members:
            continue
        out += ["", f"## {title}"]
        for v in sorted(members, key=lambda v: v.name):
            out += ["", f"### `{v.name}`", "", v.summary + ".", "", "```"]
            out += [f"{kit} {u}" for u in v.usage]
            out += ["```"]
            opts = v.options + (GLOBAL[:-1] if v.group in ("delivery", "dev") else [])
            if opts:
                out += ["", "| option | |", "|---|---|"]
                out += [f"| `{o.flag}{' <' + o.value + '>' if o.value else ''}` | {o.help} |" for o in opts]
            if v.details:
                out += ["", v.details]
            out += ["", "Exit codes: " + ", ".join(str(c) for c in v.exits) + "."]
            if v.examples:
                out += ["", "```"] + [f"{kit} {e}" for e in v.examples] + ["```"]
    out += _drivers_table() + _points_table()
    return "\n".join(out) + "\n"


def _evidence(detect: dict) -> list[str]:
    """The file names a driver's detection reads, in the order it declares them."""
    found: list[str] = []

    def walk(item) -> None:
        if isinstance(item, dict):
            if isinstance(item.get("file"), str) and item["file"] not in found:
                found.append(item["file"])
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(detect.get("all") or [])
    return found


def _drivers_table() -> list[str]:
    """The kit's drivers, from drivers/registry.json -- what each recognises a module by, the build tools it
    knows, and what its toolchain writes (never tracked)."""
    import json
    from pathlib import Path

    registry = json.loads((Path(__file__).resolve().parents[2] / "drivers" / "registry.json").read_text(encoding="utf-8"))
    rows = ["", "## Drivers", "", "From `drivers/registry.json`. `init --plan` drafts a module for each directory whose files a",
            "driver's detection holds for; a host adds its own with `extend driver <name>`.", "",
            "| driver | for | roles | recognised by | built by | writes |", "|---|---|---|---|---|---|"]
    for typ, entry in sorted(registry.items()):
        if not isinstance(entry, dict):
            continue
        tools = ", ".join(t["id"] for t in entry.get("buildTools") or []) or "-"
        rows.append(f"| `{typ}` | {entry.get('label', '')} | {', '.join(entry.get('roles') or [])} | "
                    f"{', '.join(f'`{f}`' for f in _evidence(entry.get('detect') or {})) or '-'} | {tools} | "
                    f"{', '.join(f'`{o}`' for o in entry.get('outputs') or []) or '-'} |")
    return rows


def _points_table() -> list[str]:
    """The extension points, from config/extension-points.json -- every place a host extends the kit."""
    import json
    from pathlib import Path

    points = json.loads((Path(__file__).resolve().parents[2] / "config" / "extension-points.json").read_text(encoding="utf-8"))["points"]
    rows = ["", "## Extension points", "", "From `config/extension-points.json`: `extend <point> [<name>]` makes one from its template,",
            "never overwriting; `extend --list` shows each with its state on this host. `init` lays down the",
            "points it requires.", "", "| point | what | host path | one or many | laid by init |", "|---|---|---|---|---|"]
    for p in points:
        rows.append(f"| `{p['id']}` | {p['purpose']} | `{p['host_path']}` | {p['cardinality']} | "
                    f"{'yes' if p.get('required_by') == 'init' else '-'} |")
    return rows
