"""Manifest-driven Spring application*.yml generation (P0-kit-09)."""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib.modules import driver_supports_config_gen
from lib.project_context import ProjectContext
from lib.stack_endpoints import load_stack_catalog, resolve_module_port

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PACKAGE_ROOT / "config" / "config-catalog.json"

CUSTOM_FILE = "application-custom.yml"
POSTGRES_GENERATED_FILES = (
    "application.yml",
    "application-hybrid-env.yml",
    "application-docker-env.yml",
    "application-db.yml",
    "application-nodb.yml",
)
SIMPLE_GENERATED_FILES = ("application.yml",)
ENV_PROFILES_GENERATED_FILES = (
    "application.yml",
    "application-local.yml",
    "application-dev.yml",
    "application-prod.yml",
)
ENV_PROFILE_ORDER = ("local", "dev", "prod")

MODE_POSTGRES = "postgres-profiles"
MODE_SIMPLE = "simple"
MODE_ENV_PROFILES = "env-profiles"

DEFAULT_ENV_PROFILES: dict[str, dict[str, Any]] = {
    "local": {"envFile": ".env.dev"},
    "dev": {"envFile": ".env.dev", "devtools": True},
    "prod": {"envFile": ".env.prod", "prodLogging": True},
}


def load_config_catalog(path: Path | None = None) -> dict[str, Any]:
    p = path or CATALOG_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def _slug_port_env(secrets_module: str) -> str:
    return f"{secrets_module.upper().replace('-', '_')}_PORT"


def _parse_env_file(path: Path) -> dict[str, str]:
    from lib.envfile import parse

    return parse(path)


def _port_env_key(cfg: dict[str, Any], secrets_module: str) -> str:
    spring_cfg = cfg.get("spring") if isinstance(cfg.get("spring"), dict) else {}
    override = spring_cfg.get("portEnv")
    if override:
        return str(override)
    return _slug_port_env(secrets_module)


def _secrets_env_file_rel(ctx: ProjectContext, module_id: str, env_file: str) -> str:
    rel = Path(env_file)
    if rel.is_absolute():
        return rel.as_posix()
    secret_path = ctx.secrets_module_dir(module_id) / env_file
    mod_path = ctx.module_path(module_id)
    return os.path.relpath(secret_path, mod_path).replace("\\", "/")


# Spring management-endpoint exposure. The kit default is the NARROW one (OWASP: a
# management surface is not exposure-by-default material); a consumer that wants more
# DECLARES it as modules.<id>.spring.managementEndpoints.
DEFAULT_MANAGEMENT_ENDPOINTS = "health,info"


def _management_endpoints(spring_cfg: dict[str, Any]) -> str:
    raw = spring_cfg.get("managementEndpoints")
    if isinstance(raw, list):
        joined = ",".join(str(x).strip() for x in raw if str(x).strip())
        return joined or DEFAULT_MANAGEMENT_ENDPOINTS
    text = str(raw or "").strip()
    return text or DEFAULT_MANAGEMENT_ENDPOINTS


@dataclass(frozen=True)
class ModuleConfigSpec:
    module_id: str
    mode: str
    app_name: str
    port_env: str
    port_default: str
    postgres_schema: str = ""
    postgres_db: str = ""
    default_profile: str = ""
    management_endpoints: str = DEFAULT_MANAGEMENT_ENDPOINTS
    profile_groups: dict[str, list[str]] = field(default_factory=dict)
    rabbitmq: bool = False
    events_enabled_env: str = ""
    env_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)


def _resolve_port(ctx: ProjectContext, module_id: str, cfg: dict[str, Any]) -> tuple[str, str]:
    secrets_module = ctx.secrets_module_folder(module_id)
    port_env = _port_env_key(cfg, secrets_module)
    stack_cat = load_stack_catalog(PACKAGE_ROOT / "compose" / "stack-catalog.json")
    role = ctx.get_module_role(module_id)
    role_cfg = (stack_cat.get("roles") or {}).get(role) or {}
    env = _parse_env_file(ctx.secrets_module_dir(module_id) / ".env.dev")
    port_default = resolve_module_port(
        role=role,
        role_cfg=role_cfg,
        secrets_folder=secrets_module,
        env=env,
    ) or str(role_cfg.get("defaultPort") or "8080")
    if env.get(port_env):
        port_default = env[port_env]
    return port_env, port_default


