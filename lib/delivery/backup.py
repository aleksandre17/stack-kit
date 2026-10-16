"""Backups, and a restore that is verified -- not assumed (ADR-001 amendment 14).

How a store is dumped, restored into a throwaway database, queried and dropped is the store's
declaration (compose/infra-catalog.json `backup`: shell lines run INSIDE its container, so its
credentials are read there and never pass through the CLI). What the host checks after a restore is
its own (`stack.infra.backup.<store>`: `database`, `keep`, `anchors` [{query, equals | atLeast}]).

    backup   the dump, streamed on the server into {backups}/<store>/<UTC time>.<ext> (umask 077),
             with its sha256 beside it; then pruned to `keep`
    verify   the sha256 checked; the dump restored into stack_kit_restore_check_<time>; each anchor
             queried and compared; the throwaway database dropped -- always, pass or fail
    list     the dumps, newest first
"""
from __future__ import annotations

import posixpath
import shlex
import time
from typing import Any

from lib import naming
from lib.delivery.context import Delivery, DeliveryError

CHECK_PREFIX = "stack_kit_restore_check_"


def _catalog(ctx: Delivery) -> dict[str, Any]:
    """The infra modules: the kit's catalog with the host's over it."""
    from lib.infra_tunnel import load_infra_catalog
    from lib.resolution import KIT_ROOT, Resolver

    return load_infra_catalog(KIT_ROOT / "compose" / "infra-catalog.json",
                              Resolver(ctx.root).infra_compose_dir() / "infra-catalog.json")["modules"]


