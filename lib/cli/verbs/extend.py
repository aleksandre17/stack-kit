"""`extend`: the host's extensions of the kit, each through a declared point."""
from __future__ import annotations

import sys
from pathlib import Path

from lib import identity
from lib.cli import tools
from lib.cli.registry import Args, Option, Verb


def _root(a: Args) -> Path:
    if a.value("--root"):
        return Path(a.value("--root")).resolve()
    return tools.project_root()


def _extend(a: Args) -> int:
    from lib import extend
    from lib.project_root import load_manifest

    try:
        root = _root(a)
    except FileNotFoundError as e:
        print(f"  [extend] {e} (`extend --init --root <dir>` lays a new one down)", file=sys.stderr)
        return 2
    manifest = load_manifest(root)
    plan = a.has("--plan")
    try:
        if a.has("--init"):
            said = extend.init(root, plan=plan)
        elif a.has("--upgrade"):
            said = extend.upgrade(root, plan=plan)
        elif a.has("--list") or not a.positional:
            for row in extend.listing(root, manifest):
                point, p = row["point"], row["place"]
                where = (p.rel + ("#/" + "/".join(p.pointer) if p and p.pointer else "")) if p else point["host_path"]
                print(f"  {point['id']:<24} {row['status']:<9} {row['name'] or '-':<14} {where}")
                for q in row["pending"]:
                    print(f"  {'':<24} pending: {q}")
            for rel in extend.undeclared(root, manifest):
                print(f"  {'(undeclared)':<24} {'':<9} {'':<14} {rel}  -- no point declares it")
            return 0
        else:
            point_id, name = a.positional[0], (a.positional[1] if len(a.positional) > 1 else "")
            if point_id == "module" and not name:  # the draft from the tree (`init --plan`)
                return tools.python_script("lib/draft.py", ["--approve", a.value("--approve")] if a.value("--approve") else ["--plan"])
            said = extend.make(root, manifest, point_id, name, plan=plan)
    except extend.ExtendError as e:
        print(f"  [extend] {e}", file=sys.stderr)
        return 1
    for line in said:
        print(f"  {line}")
    return 0


VERB = Verb("extend", "extend the kit through a declared point: a host file or entry from its template, pending answers shown, template upgrades merged",
            ["extend --list", "extend <point> [<name>] [--plan]", "extend module [--approve <who>]   (draft the modules from the tree)",
             "extend --upgrade [--plan]", "extend --init [--root <dir>] [--plan]"],
            _extend, options=[Option("--list", "every point: purpose, where the host file goes, status (unused | drafted | answered)"),
                              Option("--plan", "print what would be made or merged; nothing is written"),
                              Option("--upgrade", "merge each changed template 3-way into the host's file; a conflict is reported, never written"),
                              Option("--init", "every point init requires, then each infra service the manifest selects"),
                              Option("--root", "the host root (init, before a manifest exists)", "dir"),
                              Option("--approve", "module: write the draft, recording who approved it", "who")],
            exits=(0, 1, 2), examples=["extend --list", "extend infra-service postgres --plan", "extend catalog-environments staging"],
            details="A point's file is made only on demand, never overwritten; the answers only the host can give are "
                    "<<pending: ...>> markers that validate shows (an error where the manifest's `extend.profile` requires "
                    "the point). A file where a point lives that no point declares is reported. The kit copy is never edited.")
