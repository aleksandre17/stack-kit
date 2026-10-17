"""init's checklist names the host's own modules and the CI the repository already had (found adopting
a foreign project: it named `ops/config/frontend/nginx.env` for a ui module called `web`, and never
mentioned the team's own workflow left running beside the generated one)."""
from __future__ import annotations

from pathlib import Path

from lib import init_checklist


def test_the_checklist_names_the_hosts_own_modules(tmp_path):
    manifest = {"modules": {"web": {"type": "node-vite", "role": "ui", "path": "web"},
                            "api": {"type": "java-boot", "role": "api", "path": "."}}}
    files = [rel for rel, _ in init_checklist.items(tmp_path, manifest)]
    assert "ops/config/web/nginx.env" in files and not any("frontend" in f or "backend" in f for f in files), files
    assert "ops/config/api/.env.dev" in files


def test_the_checklist_names_the_ci_the_repository_already_had(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "build.yml").write_text("on: push", encoding="utf-8")
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("on: push", encoding="utf-8")
    said = init_checklist.lines(tmp_path, {"modules": {}})
    assert any("build.yml -- this repository's own CI, kept beside .github/workflows/ci.yml" in line for line in said)
    assert not any("ci.yml --" in line for line in said), "the generated one is not named against itself"
