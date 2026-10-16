"""Backups, and a restore that is verified -- not assumed (ADR-001 amendment 14).

How a store is dumped, restored into a throwaway database, queried and dropped is the store's
declaration (compose/infra-catalog.json `backup`: shell lines run INSIDE its container, so its
credentials are read there and never pass through the CLI). What the host checks after a restore is
its own (`stack.infra.backup.<store>`: `database`, `keep`, `anchors` [{query, equals | atLeast}]).

    backup   the dump, streamed on the server into {backups}/<store>/<UTC time>.<ext> (umask 077),
             with its sha256 beside it; then pruned to `keep`
    verify   the sha256 checked; the dump restored into stack_kit_restore_check_<time>_<random> (its
             files moved to names of their own, never over the source); each anchor queried there and
             compared; the throwaway database dropped -- always, pass, fail or error
    replay   the migration chain, from the first, applied to an empty throwaway database (a store that
             declares `create`, a migration service that declares `replay`); its anchors; dropped
    list     the dumps, newest first
"""
from __future__ import annotations

import posixpath
import secrets
import shlex
import time
from contextlib import contextmanager
from typing import Any, Iterator

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


def throwaway_name() -> str:
    """A database name no other check shares: the prefix, the UTC time and a random suffix."""
    return CHECK_PREFIX + time.strftime("%Y%m%d%H%M%S", time.gmtime()) + "_" + secrets.token_hex(4)


@contextmanager
def throwaway(ctx: Delivery, recipe: dict[str, Any], env: dict[str, str], *, cleanup: tuple[str, ...] = ()) -> Iterator[str]:
    """A throwaway database ($CHECK_DB) inside the store's container for the length of a check; dropped
    -- always, pass, fail or error -- by the store's `drop`, with any file the check put there."""
    c = _container(ctx, recipe)
    try:
        yield c
    finally:
        ctx.run(_exec_in(ctx, c, str(recipe.get("drop") or "true"), env), check=False)
        for inner in cleanup:
            ctx.run(_exec_in(ctx, c, f"rm -f {shlex.quote(inner)}", {}), check=False)


def _anchors(ctx: Delivery, store: str, recipe: dict[str, Any], c: str, env: dict[str, str],
             anchors: list[dict[str, Any]]) -> list[str]:
    failures = []
    for anchor in anchors:
        got = ctx.run(_exec_in(ctx, c, str(recipe["query"]), {**env, "ANCHOR": str(anchor["query"])}), check=False)
        if ctx.plan:
            continue  # a plan prints the query; it compares nothing
        why = f"query failed (exit {got.code})" if got.code != 0 else _compare(got.out, anchor)
        if why:
            failures.append(f"{store} anchor: {why}")
    return failures


def verify(ctx: Delivery, store: str, name: str = "") -> list[str]:
    """The failures of a restore check (empty: the dump restores and holds its anchors): the dump
    restored into a throwaway database of its own (never over the source), each anchor queried
    THERE, the database dropped whatever the outcome."""
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
                check=False, readonly=True)
    if r.code != 0:
        return [f"{f}: sha256 does not match its sidecar -- the dump is not what was taken"]
    check_db = throwaway_name()
    inner = posixpath.join(str(recipe.get("inContainerDir") or "/tmp"), "stack-kit-restore." + str(recipe.get("extension") or "dump"))
    env = {"CHECK_DB": check_db, "RESTORE_FILE": inner, **({"DB_NAME": str(host["database"])} if host.get("database") else {})}
    with throwaway(ctx, recipe, env, cleanup=(inner,)) as c:
        ctx.run(ctx.engine("cp", f, f"{c}:{inner}"))
        restored = ctx.run(_exec_in(ctx, c, str(recipe["restore"]), env), check=False)
        if restored.code != 0:
            return [f"{f}: the restore into {check_db} failed (exit {restored.code})"]
        failures = _anchors(ctx, store, recipe, c, env, anchors)
    if not failures and not ctx.plan:
        ctx.out(f"[backup] {store}: {posixpath.basename(f)} restores into a throwaway database and holds "
                f"{len(anchors)} anchor(s); the database is dropped")
    return failures


def replay(ctx: Delivery) -> list[str]:
    """A fresh-chain migration replay (`stack.migrate.replay`): every migration, from the first, applied
    by the migration service to an EMPTY throwaway database -- the chain a new environment would run,
    not the one the live database happens to have -- then the declared anchors queried there, then the
    database dropped whatever the outcome. The store declares how an empty database is made (`create`);
    the migration service declares how it is pointed at one (`replay`: `env` and a `urls` template per
    store, `{database}` filled)."""
    from lib.delivery import infra
    from lib.delivery.release import ship_migrations

    step = (ctx.manifest.get("stack") or {}).get("migrate") or {}
    how = step.get("replay") or {}
    if not step.get("service") or not how.get("store"):
        raise DeliveryError("stack.migrate.replay declares no store: nothing to replay the migrations against", 2)
    store, service = str(how["store"]), str(step["service"])
    recipe, _host = declared(ctx, store)
    if not recipe.get("create"):
        raise DeliveryError(f"infra '{store}' declares no `create` (compose/infra-catalog.json backup): it gives no "
                            f"empty database to replay into", 2)
    pointer = (_catalog(ctx).get(service) or {}).get("replay") or {}
    url = (pointer.get("urls") or {}).get(store)
    if not pointer.get("env") or not url:
        raise DeliveryError(f"the migration service '{service}' declares no replay against {store} "
                            f"(compose/infra-catalog.json `replay`: env, urls.{store})", 2)
    check_db = throwaway_name()
    env = {"CHECK_DB": check_db}
    with throwaway(ctx, recipe, env) as c:
        made = ctx.run(_exec_in(ctx, c, str(recipe["create"]), env), check=False)
        if made.code != 0:
            return [f"{store}: the empty database {check_db} could not be made (exit {made.code})"]
        ship_migrations(ctx, step)
        ran = ctx.run(infra.compose(ctx, "--profile", "migrate", "run", "--rm", "-e",
                                    f"{pointer['env']}={str(url).replace('{database}', check_db)}", service), check=False)
        if ran.code != 0:
            return [f"the migration chain failed on an empty database (exit {ran.code}): a fresh environment would not migrate"]
        failures = _anchors(ctx, store, recipe, c, env, list(how.get("anchors") or []))
    if not failures and not ctx.plan:
        ctx.out(f"[backup] the migration chain replays from empty into a throwaway {store} database"
                f"{' and holds ' + str(len(how.get('anchors') or [])) + ' anchor(s)' if how.get('anchors') else ''}; "
                f"the database is dropped")
    return failures
