"""How every verb that changes a server runs: plan first, then confirm when it must, then act.

1. the context: project, environment, target, the rendered environment directory -- printed
2. the plan: the same action against a dry run -- every remote path it writes and every command
   it runs, printed; reads reach the server, nothing is changed
3. `--plan` stops here (exit 0)
4. confirmation where the environment declares it (`confirm`) or the action removes: asked on a
   terminal, refused without one unless `--yes` (CI says --yes; no menu, no prompt it cannot answer)
5. the action, recorded in the run record
"""
from __future__ import annotations

import sys
from typing import Callable

from lib import identity
from lib.cli import tools
from lib.cli.registry import Args, Option
from lib.delivery.context import Delivery, DeliveryError, open_delivery
from lib.delivery.transport import TransportError
from lib.targets import LayoutError

PLAN = Option("--plan", "print the plan -- remote paths and commands -- and stop; nothing is written")
YES = Option("--yes", "answer the confirmation (CI); without a terminal a confirmation is otherwise refused")


def context(args: Args, out: Callable[[str], None] = print) -> Delivery:
    from lib.project_context import load_manifest

    root = tools.project_root()
    return open_delivery(root, load_manifest(root), environment=args.value("--env"), target=args.value("--target"), out=out)


def confirm(args: Args, question: str) -> bool:
    if args.has("--yes"):
        return True
    if not sys.stdin.isatty():
        print(f"  [refused] {question} -- needs confirmation; pass --yes to answer it (no terminal to ask)", file=sys.stderr)
        return False
    try:
        reply = input(f"  {question} [y/N] ").strip().lower()
    except EOFError:
        # A console that reports a terminal but delivers no line (a pipe under some Windows hosts)
        # is no answer, and no answer is a refusal -- never a traceback.
        print(f"\n  [refused] {question} -- no answer was read; pass --yes to answer it", file=sys.stderr)
        return False
    return reply in ("y", "yes")


def run(args: Args, what: str, action: Callable[[Delivery], int], *, destructive: bool = False,
        module: str = "", plan_first: bool = True, read_only: bool = False) -> int:
    """`read_only`: the verb changes nothing on the server, so an environment that asks first is
    never asked -- a confirmation guards a change, and a reading is not one."""
    try:
        ctx = context(args)
    except (DeliveryError, LayoutError) as e:
        print(f"  [{args.verb}] NOT RUN: {e}", file=sys.stderr)
        return getattr(e, "code", 2)
    except FileNotFoundError as e:
        print(f"  [{args.verb}] {e}", file=sys.stderr)
        return 2
    print(f"[{args.verb}] {what}: project {ctx.project}, {ctx.environment} on {ctx.target_name} "
          f"({ctx.places.environment_dir})")
    try:
        if plan_first:
            print("[plan]")
            code = action(ctx.dry())
            if code:
                return code
        if args.has("--plan"):
            print("[plan] nothing was changed (--plan)")
            return 0
        if destructive or (ctx.flag("confirm") and not read_only):
            why = "it removes" if destructive else f"{ctx.environment} asks first"
            if not confirm(args, f"{what} in {ctx.environment} on {ctx.target_name} ({why}) -- proceed?"):
                return 2
        return tools.recorded(args.verb, what, module, lambda: action(ctx), ctx.environment, ctx.target_name)
    except DeliveryError as e:
        print(f"  [{args.verb}] {e}", file=sys.stderr)
        return e.code
    except (TransportError, LayoutError) as e:
        print(f"  [{args.verb}] {e}", file=sys.stderr)
        return 2 if isinstance(e, TransportError) and "unreachable" in str(e) else 1
    finally:
        ctx.close()


def kit() -> str:
    return identity.KIT_NAME