def declared(ctx: Delivery, store: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(the store's backup recipe, the host's backup declaration for it)."""
    services = ((ctx.manifest.get("stack") or {}).get("infra") or {}).get("services") or []
    if store not in services:
        raise DeliveryError(f"'{store}' is not one of this project's infra services ({', '.join(services) or 'none'})", 2)
    entry = (_catalog(ctx).get(store) or {})
    recipe = entry.get("backup")
    if not recipe:
        raise DeliveryError(f"infra '{store}' declares no backup (compose/infra-catalog.json `backup`)", 2)
    host = (((ctx.manifest.get("stack") or {}).get("infra") or {}).get("backup") or {}).get(store) or {}
    return recipe, host


def _dir(ctx: Delivery, store: str) -> str:
    return posixpath.join(ctx.places.of("backups"), store)


def _container(ctx: Delivery, recipe: dict[str, Any]) -> str:
    return naming.remote_container(ctx.project, ctx.environment, str(recipe["container"]))


def _engine(ctx: Delivery) -> str:
    return " ".join(shlex.quote(a) for a in ctx.engine())


def _exec_in(ctx: Delivery, container: str, line: str, env: dict[str, str]) -> list[str]:
    envs = [a for k, v in sorted(env.items()) for a in ("-e", f"{k}={v}")]
    return [*ctx.engine("exec", *envs, container, "sh", "-c", line)]


def backup(ctx: Delivery, store: str) -> str:
    recipe, host = declared(ctx, store)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    d = _dir(ctx, store)
    f = posixpath.join(d, f"{stamp}.{recipe.get('extension') or 'dump'}")
    c = _container(ctx, recipe)
    env = {"DB_NAME": str(host.get("database") or "")} if host.get("database") else {}
    if recipe.get("inContainerDir"):  # a store that writes its own backup file (SQL Server)
        inner = posixpath.join(str(recipe["inContainerDir"]), posixpath.basename(f))
        ctx.run(_exec_in(ctx, c, str(recipe["dump"]), {**env, "DUMP_FILE": inner}))
        script = (f"umask 077; mkdir -p {shlex.quote(d)} && {_engine(ctx)} cp {shlex.quote(c + ':' + inner)} {shlex.quote(f)} "
                  f"&& sha256sum {shlex.quote(f)} > {shlex.quote(f + '.sha256')}")
    else:  # a store that dumps to stdout: streamed on the server, never through this machine
        dump = " ".join(shlex.quote(a) for a in _exec_in(ctx, c, str(recipe["dump"]), env))
        script = (f"umask 077; mkdir -p {shlex.quote(d)} && {dump} > {shlex.quote(f + '.partial')} "
                  f"&& mv {shlex.quote(f + '.partial')} {shlex.quote(f)} && sha256sum {shlex.quote(f)} > {shlex.quote(f + '.sha256')}")
    ctx.run(["sh", "-c", script])
    ctx.out(f"[backup] {store}: {f}")
    keep = int(host.get("keep") or 7)
    for old in listing(ctx, store)[keep:]:
        for p in (old, old + ".sha256"):
            if ctx.transport.exists(p):
                ctx.transport.remove(p)
    return f


def listing(ctx: Delivery, store: str) -> list[str]:
    d = _dir(ctx, store)
    return [posixpath.join(d, n) for n in sorted((n for n in ctx.transport.listdir(d) if not n.endswith((".sha256", ".partial"))),
                                                 reverse=True)]


def _compare(got: str, anchor: dict[str, Any]) -> str | None:
    value = got.strip().splitlines()[-1].strip() if got.strip() else ""
    if "equals" in anchor and value != str(anchor["equals"]):
        return f"{anchor['query']!r} gave {value!r}, expected {anchor['equals']!r}"
    if "atLeast" in anchor:
        try:
            if float(value) < float(anchor["atLeast"]):
                return f"{anchor['query']!r} gave {value}, expected at least {anchor['atLeast']}"
        except ValueError:
            return f"{anchor['query']!r} gave {value!r}, not a number"
    return None


def verify(ctx: Delivery, store: str, name: str = "") -> list[str]:
    """The failures of a restore check (empty: the dump restores and holds its anchors)."""
    recipe, host = declared(ctx, store)
    dumps = listing(ctx, store)
    f = posixpath.join(_dir(ctx, store), name) if name else (dumps[0] if dumps else "")
    if not f or not ctx.transport.exists(f):
        raise DeliveryError(f"no backup of {store} to verify ({name or 'none taken yet'})", 2)
    anchors = host.get("anchors") or []
    if not anchors:
        raise DeliveryError(f"stack.infra.backup.{store}.anchors declares nothing to check after a restore -- "
                            f"a restore nobody checks is not verified", 2)
    r = ctx.run(["sh", "-c", f"cd {shlex.quote(posixpath.dirname(f))} && sha256sum -c {shlex.quote(posixpath.basename(f) + '.sha256')}"],
                check=False)
    if r.code != 0:
        return [f"{f}: sha256 does not match its sidecar -- the dump is not what was taken"]
    c = _container(ctx, recipe)
    check_db = CHECK_PREFIX + time.strftime("%Y%m%d%H%M%S", time.gmtime())
    inner = posixpath.join(str(recipe.get("inContainerDir") or "/tmp"), "stack-kit-restore." + str(recipe.get("extension") or "dump"))
    env = {"CHECK_DB": check_db, "RESTORE_FILE": inner, **({"DB_NAME": str(host["database"])} if host.get("database") else {})}
    failures: list[str] = []
    try:
        ctx.run(ctx.engine("cp", f, f"{c}:{inner}"))
        restored = ctx.run(_exec_in(ctx, c, str(recipe["restore"]), env), check=False)
        if restored.code != 0:
            return [f"{f}: the restore into {check_db} failed (exit {restored.code})"]
        for anchor in anchors:
            got = ctx.run(_exec_in(ctx, c, str(recipe["query"]), {**env, "ANCHOR": str(anchor["query"])}), check=False)
            why = f"query failed (exit {got.code})" if got.code != 0 else _compare(got.out, anchor)
            if why:
                failures.append(f"{store} anchor: {why}")
    finally:
        ctx.run(_exec_in(ctx, c, str(recipe.get("drop") or "true"), env), check=False)
        ctx.run(_exec_in(ctx, c, f"rm -f {shlex.quote(inner)}", {}), check=False)
    if not failures:
        ctx.out(f"[backup] {store}: {posixpath.basename(f)} restores into a throwaway database and holds "
                f"{len(anchors)} anchor(s); the database is dropped")
    return failures
