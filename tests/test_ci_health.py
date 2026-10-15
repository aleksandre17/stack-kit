"""CI health matrix — stack.composeModules + stack-catalog roles."""
from __future__ import annotations

import json
from pathlib import Path

from lib.ci_health import stack_health_targets
from lib.project_context import ProjectContext

CATALOG = {
    "roles": {
        "ui": {
            "portEnv": ["DEPLOY_HOST_PORT"],
            "defaultPort": "5177",
            "urlPath": "/",
            "ciHealth": False,
        },
        "api": {
            "portEnv": ["API_PORT", "RETRIEVAL_PORT"],
            "defaultPort": "8090",
            "urlPath": "/health",
            "ciHealth": True,
            "healthExpect": "UP",
        },
        "worker": {
            "portEnv": ["WORKER_PORT", "INGESTION_PORT"],
            "defaultPort": "8091",
            "urlPath": "/actuator/health",
            "ciHealth": True,
            "healthExpect": "UP",
        },
    },
    "roleOrder": ["ui", "api", "worker"],
}


def _manifest(modules: dict, **extra) -> dict:
    base = {
        "version": 2,
        "package": "kits/stack-kit",
        "secrets": "ops/config",
        "modules": modules,
    }
    base.update(extra)
    return base


def _write_project(tmp: Path, manifest: dict, env_by_folder: dict[str, dict[str, str]]) -> ProjectContext:
    root = tmp / "proj"
    (root / "kits" / "stack-kit" / "compose").mkdir(parents=True)
    (root / "kits" / "stack-kit" / "compose" / "stack-catalog.json").write_text(
        json.dumps(CATALOG), encoding="utf-8"
    )
    (root / "stack-kit.json").write_text(json.dumps(manifest), encoding="utf-8")
    secrets = root / "ops" / "config"
    for folder, vals in env_by_folder.items():
        d = secrets / folder
        d.mkdir(parents=True)
        lines = [f"{k}={v}" for k, v in vals.items()]
        (d / ".env.dev").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ProjectContext(root=root, manifest=manifest)


def test_health_modules_override_skips_ui(tmp_path: Path):
    manifest = _manifest(
        {
            "frontend": {"role": "ui", "type": "node-vite", "path": "a", "secretsModule": "frontend"},
            "backend": {"role": "api", "type": "java-boot", "path": "b", "secretsModule": "backend"},
            "retrieval": {"role": "api", "type": "java-boot", "path": "c", "secretsModule": "retrieval"},
            "ingestion": {"role": "worker", "type": "java-boot", "path": "d", "secretsModule": "ingestion"},
        },
        stack={"composeModules": ["backend", "retrieval", "ingestion", "frontend"]},
        ci={"healthModules": ["backend", "retrieval", "ingestion"]},
    )
    ctx = _write_project(
        tmp_path,
        manifest,
        {
            "frontend": {"DEPLOY_HOST_PORT": "5177"},
            "backend": {"API_PORT": "8090"},
            "retrieval": {"RETRIEVAL_PORT": "8092"},
            "ingestion": {"INGESTION_PORT": "8093"},
        },
    )
    targets = stack_health_targets(ctx, catalog=CATALOG)
    assert [t.module_id for t in targets] == ["backend", "retrieval", "ingestion"]
    assert targets[0].url == "http://127.0.0.1:8090/health"
    assert targets[1].url == "http://127.0.0.1:8092/health"
    assert targets[2].url == "http://127.0.0.1:8093/actuator/health"
    assert all(t.expect == "UP" for t in targets)


def test_compose_modules_excludes_ui_by_catalog(tmp_path: Path):
    manifest = _manifest(
        {
            "frontend": {"role": "ui", "type": "node-vite", "path": "a", "secretsModule": "frontend"},
            "backend": {"role": "api", "type": "java-boot", "path": "b", "secretsModule": "backend"},
        },
        stack={"composeModules": ["backend", "frontend"]},
    )
    ctx = _write_project(tmp_path, manifest, {"backend": {"API_PORT": "8090"}})
    targets = stack_health_targets(ctx, catalog=CATALOG)
    assert len(targets) == 1
    assert targets[0].module_id == "backend"
