"""Found adopting a foreign project: init never wired the one list of secret shapes; it drafted no
`commands.validate`; the secrets root's ignore kept only a `frontend` module's examples; the root ignore
carried another host's directories and a junk line; kit-laid docs named modules the host does not have;
init printed box-drawing characters a non-UTF-8 console garbles."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
PAYLOAD = KIT / "tests" / "fixtures" / "agent-kit-secrets-edit-gates.json"


def _tree(tmp_path: Path, files: dict) -> Path:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        if text is None:
            shutil.copyfile(PAYLOAD, tmp_path / rel)
        else:
            (tmp_path / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def test_init_drafts_the_taken_secrets_policy_as_the_scans_patterns_and_never_a_law_gate(tmp_path):
    from lib import draft

    law = {"gates": [{"id": "no-x", "forbids": "X", "paths": ".*", "because": "b", "instead": "i",
                      "proves": {"path": "a", "text": "X"}, "admits": {"path": "a", "text": "y"}}]}
    root = _tree(tmp_path, {".agents/taken/secrets/payload/edit-gates.json": None,
                            ".agents/project/enforcement/edit-gates.json": json.dumps(law)})
    drafted = draft.draft(root, {"package": "kit"})
    assert drafted["security"] == {"secretPatterns": ".agents/taken/secrets/payload/edit-gates.json"}
    merged, _ = draft.merge({"security": {"secretPatterns": "mine.json"}}, drafted)
    assert merged["security"]["secretPatterns"] == "mine.json", "a declared field wins"
    assert "security" not in draft.draft(_tree(tmp_path / "bare", {"README.md": "x"}), {"package": "kit"})


def test_init_declares_the_validate_command_beside_test(tmp_path):
    from lib import draft

    drafted = draft.draft(_tree(tmp_path, {"README.md": "x"}), {"package": "kit"})
    assert drafted["commands"]["validate"].endswith(" validate")


def test_the_secrets_roots_ignore_keeps_every_modules_examples_and_follows_the_secrets_root(tmp_path):
    shutil.copyfile(KIT / "scaffold" / "ops" / "config" / ".gitignore", tmp_path / ".gitignore")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    def ignored(rel: str) -> bool:
        return subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "-q", rel]).returncode == 0

    assert not ignored("web/nginx.env.example") and not ignored("web/embed.env.example")
    assert ignored("web/nginx.env") and ignored("api/.env.prod")
    points = json.loads((KIT / "config" / "extension-points.json").read_text(encoding="utf-8"))
    point = next(p for p in points["points"] if p["id"] == "init-ops-config-gitignore") if isinstance(points, dict) \
        else next(p for p in points if p["id"] == "init-ops-config-gitignore")
    assert point["host_path"] == "{secrets|ops/config}/.gitignore"


def test_the_root_ignore_carries_no_other_hosts_directories_nor_junk():
    text = (KIT / "scaffold" / ".gitignore.example").read_text(encoding="utf-8")
    rules = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    for phantom in ("secrets/", "deploy/", "frontend/", "backend/", "-OutFile"):
        assert not any(r.lstrip("!/").startswith(phantom) for r in rules), phantom


def test_kit_laid_docs_name_no_module_the_host_may_not_have():
    named = re.compile(r"ops/config/(backend|frontend)\b|apps/backend/")
    for doc in (KIT / "scaffold" / "ops").rglob("*.md"):
        assert not named.search(doc.read_text(encoding="utf-8")), doc.relative_to(KIT).as_posix()


def test_init_prints_ascii_whatever_the_console():
    text = (KIT / "toolkit" / "init" / "Invoke-ProjectInit.ps1").read_text(encoding="utf-8-sig")
    assert all(ord(c) < 128 for c in text), sorted({hex(ord(c)) for c in text if ord(c) > 127})
