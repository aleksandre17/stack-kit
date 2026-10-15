"""dotnet-aspnet driver: arrives by declaration, and its absence changes nothing for others.

Held here:
  * the registry entry is complete and every declared script exists;
  * the shared hybrid runner reaches it through the declared ``hybrid.script`` — the
    runner itself names no new driver;
  * VS Code launch is built from the declared ``dotnet`` launch kind;
  * a project with no ``compose`` section validates (compose is optional).
"""
from __future__ import annotations

from pathlib import Path

from lib.modules import driver_registry
from lib.project_context import ProjectContext
from lib.validate_manifest import _validate_required
from lib.vscode_gen import LAUNCH_BUILDERS, build_launch_json
from conftest import PKG

DRIVER = "dotnet-aspnet"


def _manifest(path: str = "src/api", dotnet: dict | None = None) -> dict:
    module = {"type": DRIVER, "role": "api", "path": path, "secretsModule": "api"}
    if dotnet is not None:
        module["dotnet"] = dotnet
    return {"version": 2, "package": "kit", "secrets": "ops/config", "modules": {"api": module}}


class TestRegistryEntry:
    def test_registered_as_powershell_api_driver(self) -> None:
        entry = driver_registry()[DRIVER]
        assert entry["roles"] == ["api"]
        assert entry["runtime"] == "powershell"
        assert entry["deployKind"] == "artifact"
        assert entry["delivery"]["release"] == {"command": "deploy", "args": ["artifact"]}
        assert {"run", "check", "deploy"} <= set(entry["commands"])

    def test_declared_scripts_exist(self) -> None:
        entry = driver_registry()[DRIVER]
        for rel in [*entry["commands"].values(), entry["hybrid"]["script"]]:
            assert (PKG / "drivers" / DRIVER / rel).is_file(), rel

    def test_launch_kind_has_a_builder(self) -> None:
        assert driver_registry()[DRIVER]["vscode"]["launch"] in LAUNCH_BUILDERS


class TestHybridRunnerStaysDeclarative:
    def test_runner_names_no_new_driver(self) -> None:
        src = (PKG / "toolkit" / "hybrid" / "Invoke-HybridRun.ps1").read_text(encoding="utf-8")
        assert DRIVER not in src
        assert "Get-DriverHybridScript" in src

    def test_helper_reads_the_registry_declaration(self) -> None:
        src = (PKG / "lib" / "drivers.ps1").read_text(encoding="utf-8")
        assert "function Get-DriverHybridScript" in src
        assert DRIVER not in src


class TestVscodeLaunch:
    def test_single_csproj_is_found(self, tmp_path: Path) -> None:
        (tmp_path / "src" / "api").mkdir(parents=True)
        (tmp_path / "src" / "api" / "Api.csproj").write_text("<Project />", encoding="utf-8")
        ctx = ProjectContext(root=tmp_path, manifest=_manifest())
        configs = build_launch_json(ctx)["configurations"]
        dotnet = [c for c in configs if c.get("type") == "dotnet"]
        assert dotnet and dotnet[0]["projectPath"] == "${workspaceFolder}/src/api/Api.csproj"

    def test_declared_project_wins(self, tmp_path: Path) -> None:
        mod = tmp_path / "src" / "api"
        mod.mkdir(parents=True)
        (mod / "A.csproj").write_text("<Project />", encoding="utf-8")
        (mod / "B.csproj").write_text("<Project />", encoding="utf-8")
        ctx = ProjectContext(root=tmp_path, manifest=_manifest(dotnet={"project": "B.csproj"}))
        configs = [c for c in build_launch_json(ctx)["configurations"] if c.get("type") == "dotnet"]
        assert configs[0]["projectPath"].endswith("/src/api/B.csproj")

    def test_ambiguous_project_is_an_honest_absence(self, tmp_path: Path) -> None:
        mod = tmp_path / "src" / "api"
        mod.mkdir(parents=True)
        (mod / "A.csproj").write_text("<Project />", encoding="utf-8")
        (mod / "B.csproj").write_text("<Project />", encoding="utf-8")
        ctx = ProjectContext(root=tmp_path, manifest=_manifest())
        configs = build_launch_json(ctx)["configurations"]
        assert not [c for c in configs if c.get("type") == "dotnet"]


class TestComposeIsOptional:
    def test_manifest_without_compose_passes_required_checks(self) -> None:
        assert _validate_required(_manifest()) == []

    def test_no_compose_section_means_no_catalog_warning(self, tmp_path: Path) -> None:
        from lib.validate_manifest import _validate_project

        (tmp_path / "src" / "api").mkdir(parents=True)
        ctx = ProjectContext(root=tmp_path, manifest=_manifest())
        errs, warnings = _validate_project(ctx, driver_registry())
        assert not [m for m in [*errs, *warnings] if "compose.catalog" in m], (errs, warnings)

    def test_compose_without_catalog_is_still_refused(self) -> None:
        manifest = _manifest()
        manifest["compose"] = {}
        assert "compose: missing catalog" in _validate_required(manifest)


class TestCliReportsDriverFailure:
    """A PowerShell driver command that FAILS must make the CLI exit non-zero.

    The masked case is a failure that sets no $LASTEXITCODE - e.g. a parameter-binding
    error (an argument the script does not accept). The CLI used to print it and exit 0.
    """

    def test_binding_failure_exits_non_zero(self, tmp_path: Path) -> None:
        import json
        import os
        import shutil
        import subprocess

        import pytest

        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if not pwsh:
            pytest.skip("PowerShell not available")
        (tmp_path / "src" / "api").mkdir(parents=True)
        (tmp_path / "src" / "api" / "Api.csproj").write_text("<Project />", encoding="utf-8")
        (tmp_path / "ops" / "config" / "api").mkdir(parents=True)
        manifest = _manifest()
        manifest["package"] = os.path.relpath(PKG, tmp_path)
        (tmp_path / "stack-kit.json").write_text(json.dumps(manifest), encoding="utf-8")
        env = {**os.environ, "STACK_KIT_PROJECT_ROOT": str(tmp_path)}
        proc = subprocess.run(
            [pwsh, "-NoProfile", "-File", str(PKG / "cli" / "stack-kit.ps1"), "mod", "api", "check", "unexpected-positional"],
            capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
