#!/usr/bin/env python3
"""Render nginx.conf from stack-kit.json adapters.nginx + ops/config (manifest-driven)."""
from __future__ import annotations

import sys
from pathlib import Path

# Package lib on PYTHONPATH or kit root
_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from lib.manifest_defaults import load_scaffold_manifest
from lib.modules import module_by_role, module_by_type
from lib.project_context import ProjectContext  # noqa: E402

PLACEHOLDER = "__NGINX_FRAME_ANCESTORS__"
DEFAULT_ANCESTORS = "'self' http://localhost:5173 http://localhost:5174 http://localhost:5177 http://127.0.0.1:5177"


def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key.strip():
            out[key.strip()] = val
    return out


def main() -> int:
    try:
        ctx = ProjectContext.discover()
    except FileNotFoundError:
        from lib.identity import MANIFEST_FILENAME

        print(f"ERROR: project root not found ({MANIFEST_FILENAME})", file=sys.stderr)
        return 1

    root = ctx.root
    nginx = (ctx.manifest.get("adapters") or {}).get("nginx") or {}
    if not isinstance(nginx, dict):
        nginx = {}
    if not nginx:
        sc_nginx = (load_scaffold_manifest().get("adapters") or {}).get("nginx") or {}
        if isinstance(sc_nginx, dict):
            nginx = sc_nginx

    def _nginx_field(key: str) -> str:
        if nginx.get(key):
            return str(nginx[key])
        # The UI module, else the first whose driver declares it serves through nginx (`nginx.serves`).
        from lib.modules import driver_capability

        ui_id = ctx.module_id_for_role("ui") or next(
            (m for m in ctx.list_module_ids()
             if (driver_capability(str(((ctx.manifest.get("modules") or {}).get(m) or {}).get("type") or ""), "nginx", {})
                 or {}).get("serves")), None)
        if not ui_id:
            return ""
        rel = ctx.module_path(ui_id).relative_to(root).as_posix()
        sec = ctx.secrets_module_folder(ui_id)
        if key == "template":
            return f"{rel}/nginx.conf.template"
        if key == "output":
            return f"{rel}/nginx.conf"
        if key == "envExample":
            return f"{ctx.field('secrets')}/{sec}/nginx.env.example"
        if key == "env":
            return f"{ctx.field('secrets')}/{sec}/nginx.env"
        return ""

    template_rel = _nginx_field("template")
    output_rel = _nginx_field("output")
    env_example_rel = _nginx_field("envExample")
    env_file_rel = _nginx_field("env")
    if not template_rel:
        print("ERROR: adapters.nginx.template or ui module required in stack-kit.json", file=sys.stderr)
        return 1

    template = root / template_rel
    output = root / output_rel
    env_example = root / env_example_rel
    env_file = root / env_file_rel

    if not template.is_file():
        print(f"ERROR: missing {template}", file=sys.stderr)
        return 1

    env: dict[str, str] = {}
    for path in (env_example, env_file):
        env.update(parse_env(path))

    ancestors = env.get("NGINX_FRAME_ANCESTORS", DEFAULT_ANCESTORS).strip() or DEFAULT_ANCESTORS
    text = template.read_text(encoding="utf-8")
    if PLACEHOLDER not in text:
        print(f"ERROR: template missing {PLACEHOLDER}", file=sys.stderr)
        return 1

    output.write_text(text.replace(PLACEHOLDER, ancestors), encoding="utf-8", newline="\n")
    print(f"  wrote {output.relative_to(root)}")
    print(f"  frame-ancestors: {ancestors[:80]}{'...' if len(ancestors) > 80 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
