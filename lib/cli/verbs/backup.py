"""`backup`: a store's dump on the target, and its verified restore."""
from __future__ import annotations

import sys

from lib import identity
from lib.cli import remote
from lib.cli.registry import Args, Option, Verb
from lib.cli.remote import PLAN, YES


def _backup(a: Args) -> int:
    from lib.delivery import backup

    sub = a.positional[0] if a.positional else ""
    if sub == "list" and len(a.positional) == 2:
        def show(ctx):
            if not ctx.plan:
                for f in backup.listing(ctx, a.positional[1]):
                    print(f"  {f}")
            return 0
        return remote.run(a, "backup list", show, plan_first=False)
    if sub == "verify" and len(a.positional) == 2:
        def check(ctx):
            failures = backup.verify(ctx, a.positional[1], a.value("--file"))
            for f in failures:
                print(f"  [backup] FAILED {f}")
            return 6 if failures else 0
        return remote.run(a, f"verify the restore of {a.positional[1]}", check)
    if sub == "replay" and len(a.positional) == 1:
        def chain(ctx):
            failures = backup.replay(ctx)
            for f in failures:
                print(f"  [backup] FAILED {f}")
            return 6 if failures else 0
        return remote.run(a, "replay the migration chain into an empty throwaway database", chain)
    if len(a.positional) == 1 and sub not in ("list", "verify", "replay"):
        return remote.run(a, f"backup {sub}", lambda ctx: (backup.backup(ctx, sub), 0)[1])
    print(f"  Usage: {identity.KIT_NAME} backup <store> | backup verify <store> [--file <name>] | backup replay | backup list <store>  --env <id>",
          file=sys.stderr)
    return 2


VERB = Verb("backup", "a store's dump in the layout's backups place, and a restore that is checked, not assumed",
            ["backup <store> --env <id> [--plan]", "backup verify <store> [--file <name>] --env <id> [--plan]",
             "backup replay --env <id> [--plan]", "backup list <store> --env <id>"],
            _backup, options=[PLAN, YES, Option("--file", "verify: the dump to check (default the newest)", "name")],
            group="delivery", exits=(0, 1, 2, 6), examples=["backup postgres --env prod", "backup verify postgres --env prod"],
            details="How a store dumps, restores, is queried and dropped is its catalog entry (run inside its container, its "
                    "credentials read there); what a restore must still hold is the host's (stack.infra.backup.<store>.anchors). "
                    "verify restores into a uniquely named throwaway database (its files moved, never over the source), compares "
                    "each anchor there and drops the database, pass or fail; replay applies the whole migration chain to an "
                    "empty throwaway database (stack.migrate.replay) and drops it the same way. Both print their plan first.")
