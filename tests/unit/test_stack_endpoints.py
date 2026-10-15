"""Stack compose URL hints — manifest modules + stack-catalog roles."""
from __future__ import annotations

import json
from pathlib import Path

from lib.project_context import ProjectContext
from lib.stack_endpoints import (
    load_stack_catalog,
    resolve_module_port,
    stack_endpoint_lines,
)

CATALOG = {
    "roles": {
        "ui": {
            "portEnv": ["DEPLOY_HOST_PORT"],
            "defaultPort": "5177",
            "urlPath": "/",
        },
        "api": {
            "portEnv": ["API_PORT", "RETRIEVAL_PORT"],
            "defaultPort": "8090",
            "urlPath": "/health",
        },
        "worker": {
            "portEnv": ["WORKER_PORT", "INGESTION_PORT"],
            "defaultPort": "8091",
            "urlPath": "/actuator/health",
        },
    },
    "roleOrder": ["ui", "api", "worker"],
}


def _manifest(modules: dict) -> dict:
    return {
        "version": 2,
        "package": "kits/stack-kit",
        "secrets": "ops/config",
        "modules": modules,
    }


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


def test_four_modules_ordered(tmp_path: Path):
    manifest = _manifest(
        {
            "frontend": {"role": "ui", "type": "node-vite", "path": "apps/fe", "secretsModule": "frontend"},
            "backend": {"role": "api", "type": "java-boot", "path": "apps/be", "secretsModule": "backend"},
            "retrieval": {"role": "api", "type": "java-boot", "path": "apps/ret", "secretsModule": "retrieval"},
            "ingestion": {"role": "worker", "type": "java-boot", "path": "apps/ing", "secretsModule": "ingestion"},
        }
    )
    ctx = _write_project(
        tmp_path,
        manifest,
        {
            "frontend": {"DEPLOY_HOST_PORT": "5178"},
            "backend": {"API_PORT": "8090"},
            "retrieval": {"RETRIEVAL_PORT": "8092"},
            "ingestion": {"INGESTION_PORT": "8093"},
        },
    )
    lines = stack_endpoint_lines(ctx, catalog=CATALOG)
    assert len(lines) == 4
    assert "ui   (frontend)" in lines[0] and "5178" in lines[0]
    assert "api  (backend)" in lines[1] and "8090" in lines[1]
    assert "api  (retrieval)" in lines[2] and "8092" in lines[2]
    assert "worker (ingestion)" in lines[3] and "8093" in lines[3]


def test_stack_modules_filter(tmp_path: Path):
    manifest = _manifest(
        {
            "frontend": {"role": "ui", "type": "node-vite", "path": "a", "secretsModule": "frontend"},
            "backend": {"role": "api", "type": "java-boot", "path": "b", "secretsModule": "backend"},
        }
    )
    manifest["stack"] = {"modules": ["backend"]}
    ctx = _write_project(tmp_path, manifest, {"backend": {"API_PORT": "9000"}})
    lines = stack_endpoint_lines(ctx, catalog=CATALOG)
    assert len(lines) == 1
    assert "backend" in lines[0] and "9000" in lines[0]


def test_retrieval_port_prefers_secrets_slug(tmp_path: Path):
    port = resolve_module_port(
        role="api",
        role_cfg=CATALOG["roles"]["api"],
        secrets_folder="retrieval",
        env={"API_PORT": "8090", "RETRIEVAL_PORT": "8092"},
    )
    assert port == "8092"


def test_load_stack_catalog_missing(tmp_path: Path):
    assert load_stack_catalog(tmp_path / "missing.json") == {"roles": {}, "roleOrder": []}
