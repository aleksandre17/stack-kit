"""
Deploy path resolution — single source for tests and tooling.
Mirrors kits/stack-kit/toolkit/powershell/Deploy-Path.ps1
"""
from __future__ import annotations

import re
from typing import Literal

FrontendDeployKind = Literal["static", "compose-dev", "compose-prod"]
BackendDeployKind = Literal["runtime", "workspace"]
DeployKind = FrontendDeployKind
VALID_LAYOUTS = frozenset({"structured", "flat", "legacy"})
VALID_PATH_MODES = frozenset({"base", "full"})

RSYNC_DEFAULT_EXCLUDES = (
    "node_modules/",
    "dist/",
    "build/",
    ".git/",
    ".idea/",
    ".vscode/",
    "logs/",
    "coverage/",
    ".angular/",
    "tmp/",
    ".turbo/",
    ".next/",
    "deploy-staging/",
    ".cache/",
    "*.log",
)


def normalize_base(base: str) -> str:
    return base.strip().rstrip("/")


def resolve_module_deploy_path(
    *,
    base: str,
    container_name: str,
    kind: DeployKind,
    layout: str = "structured",
    path_mode: str = "base",
) -> str:
    if not base:
        raise ValueError("DEPLOY_PATH or DEPLOY_SERVER_BASE required")
    base = normalize_base(base)
    if path_mode not in VALID_PATH_MODES:
        path_mode = "base"
    if layout not in VALID_LAYOUTS:
        layout = "structured"

    if path_mode == "full":
        if base.endswith(f"/{container_name}"):
            return base
        return base

    if layout == "structured":
        if kind == "static":
            return f"{base}/static/{container_name}"
        if kind == "compose-dev":
            return f"{base}/compose/dev/{container_name}"
        return f"{base}/compose/prod/{container_name}"

    if base.endswith(f"/{container_name}"):
        return base
    return f"{base}/{container_name}"


def resolve_backend_deploy_path(
    *,
    base: str,
    container_name: str,
    kind: BackendDeployKind = "runtime",
    layout: str = "structured",
    path_mode: str = "base",
) -> str:
    if not base:
        raise ValueError("DEPLOY_PATH or DEPLOY_SERVER_BASE required")
    base = normalize_base(base)
    if path_mode not in VALID_PATH_MODES:
        path_mode = "base"
    if layout not in VALID_LAYOUTS:
        layout = "flat"

    if path_mode == "full":
        if base.endswith(f"/{container_name}"):
            return base
        return base

    if layout == "structured":
        if kind == "workspace":
            return f"{base}/workspace/{container_name}"
        return f"{base}/runtime/{container_name}"

    if base.endswith(f"/{container_name}"):
        return base
    return f"{base}/{container_name}"


def backend_deploy_path_candidates(*, base: str, container_name: str) -> list[str]:
    base = normalize_base(base)
    if not base:
        return []
    return [
        f"{base}/runtime/{container_name}",
        f"{base}/workspace/{container_name}",
        f"{base}/{container_name}",
    ]


def resolve_deploy_path_base(
    *,
    module_deploy_path: str | None,
    base_module_deploy_path: str | None,
    default_remote_base: str | None = None,
) -> str:
    """Mirror deploy-path.sh: worker modules inherit backend DEPLOY_PATH when omitted."""
    if module_deploy_path:
        return normalize_base(module_deploy_path)
    if base_module_deploy_path:
        return normalize_base(base_module_deploy_path)
    if default_remote_base:
        return normalize_base(default_remote_base)
    return ""


def deploy_path_candidates(*, base: str, container_name: str) -> list[str]:
    base = normalize_base(base)
    if not base:
        return []
    return [
        f"{base}/static/{container_name}",
        f"{base}/compose/prod/{container_name}",
        f"{base}/compose/dev/{container_name}",
        f"{base}/{container_name}",
    ]


def infer_server_base_from_ssh(server: str) -> str | None:
    m = re.match(r"^[^@]+@(.+)$", server.strip())
    if not m:
        return None
    user = server.split("@", 1)[0]
    return f"/home/{user}"


def normalize_infra_slug(slug: str) -> str:
    s = slug.strip().rstrip("/")
    return re.sub(r"[^a-z0-9._-]+", "-", s.lower()).strip("-")


def resolve_infra_deploy_path(
    *,
    deploy_path: str | None,
    server_base: str | None,
    global_project: str | None,
    consumer_slug: str,
) -> str:
    """Remote infra root: {server_base}/{global_project}/infra/{consumer_slug}."""
    slug = normalize_infra_slug(consumer_slug)
    if not slug:
        raise ValueError("INFRA_SLUG or consumer repo name required")
    if deploy_path:
        base = normalize_base(deploy_path)
        if not base.endswith(f"/infra/{slug}"):
            raise ValueError(f"DEPLOY_PATH must end with /infra/{slug}, got: {base}")
        return base
    if server_base and global_project:
        gp = normalize_infra_slug(global_project)
        return f"{normalize_base(server_base)}/{gp}/infra/{slug}"
    # No invented server path: a deploy target nobody declared is refused, never guessed.
    raise ValueError("infra deploy path: set DEPLOY_PATH in the infra env, or DEPLOY_SERVER_BASE / "
                     "DEPLOY_SERVER so it can be derived")


def infra_deploy_path_candidates(
    *, server_base: str, global_project: str, consumer_slug: str
) -> list[str]:
    slug = normalize_infra_slug(consumer_slug)
    gp = normalize_infra_slug(global_project)
    base = normalize_base(server_base)
    if not base or not slug:
        return []
    return [f"{base}/{gp}/infra/{slug}"]
