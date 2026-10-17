"""A manifest is drafted from the tree by the evidence each driver declares (ADR-001 amendment 10):
nothing true of every host is written by hand in each, and nothing a host declared is overwritten."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib import draft as drafter
from lib.layout_floor import evaluate

CSPROJ_WEB = '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>\n'
CSPROJ_TEST = ('<Project Sdk="Microsoft.NET.Sdk"><ItemGroup><PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />'
               '</ItemGroup><ItemGroup><ProjectReference Include="..\\..\\api\\Acme.Api.csproj" /></ItemGroup></Project>\n')

#: The host's manifest as its owner keeps it (modules, aliases, commands): what a draft must equal.
SHOP_MODULES = {
    "api": {"type": "dotnet-aspnet", "role": "api", "path": "platform/apps/shop/backend/api", "secretsModule": "api",
            "dotnet": {"project": "Acme.Api.csproj", "launchProfile": "http", "configuration": "Release",
                       "publishExpect": ["Acme.Api.dll", "web.config", "wwwroot/index.html"],
                       "test": "../tests/api/Acme.Api.Tests.csproj"},
            "toolchain": {"version": "8.0.x"}},
    "web": {"type": "node-spa", "role": "ui", "path": "platform/apps/shop/frontend/web", "secretsModule": "web",
            "node": {"scripts": {"test": "test:ci"}}},
}


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def dotnet_angular_shaped(tmp_path: Path) -> Path:
    return _tree(tmp_path / "shop", {
        "platform/apps/shop/Acme.sln": 'Project("{x}") = "Acme.Api", "backend\\api\\Acme.Api.csproj"\n',
        "platform/apps/shop/backend/api/Acme.Api.csproj": CSPROJ_WEB,
        "platform/apps/shop/backend/api/Program.cs": "var app = 1;\n",
        "platform/apps/shop/backend/tests/api/Acme.Api.Tests.csproj": CSPROJ_TEST,
        "platform/apps/shop/frontend/web/package.json": json.dumps({"scripts": {"build": "ng build", "test": "ng test"}}),
        "platform/apps/shop/frontend/web/angular.json": "{}",
        "platform/apps/shop/frontend/web/node_modules/vite/package.json": '{"dependencies": {"express": "4"}}',
        "platform/kits/stack-kit/tests/fixtures/x/package.json": '{"dependencies": {"express": "4"}}',
        "node_modules/some-server/package.json": '{"dependencies": {"express": "4"}}',  # dependencies are never evidence
        "ops/cli/stack-kit.ps1": "# launcher\n",
        "ops/config/README.md": "config\n",
        "docs/README.md": "docs\n",
    })


def gradle_services_shaped(tmp_path: Path) -> Path:
    boot = "plugins { id 'org.springframework.boot' version '3.3.0' }\n"
    return _tree(tmp_path / "orders", {
        "platform/apps/orders/backend/settings.gradle": "include 'gateway', 'billing', 'reports'\n",
        "platform/apps/orders/backend/build.gradle": "plugins { id 'org.springframework.boot' version '3.3.0' apply false }\n",
        "platform/apps/orders/backend/gateway/build.gradle": boot,
        "platform/apps/orders/backend/billing/build.gradle": boot,
        "platform/apps/orders/backend/reports/build.gradle": boot,
        "ops/cli/stack-kit.ps1": "# launcher\n",
    })


def _leaves(node, at: str = "") -> dict:
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            out.update(_leaves(v, f"{at}.{k}" if at else k))
        return out
    return {at: json.dumps(node)}


def _draft(root: Path, existing: dict | None = None) -> dict:
    existing = {"package": "platform/kits/stack-kit", **(existing or {})}
    return drafter.draft(root, existing)


def test_a_dotnet_and_angular_tree_drafts_the_hosts_modules(tmp_path):
    root = dotnet_angular_shaped(tmp_path)
    modules = _draft(root)["modules"]
    assert set(modules) == {"api", "web"}, modules
    for mid, drafted in modules.items():
        declared = SHOP_MODULES[mid]
        for field in ("type", "role", "path", "secretsModule"):
            assert drafted[field] == declared[field], (mid, field)
    assert modules["api"]["dotnet"] == {"project": "Acme.Api.csproj",
                                        "test": "../tests/api/Acme.Api.Tests.csproj"}


def test_merged_over_the_hosts_manifest_the_draft_changes_nothing_declared(tmp_path):
    root = dotnet_angular_shaped(tmp_path)
    existing = {"version": 2, "package": "platform/kits/stack-kit", "secrets": "ops/config/projects/shop/services",
                "modules": SHOP_MODULES, "cli": {"aliases": {"api": "api", "web": "web"}},
                "commands": {"build": "pwsh ops/cli/stack-kit.ps1 build", "test": "pwsh ops/cli/stack-kit.ps1 test"},
                "vscode": {"folder": ".vscode", "cliScript": "ops/cli/stack-kit.ps1"}}
    merged, added = drafter.merge(existing, drafter.draft(root, existing))
    assert _leaves(existing).items() <= _leaves(merged).items(), "a declared field changed"
    assert added == ['+ commands.test-api: "pwsh ops/cli/stack-kit.ps1 mod api test"',
                     '+ commands.test-web: "pwsh ops/cli/stack-kit.ps1 mod web test"',
                     '+ commands.lint: "pwsh ops/cli/stack-kit.ps1 lint"',
                     '+ commands.validate: "pwsh ops/cli/stack-kit.ps1 validate"', '+ layout: {"profile": "monorepo"}'], added


def test_a_multi_service_gradle_build_is_one_java_boot_module(tmp_path):
    modules = _draft(gradle_services_shaped(tmp_path))["modules"]
    assert modules == {"backend": {"type": "java-boot", "role": "api", "path": "platform/apps/orders/backend",
                                   "secretsModule": "backend"}}, modules


def test_a_directory_two_drivers_claim_is_refused_naming_both(tmp_path):
    root = _tree(tmp_path / "amb", {"web/package.json": "{}", "web/angular.json": "{}", "web/vite.config.ts": ""})
    with pytest.raises(drafter.DraftRefused, match="claimed by node-spa, node-vite"):
        _draft(root)


def test_a_project_driver_declares_its_own_evidence(tmp_path):
    registry = {"go-svc": {"label": "Go service", "roles": ["api"], "runtime": "bash", "commands": {},
                           "detect": {"all": [{"file": "go.mod", "matches": "^module "}]}}}
    root = _tree(tmp_path / "go", {"svc/go.mod": "module example.com/svc\n", "ops/drivers/registry.json": json.dumps(registry)})
    modules = _draft(root, {"drivers": {"registry": "ops/drivers/registry.json"}})["modules"]
    assert modules["svc"]["type"] == "go-svc" and modules["svc"]["role"] == "api"


def test_an_existing_module_keeps_its_id_and_type_and_only_gains_what_is_absent(tmp_path):
    root = dotnet_angular_shaped(tmp_path)
    existing = {"package": "platform/kits/stack-kit",
                "modules": {"server": {"type": "custom", "role": "api", "path": "platform/apps/shop/backend/api",
                                       "secretsModule": "server"}}}
    merged, added = drafter.merge(existing, drafter.draft(root, existing))
    assert merged["modules"]["server"]["type"] == "custom" and "api" not in merged["modules"]
    assert any(a.startswith("+ modules.server.dotnet:") for a in added)
    assert any(a.startswith("+ modules.web:") for a in added)


def test_the_monorepo_profile_derives_the_canonical_rows(tmp_path):
    root = dotnet_angular_shaped(tmp_path)
    (root / "platform" / "apps").mkdir(exist_ok=True)
    floor = evaluate(root, {"modules": {}, "layout": {"profile": "monorepo"}})
    assert {r["path"] for r in floor.rows} >= {"platform/apps/", "platform/kits/", "ops/cli/", "ops/config/", "docs/"}
    assert not floor.failures, floor.failures
    (root / "docs" / "README.md").unlink()
    (root / "docs").rmdir()
    assert any("docs/" in f for f in evaluate(root, {"modules": {}, "layout": {"profile": "monorepo"}}).failures)


def test_plan_writes_nothing_and_approve_records_who(tmp_path, monkeypatch, capsys):
    from lib import identity

    root = gradle_services_shaped(tmp_path)
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps({"version": 2, "package": "platform/kits/stack-kit",
                                                               "secrets": "ops/config", "modules": {}}), encoding="utf-8")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    before = (root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8")
    assert drafter.main(["--plan"]) == 0
    assert (root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8") == before
    assert drafter.main(["--approve", "owner"]) == 0
    written = json.loads((root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert written["modules"]["backend"]["type"] == "java-boot" and written["draft"]["approvedBy"] == "owner"


def test_each_module_is_given_its_own_test_command_beside_every_modules(tmp_path):
    # So a change to one module is proved by that module's tests alone (agent-kit's areas name them).
    root = dotnet_angular_shaped(tmp_path)
    existing = {"version": 2, "modules": SHOP_MODULES,
                "commands": {"test": "pwsh ops/cli/stack-kit.ps1 test", "test-api": "a host's own line"}}
    merged, _ = drafter.merge(existing, drafter.draft(root, existing))
    assert merged["commands"]["test"] == "pwsh ops/cli/stack-kit.ps1 test", "every module's, kept"
    assert merged["commands"]["test-web"] == "pwsh ops/cli/stack-kit.ps1 mod web test"
    assert merged["commands"]["test-api"] == "a host's own line", "a declared command is never replaced"


def test_a_maven_spring_boot_api_is_a_java_boot_module_that_says_it_is_maven(tmp_path):
    # Found adopting a foreign project: a Maven API was invisible -- java-boot read Gradle only.
    root = _tree(tmp_path / "mvn", {
        "pom.xml": "<project><parent><artifactId>spring-boot-starter-parent</artifactId></parent>"
                   "<artifactId>orders</artifactId></project>",
        "src/main/java/a/App.java": "class App {}",
        "web/package.json": "{}", "web/vite.config.ts": "export default {}"})
    modules = _draft(root)["modules"]
    api = next(m for m in modules.values() if m["type"] == "java-boot")
    assert api["path"] == "." and api["java"] == {"build": "maven", "artifact": "target/*.jar"}, api
    assert any(m["type"] == "node-vite" for m in modules.values())
