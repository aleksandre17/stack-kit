"""SSH tunnel forwards for stack-kit infra — manifest services + catalog port env keys."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def load_infra_catalog(*paths: Path) -> dict[str, Any]:
    merged: dict[str, Any] = {"modules": {}}
    for path in paths:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for mid, mod in (data.get("modules") or {}).items():
            merged["modules"][str(mid)] = mod
    return merged


def resolve_tunnel_forwards(
    *,
    service_ids: list[str],
    catalog: dict[str, Any],
    env_getter: Callable[[str, str], str | None],
) -> list[tuple[str, str]]:
    """
    Return (local_port, remote_port) pairs for ssh -L.
    Only services listed in service_ids with catalog tunnel[] entries.
    """
    return [(f["local"], f["remote"]) for f in tunnel_forwards(
        service_ids=service_ids, catalog=catalog, env_getter=env_getter)]


def tunnel_forwards(
    *,
    service_ids: list[str],
    catalog: dict[str, Any],
    env_getter: Callable[[str, str], str | None],
) -> list[dict[str, str]]:
    """Each forward with the service and the variable it came from: local, remote, service, env."""
    modules = catalog.get("modules") or {}
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for sid in service_ids:
        mod = modules.get(sid)
        if not mod:
            raise ValueError(
                f"stack.infra.services: unknown module '{sid}' — add to infra-catalog.json"
            )
        for spec in mod.get("tunnel") or []:
            if isinstance(spec, str):
                env_key = spec
                default = None
            else:
                env_key = str(spec.get("env") or "")
                default = spec.get("default")
            if not env_key:
                continue
            port = env_getter(env_key, str(default) if default is not None else "")
            if not port:
                raise ValueError(
                    f"infra tunnel: {env_key} not set in ops/config/infra/.env.dev "
                    f"(required for service '{sid}')"
                )
            if port in seen:
                continue
            seen.add(port)
            out.append({"local": port, "remote": port, "service": sid, "env": env_key})
    return out
