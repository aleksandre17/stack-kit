"""Manifest validation CLI logic."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.validate_manifest import validate_manifest
from conftest import FIXTURE_ROOT, PKG



def _golden_tree(tmp_path: Path) -> Path:
    """Copy the synthetic consumer fixture into tmp and repoint `package` at the kit.

    The fixture's `apps/**` already carry the config-gen golden output and the
    hand-maintained `application-custom.yml`, so validation (which runs config-gen
    drift checks) passes against a faithful copy. The `kits/stack-kit` junction
    is skipped — `package` is rewritten as a relative path to the real kit.
    """
    import os
    import shutil

    shutil.copytree(
        FIXTURE_ROOT,
        tmp_path,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("kits", "__pycache__", ".pytest_cache"),
    )
    manifest = json.loads((tmp_path / "stack-kit.json").read_text(encoding="utf-8"))
    vendored = manifest["package"].rstrip("/")
    manifest["package"] = os.path.relpath(PKG, tmp_path).replace("\\", "/")
    # Every declared path into the vendored kit follows it (the layout floor holds them all).
    for key, value in (manifest.get("ci") or {}).items():
        if isinstance(value, str) and value.startswith(vendored + "/"):
            manifest["ci"][key] = manifest["package"] + value[len(vendored):]
    (tmp_path / "stack-kit.json").write_text(json.dumps(manifest), encoding="utf-8")
    # deploy.env is gitignored / volatile; synthesize from the committed template.
    template = tmp_path / "ops" / "config" / "deploy.env.fixture"
    if template.is_file():
        (tmp_path / "ops" / "config" / "deploy.env").write_text(
            template.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return tmp_path


def test_validate_golden_consumer_passes(tmp_path: Path) -> None:
    root = _golden_tree(tmp_path)
    errs, warnings = validate_manifest(root)
    assert not errs, errs
    assert isinstance(warnings, list)


def test_validate_fails_missing_role(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STACK_KIT_PROJECT_ROOT", raising=False)
    root = _golden_tree(tmp_path)
    mf = root / "stack-kit.json"
    data = json.loads(mf.read_text(encoding="utf-8"))
    del data["modules"]["api"]["role"]
    mf.write_text(json.dumps(data), encoding="utf-8")
    errs, _ = validate_manifest(root)
    assert any("role" in e for e in errs), errs


def test_validate_cli_main(repo_root: Path) -> None:
    errs, warnings = validate_manifest(repo_root)
    assert not errs, errs


def test_validate_refuses_a_former_consumer_shape_and_names_the_door(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ADR-001 amendment 7: the kit spells no consumer's keys; a host still on one is told `migrate`.
    monkeypatch.delenv("STACK_KIT_PROJECT_ROOT", raising=False)
    root = _golden_tree(tmp_path)
    mf = root / "stack-kit.json"
    data = json.loads(mf.read_text(encoding="utf-8"))
    data["modules"]["api"]["catalog"] = {"sourceEnv": "SRC"}
    mf.write_text(json.dumps(data), encoding="utf-8")
    errs, _ = validate_manifest(root)
    assert any("modules.api.catalog -> modules.api.extensions.catalog" in e and "migrate --apply" in e
               for e in errs), errs


def test_the_commands_block_is_literal_lines_with_a_required_test(tmp_path: Path) -> None:
    # The cross-tool contract (ADR-001 amendment 8): `commands.test` required, `build` optional,
    # every value a literal string; a line naming a host script that is not there is refused.
    from lib.schema_check import validate as schema_validate
    from lib.validate_manifest import command_line_problems

    schema = json.loads((PKG / "manifest.schema.json").read_text(encoding="utf-8"))["properties"]["commands"]
    assert schema_validate({"test": "pwsh ops/cli/stack-kit.ps1 test"}, schema) == []
    assert schema_validate({"build": "x"}, schema), "a commands block without test passed"
    assert schema_validate({"test": ["pwsh", "x"]}, schema), "a non-string command passed"
    assert schema_validate({"test": "x", "deploy": "y"}, schema), "an undeclared command passed"
    (tmp_path / "ops" / "cli").mkdir(parents=True)
    (tmp_path / "ops" / "cli" / "stack-kit.ps1").write_text("", encoding="utf-8")
    ok = {"commands": {"test": "pwsh ops/cli/stack-kit.ps1 test"}}
    assert command_line_problems(tmp_path, ok) == []
    broken = {"commands": {"build": "pwsh tools/missing.ps1 build", "test": "dotnet test"}}
    assert command_line_problems(tmp_path, broken) == ["commands.build: names tools/missing.ps1, which is not there"]


def test_the_commands_block_accepts_validate_and_lint_as_literal_lines() -> None:
    # A host declares `commands.validate` so agent-kit's stack-kit adapter can vouch for
    # `stack-kit:validate` as the enforcer of a host law; `lint` sits beside build and test.
    from lib.schema_check import validate as schema_validate

    schema = json.loads((PKG / "manifest.schema.json").read_text(encoding="utf-8"))["properties"]["commands"]
    full = {"build": "pwsh ops/cli/stack-kit.ps1 build", "test": "pwsh ops/cli/stack-kit.ps1 test",
            "lint": "pwsh ops/cli/stack-kit.ps1 lint", "validate": "pwsh ops/cli/stack-kit.ps1 validate"}
    assert schema_validate(full, schema) == []
    assert schema_validate({**full, "validate": ""}, schema), "an empty validate line passed"
    assert schema_validate({**full, "validate": ["pwsh", "validate"]}, schema), "a non-string validate passed"
    assert schema_validate({"validate": full["validate"]}, schema), "validate without test passed"


def test_the_scaffold_declares_the_commands_through_the_host_launcher() -> None:
    scaffold = json.loads((PKG / "scaffold" / "stack-kit.json").read_text(encoding="utf-8"))
    assert scaffold["commands"]["test"].endswith("ops/cli/stack-kit.ps1 test")
    assert scaffold["commands"]["build"].endswith("ops/cli/stack-kit.ps1 build")
    assert (PKG / "scaffold" / "ops" / "cli" / "stack-kit.ps1").is_file()
