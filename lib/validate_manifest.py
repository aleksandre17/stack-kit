#!/usr/bin/env python3
"""Validate the project manifest — schema + package boundary checks."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from lib.compose_identity import primary_api_module_id, primary_worker_module_id
from lib.identity import MANIFEST_FILENAME, with_current_fields
from lib.credentials import all_module_credential_files, module_credentials
from lib.manifest_defaults import declared_ci_scripts
from lib.project_context import ProjectContext, load_manifest


def _load_schema(pkg_root: Path) -> dict[str, Any]:
    path = pkg_root / "manifest.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_jsonschema(instance: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    # The kit's own interpreter, on every machine -- never "when a library happens to be installed".
    from lib.schema_check import validate

    return validate(instance, schema)


def _validate_required(instance: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if instance.get("version", 0) < 2:
        errs.append("version: must be >= 2 (run: stack-kit migrate)")
    # compose is optional: a project whose drivers deploy no containers declares none.
    for key in ("package", "secrets", "modules"):
        if key not in instance:
            errs.append(f"(root): missing required field '{key}'")
    compose = instance.get("compose")
    if isinstance(compose, dict) and "catalog" not in compose:
        errs.append("compose: missing catalog")
    mods = instance.get("modules")
    if not isinstance(mods, dict) or not mods:
        errs.append("modules: at least one module required")
        return errs
    for mid, cfg in mods.items():
        if not isinstance(cfg, dict):
            errs.append(f"modules.{mid}: must be object")
            continue
        for req in ("type", "path", "secretsModule", "role"):
            if req not in cfg:
                errs.append(f"modules.{mid}: missing '{req}'")
        creds = cfg.get("credentials")
        if creds is not None:
            if not isinstance(creds, list):
                errs.append(f"modules.{mid}.credentials: must be array")
            else:
                for i, item in enumerate(creds):
                    if not isinstance(item, dict) or not item.get("file"):
                        errs.append(f"modules.{mid}.credentials[{i}]: requires 'file'")
    adapters = instance.get("adapters")
    if isinstance(adapters, dict):
        gcp = adapters.get("gcp")
        if gcp is not None and not isinstance(gcp, dict):
            errs.append("adapters.gcp: must be object")
        elif isinstance(gcp, dict) and gcp.get("enabled") is not False:
            if gcp.get("credentialsFile") and not isinstance(gcp["credentialsFile"], str):
                errs.append("adapters.gcp.credentialsFile: must be string")
        nginx = adapters.get("nginx")
        if nginx is not None and not isinstance(nginx, dict):
            errs.append("adapters.nginx: must be object")
    return errs


#: A token of a command line that names a script of the host: it has to be there.
_SCRIPT_TOKEN = (".ps1", ".sh", ".py", ".cmd")


def command_line_problems(root: Path, manifest: dict[str, Any]) -> list[str]:
    """`commands.*` are literal lines other tools run; a line naming a host script that is not there
    is broken for every one of them. The shape is the schema's; this is what a schema cannot see."""
    out = []
    for name, line in ((manifest.get("commands") or {}).items() if isinstance(manifest.get("commands"), dict) else []):
        for token in str(line).split():
            token = token.strip("'\"")
            if token.endswith(_SCRIPT_TOKEN) and not Path(token).is_absolute() and not (root / token).is_file():
                out.append(f"commands.{name}: names {token}, which is not there")
    return out


