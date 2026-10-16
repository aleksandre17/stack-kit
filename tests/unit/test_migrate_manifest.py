"""A host's own names the schema once spelled are carried, never lost (ADR-001 amendment 7)."""
from __future__ import annotations

import json

from lib.migrate_manifest import carry_host_shapes
from lib.schema_check import validate as schema_validate
from conftest import PKG


def _former() -> dict:
    return {
        "ci": {"integration": "ops/ci/run.sh", "ragSmoke": "ops/ci/rag-smoke.sh", "healthModules": ["api"]},
        "modules": {"api": {"type": "x", "role": "api", "path": "apps/api", "secretsModule": "api", "catalog": {"sourceEnv": "SRC"}, "derivation": {"phase": "p1"}}},
    }


def test_former_consumer_keys_are_carried_to_the_agnostic_homes():
    manifest = _former()
    changes = carry_host_shapes(manifest, apply=True)
    assert manifest["ci"] == {"integration": "ops/ci/run.sh", "healthModules": ["api"],
                              "scripts": {"ragSmoke": "ops/ci/rag-smoke.sh"}}
    assert manifest["modules"]["api"] == {"type": "x", "role": "api", "path": "apps/api", "secretsModule": "api", "extensions": {
        "catalog": {"sourceEnv": "SRC"}, "derivation": {"phase": "p1"}}}
    assert len(changes) == 3


def test_the_plan_writes_nothing():
    manifest = _former()
    assert carry_host_shapes(manifest, apply=False)
    assert manifest == _former()


def test_a_key_already_in_its_new_home_is_a_conflict_never_an_overwrite():
    manifest = _former()
    manifest["ci"]["scripts"] = {"ragSmoke": "ops/ci/kept.sh"}
    changes = carry_host_shapes(manifest, apply=True)
    assert manifest["ci"]["scripts"] == {"ragSmoke": "ops/ci/kept.sh"}
    assert manifest["ci"]["ragSmoke"] == "ops/ci/rag-smoke.sh"
    assert any("CONFLICT" in c for c in changes)


def test_the_schema_names_no_former_consumer_key():
    text = (PKG / "manifest.schema.json").read_text(encoding="utf-8")
    for word in ("rag", "chatCatalog", "derivation", "corpusQuality", "cutoverSource"):
        assert word not in text, word


def test_what_is_carried_is_what_the_schema_admits_and_the_former_shape_is_refused():
    schema = json.loads((PKG / "manifest.schema.json").read_text(encoding="utf-8"))
    ci_schema = schema["properties"]["ci"]
    module_schema = schema["properties"]["modules"]["additionalProperties"]
    former = _former()
    assert schema_validate(former["ci"], ci_schema), "the former ci shape still validates"
    assert schema_validate(former["modules"]["api"], module_schema), "the former module shape still validates"
    carry_host_shapes(former, apply=True)
    assert schema_validate(former["ci"], ci_schema) == []
    assert schema_validate(former["modules"]["api"], module_schema) == []


def test_a_development_run_s_lost_production_keys_are_named_per_folder(tmp_path):
    from lib.migrate_manifest import run_env_notices

    folder = tmp_path / "api-secrets"
    folder.mkdir()
    (folder / ".env.prod").write_text("DB_PASSWORD=prod-secret\nPORT=80\n", encoding="utf-8")
    (folder / ".env.dev").write_text("PORT=5000\n", encoding="utf-8")
    notices = run_env_notices(tmp_path, {"modules": {"api": {"secretsModule": "api-secrets"}}})
    assert len(notices) == 1 and "DB_PASSWORD" in notices[0] and "PORT" not in notices[0].split("--")[0]
    assert "prod-secret" not in notices[0]
