"""Manifest-driven compose service blocks (N modules — api / worker / ui)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lib.compose_identity import (
    embedded_worker_enabled,
    primary_api_module_id,
    resolve_module_service_name,
    stack_compose_module_ids,
)
from lib.credentials import module_credentials
from lib.project_context import ProjectContext
from lib.stack_endpoints import (
    _module_port_env_keys,
    _parse_env_files,
    _secrets_env_files,
    load_stack_catalog,
    resolve_module_port,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_CATALOG = PACKAGE_ROOT / "compose" / "compose-catalog.json"
STACK_CATALOG = PACKAGE_ROOT / "compose" / "stack-catalog.json"


def load_compose_catalog(path: Path | None = None) -> dict[str, Any]:
    p = path or COMPOSE_CATALOG
    if not p.is_file():
        return {"templates": {}, "templateKey": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def host_compose_catalog(ctx: ProjectContext) -> dict[str, Any]:
    """The kit's module templates with the host's own over them: a host's compose catalog may carry
    `templates` a project driver's `compose.templates` names (ADR-001 amendment 12)."""
    cat = load_compose_catalog()
    try:
        host = json.loads(ctx.catalog_path.read_text(encoding="utf-8")) if ctx.catalog_path.is_file() else {}
    except (ValueError, AttributeError):
        host = {}
    own = host.get("moduleTemplates") if isinstance(host, dict) else None
    if isinstance(own, dict):
        cat = {**cat, "templates": {**(cat.get("templates") or {}), **own}}
    return cat


def _rel_posix(from_dir: Path, to_path: Path) -> str:
    return os.path.relpath(to_path, from_dir).replace("\\", "/")


def _resolve_dockerfiles(module_path: Path, module_id: str, role: str, driver_type: str) -> tuple[str, str, str]:
    """Return (dockerfile_dev, dockerfile_prod, build_context_prod_rel_suffix): the Dockerfiles the
    driver declares (`compose.dockerfiles`), else Dockerfile.dev / Dockerfile."""
    from lib.modules import driver_capability

    declared = (driver_capability(driver_type, "compose", {}) or {}).get("dockerfiles") or {}
    return str(declared.get("dev") or "Dockerfile.dev"), str(declared.get("prod") or "Dockerfile"), "."


def missing_recipe(ctx: ProjectContext, module_id: str, profile: str) -> str:
    """Why a module's local service cannot be built here ("" when it can): it builds from a Dockerfile in
    the module that is not there, or its driver declares no compose template for its role and profile
    (never a crash in compose-gen). A module that runs its release image (`compose.fromRelease`) builds
    from the release tree `stage` writes, and is never missing one here."""
    from lib.modules import driver_capability

    cfg = (ctx.manifest.get("modules") or {}).get(module_id) or {}
    driver_type = str(cfg.get("type") or "")
    role = str(cfg.get("role") or "")
    declared = ((driver_capability(driver_type, "compose", {}) or {}).get("templates") or {}).get(role) or {}
    if not declared.get(profile):  # a driver that declares no local service for this role
        return (f"modules.{module_id} ({driver_type}) has no local {profile} service: its driver declares no compose "
                f"template for role {role or '-'} -- build and test it with `mod {module_id} build`/`test`, or run it "
                f"remotely with `dev up {module_id}`")
    if from_release(driver_type):
        return ""
    df_dev, df_prod, _suffix = _resolve_dockerfiles(ctx.module_path(module_id), module_id, str(cfg.get("role") or ""), driver_type)
    wanted = df_dev if profile == "dev" else df_prod
    if (ctx.module_path(module_id) / wanted).is_file():
        return ""
    return (f"modules.{module_id} has no {wanted} in {cfg.get('path') or '.'} -- its local {profile} service is not "
            f"written; add the recipe, or run its release image (`compose.fromRelease` on its driver)")


def _role_catalog_entry(stack_cat: dict[str, Any], role: str) -> dict[str, Any]:
    return (stack_cat.get("roles") or {}).get(role) or {}


def _module_port(
    ctx: ProjectContext,
    module_id: str,
    role: str,
    stack_cat: dict[str, Any],
) -> tuple[str, str]:
    role_cfg = _role_catalog_entry(stack_cat, role)
    secrets_folder = ctx.secrets_module_folder(module_id)
    env = _parse_env_files(_secrets_env_files(ctx.secrets_folder_path(secrets_folder)))
    keys = _module_port_env_keys(role_cfg, secrets_folder)
    role_default = str(role_cfg.get("defaultPort") or "")
    resolved = resolve_module_port(
        role=role,
        role_cfg=role_cfg,
        secrets_folder=secrets_folder,
        env=env,
    )
    default = resolved or role_default
    slug_key = f"{secrets_folder.upper().replace('-', '_')}_PORT"
    if env.get(slug_key):
        return slug_key, default
    for key in keys:
        if env.get(key):
            return key, default
    return (keys[0] if keys else "PORT"), default


