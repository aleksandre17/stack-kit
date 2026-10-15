"""K3 — the host's tree is a declared layout, held as a floor (ADR-001 decision 3).

Proof owed by the ADR: the floor gate fails a missing declared place and names an undeclared one.
Every row the reference consumer gets is derived from what its manifest declares, so the cases
below change the manifest or the tree and read the verdict -- no path of the fixture is spelled
here except the ones a case creates.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PKG, WORKING_ROOT, kit_cli_env
from lib import identity
from lib.layout_floor import derived_rows, evaluate


@pytest.fixture
def host(tmp_path) -> Path:
    root = tmp_path / "floor-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    return root


def _manifest(root: Path) -> dict:
    return json.loads((root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))


def _write(root: Path, manifest: dict) -> None:
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def test_the_reference_consumer_stands_on_its_floor(host):
    floor = evaluate(host, _manifest(host))
    assert not floor.failures, floor.failures
    assert {r["declared_by"] for r in floor.rows} >= {"package", "secrets"}


def test_a_missing_module_directory_fails_naming_the_field_that_declares_it(host):
    manifest = _manifest(host)
    mid, cfg = next(iter(manifest["modules"].items()))
    shutil.rmtree(host / cfg["path"])
    failures = evaluate(host, manifest).failures
    assert any(f"modules.{mid}.path" in f and "missing" in f for f in failures), failures


def test_a_default_the_host_never_wrote_is_not_a_place():
    rows = derived_rows({"modules": {}})
    assert rows == [], "an undeclared convention was turned into a required place"


def test_a_pending_place_is_printed_not_failed(host):
    manifest = _manifest(host)
    manifest["layout"] = {"entries": [{"path": "docs/runbooks/", "kind": "dir", "pending": "K4"}]}
    floor = evaluate(host, manifest)
    assert not floor.failures
    assert any("docs/runbooks/" in p and "K4" in p for p in floor.pending)


def test_a_closed_directory_names_its_undeclared_child_and_admits_a_declared_one(host):
    manifest = _manifest(host)
    (host / "ops" / "stray").mkdir()
    (host / "ops" / "stray" / "notes.txt").write_text("x", encoding="utf-8")
    manifest["layout"] = {"closed": ["ops/"], "entries": [
        {"path": "ops/compose/", "kind": "dir"}, {"path": "ops/cli/", "kind": "dir"},
        {"path": "ops/ci/", "kind": "dir"}]}
    failures = evaluate(host, manifest).failures
    assert any(f.startswith("ops/stray/") for f in failures), failures
    others = [f for f in failures if not f.startswith("ops/stray/")]
    assert not others, f"a declared or manifest-derived child was named undeclared: {others}"

    manifest["layout"]["entries"].append({"path": "ops/stray/", "kind": "dir", "holds": "notes"})
    assert not evaluate(host, manifest).failures


def test_validate_exits_non_zero_on_a_floor_failure(host):
    manifest = _manifest(host)
    manifest["layout"] = {"entries": [{"path": "never/built/", "kind": "dir"}]}
    _write(host, manifest)
    env = kit_cli_env({identity.env_name("PROJECT_ROOT"): str(host)})
    ran = subprocess.run([sys.executable, "-B", str(PKG / "lib" / "validate_manifest.py")], cwd=host,
                         env=env, capture_output=True, text=True)
    assert ran.returncode == 1
    assert "layout: never/built/" in ran.stderr
