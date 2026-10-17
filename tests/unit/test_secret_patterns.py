"""The secret scan's patterns may be the host's, as documents of agent-kit's edit-gate contract read by
path (ADR-001 amendment 16.10): the built-in set only when none is declared; a gate is used only once
its own calibration holds; validate names a document it cannot believe and an allowance that names a
rule the declared set lacks. The fixture token is assembled at run time, so no file carries one."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib import secret_scan as s

PREFIX = "FIX" + "TOK_"
TOKEN = PREFIX + "ABCDEFGHJKLM"


def _gates(**over) -> dict:
    gate = {"id": "no-fixture-token", "paths": r"\.(json|txt)$", "forbids": r"\b" + PREFIX + r"[A-Z]{12}\b",
            "because": "a fixture", "instead": "a placeholder",
            "proves": {"path": "a.json", "text": f'"k": "{TOKEN}"'}, "admits": {"path": "a.json", "text": f'"k": "{PREFIX}short"'}}
    gate.update(over)
    return {"schema_version": 1, "gates": [gate]}


def _repo(tmp_path: Path, files: dict[str, str], gates: dict | None) -> tuple[Path, dict]:
    git = ["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    for rel, text in files.items():
        (tmp_path / rel).write_text(text, encoding="utf-8")
    manifest = {}
    if gates is not None:
        (tmp_path / "gates.json").write_text(json.dumps(gates), encoding="utf-8")
        manifest = {"security": {"secretPatterns": "gates.json"}}
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture"], check=True)
    return tmp_path, manifest


def test_declared_gates_replace_the_built_in_set(tmp_path):
    jwt_like = "ey" + "J" + "a" * 10 + ".ey" + "J" + "b" * 10 + "." + "c" * 10
    root, manifest = _repo(tmp_path, {"a.json": f'{{"k": "{TOKEN}"}}', "b.txt": jwt_like, "c.md": TOKEN}, _gates())
    found = s.tree(root, manifest)
    assert [(f.path, f.rule) for f in found] == [("a.json", "no-fixture-token")], "the gate, on the paths it holds only"
    assert [f.rule for f in s.tree(root, {})] == ["jwt"], "no declaration: the built-in set"


def test_a_gate_whose_calibration_fails_is_not_believed(tmp_path):
    root, manifest = _repo(tmp_path, {"a.json": "{}"}, _gates(admits={"path": "a.json", "text": TOKEN}))
    with pytest.raises(s.ScanError, match="refuses its own `admits`"):
        s.tree(root, manifest)
    errors, _ = s.pattern_problems(root, manifest)
    assert errors and "not believed" in errors[0]


def test_validate_names_an_allowance_for_a_rule_the_declared_set_lacks(tmp_path):
    root, manifest = _repo(tmp_path, {"a.json": "{}"}, _gates())
    manifest["security"]["allow"] = [{"path": "x.json", "rule": "connection-string", "reason": "old"}]
    errors, warnings = s.pattern_problems(root, manifest)
    assert not errors and warnings and "built-in set is not used" in warnings[0]
    missing = {"security": {"secretPatterns": "nowhere.json"}}
    assert "is not there" in s.pattern_problems(root, missing)[0][0]


def test_a_declared_gate_that_groups_the_key_name_still_finds_the_value(tmp_path):
    # agent-kit's connection-string gate captures the KEY ("Password") and refuses placeholders by a
    # lookahead; the scan must not read the group as the value and call "Password" a placeholder.
    gate = {"id": "no-connection-string-password", "paths": ".*",
            "forbids": r"(?i)[;\"'>]\s*(password|pwd)\s*=\s*(?!__[A-Z0-9_]+__)[^;\"'\s]+",
            "because": "a fixture", "instead": "a placeholder",
            "proves": {"path": "a.json", "text": "\"d\": \"Server=x;Password=hunter2;\""},
            "admits": {"path": "a.json", "text": "\"d\": \"Server=x;Password=__DB_PASSWORD__;\""}}
    root, manifest = _repo(tmp_path, {"a.json": "\"d\": \"Server=x;Password=hunter2;\"",
                                      "b.json": "\"d\": \"Server=x;Password=__DB_PASSWORD__;\""},
                           {"schema_version": 1, "gates": [gate]})
    assert [(f.path, f.rule) for f in s.tree(root, manifest)] == [("a.json", "no-connection-string-password")]
