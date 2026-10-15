"""K5 — configuration carries its sensitivity (ADR-001 decision 5).

Proof owed by the ADR: a secret-class key with a committed value is refused. Each case builds a
small host with a catalogue and one tracked file, and reads the verdict -- and no verdict ever
carries the value it found.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.config_keys import check, env_names

VALUE = "s3cr3t-value-that-must-never-be-printed"
SECRET = {"key": "Db:Password", "sensitivity": "SECRET", "owner": "ops", "allowedSource": "env",
          "rotation": "on staff change and every 90 days"}


def _host(tmp_path: Path, rows: list[dict], files: dict[str, str], **extra) -> tuple[Path, dict]:
    (tmp_path / "ops" / "config").mkdir(parents=True)
    (tmp_path / "ops" / "config" / "keys.json").write_text(
        json.dumps({"version": 1, "keys": rows, **extra}), encoding="utf-8")
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path, {"config": {"keys": "ops/config/keys.json"}}


@pytest.mark.parametrize("rel, text", [
    ("app/appsettings.json", json.dumps({"Db": {"Password": VALUE}})),
    ("app/application.yml", f"db:\n  password: {VALUE}\n"),
    ("ops/config/api/.env.example", f"Db__Password={VALUE}\n"),
    ("ops/config/api/.env.example", f"DB_PASSWORD='{VALUE}'\n"),
])
def test_a_committed_secret_is_refused_without_printing_it(tmp_path, rel, text):
    root, manifest = _host(tmp_path, [SECRET], {rel: text})
    verdict = check(root, manifest)
    assert any(rel in f and "Db:Password" in f for f in verdict.failures), verdict.failures
    assert all(VALUE not in f for f in verdict.failures + verdict.known)


@pytest.mark.parametrize("text", [
    "Db__Password=__FROM_SECRET_STORE__\n", "Db__Password=\n", "DB_PASSWORD=${DB_PASSWORD}\n",
])
def test_a_placeholder_or_a_reference_is_not_a_value(tmp_path, text):
    root, manifest = _host(tmp_path, [SECRET], {"ops/config/api/.env.example": text})
    assert check(root, manifest).failures == []


def test_a_known_exposure_is_printed_with_its_tracking_not_failed(tmp_path):
    rel = "app/appsettings.json"
    root, manifest = _host(tmp_path, [SECRET], {rel: json.dumps({"Db": {"Password": VALUE}})},
                           knownExposures=[{"key": "Db:Password", "file": rel, "tracking": "AIR-001"}])
    verdict = check(root, manifest)
    assert verdict.failures == []
    assert any("AIR-001" in k and rel in k for k in verdict.known)


def test_a_secret_states_its_rotation_and_has_no_default(tmp_path):
    rows = [{**SECRET, "rotation": None}, {**SECRET, "key": "Api:Token", "default": "abc"}]
    rows[0].pop("rotation")
    root, manifest = _host(tmp_path, rows, {})
    failures = check(root, manifest).failures
    assert any("declares no rotation" in f for f in failures)
    assert any("declares a default" in f for f in failures)


def test_the_catalogue_is_held_to_its_shape(tmp_path):
    root, manifest = _host(tmp_path, [{**SECRET, "sensitivity": "TOP"}, {"key": "X"}], {})
    failures = check(root, manifest).failures
    assert any("sensitivity" in f for f in failures)
    assert any("missing required 'owner'" in f for f in failures)


def test_a_host_without_a_catalogue_is_not_judged(tmp_path):
    assert check(tmp_path, {}).failures == []
    assert check(tmp_path, {"config": {"keys": "nope.json"}}).failures, "a named catalogue that is missing passed"


def test_environment_spellings_of_a_key():
    assert {"Db__Password", "DB_PASSWORD"} <= env_names(SECRET)
    assert "SPRING_DATASOURCE_PASSWORD" in env_names({"key": "spring.datasource.password"})
    assert "EXTRA" in env_names({"key": "a.b", "env": ["EXTRA"]})


def test_validate_refuses_a_committed_secret(tmp_path):
    import shutil

    from conftest import WORKING_ROOT
    from lib import identity
    from lib.validate_manifest import validate_manifest

    host = tmp_path / "keys-host"
    shutil.copytree(WORKING_ROOT, host, symlinks=True)
    mf = host / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["config"] = {"keys": "ops/config/keys.json"}
    mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (host / "ops" / "config" / "keys.json").write_text(json.dumps({"version": 1, "keys": [SECRET]}), encoding="utf-8")
    (host / "ops" / "config" / "api" / ".env.example").write_text(f"Db__Password={VALUE}\n", encoding="utf-8")
    errs, _ = validate_manifest(host)
    assert any(e.startswith("config: ") and "Db:Password" in e for e in errs), errs
    assert all(VALUE not in e for e in errs)
