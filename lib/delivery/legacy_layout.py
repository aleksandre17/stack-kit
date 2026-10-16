"""`layout migrate`: one project's services out of a tree laid out before the layout, into its own
{root}/{project}/{environment}/{tier}/{service} -- planned by default, applied only with --approve,
never automatically (ADR-001 amendment 13). It replaces every per-driver migrate script.

What moves is what the target DECLARES as this project's (`legacyLayout`), never what a listing
finds: a platform root is shared, and a tier-first folder at it (backend/, frontend/, infra/ ...)
holds other projects' trees too.

    "legacyLayout": {
      "environment": "prod",                         the environment the old tree served
      "units":  { "<service>": "{root}/<old path>" }, each service's old directory -> its unit
      "places": { "infra": "...", "backups": "..." }  an environment place's old directory -> it
    }

Each move is refused when its source is a direct child of the root, lies inside the project's own
directory already, carries another project's ownership marker, or when its destination exists and
is not empty. An absent source is reported and skipped. Containers still running from an old path
keep their bind mounts: stop them before applying.
"""
from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass

from lib.delivery import preflight, running
from lib.delivery.context import Delivery, DeliveryError
from lib.targets import MARKER, LayoutError, render_legacy, under


@dataclass
class Move:
    what: str
    src: str
    dst: str
    state: str = "planned"   # planned | absent | done | refused: <why>


def declared(ctx: Delivery) -> dict:
    legacy = ctx.target.get("legacyLayout") or {}
    if not legacy:
        raise DeliveryError(f"targets.{ctx.target_name} declares no legacyLayout: nothing to migrate", 2)
    want = legacy.get("environment") or ctx.environment
    if want != ctx.environment:
        raise DeliveryError(f"targets.{ctx.target_name}.legacyLayout is the old tree of {want}; run it with --env {want}", 2)
    return legacy


def plan(ctx: Delivery) -> list[Move]:
    legacy = declared(ctx)
    by_id = {s.id: s for s in running.services(ctx)}
    moves: list[Move] = []
    try:
        for sid, tpl in (legacy.get("units") or {}).items():
            if sid not in by_id or by_id[sid].module is None:
                raise DeliveryError(f"legacyLayout.units.{sid}: no service '{sid}' in this project ({', '.join(sorted(by_id))})")
            s = by_id[sid]
            moves.append(Move(f"unit {sid}", render_legacy(ctx.target, tpl, project=ctx.project, service=sid, tier=s.tier),
                              ctx.places.of("unit", s)))
        for kind, tpl in (legacy.get("places") or {}).items():
            if kind not in ("infra", "backups", "stack"):
                raise DeliveryError(f"legacyLayout.places.{kind}: only infra, backups, stack are environment places")
            moves.append(Move(kind, render_legacy(ctx.target, tpl, project=ctx.project), ctx.places.of(kind)))
    except LayoutError as e:
        raise DeliveryError(str(e), 2) from e
    seen: set[str] = set()
    for m in moves:
        if m.src in seen:
            m.state = "refused: declared twice"
        seen.add(m.src)
        if m.state != "planned":
            continue
        if under(m.src, ctx.places.project_dir) or under(ctx.places.project_dir, m.src):
            m.state = "refused: the source overlaps the project's own directory"
        elif not ctx.transport.exists(m.src):
            m.state = "absent"
        elif _foreign(ctx, m.src):
            m.state = f"refused: {m.src} carries another project's ownership marker"
        elif ctx.transport.exists(m.dst) and ctx.transport.listdir(m.dst):
            m.state = f"refused: {m.dst} exists and is not empty"
    return moves


def _foreign(ctx: Delivery, path: str) -> bool:
    raw = ctx.transport.read(posixpath.join(path, MARKER))
    if raw is None:
        return False
    try:
        return json.loads(raw.decode("utf-8")).get("project") != ctx.project
    except (UnicodeDecodeError, json.JSONDecodeError):
        return True


def apply(ctx: Delivery, moves: list[Move]) -> list[Move]:
    refused = [m for m in moves if m.state.startswith("refused")]
    if refused:
        raise DeliveryError("refused, nothing moved: " + "; ".join(f"{m.what}: {m.state[9:]}" for m in refused), 3)
    preflight.claim(ctx)
    for m in moves:
        if m.state != "planned":
            continue
        if ctx.transport.exists(m.dst):
            ctx.transport.remove(m.dst, confine=ctx.places.project_dir)  # empty, checked in the plan
        ctx.transport.move(m.src, m.dst)
        m.state = "done"
    return moves


def report(moves: list[Move]) -> list[str]:
    return [f"{m.what:<20} {m.src} -> {m.dst}  [{m.state}]" for m in moves] or ["nothing declared to move"]
