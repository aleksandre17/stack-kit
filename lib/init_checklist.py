"""What init leaves the host to fill in, named by the host's OWN modules -- never by the scaffold's
(found adopting a foreign project: the checklist named the scaffold's ui folder for a ui module called
`web`) -- and the CI the repository already had, named beside the one `ci-gen` wrote (a second
pipeline nobody mentioned).

    python lib/init_checklist.py        (from the host root; init prints it last)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

HINTS = {"ui": ["VITE_API_URL"], "api": ["API_KEY"], "worker": ["API_INTERNAL_URL"]}
TODO = re.compile(r"YOUR_|example\.com|CHANGEME|user@YOUR")


def items(root: Path, manifest: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """(host-relative file, hints): each module's env files, and the ui module's nginx env."""
    secrets = str(manifest.get("secrets") or "ops/config").strip("/")
    out = []
    ui = None
    for mid, cfg in (manifest.get("modules") or {}).items():
        if not isinstance(cfg, dict):
            continue
        folder = str(cfg.get("secretsModule") or mid)
        role = str(cfg.get("role") or "")
        ui = ui or (folder if role == "ui" else None)
        for env in ("dev", "prod"):
            out.append((f"{secrets}/{folder}/.env.{env}", HINTS.get(role, [])))
    if ui:
        declared = ((manifest.get("adapters") or {}).get("nginx") or {}).get("env")
        out.append((str(declared or f"{secrets}/{ui}/nginx.env"), ["NGINX_FRAME_ANCESTORS"]))
    return out


def existing_ci(root: Path, manifest: dict[str, Any]) -> list[str]:
    """Workflows the repository carries beside the one `ci-gen` writes."""
    from lib.ci_gen import DEFAULT_WORKFLOW

    ours = str((manifest.get("ci") or {}).get("workflow") or DEFAULT_WORKFLOW)
    folder = root / ".github" / "workflows"
    return sorted(p.relative_to(root).as_posix() for p in folder.glob("*.y*ml")
                  if p.is_file() and p.relative_to(root).as_posix() != ours) if folder.is_dir() else []


def lines(root: Path, manifest: dict[str, Any]) -> list[str]:
    out = []
    for rel, _hints in items(root, manifest):
        path = root / rel
        if not path.is_file():
            out.append(f"  [ ] {rel} -- create / seed")
        else:
            out.append(f"  {'[ ]' if TODO.search(path.read_text(encoding='utf-8', errors='replace')) else '[x]'} {rel}")
    from lib.ci_gen import DEFAULT_WORKFLOW

    ours = str((manifest.get("ci") or {}).get("workflow") or DEFAULT_WORKFLOW)
    for other in existing_ci(root, manifest):
        out.append(f"  [!] {other} -- this repository's own CI, kept beside {ours}: two pipelines now run on "
                   f"every push; retire one, or keep both on purpose")
    return out


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib.project_context import ProjectContext

    ctx = ProjectContext.discover()
    print("\n".join(lines(ctx.root, ctx.manifest)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