def _credential_blocks(
    manifest: dict[str, Any],
    module_id: str,
    secrets_rel: str,
    primary_api: str | None,
) -> tuple[str, str]:
    cfg = (manifest.get("modules") or {}).get(module_id) or {}
    if not isinstance(cfg, dict):
        return "", ""
    if cfg.get("credentials") or module_id == primary_api:
        creds = module_credentials(manifest, module_id)
    else:
        creds = []
    if not creds:
        return "", ""
    vol_lines = [
        f"      - {secrets_rel}/{c['file']}:{c['mount']}:ro" for c in creds
    ]
    vol_block = "    volumes:\n" + "\n".join(vol_lines) + "\n"
    env_lines = [f"      {c['envVar']}: {c['mount']}" for c in creds if c.get("envVar")]
    env_block = "\n".join(env_lines) + "\n" if env_lines else ""
    return vol_block, env_block


def from_release(driver_type: str) -> bool:
    """Whether the local stack runs the module's release image (`compose.fromRelease`): built from
    the release tree `stack` stages (lib/package.py `stage`), by the recipe a deploy builds."""
    from lib.modules import driver_capability

    return bool((driver_capability(driver_type, "compose", {}) or {}).get("fromRelease"))


def _release_fmt(ctx: ProjectContext, module_id: str, compose_dir: Path) -> dict[str, str]:
    """The release template's values: the staged tree as the build context, the service's internal
    port, and a link per proxied service (its local compose name under the service id the rendered
    server config proxies to -- the name it has on a target's stack)."""
    from lib import package
    from lib.delivery.model import all_services, module_services

    svc = module_services(ctx.manifest, module_id)[0]
    by_id = {s.id: s for s in all_services(ctx.manifest)}
    links = [f"      - {resolve_module_service_name(str(by_id[sid].module), ctx.manifest, ctx.root)}:{sid}"
             for sid in sorted({str(v) for v in (svc.spec.get("proxy") or {}).values()})
             if sid in by_id and by_id[sid].module]
    return {"release_context": _rel_posix(compose_dir, package.local_tree(ctx.root, module_id) / svc.id),
            "container_port": str(svc.spec.get("port") or ""),
            "release_links": ("    links:\n" + "\n".join(links) + "\n") if links else ""}


def _template_for(driver_type: str, role: str, profile: str, cat: dict[str, Any]) -> str:
    """The template the module's DRIVER declares for its role and profile (`compose.templates`; a
    project driver declares its own), from the kit's templates or the host's own."""
    from lib.modules import driver_capability

    key_map = ((driver_capability(driver_type, "compose", {}) or {}).get("templates") or {}).get(role, {})
    tpl_key = key_map.get(profile)
    if not tpl_key:
        raise ValueError(
            f"compose-catalog: no template for type={driver_type!r} role={role!r} profile={profile!r}"
        )
    templates = cat.get("templates") or {}
    if tpl_key not in templates:
        raise KeyError(f"compose-catalog missing template {tpl_key!r}")
    return templates[tpl_key]


def _ordered_modules(manifest: dict[str, Any], module_ids: list[str]) -> list[str]:
    mods = manifest.get("modules") or {}
    apis = [m for m in module_ids if isinstance(mods.get(m), dict) and mods[m].get("role") == "api"]
    workers = [
        m for m in module_ids if isinstance(mods.get(m), dict) and mods[m].get("role") == "worker"
    ]
    uis = [m for m in module_ids if isinstance(mods.get(m), dict) and mods[m].get("role") == "ui"]
    rest = [m for m in module_ids if m not in apis + workers + uis]
    primary = primary_api_module_id(manifest, apis)
    if primary and primary in apis:
        apis = [primary] + [m for m in apis if m != primary]
    return apis + workers + uis + rest


