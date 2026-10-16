#!/usr/bin/env python3
"""Compose generator engine — reads project manifest + catalog (no app logic)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
HEADER = "# GENERATED — do not edit. Run: stack-kit compose-gen\n\n"

def find_project_root() -> Path:
    # One discovery, owned by the project context -- never a second copy here.
    from lib.project_context import find_project_root as discover

    try:
        return discover()
    except FileNotFoundError as e:
        raise SystemExit(f"ERROR: {e}") from None


def load_manifest(root: Path) -> dict:
    from lib.project_context import load_manifest as load

    return load(root)


def catalog_path(root: Path, manifest: dict) -> Path:
    rel = manifest.get("compose", {}).get("catalog", "ops/compose/catalog.json")
    return root / rel


def global_fmt(root: Path) -> dict[str, str]:
    from lib.compose_identity import build_global_fmt

    return build_global_fmt(manifest=load_manifest(root), root=root)


def load_catalog(root: Path) -> tuple[dict, dict, dict]:
    path = catalog_path(root, load_manifest(root))
    if not path.is_file():
        print(f"ERROR: missing {path}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    templates = data["templates"]
    features = data.get("features", {})
    targets = {root / rel: spec for rel, spec in data["targets"].items()}
    return templates, targets, features


def resolve_services(spec: dict, features: dict) -> list[str]:
    services = list(spec.get("services", []))
    services_if: dict = spec.get("services_if") or {}
    out: list[str] = []
    for key in services:
        flag = services_if.get(key)
        if flag and not features.get(flag, False):
            continue
        out.append(key)
    return out


def render(templates: dict, services: list[str], fmt: dict) -> str:
    return "services:\n" + "".join(templates[key].format(**fmt) for key in services)


def build_target(
    templates: dict,
    spec: dict,
    fmt_global: dict,
    features: dict,
    *,
    root: Path,
    target_path: Path,
) -> str:
    fmt = {**fmt_global, **spec.get("fmt", {})}
    if spec.get("manifestStack"):
        from manifest_compose import build_manifest_stack_services
        from lib.project_context import ProjectContext

        profile = str(spec["manifestStack"])
        ctx = ProjectContext(root=root, manifest=load_manifest(root))
        body = "services:\n" + build_manifest_stack_services(
            ctx=ctx,
            profile=profile,
            compose_dir=target_path.parent,
            fmt_global=fmt_global,
            fmt_extra=spec.get("fmt", {}),
            features=features,
            module_fmt=spec.get("moduleFmt", {}),
        )
    elif spec.get("manifestModule"):
        from manifest_compose import build_single_module_compose
        from lib.project_context import ProjectContext

        profile = str(spec.get("manifestProfile") or "dev")
        ctx = ProjectContext(root=root, manifest=load_manifest(root))
        body = "services:\n" + build_single_module_compose(
            ctx=ctx,
            module_id=str(spec["manifestModule"]),
            profile=profile,
            compose_dir=target_path.parent,
            fmt_global=fmt_global,
            fmt_extra=spec.get("fmt", {}),
        )
    else:
        services = resolve_services(spec, features)
        body = render(templates, services, fmt)
    comment = spec.get("comment", "")
    if comment:
        comment = comment.format(**fmt)
    out = HEADER + comment + body
    if spec.get("extraServices"):
        # Companion service(s) appended inside the `services:` block (e.g. a
        # sidecar a module needs). The template is project-supplied; the engine
        # stays brand-agnostic — it only knows the spec key.
        out += templates[spec["extraServices"]].format(**fmt)
    if spec.get("networks"):
        out += "\n" + templates[spec["networks"]].format(**fmt)
    if spec.get("volumes"):
        out += "\n" + templates[spec["volumes"]].format(**fmt)
    return out + "\n"


def main() -> int:
    root = find_project_root()
    from lib.identity import env_name

    os.environ.setdefault(env_name("PROJECT_ROOT"), str(root))
    fmt_global = global_fmt(root)
    manifest = load_manifest(root)
    templates, targets, catalog_features = load_catalog(root)
    from lib.compose_identity import effective_compose_features

    features = effective_compose_features(manifest, catalog_features)
    for path, spec in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            build_target(
                templates, spec, fmt_global, features, root=root, target_path=path
            ),
            encoding="utf-8",
            newline="\n",
        )
        print(f"  wrote {path.relative_to(root)}")
    sync = PACKAGE_ROOT / "compose/sync_ops_modules.py"
    if sync.is_file():
        r = subprocess.run([sys.executable, str(sync)], cwd=root, check=False, env=os.environ.copy())
        if r.returncode != 0:
            return r.returncode
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