def _postgres_module_spec(ctx: ProjectContext, module_id: str, cfg: dict[str, Any]) -> ModuleConfigSpec:
    datastores = cfg["datastores"]
    pg = datastores["postgres"]
    port_env, port_default = _resolve_port(ctx, module_id, cfg)

    spring_cfg = cfg.get("spring") if isinstance(cfg.get("spring"), dict) else {}
    app_name = str(spring_cfg.get("applicationName") or f"{module_id}-service")
    default_profile = str(spring_cfg.get("defaultProfile") or "nodb")
    groups_raw = spring_cfg.get("profileGroups")
    if isinstance(groups_raw, dict) and groups_raw:
        profile_groups = {str(k): list(v) for k, v in groups_raw.items()}
    else:
        profile_groups = {
            "hybrid": ["db", "hybrid-env"],
            "docker": ["db", "docker-env"],
        }

    rabbitmq = isinstance(datastores.get("rabbitmq"), dict)
    events_env = "INGESTION_EVENTS_ENABLED"
    events_cfg = datastores.get("events") if isinstance(datastores.get("events"), dict) else {}
    if events_cfg.get("enabledEnv"):
        events_env = str(events_cfg["enabledEnv"])

    return ModuleConfigSpec(
        module_id=module_id,
        mode=MODE_POSTGRES,
        app_name=app_name,
        port_env=port_env,
        port_default=port_default,
        postgres_schema=str(pg.get("schema") or module_id),
        postgres_db=str(pg.get("database") or "app"),
        default_profile=default_profile,
        management_endpoints=_management_endpoints(spring_cfg),
        profile_groups=profile_groups,
        rabbitmq=rabbitmq,
        events_enabled_env=events_env,
    )


def _simple_module_spec(ctx: ProjectContext, module_id: str, cfg: dict[str, Any]) -> ModuleConfigSpec:
    port_env, port_default = _resolve_port(ctx, module_id, cfg)
    spring_cfg = cfg.get("spring") if isinstance(cfg.get("spring"), dict) else {}
    app_name = str(spring_cfg.get("applicationName") or f"{module_id}-service")
    return ModuleConfigSpec(
        module_id=module_id,
        mode=MODE_SIMPLE,
        app_name=app_name,
        port_env=port_env,
        port_default=port_default,
        management_endpoints=_management_endpoints(spring_cfg),
    )


def _env_profiles_module_spec(ctx: ProjectContext, module_id: str, cfg: dict[str, Any]) -> ModuleConfigSpec:
    port_env, port_default = _resolve_port(ctx, module_id, cfg)
    spring_cfg = cfg.get("spring") if isinstance(cfg.get("spring"), dict) else {}
    app_name = str(spring_cfg.get("applicationName") or f"{module_id}-service")
    default_profile = str(spring_cfg.get("defaultProfile") or "local")

    profiles_raw = spring_cfg.get("envProfiles")
    if isinstance(profiles_raw, dict) and profiles_raw:
        profiles = {str(k): dict(v) for k, v in profiles_raw.items() if isinstance(v, dict)}
    else:
        profiles = copy.deepcopy(DEFAULT_ENV_PROFILES)

    enriched: dict[str, dict[str, Any]] = {}
    for name, profile_cfg in profiles.items():
        pc = dict(profile_cfg)
        env_file = str(pc.get("envFile") or ".env.dev")
        pc["envImport"] = _secrets_env_file_rel(ctx, module_id, env_file)
        enriched[name] = pc

    return ModuleConfigSpec(
        module_id=module_id,
        mode=MODE_ENV_PROFILES,
        app_name=app_name,
        port_env=port_env,
        port_default=port_default,
        default_profile=default_profile,
        management_endpoints=_management_endpoints(spring_cfg),
        env_profiles=enriched,
    )


