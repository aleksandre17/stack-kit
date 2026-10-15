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
