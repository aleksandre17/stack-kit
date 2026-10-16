"""Environment isolation by data source (ADR-001 amendment 16.6): two environments that name the same
server and database through a catalogued data-source key are refused by a deploy and reported by
validate, unless the sharing is declared with its reason; only the server and database are compared,
and no value is ever printed. Every value here is a fixture (example.test hosts, placeholder
credentials)."""
from __future__ import annotations

import json

import pytest

from delivery_host import commit, ctx_for, host, manifest_of, packaged, server
from lib import data_sources, identity
from lib.delivery import release
from lib.delivery.context import DeliveryError

KEY = "ConnectionStrings:Default"
MARK = "__DB_PASSWORD__"


@pytest.mark.parametrize("value, ident", [
    ("Server=tcp:db.example.test,1433;Database=Shop;User Id=app;Password=__DB_PASSWORD__", ("db.example.test:1433", "shop")),
    ("Data Source=DB01\\SQL;Initial Catalog=Shop;Integrated Security=true", ("db01\\sql", "shop")),
    ("postgres://app@pg.example.test:5432/shop?sslmode=require", ("pg.example.test:5432", "shop")),
    ("jdbc:sqlserver://sql.example.test:1433;databaseName=Shop;encrypt=true", ("sql.example.test:1433", "shop")),
    ("host=pg.example.test port=5433 dbname=shop user=app", ("pg.example.test:5433", "shop")),
    ("Server=(local);Database=Shop", ("localhost", "shop")),
    ("not a connection string", None),
])
def test_a_value_is_reduced_to_its_server_and_database(value, ident):
    assert data_sources.identity(value) == ident


def _project(tmp_path, monkeypatch, dev: str, staging: str, **config):
    root = host(tmp_path)
    (root / "ops" / "config" / "keys.json").write_text(json.dumps({"version": 1, "keys": [
        {"key": KEY, "sensitivity": "SECRET", "owner": "app", "allowedSource": "env file", "rotation": "yearly",
         "dataSource": True}]}), encoding="utf-8")
    m = manifest_of(root)
    m["config"] = {"keys": "ops/config/keys.json", **config}
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")
    for env, value in (("dev", dev), ("staging", staging)):
        f = root / "ops" / "config" / "edge" / f".env.{env}"
        f.write_text(f.read_text(encoding="utf-8") + f"ConnectionStrings__Default={value}\n", encoding="utf-8")
    commit(root, "with a data source")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
    return root


SAME_A = "Server=db.example.test;Database=Shop;User Id=dev;Password=__DB_PASSWORD__"
SAME_B = "Data Source=DB.EXAMPLE.TEST;Initial Catalog=shop;User Id=ops;Password=__DB_PASSWORD__"


def test_a_deploy_into_an_environment_that_shares_a_store_is_refused_and_prints_no_value(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch, SAME_A, SAME_B)
    t = server(tmp_path)
    with pytest.raises(DeliveryError, match="share a data source") as e:
        release.release(ctx_for(root, t), "edge", packaged(root))
    text = str(e.value)
    assert e.value.code == 4 and KEY in text and "dev" in text and "staging" in text
    assert MARK not in text and "db.example.test" not in text.lower() and "Shop" not in text
    assert not [x for x in t.log if x[0] == "exec" and " up -d " in " ".join(x[1])], "nothing started"


def test_validate_reports_the_sharing(tmp_path, monkeypatch):
    from lib.project_context import ProjectContext
    from lib.validate_manifest import _shared_data_sources

    root = _project(tmp_path, monkeypatch, SAME_A, SAME_B)
    found = _shared_data_sources(ProjectContext.discover(root))
    assert len(found) == 1 and "same server and database" in found[0] and MARK not in found[0]


def test_distinct_databases_and_the_none_sentinel_are_not_shared(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch, "Server=db.example.test;Database=ShopDev",
                    "Server=db.example.test;Database=Shop")
    assert release.shared_data_sources(ctx_for(root, server(tmp_path))) == []
    sentinel = f"Server={data_sources.SENTINEL_HOST};Database=none"
    root2 = _project(tmp_path / "s", monkeypatch, sentinel, sentinel)
    assert release.shared_data_sources(ctx_for(root2, server(tmp_path / "s"))) == []


def test_a_declared_sharing_with_its_reason_is_allowed(tmp_path, monkeypatch):
    shared = [{"key": KEY, "environments": ["dev", "staging"], "reason": "a read-only replica both use, by decision"}]
    root = _project(tmp_path, monkeypatch, SAME_A, SAME_B, sharedDataSources=shared)
    assert release.shared_data_sources(ctx_for(root, server(tmp_path))) == []


def test_a_value_in_the_shared_env_file_is_every_environments_store(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch, "", "")
    for env in ("dev", "staging"):
        f = root / "ops" / "config" / "edge" / f".env.{env}"
        f.write_text("".join(line + "\n" for line in f.read_text(encoding="utf-8").splitlines()
                             if not line.startswith("ConnectionStrings")), encoding="utf-8")
    (root / "ops" / "config" / "edge" / ".env").write_text(f"ConnectionStrings__Default={SAME_A}\n", encoding="utf-8")
    assert release.shared_data_sources(ctx_for(root, server(tmp_path)))


def test_a_runtime_config_file_is_read_where_the_application_reads_it(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch, "", "")
    for env in ("dev", "staging"):
        (root / "apps" / "edge" / f"settings.{env}.json").write_text(json.dumps(
            {"ConnectionStrings": {"Default": "Server=db.example.test;Database=Shop;Integrated Security=true"}}), encoding="utf-8")
    m = manifest_of(root)
    m["modules"]["edge"]["runtimeConfig"] = [
        {"from": f"apps/edge/settings.{env}.json", "to": "settings.json", "environments": [env]} for env in ("dev", "staging")]
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")
    found = release.shared_data_sources(ctx_for(root, server(tmp_path)))
    assert found and "apps/edge/settings.dev.json" in found[0] and "apps/edge/settings.staging.json" in found[0]
