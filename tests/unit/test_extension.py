"""A project extends the kit by declaration alone, the kit untouched (ADR-001 amendment 12): an
environment (`staging`), a lifecycle step (`typecheck`), a role, a target runtime, a CI action pin, a
driver's launch configuration -- and a malformed registry is refused by name, never read as empty."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import PKG, WORKING_ROOT
from lib import catalogs, ci_gen, envfile, identity, targets
from lib.modules import DriverRegistryError, _read_registry
from lib.project_context import ProjectContext

STAGING = {"id": "staging", "after": "dev"}
TYPECHECK = {"id": "typecheck", "after": "lint", "optional": True}


def _host(tmp_path: Path, **manifest_extra) -> Path:
    root = tmp_path / "ext-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest.update(manifest_extra)
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _manifest(root: Path) -> dict:
    return json.loads((root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))


# ── staging: an environment, declared ────────────────────────────────────────

def test_an_environment_declared_by_the_host_is_one_in_every_place(tmp_path, monkeypatch):
    from lib.resolution import Resolver

    root = _host(tmp_path, catalogs={"environments": [STAGING]})
    manifest = _manifest(root)
    assert catalogs.ids("environments", manifest) == ["dev", "staging", "prod"]
    folder = next(iter(manifest["modules"].values()))["secretsModule"]
    (root / manifest["secrets"] / folder / ".env.staging").write_text("WHERE=staging\n", encoding="utf-8")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    r = Resolver(root)
    assert r.run_env(folder, "staging")["WHERE"] == "staging"
    assert (root / manifest["secrets"] / folder / ".env.staging") in r.env_files(folder, "staging")
    target = {"runtime": "docker-compose", "host": "h", "user": "u", "root": "/srv"}
    assert targets.render(target, "unit", project="p", environment="staging", service="s", tier="backend") == "/srv/p/staging/backend/s"
    with pytest.raises(ValueError, match="not 'qa'"):
        envfile.run_files(root / manifest["secrets"], folder, "qa", catalogs.ids("environments", manifest))


def test_cd_promotes_through_a_declared_environment_in_catalog_order(tmp_path, monkeypatch):
    root = _host(tmp_path, catalogs={"environments": [STAGING]}, deploy={"targets": "ops/deploy/targets.json"})
    t = {"runtime": "docker-compose", "host": "h", "user": "u", "root": "/srv"}
    (root / "ops" / "deploy").mkdir(parents=True)
    (root / "ops" / "deploy" / "targets.json").write_text(json.dumps({"schema": 1,
        "defaults": {"dev": "d", "staging": "s", "prod": "p"}, "targets": {"d": t, "s": t, "p": t}}), encoding="utf-8")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    text = ci_gen.render(ProjectContext.discover(root))
    assert "deploy-staging:" in text and "needs: [deploy-dev]" in text.split("deploy-staging:")[1].split("deploy-prod:")[0]
    assert "needs: [deploy-staging]" in text.split("deploy-prod:")[1]
    assert targets.problems(root, _manifest(root)) == []


# ── typecheck: a lifecycle step, declared ────────────────────────────────────

def test_a_lifecycle_step_declared_by_the_host_is_a_step_and_a_ci_step(tmp_path, monkeypatch):
    from lib.modules import compose_registry, lifecycle_steps, optional_steps

    registry = {"py-svc": {"label": "a typed service", "roles": ["api"], "commands": {"typecheck": "tc.py", "build": "b.py", "test": "t.py"}}}
    root = _host(tmp_path, catalogs={"lifecycle": [TYPECHECK]}, drivers={"registry": "ops/drivers/registry.json"})
    (root / "ops" / "drivers" / "py-svc").mkdir(parents=True)
    for s in ("tc.py", "b.py", "t.py"):
        (root / "ops" / "drivers" / "py-svc" / s).write_text("", encoding="utf-8")
    (root / "ops" / "drivers" / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    manifest = _manifest(root)
    manifest["modules"]["typed"] = {"type": "py-svc", "role": "api", "path": "apps/typed", "secretsModule": "typed"}
    (root / "apps" / "typed").mkdir(parents=True)
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    assert lifecycle_steps(manifest) == ["lint", "typecheck", "build", "test"]
    assert "typecheck" in optional_steps(manifest)
    job = ci_gen.render(ProjectContext.discover(root)).split("\n  typed:\n")[1]
    assert job.index("mod typed typecheck") < job.index("mod typed build")


# ── roles and target runtimes ────────────────────────────────────────────────

def test_a_role_declared_by_the_host_orders_the_stack_and_validates(tmp_path):
    from lib.validate_manifest import registry_problems

    manifest = {"catalogs": {"roles": [{"id": "edge", "deployOrder": 0}]}, "modules": {}}
    assert catalogs.ordered("roles", "deployOrder", manifest)[0] == "edge"
    reg = {"edge-proxy": {"label": "x", "roles": ["edge"], "commands": {}},
           "typo": {"label": "x", "roles": ["egde"], "commands": {}}}
    found = registry_problems(reg, manifest)
    assert any("typo.roles: 'egde' is not a declared role" in f for f in found)
    assert not any("edge-proxy" in f for f in found)


def test_a_target_runtime_declared_by_the_host_is_accepted_and_an_unknown_one_refused(tmp_path):
    root = _host(tmp_path, catalogs={"targetRuntimes": [{"id": "k8s"}]}, deploy={"targets": "ops/deploy/targets.json"})
    (root / "ops" / "deploy").mkdir(parents=True)
    doc = {"schema": 1, "targets": {"a": {"runtime": "k8s", "host": "h", "user": "u", "root": "/srv"},
                                    "b": {"runtime": "nomad", "host": "h", "user": "u", "root": "/srv"}}}
    (root / "ops" / "deploy" / "targets.json").write_text(json.dumps(doc), encoding="utf-8")
    found = targets.problems(root, _manifest(root))
    assert any("targets.b.runtime: 'nomad' is not a declared target runtime" in f for f in found), found
    assert not any("targets.a.runtime" in f for f in found)


# ── CI pins and launch configuration ─────────────────────────────────────────

def test_a_project_pins_its_own_action_by_sha_and_a_tag_is_refused(tmp_path):
    root = _host(tmp_path, ci={"actions": "ops/ci/actions.json"})
    (root / "ops" / "ci").mkdir(parents=True, exist_ok=True)
    good = {"actions": {"actions/setup-python": {"version": "v5.0.0", "sha": "a" * 40}}}
    (root / "ops" / "ci" / "actions.json").write_text(json.dumps(good), encoding="utf-8")
    pins = ci_gen._pins(ProjectContext.discover(root))
    assert pins["actions/setup-python"]["sha"] == "a" * 40 and "actions/checkout" in pins
    bad = {"actions": {"actions/setup-python": {"version": "v5", "sha": "v5"}}}
    (root / "ops" / "ci" / "actions.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ci_gen.UnpinnedAction, match="full 40-hex"):
        ci_gen._pins(ProjectContext.discover(root))


def test_a_driver_declares_its_launch_configuration_as_data(tmp_path, monkeypatch):
    from lib import vscode_gen

    registry = {"py-svc": {"label": "x", "roles": ["api"], "commands": {},
                           "vscode": {"launch": {"type": "debugpy", "request": "launch", "name": "{label}",
                                                 "cwd": "{path}", "module": "{module}.main"}}}}
    root = _host(tmp_path, drivers={"registry": "ops/drivers/registry.json"})
    (root / "ops" / "drivers").mkdir(parents=True)
    (root / "ops" / "drivers" / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    manifest = _manifest(root)
    manifest["modules"]["pysvc"] = {"type": "py-svc", "role": "api", "path": "apps/pysvc", "secretsModule": "pysvc"}
    (root / "apps" / "pysvc").mkdir(parents=True)
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    cfg = vscode_gen.LAUNCH_BUILDERS["data"](ProjectContext.discover(root), "pysvc", {})
    assert cfg == {"type": "debugpy", "request": "launch", "name": "pysvc", "cwd": "${workspaceFolder}/apps/pysvc",
                   "module": "pysvc.main"}


# ── the registry itself ──────────────────────────────────────────────────────

def test_the_kits_registry_honours_its_schema():
    from lib.modules import driver_registry
    from lib.validate_manifest import registry_problems

    assert registry_problems(driver_registry(), {}) == []


def test_a_misspelt_registry_field_is_refused():
    from lib.validate_manifest import registry_problems

    found = registry_problems({"x": {"label": "x", "commands": {}, "comands": {}}}, {})
    assert any("comands" in f for f in found), found


@pytest.mark.parametrize("text,why", [("{not json", "not JSON"), ("[]", "an object of drivers"),
                                      ('{"a": "b"}', "not a driver declaration")])
def test_a_malformed_registry_is_refused_by_name_never_read_as_empty(tmp_path, text, why):
    path = tmp_path / "registry.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(DriverRegistryError, match=why):
        _read_registry(path)