def render_module_service(
    *,
    ctx: ProjectContext,
    module_id: str,
    profile: str,
    compose_dir: Path,
    fmt_global: dict[str, str],
    fmt_extra: dict[str, str],
    compose_cat: dict[str, Any],
    stack_cat: dict[str, Any],
    module_fmt: dict[str, str] | None = None,
) -> str:
    manifest = ctx.manifest
    cfg = (manifest.get("modules") or {}).get(module_id)
    if not isinstance(cfg, dict):
        raise KeyError(f"manifest modules.{module_id} missing")
    driver_type = str(cfg.get("type") or "")
    role = str(cfg.get("role") or "")
    target = str(cfg.get("target") or module_id)
    module_path = ctx.module_path(module_id)
    secrets_folder = ctx.secrets_module_folder(module_id)
    secrets_rel = _rel_posix(compose_dir, ctx.secrets_folder_path(secrets_folder))
    module_context = _rel_posix(compose_dir, module_path)
    port_env, port_default = _module_port(ctx, module_id, role, stack_cat)
    role_cfg = _role_catalog_entry(stack_cat, role)
    health_path = str(role_cfg.get("urlPath") or "/health")
    own = cfg.get("container") if isinstance(cfg.get("container"), dict) else {}
    if own.get("port"):  # the module's own (read from the app, e.g. Spring's server.port), over the role's default
        port_default = str(own["port"])
    if own.get("healthPath"):
        health_path = str(own["healthPath"])
    primary = primary_api_module_id(manifest)
    cred_vols, cred_env = _credential_blocks(manifest, module_id, secrets_rel, primary)
    df_dev, df_prod, prod_ctx_suffix = _resolve_dockerfiles(module_path, module_id, role, driver_type)
    service = resolve_module_service_name(module_id, manifest, ctx.root)
    tpl = _template_for(driver_type, role, profile, compose_cat)
    module_build_context = module_context
    if prod_ctx_suffix == "src" and profile == "prod":
        module_build_context = f"{module_context}/src" if not module_context.endswith("/src") else module_context
    fmt = {
        # Optional container resource-limit block — brand-agnostic seam, empty by
        # default. A consumer opts in by supplying `resource_limits` via a target's
        # `fmt` or per-module `moduleFmt` (e.g. "    mem_limit: 1g\n    cpus: 1.5\n").
        # Keeps sizing constants in the consumer catalog, not kit runtime (Law 10).
        "resource_limits": "",
        **fmt_global,
        **fmt_extra,
        **(module_fmt or {}),
        "service": service,
        "module_context": module_context,
        "module_build_context": module_build_context,
        "secrets_rel": secrets_rel,
        "dockerfile_dev": df_dev,
        "dockerfile_prod": df_prod,
        "port_env": port_env,
        "port_default": port_default,
        "health_path": health_path,
        "credential_volumes_block": cred_vols,
        "credential_env_block": cred_env,
        "primary_api_service": (
            resolve_module_service_name(primary, manifest, ctx.root)
            if primary
            else fmt_global["api_service"]
        ),
        "app_dev_mount": module_context,
        **(_release_fmt(ctx, module_id, compose_dir) if from_release(driver_type) else {}),
    }
    return tpl.format(**fmt)


def render_backend_embedded_worker(
    *,
    profile: str,
    compose_dir: Path,
    ctx: ProjectContext,
    fmt_global: dict[str, str],
    fmt_extra: dict[str, str],
    compose_cat: dict[str, Any],
) -> str:
    primary = primary_api_module_id(manifest := ctx.manifest, stack_compose_module_ids(manifest))
    if not primary:
        return ""
    backend_path = ctx.module_path(primary)
    secrets_rel = _rel_posix(compose_dir, ctx.secrets_folder_path(ctx.secrets_module_folder(primary)))
    tpl_name = (
        "module_backend_worker_dev" if profile == "dev" else "module_backend_worker_prod"
    )
    tpl = compose_cat["templates"][tpl_name]
    fmt = {
        **fmt_global,
        **fmt_extra,
        "backend_context": _rel_posix(compose_dir, backend_path),
        "secrets_backend": secrets_rel,
    }
    return tpl.format(**fmt)