def _module_spec(ctx: ProjectContext, module_id: str) -> ModuleConfigSpec | None:
    cfg = (ctx.manifest.get("modules") or {}).get(module_id)
    if not isinstance(cfg, dict) or not driver_supports_config_gen(str(cfg.get("type") or "")):
        return None

    config_gen = cfg.get("configGen") if isinstance(cfg.get("configGen"), dict) else {}
    mode = str(config_gen.get("mode") or "")

    if mode == MODE_ENV_PROFILES:
        return _env_profiles_module_spec(ctx, module_id, cfg)

    datastores = cfg.get("datastores")
    if not isinstance(datastores, dict):
        return None

    if datastores.get("postgres") and isinstance(datastores["postgres"], dict):
        return _postgres_module_spec(ctx, module_id, cfg)
    if mode == MODE_SIMPLE or datastores.get("qdrant"):
        return _simple_module_spec(ctx, module_id, cfg)
    return None


def generated_files_for_spec(spec: ModuleConfigSpec) -> tuple[str, ...]:
    if spec.mode == MODE_SIMPLE:
        return SIMPLE_GENERATED_FILES
    if spec.mode == MODE_ENV_PROFILES:
        return ENV_PROFILES_GENERATED_FILES
    return POSTGRES_GENERATED_FILES


