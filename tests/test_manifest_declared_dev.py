"""Manifest-declared compose location and remote-dev service settings.

Exercises the real bash resolvers against a throw-away consumer so the contract
is proven by behaviour, not by grepping script text:

* ``modules.<id>.composeDir`` relocates compose discovery; absent → module path.
* ``modules.<id>.secretsModule`` drives java-boot secrets when no ops.config.sh.
* ``modules.<id>.dev.services.<svc>.*`` and ``dev.watchRoots`` override the
  conventional port / health / Dockerfile / watch defaults; absent → unchanged.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]

BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def _consumer(tmp_path: Path, module: dict) -> Path:
    root = tmp_path / "consumer"
    backend = root / "apps" / "backend"
    for sub in ("api", "mobile"):
        (backend / sub).mkdir(parents=True)
        (backend / sub / "build.gradle").write_text("", encoding="utf-8")
    compose_dir = root / "ops" / "compose"
    compose_dir.mkdir(parents=True)
    compose = "services:\n  api:\n    container_name: demo-api-dev\n  mobile:\n    image: x\n"
    (compose_dir / "docker-compose.dev.yml").write_text(compose, encoding="utf-8")
    (root / "geostat.ops.json").write_text(
        json.dumps(
            {
                "version": 2,
                "package": "kit",
                "secrets": "ops/config",
                "compose": {"catalog": "ops/compose/catalog.json"},
                "modules": {"backend": {"type": "java-boot", "role": "api", "path": "apps/backend", **module}},
            }
        ),
        encoding="utf-8",
    )
    return root


def _run(root: Path, body: str) -> str:
    script = f"""
set -e
export GEOSTAT_PROJECT_ROOT='{root.as_posix()}'
export GEOSTAT_KIT_ROOT='{PKG.as_posix()}'
export GEOSTAT_MODULE_ID=backend
source "$GEOSTAT_KIT_ROOT/lib/project.sh"
source "$GEOSTAT_KIT_ROOT/lib/env.sh"
source "$GEOSTAT_KIT_ROOT/lib/drivers.sh"
PROJECT_DIR="$(geostat_module_project_dir backend)"
COMPOSE_DIR="$(geostat_module_compose_dir backend)"
COMPOSE_FILE=docker-compose.dev.yml
source "$GEOSTAT_KIT_ROOT/toolkit/deploy/modules.sh"
source "$GEOSTAT_KIT_ROOT/toolkit/deploy/dev-remote.sh"
{body}
"""
    out = subprocess.run([BASH, "-c", script], capture_output=True, text=True, check=True)
    return out.stdout.replace("\r", "").strip()


def test_compose_dir_defaults_to_module_path(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"secretsModule": "backend"})
    assert _run(root, 'echo "$COMPOSE_DIR"').endswith("/apps/backend")


def test_compose_dir_declared_outside_source_tree(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"secretsModule": "backend", "composeDir": "ops/compose"})
    out = _run(root, 'echo "$COMPOSE_DIR"; source "$GEOSTAT_KIT_ROOT/toolkit/deploy/common.sh"; container_name_for api')
    compose_dir, container = out.splitlines()
    assert compose_dir.endswith("/ops/compose")
    assert container == "demo-api-dev"


def test_secrets_module_resolves_from_manifest(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"secretsModule": "projects/demo/services/api"})
    assert _run(root, "geostat_secrets_module_name backend") == "projects/demo/services/api"


def test_undeclared_dev_settings_keep_conventions(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"secretsModule": "backend"})
    out = _run(
        root,
        "dev_port_var_for api; dev_default_port_for api; dev_health_path_for api; dev_dockerfile_for api; dev_watch_roots",
    ).splitlines()
    assert out == ["WORKER_PORT", "8091", "/actuator/health", "api/Dockerfile.dev.remote", "src", "shared", "worker"]


def test_declared_dev_settings_override_conventions(tmp_path: Path) -> None:
    root = _consumer(
        tmp_path,
        {
            "secretsModule": "backend",
            "dev": {
                "watchRoots": ["core/src", "api/src"],
                "services": {
                    "api": {"portEnv": "API_PORT", "port": 8081, "healthPath": "/health", "dockerfile": "api/Dockerfile.dev"}
                },
            },
        },
    )
    out = _run(
        root,
        "dev_port_var_for api; dev_default_port_for api; dev_health_path_for api; dev_dockerfile_for api; dev_watch_roots; dev_port_var_for mobile",
    ).splitlines()
    assert out == ["API_PORT", "8081", "/health", "api/Dockerfile.dev", "core/src", "api/src", "WORKER_PORT"]


def test_workspace_manifest_marker_uses_module_id() -> None:
    text = (PKG / "toolkit" / "deploy" / "dev-remote.sh").read_text(encoding="utf-8")
    assert '"module":"backend"' not in text
    assert '"module":"${GEOSTAT_MODULE_ID:-}"' in text