def registry_problems(registry: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    """The composed registry (the kit's and the project's drivers) against drivers/registry.schema.json,
    its roles against catalogs.roles, its command runtimes against the declared runtimes."""
    from lib import catalogs
    from lib.modules import script_runtimes
    from lib.schema_check import validate as schema_validate

    schema = json.loads((Path(__file__).resolve().parents[1] / "drivers" / "registry.schema.json").read_text(encoding="utf-8"))
    out = [f"drivers: {e}" for e in schema_validate(registry, schema)]
    roles = set(catalogs.ids("roles", manifest)) | {"any"}
    runtimes = set(script_runtimes(manifest))
    for typ, entry in registry.items():
        for role in entry.get("roles") or []:
            if role not in roles:
                out.append(f"drivers: {typ}.roles: '{role}' is not a declared role ({', '.join(sorted(roles))})")
        for name, cmd in (entry.get("commands") or {}).items():
            if isinstance(cmd, dict) and cmd.get("runtime") and cmd["runtime"] not in runtimes:
                out.append(f"drivers: {typ}.commands.{name}.runtime: '{cmd['runtime']}' is not a declared runtime "
                           f"({', '.join(sorted(runtimes))}; a host adds one in `runtimes`)")
    return out


def _validate_project(ctx: ProjectContext, registry: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    warnings: list[str] = []
    root = ctx.root
    pkg = ctx.package_root
    if not pkg.is_dir():
        errs.append(f"package: path not found: {pkg.relative_to(root)}")

    for mid, cfg in (ctx.manifest.get("modules") or {}).items():
        if not isinstance(cfg, dict):
            continue
        typ = cfg.get("type")
        if typ and typ not in registry:
            errs.append(f"modules.{mid}.type: unknown driver '{typ}'")
        rel = cfg.get("path")
        if rel and not (root / str(rel)).is_dir():
            warnings.append(f"modules.{mid}.path: directory missing ({rel})")
        for cred in module_credentials(ctx.manifest, str(mid)):
            fn = cred["file"]
            if ".." in fn or fn.startswith("/"):
                errs.append(f"modules.{mid}.credentials: invalid file '{fn}'")

    # A project that declares no compose section has no catalog to miss (compose is optional).
    cat = ctx.catalog_path if "compose" in ctx.manifest else None
    if cat is not None and not cat.is_file():
        warnings.append(f"compose.catalog: missing ({cat.relative_to(root)})")
    elif cat is not None and cat.is_file():
        catalog = json.loads(cat.read_text(encoding="utf-8"))
        cat_worker = bool((catalog.get("features") or {}).get("worker", False))
        primary = primary_api_module_id(ctx.manifest)
        if primary:
            pcfg = (ctx.manifest.get("modules") or {}).get(primary) or {}
            compose = pcfg.get("compose") if isinstance(pcfg, dict) else None
            has_manifest_flag = isinstance(compose, dict) and "embeddedWorker" in compose
            if cat_worker and not has_manifest_flag:
                warnings.append(
                    "compose.catalog features.worker=true is deprecated — set "
                    f"modules.{primary}.compose.embeddedWorker in {MANIFEST_FILENAME} (P0-kit-13)"
                )
            if cat_worker and primary_worker_module_id(ctx.manifest):
                warnings.append(
                    "features.worker + manifest role=worker module — pick one worker model (Architecture B)"
                )

    for dotted, rel in declared_ci_scripts(ctx.manifest):
        if not (root / rel).is_file():
            warnings.append(f"{dotted}: file missing ({rel})")

    for mid, cfg in (ctx.manifest.get("modules") or {}).items():
        if not isinstance(cfg, dict):
            continue
        sm = str(cfg.get("secretsModule", mid))
        sdir = ctx.secrets_folder_path(sm)
        ex = sdir / ".env.example"
        if sdir.is_dir() and not ex.is_file():
            warnings.append(f"modules.{mid}: missing secrets example ({ex.relative_to(root)})")
        elif not sdir.is_dir() and not ex.is_file():
            warnings.append(f"modules.{mid}: secrets dir missing ({sdir.relative_to(root)})")

    api_ids = ctx.module_ids_for_role("api")
    if len(api_ids) > 1:
        warnings.append(
            f"modules: multiple role=api ({', '.join(api_ids)}); set ci.healthModules explicitly"
        )

    seen_sm: dict[str, str] = {}
    for mid, cfg in (ctx.manifest.get("modules") or {}).items():
        if not isinstance(cfg, dict):
            continue
        sm = str(cfg.get("secretsModule", mid))
        if sm in seen_sm and seen_sm[sm] != mid:
            warnings.append(f"modules: duplicate secretsModule '{sm}' ({seen_sm[sm]}, {mid})")
        seen_sm[sm] = str(mid)

    all_creds = all_module_credential_files(ctx.manifest)
    for mid, items in all_creds.items():
        files = [c["file"] for c in items]
        if len(files) != len(set(files)):
            errs.append(f"modules.{mid}.credentials: duplicate file names")

    # Every deployed service assembles from its declarations (driver container/dev, module, stack).
    from lib.delivery.model import ModelError, all_services

    try:
        all_services(ctx.manifest)
    except (ModelError, ValueError) as e:
        errs.append(f"delivery: {e}")

    try:
        from lib.config_gen import check_module_drift, config_gen_modules_with_datastores

        for mid in config_gen_modules_with_datastores(ctx):
            for issue in check_module_drift(ctx, mid):
                errs.append(f"config-gen: {issue}")
    except ImportError:
        pass

    return errs, warnings


def validate_manifest(
    root: Path | None = None, *, pkg_root: Path | None = None
) -> tuple[list[str], list[str]]:
    ctx = ProjectContext.discover(root)
    pkg = pkg_root or ctx.package_root
    schema = _load_schema(pkg)
    from lib.modules import DriverCollision, compose_registry

    try:
        registry, _ = compose_registry(ctx.root, ctx.manifest)
    except DriverCollision as e:
        return [f"drivers: {e}"], []

    errs = _validate_required(ctx.manifest)
    errs.extend(registry_problems(registry, ctx.manifest))
    errs.extend(_validate_jsonschema(with_current_fields(ctx.manifest), schema))
    # A host on a shape the kit no longer spells is told the door that carries it (amendment 7).
    from lib.migrate_manifest import carry_host_shapes

    errs.extend(f"{c} -- run `migrate --apply`" for c in carry_host_shapes(ctx.manifest))
    proj_errs, warnings = _validate_project(ctx, registry)
    errs.extend(proj_errs)
    warnings.extend(f"drivers: {typ}.runtime is removed and ignored -- a command runs by its script's runtime "
                    f"(config/runtimes.json, manifest `runtimes`) or its own {{script, runtime}}"
                    for typ, entry in registry.items() if "runtime" in entry)
    errs.extend(command_line_problems(ctx.root, ctx.manifest))
    # The declared tree, held as a floor (ADR-001 decision 3).
    from lib.layout_floor import evaluate

    floor = evaluate(ctx.root, ctx.manifest)
    errs.extend(f"layout: {f}" for f in floor.failures)
    warnings.extend(f"layout: {p}" for p in floor.pending)
    # Migrations shape the store; data has one way in, the ingest stage (ADR-001 decision 4).
    from lib.migrations_gate import check as migrations_carry_data

    errs.extend(f"migrations: {f}" for f in migrations_carry_data(ctx.root, ctx.manifest))
    from lib.migrations_gate import ledger_problems

    errs.extend(f"migrations: {f}" for f in ledger_problems(ctx.root, ctx.manifest))
    # Configuration carries its sensitivity; a committed secret is refused (ADR-001 decision 5).
    from lib.config_keys import check as config_keys

    keys = config_keys(ctx.root, ctx.manifest)
    errs.extend(f"config: {f}" for f in keys.failures)
    from lib.config_keys import runtime_config_problems

    errs.extend(f"config: {f}" for f in runtime_config_problems(ctx.root, ctx.manifest))
    warnings.extend(f"config: {k}" for k in keys.known)
    # Deploy targets are declared configuration (amendment 9): refused shapes and secrets; notices.
    from lib import targets as deploy_targets

    errs.extend(f"deploy: {p}" for p in deploy_targets.problems(ctx.root, ctx.manifest))
    warnings.extend(f"deploy: {n}" for n in deploy_targets.notices(ctx.root, ctx.manifest))
    # Every host extension through a declared point (amendment 15): pending answers and undeclared files.
    from lib import extend

    ext_errors, ext_notices = extend.problems(ctx.root, ctx.manifest)
    errs.extend(ext_errors)
    warnings.extend(ext_notices)
    # A value has one home (amendment 13): a former one present is refused, naming `migrate`.
    from lib import legacy

    errs.extend(f"legacy: {p}" for p in legacy.problems(ctx.root, ctx.secrets_root, ctx.manifest))
    # A development run reads development configuration only (amendment 8): what it lost is named.
    from lib.migrate_manifest import run_env_notices

    warnings.extend(f"env: {n}" for n in run_env_notices(ctx.secrets_root, ctx.manifest))
    # A declared pipeline must be a proof before it is ever run (ADR-001 decision 4).
    stages = (ctx.manifest.get("validate") or {}).get("stages")
    if stages is not None:
        from lib.pipeline import problems

        errs.extend(problems(stages))
    return errs, warnings


def main() -> int:
    try:
        errs, warnings = validate_manifest()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    for w in warnings:
        print(f"WARN: {w}")
    if errs:
        for e in errs:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"[validate] {MANIFEST_FILENAME} OK")
    if "--stages" in sys.argv[1:]:
        from lib.pipeline import run

        ctx = ProjectContext.discover()
        stages = (ctx.manifest.get("validate") or {}).get("stages")
        if stages is None:
            print(f"ERROR: --stages: {MANIFEST_FILENAME} declares no validate.stages", file=sys.stderr)
            return 1
        return run(ctx.root, stages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
