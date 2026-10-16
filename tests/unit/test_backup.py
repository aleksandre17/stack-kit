"""Backup and a verified restore (ADR-001 amendment 14), against a recorded server: the dump streams
on the server into the layout's backups place with its sha256; a restore goes into a throwaway
database, each anchor is compared, and the database is dropped whatever the outcome; credentials
stay inside the store's container."""
from __future__ import annotations

import json

import pytest

from delivery_host import ROOT, commit, ctx_for, host, manifest_of, server
from lib import identity
from lib.delivery import backup
from lib.delivery.context import DeliveryError
from lib.delivery.transport import Result


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = host(tmp_path)
    m = manifest_of(root)
    m["stack"] = {"infra": {"services": ["postgres"], "backup": {"postgres": {
        "keep": 2, "anchors": [{"query": "select count(*) from orders", "atLeast": 1}, {"query": "select 1", "equals": "1"}]}}}}
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")
    commit(root, "with infra")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
    return root


def _answers(rows: str = "5"):
    def answer(argv, cwd, env):
        line = " ".join(argv)
        if "psql" in line and "select count" in line:
            return Result(0, rows + "\n")
        if "psql" in line:
            return Result(0, "1\n")
        return Result(0)
    return answer


def test_a_backup_streams_on_the_server_with_its_sha256_and_is_pruned(project, tmp_path):
    t = server(tmp_path)
    t.responses = _answers()
    ctx = ctx_for(project, t)
    f = backup.backup(ctx, "postgres")
    assert f.startswith(f"{ROOT}/shop/staging/backups/postgres/") and f.endswith(".dump")
    script = [e[1][2] for e in t.log if e[0] == "exec" and e[1][:2] == ("sh", "-c")][0]
    assert "umask 077" in script and "pg_dump -Fc" in script and "shop-staging-postgres" in script
    assert "sha256sum" in script and ".partial" in script and "PASSWORD" not in script.replace("$POSTGRES", "")


def test_a_restore_is_checked_against_its_anchors_and_the_throwaway_database_always_dropped(project, tmp_path):
    t = server(tmp_path)
    t.write(f"{ROOT}/shop/staging/backups/postgres/20261016T000000Z.dump", b"dump")
    t.responses = _answers()
    ctx = ctx_for(project, t)
    assert backup.verify(ctx, "postgres") == []
    steps = [" ".join(e[1]) for e in t.log if e[0] == "exec"]
    order = [next(i for i, s in enumerate(steps) if k in s) for k in ("sha256sum -c", "pg_restore", "select count", "dropdb")]
    assert order == sorted(order)
    assert any(f"CHECK_DB={backup.CHECK_PREFIX}" in s for s in steps)
    t.log.clear()
    t.responses = _answers(rows="0")
    failures = backup.verify(ctx, "postgres")
    assert failures and "expected at least 1" in failures[0]
    assert any("dropdb" in " ".join(e[1]) for e in t.log if e[0] == "exec"), "dropped even when an anchor fails"


