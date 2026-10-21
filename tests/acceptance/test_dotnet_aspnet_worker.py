"""dotnet-aspnet serves `role: worker` as it serves `role: api` (ADR-001 amendment 26).

Held here:
  * the driver admits both roles and declares its health in the registry (`health`), the status of the
    probe and not a body holding `UP`; a worker declares the path its host answers (`container.healthPath`);
  * `validate` refuses a worker with no path, naming the module and the rule, and reads it from the registry;
  * the worker's release recipe probes that path for a 2xx; its remote-dev service is the api's;
  * CI health and the stack endpoints ask the declared path and judge the status only, the worker's port
    from the role's `portEnv` (WORKER_PORT, 8091);
  * Java's worker and a dotnet-aspnet api keep what they had.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from lib import package
from lib.ci_health import stack_health_targets
from lib.delivery.model import module_services
from lib.modules import driver_registry
from lib.project_context import ProjectContext
from lib.stack_endpoints import stack_endpoint_lines
from lib.validate_manifest import _validate_project, _validate_required
from conftest import PKG

DRIVER = "dotnet-aspnet"


def _manifest(health_path: str | None = "/health/ready") -> dict:
    worker = {"type": DRIVER, "role": "worker", "path": "src/evidence", "secretsModule": "evidence",
              "toolchain": {"version": "8.0"}}
    if health_path:
        worker["container"] = {"healthPath": health_path}
    api = {"type": DRIVER, "role": "api", "path": "src/api", "secretsModule": "api", "toolchain": {"version": "8.0"}}
    return {"version": 2, "package": "kit", "secrets": "ops/config", "modules": {"api": api, "evidence": worker}}


def _ctx(tmp_path: Path, manifest: dict) -> ProjectContext:
    (tmp_path / "kit").mkdir(exist_ok=True)
    for mod in manifest["modules"].values():
        (tmp_path / mod["path"]).mkdir(parents=True, exist_ok=True)
    return ProjectContext(root=tmp_path, manifest=manifest)


def _problems(tmp_path: Path, manifest: dict, registry: dict | None = None) -> list[str]:
    errs, _warnings = _validate_project(_ctx(tmp_path, manifest), registry or driver_registry())
    return errs


def _recipe(tmp_path: Path, manifest: dict, module: str) -> str:
    (svc,) = module_services(manifest, module)
    return package.recipe(tmp_path, manifest, svc, {}, artifact="app.dll")["Dockerfile"].decode()


class TestTheDriverDeclares:
    def test_it_serves_both_roles_and_judges_health_by_status(self) -> None:
        entry = driver_registry()[DRIVER]
        assert entry["roles"] == ["api", "worker"]
        assert entry["health"]["expect"] == "status" and "worker" in entry["health"]["pathRequired"]

    def test_java_declares_no_health_so_keeps_its_roles_defaults(self) -> None:
        assert "health" not in driver_registry()["java-boot"]


class TestValidate:
    def test_an_api_and_a_worker_with_a_path_validate(self, tmp_path: Path) -> None:
        manifest = _manifest()
        assert _validate_required(manifest) == [] and _problems(tmp_path, manifest) == []

    def test_a_worker_without_a_path_is_refused_naming_the_module_and_the_rule(self, tmp_path: Path) -> None:
        errs = [e for e in _problems(tmp_path, _manifest(None)) if "healthPath" in e]
        assert len(errs) == 1 and "modules.evidence" in errs[0] and DRIVER in errs[0] and "role worker" in errs[0]

    def test_an_api_needs_no_path_as_before(self, tmp_path: Path) -> None:
        assert not [e for e in _problems(tmp_path, _manifest()) if "modules.api" in e]

    def test_the_rule_is_read_from_the_registry_not_named_in_code(self, tmp_path: Path) -> None:
        registry = copy.deepcopy(driver_registry())
        registry[DRIVER]["health"]["pathRequired"] = []
        assert not [e for e in _problems(tmp_path, _manifest(None), registry) if "healthPath" in e]
        registry["java-boot"]["health"] = {"expect": "status", "pathRequired": ["worker"]}
        manifest = _manifest()
        manifest["modules"]["evidence"] = {"type": "java-boot", "role": "worker", "path": "src/evidence", "secretsModule": "evidence"}
        assert [e for e in _problems(tmp_path, manifest, registry) if "modules.evidence" in e and "healthPath" in e]


class TestItsRecipes:
    def test_the_release_recipe_probes_the_declared_path_for_a_2xx(self, tmp_path: Path) -> None:
        recipe = _recipe(tmp_path, _manifest(), "evidence")
        assert "GET /health/ready HTTP/1.0" in recipe and '" [23][0-9][0-9] "' in recipe and "UP" not in recipe.split("HEALTHCHECK")[1]
        assert "EXPOSE 8080" in recipe and "ASPNETCORE_URLS=http://+:8080" in recipe

    def test_the_remote_dev_service_is_the_apis_with_the_declared_path(self) -> None:
        manifest = _manifest()
        (worker,), (api,) = module_services(manifest, "evidence"), module_services(manifest, "api")
        assert worker.spec["healthPath"] == "/health/ready" and "healthPath" not in api.spec
        assert worker.dev == api.dev and worker.dev["command"][:3] == ["dotnet", "watch", "run"] and worker.dev["port"] == 8080

    def test_an_api_recipe_is_what_it_was(self, tmp_path: Path) -> None:
        recipe = _recipe(tmp_path, _manifest(), "api")
        assert "/dev/tcp/127.0.0.1/8080" in recipe and "GET" not in recipe


def _host(tmp_path: Path, manifest: dict, env: dict[str, str] | None = None) -> ProjectContext:
    kit = tmp_path / "kit" / "compose"
    kit.mkdir(parents=True)
    (kit / "stack-catalog.json").write_text((PKG / "compose" / "stack-catalog.json").read_text(encoding="utf-8"), encoding="utf-8")
    manifest["package"] = "kit"
    (tmp_path / "stack-kit.json").write_text(json.dumps(manifest), encoding="utf-8")
    for folder in ("api", "evidence"):
        d = tmp_path / "ops" / "config" / folder
        d.mkdir(parents=True)
        (d / ".env.dev").write_text("".join(f"{k}={v}\n" for k, v in (env or {}).items()) if folder == "evidence" else "", encoding="utf-8")
    return _ctx(tmp_path, manifest)


class TestHealthIsJudgedByStatus:
    def test_ci_health_asks_the_declared_path_on_the_workers_port_for_a_status(self, tmp_path: Path) -> None:
        ctx = _host(tmp_path, _manifest())
        by = {t.module_id: t for t in stack_health_targets(ctx)}
        assert by["evidence"].url == "http://127.0.0.1:8091/health/ready" and by["evidence"].expect == ""
        assert by["api"].url == "http://127.0.0.1:8090/health" and by["api"].expect == ""

    def test_the_workers_port_comes_from_the_roles_port_env(self, tmp_path: Path) -> None:
        ctx = _host(tmp_path, _manifest(), {"WORKER_PORT": "9191"})
        assert {t.module_id: t.url for t in stack_health_targets(ctx)}["evidence"] == "http://127.0.0.1:9191/health/ready"

    def test_the_stack_endpoints_show_the_declared_path(self, tmp_path: Path) -> None:
        lines = stack_endpoint_lines(_host(tmp_path, _manifest()))
        assert any("(evidence) -> http://localhost:8091/health/ready" in line for line in lines)

    def test_a_java_worker_is_still_judged_by_UP_on_the_actuator(self, tmp_path: Path) -> None:
        manifest = _manifest()
        manifest["modules"]["evidence"] = {"type": "java-boot", "role": "worker", "path": "src/evidence",
                                           "secretsModule": "evidence", "container": {"healthPath": "/x"}}
        by = {t.module_id: t for t in stack_health_targets(_host(tmp_path, manifest))}
        assert by["evidence"].url == "http://127.0.0.1:8091/actuator/health" and by["evidence"].expect == "UP"
