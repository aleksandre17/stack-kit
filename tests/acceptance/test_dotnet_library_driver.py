"""dotnet-library driver: a .NET class library is a module of its own -- built, tested, linted and
audited by the scripts the .NET family shares, and never run, packaged, released or composed.

Held here:
  * its lifecycle commands are dotnet-aspnet's own scripts (drivers/_shared/dotnet), one home each;
  * it declares no run, package, container, dev, delivery, vscode or compose -- so nothing deploys it;
  * CI builds and tests it and packages nothing for it;
  * a manifest declaring it passes the required checks.
The real `dotnet build` / `dotnet test` of a library and its test project: tests/acceptance/test_lifecycle.py.
"""
from __future__ import annotations

from pathlib import Path

from lib.ci_gen import delivery_plan, render
from lib.delivery.model import all_services, deployable
from lib.modules import driver_commands, driver_registry
from lib.project_context import ProjectContext
from lib.validate_manifest import _validate_required

DRIVER = "dotnet-library"
SERVICE = "dotnet-aspnet"


def _manifest() -> dict:
    core = {"type": DRIVER, "role": "other", "path": "src/core", "secretsModule": "core",
            "dotnet": {"test": "../tests/Core.Tests.csproj"}}
    api = {"type": SERVICE, "role": "api", "path": "src/api", "secretsModule": "api"}
    return {"version": 2, "package": "kit", "secrets": "ops/config", "modules": {"core": core, "api": api}}


class TestRegistryEntry:
    def test_its_steps_are_the_dotnet_familys_shared_scripts(self) -> None:
        mine, service = driver_commands(DRIVER), driver_commands(SERVICE)
        assert set(mine) == {"check", "build", "test", "lint", "audit"}
        for step, script in mine.items():
            assert script.resolve() == service[step].resolve(), step  # one home: never a copy
            assert script.resolve().is_file() and script.resolve().parent.name == "dotnet", script

    def test_it_declares_nothing_that_runs_or_ships(self) -> None:
        entry = driver_registry()[DRIVER]
        assert entry["roles"] == ["other"]
        assert entry["delivery"] == {}  # no rung: nothing delivers it, said rather than left out
        for key in ("hybrid", "package", "container", "dev", "vscode", "compose", "detect"):
            assert key not in entry, key
        assert not {"run", "package"} & set(driver_commands(DRIVER))


class TestNothingDeploysIt:
    def test_it_is_not_deployable_and_has_no_service(self) -> None:
        manifest = _manifest()
        assert not deployable(manifest, "core") and deployable(manifest, "api")
        assert {s.module for s in all_services(manifest)} == {"api"}

    def test_ci_builds_and_tests_it_and_packages_nothing_for_it(self, tmp_path: Path) -> None:
        ctx = ProjectContext(root=tmp_path, manifest=_manifest())
        _chosen, promoted, reasons = delivery_plan(ctx)
        assert "core" not in promoted
        assert "core (dotnet-library): its driver declares no package step" in reasons
        ci = render(ctx)
        job = ci[ci.index("  core:"):ci.index("  api:")]
        for step in ("build", "test", "lint", "audit"):
            assert f"mod core {step}" in job, step
        assert "package" not in job and "actions/setup-dotnet" in job

    def test_a_manifest_declaring_it_passes_the_required_checks(self) -> None:
        assert _validate_required(_manifest()) == []
