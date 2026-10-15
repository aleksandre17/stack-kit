"""K4 — `validate.stages` is a pipeline that ends on value anchors (ADR-001 decision 4).

Proof owed by the ADR: a stage list without an anchor is refused; a failing stage tears down and
exits non-zero. Stages here are interpreter one-liners, so the pipeline's own behaviour is under test
and not docker's: a stage writes a value, an anchor reads it back and compares, teardown leaves a mark.
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
from lib.pipeline import problems

PY = sys.executable


def _py(code: str) -> list[str]:
    return [PY, "-c", code]


WRITE = {"id": "ingest", "kind": "ingest", "run": _py("open('rows.txt','w').write('42')")}
READ = {"id": "count", "kind": "anchor", "run": _py("print(open('rows.txt').read())"), "expect": {"equals": "42"}}
TEARDOWN = {"id": "down", "kind": "teardown", "run": _py("open('torn-down','w').write('1')")}


@pytest.fixture
def host(tmp_path) -> Path:
    root = tmp_path / "pipeline-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    return root


def _validate(host: Path, stages: list[dict], *args: str) -> subprocess.CompletedProcess[str]:
    mf = host / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["validate"] = {"stages": stages}
    mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    env = kit_cli_env({identity.env_name("PROJECT_ROOT"): str(host)})
    return subprocess.run([PY, "-B", str(PKG / "lib" / "validate_manifest.py"), *args], cwd=host, env=env,
                          capture_output=True, text=True)


def test_a_pipeline_ending_on_a_held_anchor_passes_and_tears_down(host):
    ran = _validate(host, [WRITE, READ, TEARDOWN], "--stages")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "value: 42" in ran.stdout
    assert (host / "torn-down").is_file()


def test_an_anchor_that_does_not_hold_fails_with_what_it_saw(host):
    wrong = {**READ, "expect": {"equals": "41"}}
    ran = _validate(host, [WRITE, wrong, TEARDOWN], "--stages")
    assert ran.returncode == 1
    assert "expected '41', got '42'" in ran.stderr
    assert (host / "torn-down").is_file(), "teardown did not run after a failed anchor"


def test_a_failing_stage_stops_the_pipeline_tears_down_and_exits_non_zero(host):
    boom = {"id": "migrate", "kind": "migrate", "run": _py("raise SystemExit(3)")}
    ran = _validate(host, [boom, WRITE, READ, TEARDOWN], "--stages")
    assert ran.returncode == 1
    assert "exited 3" in ran.stderr
    assert not (host / "rows.txt").exists(), "a stage after the failure ran"
    assert (host / "torn-down").is_file(), "teardown did not run after a failed stage"


def test_a_stage_list_without_an_anchor_is_refused_before_anything_runs(host):
    ran = _validate(host, [WRITE, TEARDOWN], "--stages")
    assert ran.returncode == 1
    assert "no anchor" in ran.stderr
    assert not (host / "rows.txt").exists(), "a refused pipeline ran a stage"
    # and plain `validate` refuses the declaration too, without running it
    ran = _validate(host, [WRITE, TEARDOWN])
    assert ran.returncode == 1 and "no anchor" in ran.stderr


@pytest.mark.parametrize("stages, says", [
    ([WRITE, READ, {"id": "after", "kind": "build", "run": _py("pass")}], "not an anchor"),
    ([{**READ, "expect": {}}], "exactly one of"),
    ([{**READ, "expect": {"equals": "1", "matches": "1"}}], "exactly one of"),
    ([{**WRITE, "run": "a string"}, READ], "argv list"),
    ([WRITE, {**WRITE}, READ], "used twice"),
    ([{**WRITE, "kind": "deploy"}, READ], "kind must be one of"),
])
def test_what_a_proof_cannot_be(stages, says):
    assert any(says in p for p in problems(stages)), problems(stages)


def test_matches_and_at_least_compare_values():
    from lib.pipeline import _compare

    assert _compare({"matches": r"^\d+ rows$"}, "12 rows") is None
    assert _compare({"atLeast": 10}, "12") is None
    assert "at least 13" in _compare({"atLeast": 13}, "12")
    assert "a number" in _compare({"atLeast": 1}, "twelve")
