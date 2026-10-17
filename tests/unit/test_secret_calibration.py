"""The two kits never refuse each other (found adopting a foreign project): agent-kit's secrets policy
carries credential-SHAPED specimens on purpose -- each gate's `proves` -- and stack-kit's scan reads a
document of the edit-gate contract by its shape, wherever it lies, as calibration and never as a leak.
The fixture is agent-kit's real secrets payload, copied verbatim."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from lib import secret_scan as s

PAYLOAD = Path(__file__).resolve().parents[1] / "fixtures" / "agent-kit-secrets-edit-gates.json"


def _repo(tmp_path: Path, rel: str) -> Path:
    git = ["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PAYLOAD, tmp_path / rel)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "the agent kit's secrets policy, taken"], check=True)
    return tmp_path


def test_a_taken_edit_gate_document_is_calibration_wherever_it_lies(tmp_path):
    root = _repo(tmp_path, ".agents/taken/secrets/payload/edit-gates.json")
    assert s.scan_text(".agents/taken/secrets/payload/edit-gates.json", PAYLOAD.read_text(encoding="utf-8")), \
        "its specimens are credential-shaped: a scan that saw nothing would prove nothing here"
    assert s.tree(root, {}) == [], "the tree scan reads its specimens as calibration"
    assert s.history(root, {}) == [], "and so does the history scan"


def test_a_settings_file_that_merely_has_gates_is_still_scanned():
    assert s.calibration_document(PAYLOAD.read_text(encoding="utf-8"))
    assert not s.calibration_document('{"gates": [{"id": "x"}], "Password": "hunter2hunter2"}')
    assert not s.calibration_document("not json")