def test_a_restore_without_anchors_is_not_called_verified(project, tmp_path):
    m = manifest_of(project)
    m["stack"]["infra"]["backup"]["postgres"]["anchors"] = []
    (project / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")
    t = server(tmp_path)
    t.write(f"{ROOT}/shop/staging/backups/postgres/20261016T000000Z.dump", b"dump")
    with pytest.raises(DeliveryError, match="nobody checks is not verified"):
        backup.verify(ctx_for(project, t), "postgres")


# ── SQL Server restores into a throwaway database too; the chain replays from empty (amendment 16.3) ──
# Proven against the recorded transport only: unproven against a real SQL Server or Postgres.

def _with(project, services, **stack):
    m = manifest_of(project)
    m["stack"] = {"infra": {"services": services, "backup": {s: {"database": "Shop", "anchors": [
        {"query": "select count(*) from orders", "atLeast": 1}]} for s in services}}, **stack}
    (project / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")


def _sql_answers(rows: str = "5", restore: int = 0):
    def answer(argv, cwd, env):
        line = " ".join(argv)
        if "RESTORE DATABASE" in line:
            return Result(restore)
        if "select count" in line:
            return Result(0, rows + "\n")
        return Result(0)
    return answer


def test_sql_server_restores_with_move_into_a_throwaway_database_queried_there_and_dropped(project, tmp_path):
    _with(project, ["sqlserver"])
    t = server(tmp_path)
    t.write(f"{ROOT}/shop/staging/backups/sqlserver/20261016T000000Z.bak", b"bak")
    t.responses = _sql_answers()
    assert backup.verify(ctx_for(project, t), "sqlserver") == []
    steps = [" ".join(e[1]) for e in t.log if e[0] == "exec"]
    restore = next(s for s in steps if "RESTORE DATABASE" in s)
    assert "VERIFYONLY" not in " ".join(steps)
    assert "RESTORE FILELISTONLY" in restore and "WITH $MOVES, CHECKSUM, RECOVERY" in restore and "MOVE N" in restore
    query = next(s for s in steps if "select count" in s)
    assert '-d "$CHECK_DB"' in query and "DB_NAME" not in query.split("sqlcmd", 1)[1], "anchors ask the restored copy, never the source"
    drop = next(s for s in steps if "DROP DATABASE" in s)
    assert steps.index(drop) > steps.index(query)
    assert "PASSWORD" not in " ".join(steps).replace("$MSSQL_SA_PASSWORD", "").replace("SQLCMDPASSWORD", "")
    names = {a.split("=", 1)[1] for s in steps for a in s.split() if a.startswith("CHECK_DB=")}
    assert len(names) == 1 and next(iter(names)).startswith(backup.CHECK_PREFIX)


def test_the_throwaway_database_is_dropped_when_the_restore_fails_or_errors(project, tmp_path):
    _with(project, ["sqlserver"])
    t = server(tmp_path)
    t.write(f"{ROOT}/shop/staging/backups/sqlserver/20261016T000000Z.bak", b"bak")
    t.responses = _sql_answers(restore=1)
    failures = backup.verify(ctx_for(project, t), "sqlserver")
    assert failures and "restore into" in failures[0]
    assert any("DROP DATABASE" in " ".join(e[1]) for e in t.log if e[0] == "exec")

    def broken(argv, cwd, env):
        if "RESTORE DATABASE" in " ".join(argv):
            raise RuntimeError("connection lost")
        return Result(0)
    t.log.clear()
    t.responses = broken
    with pytest.raises(RuntimeError):
        backup.verify(ctx_for(project, t), "sqlserver")
    assert any("DROP DATABASE" in " ".join(e[1]) for e in t.log if e[0] == "exec"), "dropped in a finally"


def test_two_checks_never_share_a_throwaway_name():
    assert len({backup.throwaway_name() for _ in range(50)}) == 50


def _replay_project(project, store="postgres", **replay):
    from lib import extend

    (project / "db" / "migrations").mkdir(parents=True, exist_ok=True)
    (project / "db" / "migrations" / "V1__init.sql").write_text("create table orders (id int);", encoding="utf-8")
    _with(project, [store, "flyway"], migrate={"service": "flyway", "files": "db/migrations",
                                               "replay": {"store": store, **replay}})
    m = manifest_of(project)
    for svc in (store, "flyway"):
        extend.make(project, m, "infra-service", svc)
    extend.make(project, m, "init-ops-compose-infra-docker-composebaseyml")


def test_the_migration_chain_replays_from_empty_into_a_throwaway_database(project, tmp_path):
    _replay_project(project, anchors=[{"query": "select count(*) from orders", "atLeast": 0}])
    t = server(tmp_path)
    t.responses = _answers()
    assert backup.replay(ctx_for(project, t)) == []
    steps = [" ".join(e[1]) for e in t.log if e[0] == "exec"]
    created = next(i for i, s in enumerate(steps) if "createdb" in s)
    migrated = next(i for i, s in enumerate(steps) if "run --rm" in s)
    queried = next(i for i, s in enumerate(steps) if "select count" in s)
    dropped = next(i for i, s in enumerate(steps) if "dropdb" in s)
    assert created < migrated < queried < dropped
    check_db = next(a.split("=", 1)[1] for a in steps[created].split() if a.startswith("CHECK_DB="))
    assert f"FLYWAY_URL=jdbc:postgresql://postgres:5432/{check_db}" in steps[migrated], "the chain runs against the empty copy"


def test_a_chain_that_fails_on_empty_is_reported_and_the_database_still_dropped(project, tmp_path):
    _replay_project(project)
    t = server(tmp_path)

    def answer(argv, cwd, env):
        return Result(1) if "run --rm" in " ".join(argv) else Result(0)
    t.responses = answer
    failures = backup.replay(ctx_for(project, t))
    assert failures and "fresh environment would not migrate" in failures[0]
    assert any("dropdb" in " ".join(e[1]) for e in t.log if e[0] == "exec")


def test_a_replay_needs_a_store_that_makes_an_empty_database_and_a_tool_that_points_at_one(project, tmp_path):
    _replay_project(project, store="redis")
    with pytest.raises(DeliveryError, match="declares no backup|declares no `create`"):
        backup.replay(ctx_for(project, server(tmp_path)))
    m = manifest_of(project)
    m["stack"]["migrate"].pop("replay")
    (project / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(DeliveryError, match="declares no store"):
        backup.replay(ctx_for(project, server(tmp_path)))


def test_a_planned_replay_prints_every_step_and_changes_nothing(project, tmp_path):
    _replay_project(project)
    t = server(tmp_path)
    ctx = ctx_for(project, t)
    lines = []
    ctx.out = lines.append
    assert backup.replay(ctx.dry()) == []
    assert not [e for e in t.log if e[0] == "exec"], "a plan runs nothing on the server"
    text = "\n".join(lines)
    assert "createdb" in text and "run --rm" in text and "dropdb" in text