def build_manifest_stack_services(
    *,
    ctx: ProjectContext,
    profile: str,
    compose_dir: Path,
    fmt_global: dict[str, str],
    fmt_extra: dict[str, str],
    features: dict[str, Any],
    compose_cat: dict[str, Any] | None = None,
    stack_cat: dict[str, Any] | None = None,
    module_fmt: dict[str, dict[str, str]] | None = None,
) -> str:
    compose_cat = compose_cat or host_compose_catalog(ctx)
    stack_cat = stack_cat or load_stack_catalog(STACK_CATALOG)
    module_ids = stack_compose_module_ids(ctx.manifest)
    ordered = _ordered_modules(ctx.manifest, module_ids)
    chunks: list[str] = []
    for mid in ordered:
        cfg = (ctx.manifest.get("modules") or {}).get(mid)
        if not isinstance(cfg, dict):
            continue
        role = str(cfg.get("role") or "")
        if role not in ("api", "worker", "ui"):
            continue
        why = missing_recipe(ctx, mid, profile)
        if why:
            import sys
            print(f"  skip {why}", file=sys.stderr)
            continue
        chunks.append(
            render_module_service(
                ctx=ctx,
                module_id=mid,
                profile=profile,
                compose_dir=compose_dir,
                fmt_global=fmt_global,
                fmt_extra=fmt_extra,
                compose_cat=compose_cat,
                stack_cat=stack_cat,
                module_fmt=(module_fmt or {}).get(mid),
            )
        )
    if embedded_worker_enabled(ctx.manifest, features) and primary_api_module_id(
        ctx.manifest, module_ids
    ):
        chunks.append(
            render_backend_embedded_worker(
                profile=profile,
                compose_dir=compose_dir,
                ctx=ctx,
                fmt_global=fmt_global,
                fmt_extra=fmt_extra,
                compose_cat=compose_cat,
            )
        )
    return "".join(chunks)


def build_single_module_compose(
    *,
    ctx: ProjectContext,
    module_id: str,
    profile: str,
    compose_dir: Path,
    fmt_global: dict[str, str],
    fmt_extra: dict[str, str],
    compose_cat: dict[str, Any] | None = None,
    stack_cat: dict[str, Any] | None = None,
) -> str:
    compose_cat = compose_cat or host_compose_catalog(ctx)
    stack_cat = stack_cat or load_stack_catalog(STACK_CATALOG)
    return render_module_service(
        ctx=ctx,
        module_id=module_id,
        profile=profile,
        compose_dir=compose_dir,
        fmt_global=fmt_global,
        fmt_extra=fmt_extra,
        compose_cat=compose_cat,
        stack_cat=stack_cat,
    )


def ops_modules_declaration(driver_type: str) -> dict[str, Any]:
    """What a driver declares for the generated ops.modules registry (`compose.opsModules`): its
    `kind`, the `columns` header, the `embeddedWorker` row and the `shared` build module row
    (`marker` under the module, `row`). A bare string is the kind alone. The kit names no build tool."""
    from lib.modules import driver_capability

    value = (driver_capability(driver_type, "compose", {}) or {}).get("opsModules")
    if isinstance(value, str):
        return {"kind": value} if value else {}
    return value if isinstance(value, dict) and value.get("kind") else {}


def _ops_modules_kind(driver_type: str) -> str:
    """The artifact kind a driver's modules take in the generated ops.modules registry, or ""."""
    return str(ops_modules_declaration(driver_type).get("kind") or "")


def ops_modules_lines(
    ctx: ProjectContext,
    fmt_global: dict[str, str],
    features: dict[str, Any],
) -> list[str]:
    """Build/container registry lines for the modules whose driver declares `compose.opsModules`, plus
    the embedded backend worker row the primary api module's driver declares."""
    lines: list[str] = []
    module_ids = stack_compose_module_ids(ctx.manifest)
    mods = ctx.manifest.get("modules") or {}
    for mid in _ordered_modules(ctx.manifest, module_ids):
        cfg = mods.get(mid)
        if not isinstance(cfg, dict) or not _ops_modules_kind(str(cfg.get("type") or "")):
            continue
        role = str(cfg.get("role") or "")
        service = resolve_module_service_name(mid, ctx.manifest, ctx.root)
        module_path = ctx.module_path(mid)
        _, df_prod, prod_suffix = _resolve_dockerfiles(module_path, mid, role, str(cfg.get("type")))
        if prod_suffix == "src" and not df_prod.startswith("src/"):
            df_prod = f"src/{df_prod}"
        # A standalone module builds its own artifact kind; the embedded backend worker is appended below.
        lines.append(f"{service}||{_ops_modules_kind(str(cfg.get('type')))}|{df_prod}|yes")
    primary = primary_api_module_id(ctx.manifest, module_ids)
    if embedded_worker_enabled(ctx.manifest, features) and primary:
        row = ops_modules_declaration(str((mods.get(primary) or {}).get("type") or "")).get("embeddedWorker")
        if row:
            lines.append(str(row).format_map(fmt_global))
    return lines
