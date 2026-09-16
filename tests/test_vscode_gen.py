"""VS Code launch/tasks generation from manifest."""
from __future__ import annotations

import json

import pytest

from lib.project_context import ProjectContext
from lib.vscode_gen import build_launch_json, build_tasks_json, write_vscode


def test_launch_paths_use_manifest_modules(repo_root: Path, manifest: dict) -> None:
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    launch = build_launch_json(ctx)
    names = {c["name"]: c for c in launch["configurations"]}
    fe = next(c for c in launch["configurations"] if "npm run" in c.get("command", ""))
    assert fe["cwd"].endswith("apps/web")
    java = next(c for c in launch["configurations"] if c.get("type") == "java")
    assert java["cwd"].endswith("apps/api")
    assert java["mainClass"] == "com.example.app.AppApplication"
    assert "/frontend" not in fe["cwd"].replace("apps/frontend", "")


def test_tasks_include_validate(repo_root: Path, manifest: dict) -> None:
    ctx = ProjectContext(root=repo_root, manifest=manifest)
    tasks = build_tasks_json(ctx)
    labels = [t["label"] for t in tasks["tasks"]]
    assert "geostat: validate" in labels
    # Per-module check tasks are labelled by the manifest cli alias, not by any
    # consumer vocabulary: the fixture declares w -> web, a -> api.
    assert any("w check" in lb or "a check" in lb for lb in labels)


def test_write_vscode_tmp(tmp_path: Path) -> None:
    import os
    from pathlib import Path

    manifest = {
        "version": 2,
        "package": ".",
        "secrets": "ops/config",
        "compose": {"catalog": "ops/compose/catalog.json"},
        "modules": {
            "web": {
                "role": "ui",
                "type": "node-vite",
                "path": "apps/web",
                "secretsModule": "web",
            }
        },
        "vscode": {"folder": ".vscode", "geostatScript": "tools/geostat.ps1"},
    }
    (tmp_path / "geostat.ops.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "apps" / "web").mkdir(parents=True)
    pkg = Path(__file__).resolve().parents[1]
    manifest["package"] = os.path.relpath(pkg, tmp_path).replace("\\", "/")
    (tmp_path / "geostat.ops.json").write_text(json.dumps(manifest), encoding="utf-8")
    ctx = ProjectContext(root=tmp_path, manifest=manifest)
    paths = write_vscode(ctx, force=True)
    assert any(p.endswith("launch.json") for p in paths)
    launch = json.loads((tmp_path / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    assert launch["configurations"][0]["cwd"].endswith("apps/web")
