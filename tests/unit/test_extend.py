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
    assert schema_check.validate(reg, schema) == []  # the shared shape (tests/unit/test_vendored.py)
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


def test_an_ignored_file_is_machine_state_not_an_undeclared_extension(root):
    import subprocess

    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    (root / ".gitignore").write_text("*.local.txt\n", encoding="utf-8")
    (root / "ops/compose/infra/services/notes.local.txt").write_text("x", encoding="utf-8")
    (root / "ops/compose/infra/services/more.local.txt").write_text("x", encoding="utf-8")
    found = extend.undeclared(root, manifest(root))
    assert not [u for u in found if u.endswith(".local.txt")], found  # every ignored file, not only the last


def test_a_driver_made_by_the_door_is_known_and_its_scripts_are_declared(root):
    # Found adopting a foreign project: `extend driver` wrote a registry the kit did not read
    # ("unknown driver" until `drivers.registry` was found in the reference), and the scripts every
    # driver needs were "in a place an extension point owns, but no point declares it".
    from lib.modules import compose_registry

    said = extend.make(root, manifest(root), "driver", "java-maven")
    assert (root / "ops/drivers/java-maven/container/Dockerfile").is_file()
    for step in ("build", "test"):
        script = root / f"ops/drivers/java-maven/ps1/{step}.ps1"
        assert script.is_file() and "<<pending:" in script.read_text(encoding="utf-8"), step
    from lib.modules import DEFAULT_PROJECT_REGISTRY

    assert "drivers" not in manifest(root), "nothing to declare: the reader's default is the writer's"
    assert extend.points()["driver-entry"]["host_path"].startswith("{drivers.registry|" + DEFAULT_PROJECT_REGISTRY + "}")
    entry = json.loads((root / "ops/drivers/registry.json").read_text(encoding="utf-8"))["java-maven"]
    assert entry["commands"] == {"build": "ps1/build.ps1", "test": "ps1/test.ps1"}
    registry, _ = compose_registry(root, manifest(root))
    assert "java-maven" in registry, "the door's driver is known the moment it exists"
    assert extend.undeclared(root, manifest(root)) == [], "its scripts are declared places"


def _modules_host(tmp_path, modules):
    r = tmp_path / "mod-host"
    r.mkdir()
    (r / "stack-kit.json").write_text(json.dumps({"version": 2, "modules": modules}), encoding="utf-8")
    return r


def test_init_lays_files_only_for_the_modules_the_host_has(tmp_path):
    # Found adopting a foreign project: `apps/backend/` and its env example were scaffolded for a
    # project with no backend, and the embedded worker row for a worker nobody declared.
    r = _modules_host(tmp_path, {"web": {"type": "node-vite", "role": "ui", "path": "web"}})
    said = extend.init(r)
    assert not (r / "apps").exists(), "no folder for a tier no module lives in"
    assert any("skipped -- no module lives in tier backend" in line for line in said)
    catalog = json.loads((r / "ops/compose/catalog.json").read_text(encoding="utf-8"))
    assert not any("backend" in k for k in catalog["targets"]) and catalog["features"]["worker"] is False
    assert any(k.startswith("web/") for k in catalog["targets"]), "the module it has is served"


def test_a_root_module_is_composed_from_its_own_declaration_and_stays_inside_the_repo(tmp_path):
    r = _modules_host(tmp_path, {"app": {"type": "java-boot", "role": "api", "path": "."}})
    extend.init(r)
    catalog = json.loads((r / "ops/compose/catalog.json").read_text(encoding="utf-8"))
    dev = catalog["targets"]["./docker-compose.dev.yml"] if "./docker-compose.dev.yml" in catalog["targets"] \
        else catalog["targets"]["docker-compose.dev.yml"]
    assert dev["manifestModule"] == "app" and "services" not in dev, "the module's own service, not a template's"
    assert extend.placed("<up:backend>/ops", {"modules": {"app": {"role": "api", "path": "."}}}) == "./ops"


def test_validate_refuses_a_compose_that_builds_from_a_recipe_that_is_not_there(tmp_path):
    from lib import compose_refs

    r = tmp_path / "refs"
    (r / "ops/compose").mkdir(parents=True)
    (r / "ops/compose/catalog.json").write_text(json.dumps({"targets": {"docker-compose.dev.yml": {}}}), encoding="utf-8")
    (r / "docker-compose.dev.yml").write_text(
        "services:\n  app:\n    build:\n      context: .\n      dockerfile: src/Dockerfile.dev\n", encoding="utf-8")
    found = compose_refs.problems(r, {})
    assert len(found) == 1 and "src/Dockerfile.dev, which is not there" in found[0]
    (r / "src").mkdir()
    (r / "src/Dockerfile.dev").write_text("FROM x", encoding="utf-8")
    assert compose_refs.problems(r, {}) == []
