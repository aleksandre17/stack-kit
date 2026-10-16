"""`tls`: an internal CA on the target, a leaf per host, and the public truststore."""
from __future__ import annotations

import sys
from pathlib import Path

from lib import identity
from lib.cli import remote, tools
from lib.cli.registry import Args, Option, Verb
from lib.cli.remote import PLAN, YES


def _tls(a: Args) -> int:
    from lib.delivery import tls

    sub = a.positional[0] if a.positional else ""
    if sub == "ca":
        return remote.run(a, "tls ca", lambda ctx: (tls.ca(ctx), 0)[1])
    if sub == "leaf" and len(a.positional) >= 2:
        sans = [s for s in (a.value("--san") or "").split(",") if s]
        return remote.run(a, f"tls leaf {a.positional[1]}", lambda ctx: (tls.leaf(ctx, a.positional[1], sans), 0)[1])
    if sub == "truststore":
        out = Path(a.value("--out") or (tools.project_root() / "ops" / "deploy" / "tls"))

        def fetch(ctx):
            for f in tls.truststore(ctx, out):
                print(f"  wrote {f}")
            return 0
        return remote.run(a, "tls truststore", fetch)
    print(f"  Usage: {identity.KIT_NAME} tls ca | tls leaf <host> [--san name,ip,...] | tls truststore [--out <dir>]  --env <id>",
          file=sys.stderr)
    return 2


VERB = Verb("tls", "TLS on a private network: an internal CA on the target, a leaf per host, a public password-less truststore",
            ["tls ca --env <id>", "tls leaf <host> [--san <name,ip,...>] --env <id>", "tls truststore [--out <dir>] --env <id>"],
            _tls, options=[PLAN, YES, Option("--san", "leaf: further DNS names and IPs", "list"),
                           Option("--out", "truststore: where the public files go (default ops/deploy/tls)", "dir")],
            group="delivery", exits=(0, 1, 2),
            details="The CA's key is made on the target and never leaves it; `ca` never replaces one. A leaf (397 days) lands "
                    "where the edge template reads it (infra/tls/live). The truststore holds only the CA certificate, so it "
                    "needs no password.")
