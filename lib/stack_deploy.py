"""Stack remote deploy steps — manifest modules (stack.composeModules) or explicit stackDeploy.steps."""
from __future__ import annotations

from typing import Any

from lib.modules import _modules, driver_deploy_args, module_ids, module_role

ROLE_DEPLOY_ORDER = ("api", "worker", "gateway", "data", "ui", "other")


def stack_deploy_module_ids(manifest: dict[str, Any]) -> list[str]:
    """Module ids for stack-deploy when steps are generated (not explicit)."""
    sd = manifest.get("stackDeploy") or {}
    if isinstance(sd.get("modules"), list) and sd["modules"]:
        return [str(m) for m in sd["modules"]]
    stack = manifest.get("stack") or {}
    if isinstance(stack.get("composeModules"), list) and stack["composeModules"]:
        return [str(m) for m in stack["composeModules"]]
    return module_ids(manifest)


def ordered_stack_deploy_modules(manifest: dict[str, Any], module_filter: list[str] | None = None) -> list[str]:
    """Role-ordered subset preserving relative order within each role from module_filter."""
    allowed = module_filter if module_filter is not None else stack_deploy_module_ids(manifest)
    mods = _modules(manifest)
    by_role: dict[str, list[str]] = {r: [] for r in ROLE_DEPLOY_ORDER}
    extra: list[str] = []
    for mid in allowed:
        if mid not in mods:
            continue
        role = module_role(manifest, mid)
        if role in by_role:
            by_role[role].append(mid)
        else:
            extra.append(mid)
    out: list[str] = []
    for role in ROLE_DEPLOY_ORDER:
        out.extend(by_role.get(role, []))
    out.extend(extra)
    return out


def deploy_step_for_module(manifest: dict[str, Any], module_id: str) -> dict[str, Any]:
    """The deploy step for a module — argv comes from what its DRIVER declares.

    The interpreter knows there is a `deploy` command and that a driver may need
    extra argv; it does not know any driver's name. A driver whose `release` rung declares no
    `args` deploys with none.
    """
    cfg = _modules(manifest).get(module_id) or {}
    typ = str(cfg.get("type") or "")
    return {"module": module_id, "command": "deploy", "args": driver_deploy_args(typ)}


def default_stack_deploy_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Role-ordered deploy plan from stack.composeModules / stackDeploy.modules / all modules."""
    return [
        deploy_step_for_module(manifest, mid)
        for mid in ordered_stack_deploy_modules(manifest)
    ]


def stack_deploy_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    sd = manifest.get("stackDeploy") or {}
    steps = sd.get("steps")
    if isinstance(steps, list) and steps:
        return steps
    return default_stack_deploy_steps(manifest)


def validate_stack_deploy(manifest: dict[str, Any]) -> list[str]:
    """Warnings when explicit steps diverge from stack module set."""
    warnings: list[str] = []
    sd = manifest.get("stackDeploy") or {}
    steps = sd.get("steps")
    if not isinstance(steps, list) or not steps:
        return warnings
    expected = set(ordered_stack_deploy_modules(manifest))
    step_mods = {str(s.get("module")) for s in steps if isinstance(s, dict) and s.get("module")}
    missing = expected - step_mods
    if missing:
        warnings.append(
            f"stackDeploy.steps: missing modules {sorted(missing)} "
            f"(omit steps to auto-generate from stack.composeModules)"
        )
    unknown = step_mods - set(_modules(manifest).keys())
    if unknown:
        warnings.append(f"stackDeploy.steps: unknown modules {sorted(unknown)}")
    return warnings