def _profile_groups_yaml(groups: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for name, members in groups.items():
        lines.append(f"      {name}:")
        for m in members:
            lines.append(f"        - {m}")
    return "\n".join(lines)


def _render_env_profile_file(
    profile_name: str,
    profile_cfg: dict[str, Any],
    tpl: dict[str, Any],
) -> str:
    fmt = {
        "env_import": profile_cfg["envImport"],
        "secrets_block": tpl["envProfileSecretsBlock"].format(),
    }
    if profile_cfg.get("devtools"):
        return tpl["envProfileDevYml"].format(**fmt)
    if profile_cfg.get("prodLogging"):
        return tpl["envProfileProdYml"].format(**fmt)
    return tpl["envProfileLocalYml"].format(**fmt)


def render_module_files(
    spec: ModuleConfigSpec,
    catalog: dict[str, Any] | None = None,
) -> dict[str, str]:
    cat = catalog or load_config_catalog()
    tpl = cat["javaBoot"]
    header = cat.get("generatedHeader") or "# generated by stack-kit config-gen\n"

    fmt = {
        "port_env": spec.port_env,
        "port_default": spec.port_default,
        "app_name": spec.app_name,
        "default_profile": spec.default_profile,
        "management_endpoints": spec.management_endpoints,
        "profile_groups_yaml": _profile_groups_yaml(spec.profile_groups),
        "postgres_schema": spec.postgres_schema,
        "postgres_db": spec.postgres_db,
        "events_enabled_env": spec.events_enabled_env,
        "rabbitmq_docker_block": tpl["rabbitmqDockerBlock"] if spec.rabbitmq else "",
        "rabbitmq_hybrid_block": tpl["rabbitmqHybridBlock"] if spec.rabbitmq else "",
    }

    out: dict[str, str] = {}
    if spec.mode == MODE_SIMPLE:
        out["application.yml"] = header + tpl["simpleApplicationYml"].format(**fmt)
        return out

    if spec.mode == MODE_ENV_PROFILES:
        out["application.yml"] = header + tpl["envProfilesApplicationYml"].format(**fmt)
        for profile_name in ENV_PROFILE_ORDER:
            profile_cfg = spec.env_profiles.get(profile_name)
            if not profile_cfg:
                continue
            file_name = f"application-{profile_name}.yml"
            out[file_name] = header + _render_env_profile_file(profile_name, profile_cfg, tpl)
        return out

    out["application.yml"] = header + tpl["applicationYml"].format(**fmt)
    out["application-hybrid-env.yml"] = header + tpl["hybridEnvYml"].format(**fmt)
    out["application-docker-env.yml"] = header + tpl["dockerEnvYml"].format(**fmt)
    out["application-db.yml"] = header + tpl["dbYml"].format(**fmt)
    out["application-nodb.yml"] = header + tpl["nodbYml"].format(**fmt)
    return out


def java_boot_modules_with_datastores(ctx: ProjectContext) -> list[str]:
    out: list[str] = []
    for mid in ctx.list_module_ids():
        if _module_spec(ctx, mid):
            out.append(mid)
    return out


def write_module_config(
    ctx: ProjectContext,
    module_id: str,
    *,
    dry_run: bool = False,
) -> list[Path]:
    spec = _module_spec(ctx, module_id)
    if not spec:
        raise ValueError(
            f"module '{module_id}' is not eligible for config-gen "
            "(need configGen.mode, datastores.postgres, or datastores.qdrant)"
        )
    resources = ctx.module_path(module_id) / "src" / "main" / "resources"
    rendered = render_module_files(spec)
    written: list[Path] = []
    for name in generated_files_for_spec(spec):
        path = resources / name
        content = rendered[name]
        if dry_run:
            print(f"[config-gen] would write {path.relative_to(ctx.root)}")
            continue
        resources.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def strip_generated_header(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith("# generated by stack-kit config-gen"):
        return "".join(lines[1:])
    return text


def check_module_drift(ctx: ProjectContext, module_id: str) -> list[str]:
    spec = _module_spec(ctx, module_id)
    if not spec:
        return [f"{module_id}: not eligible for config-gen"]
    resources = ctx.module_path(module_id) / "src" / "main" / "resources"
    rendered = render_module_files(spec)
    issues: list[str] = []
    for name in generated_files_for_spec(spec):
        path = resources / name
        if not path.is_file():
            issues.append(f"{module_id}: missing {name}")
            continue
        on_disk = strip_generated_header(path.read_text(encoding="utf-8"))
        expected = strip_generated_header(rendered[name])
        if on_disk != expected:
            issues.append(f"{module_id}: drift in {name}")
    custom = resources / CUSTOM_FILE
    if not custom.is_file():
        issues.append(f"{module_id}: missing {CUSTOM_FILE} (hand-maintained)")
    return issues


def port_env_for_module(ctx: ProjectContext, module_id: str) -> str:
    mods = ctx.manifest.get("modules") or {}
    cfg = mods.get(module_id) if isinstance(mods, dict) else {}
    if not isinstance(cfg, dict):
        cfg = {}
    return _port_env_key(cfg, ctx.secrets_module_folder(module_id))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="stack-kit config-gen — Spring YAML from manifest")
    parser.add_argument("module", nargs="?", help="Module id (omit with --all)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="All modules whose driver declares config-gen support",
    )
    parser.add_argument("--port-env", metavar="MODULE", help="Print port env var name for module")
    parser.add_argument("--check", action="store_true", help="Report drift only; exit 1 if any")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    ctx = ProjectContext.discover()

    if args.port_env:
        print(port_env_for_module(ctx, args.port_env))
        return 0
    targets: list[str]
    if args.all:
        targets = java_boot_modules_with_datastores(ctx)
    elif args.module:
        targets = [args.module]
    else:
        parser.error("module id or --all required")

    if args.check:
        all_issues: list[str] = []
        for mid in targets:
            all_issues.extend(check_module_drift(ctx, mid))
        if all_issues:
            for msg in all_issues:
                print(f"  [config-gen] {msg}", file=sys.stderr)
            return 1
        print(f"[config-gen] OK ({len(targets)} module(s))")
        return 0

    for mid in targets:
        write_module_config(ctx, mid, dry_run=args.dry_run)
        if not args.dry_run:
            rel = ctx.module_path(mid).relative_to(ctx.root)
            print(f"[config-gen] wrote {rel}/src/main/resources/application*.yml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
