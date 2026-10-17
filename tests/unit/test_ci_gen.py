"""The CI workflow is generated from the manifest, every action pinned by SHA (ADR-001 amendment 8)."""
from __future__ import annotations

import json
import re

from conftest import PKG, WORKING_ROOT
from lib import ci_gen
from lib.modules import driver_registry
from lib.project_context import ProjectContext

SHA = re.compile(r"^ +(?:- )?uses: [\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$")


def _render() -> tuple[str, dict]:
    ctx = ProjectContext.discover(WORKING_ROOT)
    return ci_gen.render(ctx), ctx.manifest


def test_every_action_is_pinned_by_a_full_commit_sha():
    text, _ = _render()
    uses = [ln for ln in text.splitlines() if "uses:" in ln]
    assert uses and all(SHA.match(ln) for ln in uses), [ln for ln in uses if not SHA.match(ln)]


def test_a_job_per_module_runs_its_drivers_lifecycle_steps_through_the_launcher():
    text, manifest = _render()
    cli = ci_gen.launcher(manifest)
    for mid in manifest["modules"]:
        assert f"\n  {mid}:\n" in text, mid
        assert f"'pwsh {cli} mod {mid} build'" in text and f"'pwsh {cli} mod {mid} test'" in text, mid
    assert "permissions:\n  contents: read" in text


def test_the_toolchain_version_is_the_modules_else_the_drivers():
    ctx = ProjectContext.discover(WORKING_ROOT)
    mid, module = next((m, c) for m, c in ctx.manifest["modules"].items() if c["type"] == "java-boot")
    assert "java-version: '17'" in ci_gen.render(ctx)
    module["toolchain"] = {"version": "21"}
    assert "java-version: '21'" in ci_gen.render(ctx)


def test_every_action_a_driver_asks_for_is_pinned():
    pins = json.loads((PKG / "lib" / "ci-actions.json").read_text(encoding="utf-8"))["actions"]
    for typ, entry in driver_registry().items():
        for setup in (entry.get("ci") or {}).get("setup", []):
            assert "uses" not in setup or setup["uses"] in pins, (typ, setup)
    assert all(re.fullmatch(r"[0-9a-f]{40}", p["sha"]) for p in pins.values())


def test_check_fails_on_drift_and_passes_when_current(tmp_path, monkeypatch):
    import shutil

    root = tmp_path / "ci-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    monkeypatch.setenv("STACK_KIT_PROJECT_ROOT", str(root))
    assert ci_gen.main([]) == 0
    assert ci_gen.main(["--check"]) == 0
    wf = root / ci_gen.DEFAULT_WORKFLOW
    wf.write_text(wf.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    assert ci_gen.main(["--check"]) == 1


def test_the_workflow_token_is_read_only_but_where_a_package_is_attested():
    from lib.ci_gen import render
    from lib.project_context import ProjectContext

    text = render(ProjectContext.discover())
    head = text.split("jobs:")[0]
    assert "permissions:\n  contents: read" in head
    import re

    jobs = re.split(r"\n  (?=[A-Za-z0-9_-]+:\n)", text.split("jobs:\n", 1)[1])
    widened = [j for j in jobs if "id-token: write" in j]
    assert widened and all("attestations: write" in j and "name: package" in j for j in widened)


def test_every_step_name_is_a_quoted_scalar_so_the_workflow_parses():
    # A name in words may carry `: ` ("build once: one archive"), which ends a plain YAML scalar and
    # makes GitHub refuse the whole workflow before a job starts.
    text, _ = _render()
    names = [line for line in text.splitlines() if re.match(r"^\s*- name: ", line)]
    assert names and all(re.match(r"^\s*- name: '(?:[^']|'')*'$", line) for line in names), names
