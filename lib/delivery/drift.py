"""Drift: the declared state of an environment against the host's, read-only (OpenGitOps:
declarative, versioned, applied by `deploy`, its drift reported by `targets --verify`).

The declared state: the compose file the declarations and the units' `current` releases generate,
each service running the image of its `current` release, and each env file and runtime config file
holding exactly what the repository says -- compared by sha256, a value never printed. Nothing is
changed here: a drift is undone by the verb that owns it (`deploy`, `release rollback`).
"""
from __future__ import annotations

import hashlib
import posixpath

from lib import naming
from lib.delivery import running, stack
from lib.delivery.context import Delivery


def _digest(data: bytes | None) -> str:
    return hashlib.sha256(data).hexdigest()[:12] if data is not None else "absent"


def expected_compose(ctx: Delivery, states: dict[str, stack.State]) -> bytes:
    docs = {}
    for s in running.services(ctx):
        state = states.get(s.id) or stack.State()
        if s.module is not None and not state.running:
            continue
        creds = sorted(running.credential_files(ctx, s)) if s.module else []
        docs[s.id] = stack.service_document(s, project=ctx.project, environment=ctx.environment, target=ctx.target,
                                            places=ctx.places, state=state, revision=state.release or "",
                                            credentials=creds, env_file=bool(s.secrets_folder),
                                            generated=sorted(running.generated(ctx, s)) if s.module else [])
    return stack.render(stack.compose_document(project=ctx.project, environment=ctx.environment, services=docs))


def drift(ctx: Delivery) -> list[str]:
    out: list[str] = []
    st = running.states(ctx)
    if not any(state.running for state in st.values()):
        return out  # nothing deployed in this environment yet: nothing to drift from
    have = ctx.transport.read(ctx.places.of("stackCompose"))
    want = expected_compose(ctx, st)
    if have != want:
        out.append(f"stack compose differs from the declarations ({_digest(have)} != {_digest(want)}): "
                   f"{ctx.places.of('stackCompose')}")
    for s in running.services(ctx):
        state = st.get(s.id) or stack.State()
        if s.module is None or not state.running:
            continue
        unit = ctx.places.unit(s)
        env_have, env_want = ctx.transport.read(unit["stackEnv"]), running.env_file(ctx, s)
        if env_have != env_want:
            out.append(f"{s.id}: env file differs ({_digest(env_have)} != {_digest(env_want)}): {unit['stackEnv']}")
        for item in s.runtime_config:
            if ctx.environment in (item.get("environments") or []):
                path = posixpath.join(unit["runtime"], str(item["to"]))
                src = ctx.root / str(item["from"])
                local = src.read_bytes() if src.is_file() else None
                remote = ctx.transport.read(path)
                if remote != local:
                    out.append(f"{s.id}: runtime config {item['to']} differs ({_digest(remote)} != {_digest(local)})")
        if state.workspace or not ctx.commands["engine"]:
            continue
        name = naming.remote_container(ctx.project, ctx.environment, s.id)
        r = ctx.transport.exec(ctx.engine("inspect", "-f", "{{.Config.Image}}", name), readonly=True)
        image = r.out.strip() if r.code == 0 else ""
        expected = (naming.remote_image(ctx.project, ctx.environment, s.id, state.release) if s.kind == "build"
                    else (s.spec.get("static") or {}).get("image") or s.spec.get("image"))
        if image != expected:
            out.append(f"{s.id}: runs {image or 'nothing'}, its current release says {expected}")
    return out
