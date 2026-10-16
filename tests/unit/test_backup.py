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
