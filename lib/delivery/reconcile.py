"""Drift between the declared state and the host's, and its reconciliation (OpenGitOps: declarative,
versioned, applied, continuously reconciled -- ADR-001 amendment 13).

The declared state of an environment on a target: its places (the layout), its ownership marker,
the compose file the declarations and the units' `current` releases generate, each service running
the image of its `current` release, and each env file and runtime config file holding exactly what
the repository says (compared by sha256 -- a value is never printed).

`drift` reads the host and returns each difference with the act that removes it. Reading changes
nothing (`targets --verify`). `targets --reconcile` prints those acts as its plan and applies them only
behind approval; a release is never chosen by it -- only what `current` already says is run.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
from dataclasses import dataclass
from typing import Callable

from lib import naming
from lib.delivery import preflight, running, stack
from lib.delivery.context import Delivery


@dataclass
class Drift:
    what: str
    fix: Callable[[], object] | None   # None: reported only (it is the owner's to resolve)


def _digest(data: bytes | None) -> str:
    return hashlib.sha256(data).hexdigest()[:12] if data is not None else "absent"


def _expected_compose(ctx: Delivery) -> bytes:
    docs = {}
    st = running.states(ctx)
    for s in running.services(ctx):
        state = st.get(s.id) or stack.State()
        if s.module is not None and not state.running:
            continue
        creds = sorted(running.credential_files(ctx, s)) if s.module else []
        docs[s.id] = stack.service_document(s, project=ctx.project, environment=ctx.environment, target=ctx.target,
                                            places=ctx.places, state=state, revision=state.release or "",
                                            credentials=creds, env_file=bool(s.secrets_folder))
    return stack.render(stack.compose_document(project=ctx.project, environment=ctx.environment, services=docs))


def drift(ctx: Delivery) -> list[Drift]:
    from lib.delivery import tree

    out: list[Drift] = []
    if not preflight.owned(ctx):
        out.append(Drift(f"ownership marker absent or another project's: {ctx.places.marker()}", None))
        return out
    dirs, _ = tree.places(ctx)
    for d in dirs:
        if not ctx.transport.exists(d):
            out.append(Drift(f"missing place: {d}", lambda d=d: ctx.transport.mkdir(d)))
    want = _expected_compose(ctx)
    have = ctx.transport.read(ctx.places.of("stackCompose"))
    if have != want:
        out.append(Drift(f"stack compose differs from the declarations ({_digest(have)} != {_digest(want)}): "
                         f"{ctx.places.of('stackCompose')}", lambda: running.regenerate(ctx)))
    st = running.states(ctx)
    restart: list[str] = []
    for s in running.services(ctx):
        state = st.get(s.id) or stack.State()
        if s.module is None or not state.running:
            continue
        unit = ctx.places.unit(s)
        env_want = running.env_file(ctx, s)
        if ctx.transport.read(unit["stackEnv"]) != env_want:
            out.append(Drift(f"{s.id}: env file differs ({_digest(ctx.transport.read(unit['stackEnv']))} != "
                             f"{_digest(env_want)}): {unit['stackEnv']}", lambda s=s: running.place_files(ctx, s)))
            restart.append(s.id)
        for item in s.runtime_config:
            if ctx.environment in (item.get("environments") or []):
                path = posixpath.join(unit["runtime"], str(item["to"]))
                local = (ctx.root / str(item["from"])).read_bytes() if (ctx.root / str(item["from"])).is_file() else None
                if ctx.transport.read(path) != local:
                    out.append(Drift(f"{s.id}: runtime config {item['to']} differs ({_digest(ctx.transport.read(path))} != "
                                     f"{_digest(local)})", lambda s=s: running.place_files(ctx, s)))
                    restart.append(s.id)
        if state.workspace or not ctx.commands["engine"]:
            continue
        name = naming.remote_container(ctx.project, ctx.environment, s.id)
        r = ctx.transport.exec(ctx.engine("inspect", "-f", "{{.Config.Image}}", name), readonly=True)
        image = r.out.strip() if r.code == 0 else ""
        expected = (naming.remote_image(ctx.project, ctx.environment, s.id, state.release) if s.kind == "build"
                    else (s.spec.get("static") or {}).get("image") or s.spec.get("image"))
        if image != expected:
            out.append(Drift(f"{s.id}: runs {image or 'nothing'}, its current release says {expected}", None))
            restart.append(s.id)
    if restart and ctx.commands["compose"]:
        ids = sorted(set(restart))
        out.append(Drift(f"to apply: up -d {' '.join(ids)}", lambda: (running.regenerate(ctx), running.up(ctx, ids))))
    return out


def report(items: list[Drift]) -> list[str]:
    return [f"{'fixable' if d.fix else 'owner   '}  {d.what}" for d in items]


def reconcile(ctx: Delivery) -> int:
    items = drift(ctx)
    for d in items:
        if d.fix is not None:
            d.fix()
    left = [d for d in items if d.fix is None]
    for d in left:
        ctx.out(f"[reconcile] not reconciled (the owner's): {d.what}")
    ctx.out(f"[reconcile] {len(items) - len(left)} applied, {len(left)} left")
    return 1 if left else 0


def as_json(items: list[Drift]) -> str:
    return json.dumps([{"what": d.what, "fixable": d.fix is not None} for d in items], indent=1)
