"""A lifecycle step's verdict counts only the modules that ran (lib/cli/verbs/step.py): a module whose
driver ran nothing -- declared none, skipped -- is named as NOT RUN with its reason, never counted as
one that ran (CWE-223). Proven on a driver the kit does not ship."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from conftest import WORKING_ROOT
from lib import identity
from lib.cli.tools import driver_step
from lib.cli.verbs.step import verdict

#: The fixture driver's test command: it runs, or -- told to by its module's name -- it says it ran nothing.
TEST = """import os, sys
if os.environ["STACK_KIT_MODULE_ID"] == "empty":
    with open(os.environ["STACK_KIT_NOT_RUN"], "w", encoding="utf-8") as f:
        f.write("declared none")
    print("  [empty test] declared none")
sys.exit(0)
"""


def _host(tmp_path: Path) -> Path:
    root = tmp_path / "step-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    (root / "ops" / "drivers" / "py-svc").mkdir(parents=True)
    (root / "ops" / "drivers" / "py-svc" / "t.py").write_text(TEST, encoding="utf-8")
    (root / "ops" / "drivers" / "registry.json").write_text(json.dumps(
        {"py-svc": {"label": "a service", "roles": ["api"], "commands": {"test": "t.py"}}}), encoding="utf-8")
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["drivers"] = {"registry": "ops/drivers/registry.json"}
    manifest["modules"] = {mid: {"type": "py-svc", "role": "api", "path": f"apps/{mid}", "secretsModule": mid}
                           for mid in ("full", "empty")}
    for mid in ("full", "empty"):
        (root / "apps" / mid).mkdir(parents=True, exist_ok=True)
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_a_driver_that_ran_nothing_says_why_and_one_that_ran_says_nothing(tmp_path, monkeypatch):
    root = _host(tmp_path)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    assert driver_step("full", "test", []) == (0, None)
    assert driver_step("empty", "test", []) == (0, "declared none")


def test_the_verdict_names_every_module_that_ran_nothing():
    assert verdict("test", ["api", "web"], []) == "  test OK (2 module(s) ran)"
    assert verdict("test", ["api"], [("web", "declared none")]) == "  test OK (1 module(s) ran; not run: web (declared none))"
    assert verdict("test", [], [("web", "declared none")]) == "  test: NOTHING RAN -- not run: web (declared none)"
    assert verdict("test", [], []) == "  test: NOTHING RAN -- no module was selected"


def test_a_run_record_whose_status_git_cannot_read_is_unknown_never_clean(tmp_path, monkeypatch):
    """The run record's `gitDirty` is null when `git status` fails -- never false (CWE-636)."""
    import subprocess as sp

    from lib.cli import tools

    root = _host(tmp_path)
    git = ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
    sp.run([*git, "init", "-q"], check=True)
    sp.run([*git, "add", "-A"], check=True)
    sp.run([*git, "commit", "-qm", "host"], check=True)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    real = sp.run

    def status_fails(argv, *a, **k):
        if "status" in argv:
            return sp.CompletedProcess(argv, 128, "", "fatal: index file corrupt")
        return real(argv, *a, **k)

    monkeypatch.setattr(tools.subprocess, "run", status_fails)
    assert tools.recorded("step", "test", "full", lambda: 0) == 0
    last = json.loads(tools.runs_file(root).read_text(encoding="utf-8").splitlines()[-1])
    assert last["gitSha"] and last["gitDirty"] is None and last["notRun"] is None
