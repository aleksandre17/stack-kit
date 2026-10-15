"""Stack remote deploy — manifest composeModules drives steps."""
from __future__ import annotations

import json

from lib.stack_deploy import (
    default_stack_deploy_steps,
    ordered_stack_deploy_modules,
    stack_deploy_module_ids,
    stack_deploy_steps,
    validate_stack_deploy,
)


def _arch_b_manifest() -> dict:
    return {
        "version": 2,
        "modules": {
            "backend": {"role": "api", "type": "java-boot", "path": "a", "secretsModule": "backend"},
            "retrieval": {"role": "api", "type": "java-boot", "path": "b", "secretsModule": "retrieval"},
            "ingestion": {"role": "worker", "type": "java-boot", "path": "c", "secretsModule": "ingestion"},
            "frontend": {"role": "ui", "type": "node-vite", "path": "d", "secretsModule": "frontend"},
        },
        "stack": {
            "composeModules": ["backend", "retrieval", "ingestion", "frontend"],
        },
    }


def test_stack_deploy_module_ids_from_compose_modules() -> None:
    m = _arch_b_manifest()
    assert stack_deploy_module_ids(m) == ["backend", "retrieval", "ingestion", "frontend"]


def test_ordered_role_api_before_worker_before_ui() -> None:
    m = _arch_b_manifest()
    order = ordered_stack_deploy_modules(m)
    assert order.index("backend") < order.index("retrieval")
    assert order.index("retrieval") < order.index("ingestion")
    assert order.index("ingestion") < order.index("frontend")


def test_default_steps_include_all_compose_modules() -> None:
    m = _arch_b_manifest()
    steps = default_stack_deploy_steps(m)
    ids = [s["module"] for s in steps]
    assert ids == ["backend", "retrieval", "ingestion", "frontend"]
    assert steps[0]["args"] == ["all"]
    assert "dist" in steps[-1]["args"]
    assert "{environment}" in steps[-1]["args"]


def test_explicit_steps_override() -> None:
    m = _arch_b_manifest()
    m["stackDeploy"] = {
        "steps": [{"module": "frontend", "command": "deploy", "args": ["dist"]}],
    }
    assert len(stack_deploy_steps(m)) == 1


def test_validate_warns_missing_modules_in_explicit_steps() -> None:
    m = _arch_b_manifest()
    m["stackDeploy"] = {
        "steps": [
            {"module": "backend", "command": "deploy", "args": ["all"]},
            {"module": "frontend", "command": "deploy", "args": ["dist"]},
        ],
    }
    warns = validate_stack_deploy(m)
    assert any("retrieval" in w for w in warns)


def test_stack_deploy_modules_override() -> None:
    m = _arch_b_manifest()
    m["stackDeploy"] = {"modules": ["backend", "frontend"]}
    steps = default_stack_deploy_steps(m)
    assert [s["module"] for s in steps] == ["backend", "frontend"]
