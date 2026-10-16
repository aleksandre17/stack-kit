"""Extension points (ADR-001 amendment 15): a fixture host extends points, the composed result the
kit serves includes them, a pending answer shows, a changed template merges 3-way into a modified
host file (a conflict is reported, the host's file kept), an undeclared extension file is reported,
and every scaffold file is some point's template."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import PKG
from lib import catalogs, extend, schema_check


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "host"
    r.mkdir()
    extend.init(r)
    return r


def manifest(r: Path) -> dict:
    return json.loads((r / "stack-kit.json").read_text(encoding="utf-8"))


def test_the_registry_has_the_shared_shape():
    reg = json.loads((PKG / "config" / "extension-points.json").read_text(encoding="utf-8"))
    schema = json.loads((PKG / "config" / "extension-points.schema.json").read_text(encoding="utf-8"))
    assert schema_check.validate(reg, schema) == []
    ids = [p["id"] for p in reg["points"]]
    assert len(ids) == len(set(ids))
    for p in reg["points"]:
        assert (PKG / p["template"].split("<name>")[0]).exists(), p["template"]


def test_every_scaffold_file_is_a_points_template():
    out = subprocess.run(["git", "-C", str(PKG), "ls-files", "-co", "--exclude-standard", "scaffold"], capture_output=True, text=True)
    templates = {p["template"] for p in extend.points().values()}
    infra = {f"scaffold/ops/compose/infra/{f}" for m in json.loads((PKG / "compose/infra-catalog.json").read_text(encoding="utf-8"))
             ["modules"].values() for f in m.get("files") or []}
    orphans = [f for f in out.stdout.split() if f not in templates and f not in infra
               and not f.startswith("scaffold/ops/compose/infra/services/") and f not in ("scaffold/README.md",)
               and f != "scaffold/ops/compose/catalog.minimal.json"]
    assert not orphans, f"scaffold files no point serves: {orphans}"


def test_init_lays_down_its_points_and_the_selected_infra_only(root):
    assert (root / "stack-kit.json").is_file() and (root / "ops/cli/stack-kit.ps1").is_file()
    services = manifest(root)["stack"]["infra"]["services"]
    assert sorted(p.stem for p in (root / "ops/compose/infra/services").glob("*.yml")) == sorted(services)
    assert not (root / "ops/compose/infra/services/sqlserver.yml").exists(), "on demand, not a tree of files"
    assert extend.init(root) and not any(line.startswith("create") for line in extend.init(root)), "idempotent"


def test_an_extended_catalog_is_in_what_the_kit_serves_and_its_pending_answer_shows(root):
    said = extend.make(root, manifest(root), "catalog-environments", "staging", plan=True)
    assert said[0].startswith("plan: add stack-kit.json#/catalogs/environments/-") and "catalogs" not in manifest(root)
    extend.make(root, manifest(root), "catalog-environments", "staging")
    assert "staging" in catalogs.ids("environments", {**manifest(root), "catalogs": {"environments": [{"id": "staging"}]}})
    assert manifest(root)["catalogs"]["environments"][0]["id"] == "staging"
    row = next(r for r in extend.listing(root, manifest(root)) if r["point"]["id"] == "catalog-environments")
    assert row["status"] == "drafted" and row["pending"] == ["the environment it follows"]
    errors, notices = extend.problems(root, manifest(root))
    assert any("catalog-environments staging: pending -- the environment it follows" in n for n in notices) and not errors
    assert extend.make(root, manifest(root), "catalog-environments", "staging")[0].endswith("not overwritten")


def test_a_pending_answer_is_an_error_where_the_profile_requires_the_point(root):
    m = manifest(root)
    m["extend"] = {"profile": "release"}
    m["deploy"] = {"targets": "ops/deploy/targets.json"}
    (root / "stack-kit.json").write_text(json.dumps(m), encoding="utf-8")
    extend.make(root, m, "target", "edge")
    errors, _ = extend.problems(root, m)
    assert any("extension target edge: pending" in e for e in errors), errors


def test_a_changed_template_merges_into_a_modified_host_file_and_a_conflict_is_kept(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    for rel in ("config/extension-points.json", "compose/infra-catalog.json", "scaffold/ops/compose/infra/services/postgres.yml"):
        (kit / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PKG / rel, kit / rel)
    shutil.copytree(PKG / "config/extension-templates", kit / "config/extension-templates")
    monkeypatch.setattr(extend, "KIT", kit)
    monkeypatch.setattr(extend, "REGISTRY", kit / "config/extension-points.json")
    host = tmp_path / "h"
    host.mkdir()
    extend.make(host, {}, "infra-service", "postgres")
    f = host / "ops/compose/infra/services/postgres.yml"
    f.write_text(f.read_text(encoding="utf-8") + "# the host's own line\n", encoding="utf-8")
    t = kit / "scaffold/ops/compose/infra/services/postgres.yml"
    t.write_text(t.read_text(encoding="utf-8").replace("image: postgres:16-alpine", "image: postgres:17-alpine"), encoding="utf-8")
    assert extend.upgrade(host, plan=True)[0].startswith("plan: merge")
    extend.upgrade(host)
    text = f.read_text(encoding="utf-8")
    assert "postgres:17-alpine" in text and "# the host's own line" in text
    f.write_text(text.replace("postgres:17-alpine", "postgres:16.4-alpine"), encoding="utf-8")
    t.write_text(t.read_text(encoding="utf-8").replace("postgres:17-alpine", "postgres:18-alpine"), encoding="utf-8")
    said = extend.upgrade(host)
    assert "CONFLICT" in said[0] and "postgres:16.4-alpine" in f.read_text(encoding="utf-8")


def test_an_undeclared_extension_file_is_reported(root):
    (root / "ops/compose/infra/services/notes.txt").write_text("x", encoding="utf-8")
    assert "ops/compose/infra/services/notes.txt" in extend.undeclared(root, manifest(root))
    assert not [u for u in extend.undeclared(root, manifest(root)) if u.endswith(".yml")]
