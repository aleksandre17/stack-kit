"""N-module manifest: roles, aliases, stack steps — abstract module ids."""
from __future__ import annotations

import json

from lib.modules import (
    default_stack_deploy_steps,
    infer_cli_aliases,
    module_by_role,
    modules_by_role,
    resolve_cli_alias,
)
from lib.project_context import ProjectContext


def _manifest_three_modules() -> dict:
    return {
        "version": 2,
        "package": "kits/stack-kit",
        "secrets": "ops/config",
        "cli": {
            "aliases": {"w": "web", "a": "api"},
        },
        "modules": {
            "web": {
                "role": "ui",
                "type": "node-vite",
                "path": "apps/web",
                "secretsModule": "web",
            },
            "api": {
                "role": "api",
                "type": "java-boot",
                "path": "services/api",
                "secretsModule": "api",
            },
            "worker": {
                "role": "worker",
                "type": "java-boot",
                "path": "services/worker",
                "secretsModule": "worker",
            },
        },
    }


def test_modules_by_role_returns_all() -> None:
    m = _manifest_three_modules()
    assert modules_by_role(m, "ui") == ["web"]
    assert modules_by_role(m, "api") == ["api"]
    assert modules_by_role(m, "worker") == ["worker"]


def test_infer_cli_aliases_merges_custom_and_role() -> None:
    m = _manifest_three_modules()
    aliases = infer_cli_aliases(m)
    assert aliases["w"] == "web"
    assert aliases["a"] == "api"
    assert aliases["ui"] == "web"
    assert aliases["worker"] == "worker"


def test_resolve_alias_module_id_or_shortcut() -> None:
    m = _manifest_three_modules()
    assert resolve_cli_alias("w", m) == "web"
    assert resolve_cli_alias("worker", m) == "worker"
    assert resolve_cli_alias("web", m) == "web"


def test_default_stack_deploy_api_before_ui() -> None:
    m = _manifest_three_modules()
    steps = default_stack_deploy_steps(m)
    ids = [s["module"] for s in steps]
    assert ids.index("api") < ids.index("web")
    assert "worker" in ids


def test_project_context_role_api(tmp_path) -> None:
    mf = tmp_path / "stack-kit.json"
    data = _manifest_three_modules()
    mf.write_text(json.dumps(data), encoding="utf-8")
    ctx = ProjectContext(root=tmp_path, manifest=data)
    assert ctx.module_id_for_role("ui") == "web"
    assert ctx.module_ids_for_role("api") == ["api"]
    assert ctx.layout_simulator_script("web") == "simulate-frontend-layout.ps1"
    assert module_by_role(data, "api") == "api"
