"""K7b — a project may declare its own drivers (ADR-001 decision 7).

Proof owed by the ADR: a project driver is found, and an id collision is refused. The project
driver here is a one-command driver whose script prints a marker; it is found through the composed
registry by Python, bash and PowerShell alike, and run by the kit's own driver dispatch.
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
from lib.modules import DriverCollision, _read_registry, compose_registry

KIT_DRIVER = next(iter(_read_registry(PKG / "drivers" / "registry.json")))
OWN = "project-sample"


def _host(tmp_path: Path, driver_id: str = OWN) -> Path:
    root = tmp_path / "drivers-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    reg = root / "ops" / "drivers"
    (reg / driver_id / "sh").mkdir(parents=True)
    (reg / driver_id / "sh" / "check.sh").write_text("echo project-driver-ran\n", encoding="utf-8")
    (reg / "registry.json").write_text(json.dumps({driver_id: {
        "label": "a project's own driver", "roles": ["worker"],
        "commands": {"check": "sh/check.sh"}}}), encoding="utf-8")
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["drivers"] = {"registry": "ops/drivers/registry.json"}
    manifest["modules"]["own"] = {"type": driver_id, "path": "apps/own", "secretsModule": "own", "role": "worker"}
    (root / "apps" / "own").mkdir(parents=True)
    mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


def test_a_project_driver_is_composed_with_the_kits(tmp_path):
    root = _host(tmp_path)
    manifest = json.loads((root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    registry, homes = compose_registry(root, manifest)
    assert OWN in registry and KIT_DRIVER in registry
    assert homes[OWN] == root / "ops" / "drivers" / OWN


def test_an_id_the_kit_already_has_is_refused(tmp_path):
    root = _host(tmp_path, driver_id=KIT_DRIVER)
    manifest = json.loads((root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    with pytest.raises(DriverCollision, match=KIT_DRIVER):
        compose_registry(root, manifest)
    env = kit_cli_env({identity.env_name("PROJECT_ROOT"): str(root)})
    ran = subprocess.run([sys.executable, "-B", str(PKG / "lib" / "validate_manifest.py")], cwd=root, env=env,
                         capture_output=True, text=True)
    assert ran.returncode == 1 and "drivers:" in ran.stderr and KIT_DRIVER in ran.stderr


def test_the_resolver_and_validate_find_the_project_driver(tmp_path):
    root = _host(tmp_path)
    env = kit_cli_env({identity.env_name("PROJECT_ROOT"): str(root)})
    ran = subprocess.run([sys.executable, "-B", str(PKG / "lib" / "resolve_cli.py"), "context"], cwd=root,
                         env=env, capture_output=True, text=True)
    assert ran.returncode == 0, ran.stderr
    ctx = json.loads(ran.stdout)["context"]
    assert Path(ctx[f"driver:{OWN}:command:check"]) == root / "ops" / "drivers" / OWN / "sh" / "check.sh"
    assert ctx["module:own:type"] == OWN
    ran = subprocess.run([sys.executable, "-B", str(PKG / "lib" / "resolve_cli.py"), "driver-command", "own", "check"],
                         cwd=root, env=env, capture_output=True, text=True)
    assert ran.returncode == 0, ran.stderr
    assert Path(ran.stdout.strip()) == root / "ops" / "drivers" / OWN / "sh" / "check.sh"
