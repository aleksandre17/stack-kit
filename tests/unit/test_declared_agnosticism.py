"""Wave 2b — every new capability is a DECLARATION, and absent declarations change nothing.

Three properties are held here:
  1. No generator carries a driver name (open/closed: a driver arrives by declaration).
  2. Every new manifest/registry key is declared in manifest.schema.json.
  3. With the key ABSENT, an existing consumer's rendered output is byte-identical.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lib.config_gen import DEFAULT_MANAGEMENT_ENDPOINTS, _management_endpoints
from lib.identity import MANIFEST_FILENAME, manifest_filenames
from lib.modules import driver_default_role, driver_registry
from lib.project_context import ProjectContext
from lib.vscode_gen import build_tasks_json
from conftest import PKG


# ── 1. No driver is named outside its own directory ───────────────────────────

#: Where a driver may be named: its own directory and the tests. Everything else -- every interpreter,
#: shim, toolkit script, adapter, CI helper and scaffold script, comments included -- is denied by
#: default (ADR-001 amendment 12). An allowlist of cured files is how an uncured one stays unseen.
NAMED_ONLY_IN = ("drivers/", "tests/")


def _driver_spellings() -> list:
    """Each driver id as a pattern that matches its hyphen and its underscore spelling."""
    return [(d, re.compile("[-_]".join(re.escape(part) for part in d.split("-")), re.IGNORECASE))
            for d in driver_registry()]


def test_no_script_outside_drivers_names_a_driver() -> None:
    import subprocess

    tracked = subprocess.run(["git", "-C", str(PKG), "ls-files", "-co", "--exclude-standard", "*.py", "*.ps1", "*.sh"],
                             capture_output=True, text=True).stdout.splitlines()
    spellings = _driver_spellings()
    offenders = []
    for rel in tracked:
        if rel.startswith(NAMED_ONLY_IN) or not (PKG / rel).is_file():
            continue
        for n, line in enumerate((PKG / rel).read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
            hit = next((d for d, pat in spellings if pat.search(line)), None)
            if hit:
                offenders.append(f"{rel}:{n} names {hit}")
    assert not offenders, "\n".join(offenders)


# ── 1b. The kit's own name has ONE home ───────────────────────────────────────

#: `identity.py` IS the home, so it is the only file allowed to spell the name.
IDENTITY_HOME = "lib/identity.py"


def test_no_interpreter_spells_the_manifest_filename() -> None:
    """The manifest filename is DECLARED in identity.py and projected everywhere else.

    It once lived in 77 places across three languages. A truth with many homes does
    not become wrong — it becomes unverifiable, because every copy stays locally
    correct while the set drifts. Renaming the kit must be a change to ONE file.
    """
    offenders: list[str] = []
    for path in sorted((PKG / "lib").glob("*.py")):
        rel = f"lib/{path.name}"
        if rel == IDENTITY_HOME:
            continue
        if MANIFEST_FILENAME in path.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert not offenders, (
        f"these spell '{MANIFEST_FILENAME}' instead of importing it from {IDENTITY_HOME}: {offenders}"
    )


def test_legacy_manifest_names_are_declared_not_improvised() -> None:
    """Every accepted manifest name is declared, canonical first, with no duplicates."""
    names = manifest_filenames()
    assert names[0] == MANIFEST_FILENAME, "the canonical name must be tried first"
    assert len(set(names)) == len(names), "a name is declared once"


def test_every_driver_declares_a_role_and_launch_kind() -> None:
    for driver_id, entry in driver_registry().items():
        assert entry.get("roles"), f"{driver_id} declares no roles"
        assert driver_default_role(driver_id), f"{driver_id} role is not a known role"
        launch = (entry.get("vscode") or {}).get("launch")
        assert isinstance(launch, dict), f"{driver_id} declares no launch data ({launch!r})"


def test_declared_watch_tasks_reach_a_real_driver_command() -> None:
    """A declared task's first argv element must be a command the driver actually has."""
    for driver_id, entry in driver_registry().items():
        commands = entry.get("commands") or {}
        for name, argv in (entry.get("tasks") or {}).items():
            assert isinstance(argv, list) and argv, f"{driver_id}.tasks.{name} empty"
            assert argv[0] in commands, f"{driver_id}.tasks.{name} -> no '{argv[0]}' command"


def test_node_api_gets_watch_tasks(repo_root: Path, manifest: dict) -> None:
    """The row-31 symptom: node-api existed and silently got no VS Code tasks."""
    node_api_ids = [m for m, c in manifest["modules"].items() if c.get("type") == "node-api"]
    assert node_api_ids, "fixture must carry a node-api module"
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    labels = [t["label"] for t in build_tasks_json(ctx)["tasks"]]
    assert any("dev watch" in lb for lb in labels), labels  # from the driver's `dev` declaration


# ── 2. Schema declares every new key ──────────────────────────────────────────


def _schema() -> dict:
    return json.loads((PKG / "manifest.schema.json").read_text(encoding="utf-8"))


def test_node_prebuild_scripts_declared() -> None:
    mod = _schema()["properties"]["modules"]["additionalProperties"]["properties"]
    node = mod["node"]["properties"]["prebuildScripts"]
    assert node["type"] == "array"
    assert node["default"] == []


def test_management_endpoints_declared_with_narrow_default() -> None:
    spring = _schema()["properties"]["modules"]["additionalProperties"]["properties"]["spring"]
    assert spring["properties"]["managementEndpoints"]["default"] == "health,info"


def test_dev_boot_order_declared() -> None:
    dev = _schema()["properties"]["dev"]["properties"]["bootOrder"]
    assert dev["default"] == ["api", "worker", "ui"]


# ── 3. Absent key ⇒ unchanged output ──────────────────────────────────────────


def test_management_endpoints_absent_is_the_narrow_default() -> None:
    assert _management_endpoints({}) == DEFAULT_MANAGEMENT_ENDPOINTS == "health,info"
    assert _management_endpoints({"managementEndpoints": ""}) == "health,info"


def test_management_endpoints_declared_widens_only_on_request() -> None:
    assert _management_endpoints({"managementEndpoints": "health,info,prometheus"}) == (
        "health,info,prometheus"
    )
    assert _management_endpoints({"managementEndpoints": ["health", "metrics"]}) == "health,metrics"


def test_catalog_renders_narrow_default_when_module_declares_nothing() -> None:
    """Byte-identical proof: the template placeholder resolves to the pre-wave literal."""
    catalog = json.loads((PKG / "config" / "config-catalog.json").read_text(encoding="utf-8"))
    spring = catalog["javaBoot"]
    for key in ("simpleApplicationYml", "applicationYml"):
        tpl = spring[key]
        assert "{management_endpoints}" in tpl
        rendered = tpl.replace("{management_endpoints}", _management_endpoints({}))
        assert "include: health,info\n" in rendered.replace("\\n", "\n")


def test_dev_orchestrator_is_registry_driven() -> None:
    src = (PKG / "toolkit" / "dev" / "Invoke-DevUp.ps1").read_text(encoding="utf-8")
    for token in ("node-vite", "java-boot", "node-api", "chat-api", "frontend"):
        assert token not in src, f"Invoke-DevUp.ps1 names '{token}'"
    # A module's role is the resolver's answer (declared, else its driver's) -- never inferred here.
    assert "Get-ModuleRole" in src and "ConvertFrom-Json" not in src
