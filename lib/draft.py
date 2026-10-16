#!/usr/bin/env python3
"""Draft a host's manifest from its tree, by the evidence each driver DECLARES (ADR-001 amendment 10).

A driver says, in its registry entry `detect`, what makes a directory one of its modules (`all`:
conditions on the directory's own files -- `file` + `matches`, `any`, `none`) and what it reads from
that evidence (`reads`: `name` -- a matched file's name; `find` -- a repository file whose content
`matches` and `mentions` another read, as a path from the module). This module holds no ecosystem:
it evaluates declarations. A project's own drivers (K7b) declare their evidence the same way.

The draft PROPOSES. Merged over an existing manifest, every declared field wins and only what is
absent is added; a directory two drivers claim is refused, naming both, never guessed; the outermost
claim wins, so a multi-project build is one module.

    draft.py --plan                 the drafted manifest's additions, as a diff against the current one
    draft.py --approve <who>        write the merged manifest, recording who approved the draft
"""
from __future__ import annotations

import fnmatch
import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

if __name__ == "__main__":  # run as a file: the kit root, not lib/, is what `lib.` resolves from
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.stdout.reconfigure(encoding="utf-8")

from lib import identity  # noqa: E402

KIT = Path(__file__).resolve().parents[1]
PROFILES = KIT / "config" / "layout-profiles"
#: Directories that are never a module's own evidence: build output, dependencies, VCS.
def never() -> set[str]:
    """What is never drafted from: git's directory, and every output a driver declares its toolchain writes."""
    from lib.modules import driver_registry

    return {".git/", *(str(g) for d in driver_registry().values() for g in d.get("outputs") or [])}


class DraftRefused(ValueError):
    """The tree could not be drafted honestly: ambiguity, named."""


def repository_files(root: Path, package: str | None) -> list[str]:
    """The repository's files, posix and relative: what git tracks or would track; the vendored kit
    and any nested host (a directory with its own manifest) are not this host's evidence."""
    try:
        ran = subprocess.run(["git", "-C", str(root), "ls-files", "-co", "--exclude-standard"],
                             capture_output=True, text=True)
        files = ran.stdout.splitlines() if ran.returncode == 0 and ran.stdout.strip() else None
    except OSError:
        files = None
    if files is None:
        files = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
    from lib.delivery.sync import excluded

    skip = sorted(never())
    out = [f for f in files if not excluded(f, skip)]
    if package:
        out = [f for f in out if not (f + "/").startswith(package.rstrip("/") + "/")]
    nested = {posixpath.dirname(f) for f in out
              if posixpath.basename(f) in identity.manifest_filenames() and posixpath.dirname(f)}
    return sorted(f for f in out if not any(f.startswith(n + "/") for n in nested))


def _in_dir(files: list[str], directory: str, pattern: str) -> list[str]:
    """Files at `pattern` relative to `directory` (segments matched one by one; `*/x` is one level)."""
    prefix = directory + "/" if directory else ""
    parts = pattern.split("/")
    out = []
    for f in files:
        if not f.startswith(prefix):
            continue
        rel = f[len(prefix):].split("/")
        if len(rel) == len(parts) and all(fnmatch.fnmatch(r, p) for r, p in zip(rel, parts)):
            out.append(f)
    return sorted(out)


def _text(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _holds(root: Path, files: list[str], directory: str, cond: dict[str, Any]) -> bool:
    if "any" in cond:
        return any(_holds(root, files, directory, c) for c in cond["any"])
    if "none" in cond:
        return not _in_dir(files, directory, cond["none"])
    hits = _in_dir(files, directory, cond["file"])
    if "matches" in cond:
        hits = [h for h in hits if re.search(cond["matches"], _text(root, h))]
    return bool(hits)


def _reads(root: Path, files: list[str], directory: str, reads: dict[str, Any]) -> dict[str, str]:
    """What a driver reads from its evidence, field by field (in declaration order: a `find` may
    mention an earlier read)."""
    out: dict[str, str] = {}
    for field, how in reads.items():
        if "name" in how:
            hits = _in_dir(files, directory, how["name"])
            if "matches" in how:
                hits = [h for h in hits if re.search(how["matches"], _text(root, h))]
            if hits:
                out[field] = posixpath.basename(hits[0])
        elif "find" in how:
            mention = out.get(how.get("mentions", ""), "")
            hits = [f for f in files if fnmatch.fnmatch(f, how["find"]) or fnmatch.fnmatch("/" + f, "/" + how["find"])]
            hits = [h for h in hits if re.search(how.get("matches", ""), _text(root, h))
                    and (not mention or mention in _text(root, h)) and posixpath.dirname(h) != directory]
            if hits:
                out[field] = posixpath.relpath(sorted(hits)[0], directory or ".")
    return out


def _set(doc: dict[str, Any], dotted: str, value: Any) -> None:
    cur = doc
    *head, last = dotted.split(".")
    for part in head:
        cur = cur.setdefault(part, {})
    cur[last] = value


def detect(root: Path, registry: dict[str, Any], files: list[str]) -> list[dict[str, Any]]:
    """[{dir, type, reads}] for every directory a driver's evidence claims; the outermost claim wins,
    and a directory two drivers claim is refused."""
    dirs = sorted({posixpath.dirname(f) for f in files} | {""}, key=lambda d: (d.count("/") if d else -1, d))
    claimed: list[dict[str, Any]] = []
    for d in dirs:
        if any(d == c["dir"] or d.startswith(c["dir"] + "/") for c in claimed if c["dir"]):
            continue
        hits = [(typ, entry["detect"]) for typ, entry in sorted(registry.items())
                if isinstance(entry, dict) and isinstance(entry.get("detect"), dict)
                and all(_holds(root, files, d, c) for c in entry["detect"].get("all", []))]
        if len(hits) > 1:
            raise DraftRefused(f"{d or '.'}: claimed by {', '.join(t for t, _ in hits)} -- declare its module "
                               f"by hand (`modules.<id>.type`); the kit never guesses between drivers")
        if hits:
            typ, ev = hits[0]
            claimed.append({"dir": d, "type": typ, "reads": _reads(root, files, d, ev.get("reads") or {})})
    return claimed


def _profile_fits(root: Path, name: str) -> bool:
    path = PROFILES / f"{name}.json"
    if not path.is_file():
        return False
    entries = json.loads(path.read_text(encoding="utf-8")).get("entries") or []
    return all((root / e["path"]).exists() for e in entries)


def draft(root: Path, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """The manifest the tree declares, by the drivers' evidence -- before any merge."""
    from lib.modules import compose_registry

    existing = existing or {}
    package = existing.get("package") or Path(os.path.relpath(KIT, root)).as_posix()
    registry, _homes = compose_registry(root, existing)
    files = repository_files(root, package)
    modules: dict[str, Any] = {}
    for claim in detect(root, registry, files):
        name = posixpath.basename(claim["dir"]) or "app"
        mid = name if name not in modules else f"{posixpath.basename(posixpath.dirname(claim['dir']))}-{name}"
        roles = [r for r in (registry[claim["type"]].get("roles") or []) if r != "any"]
        module: dict[str, Any] = {"type": claim["type"], "role": roles[0] if roles else "other",
                                  "path": claim["dir"] or ".", "secretsModule": mid}
        for field, value in claim["reads"].items():
            _set(module, field, value)
        modules[mid] = module
    launcher = (existing.get("vscode") or {}).get("cliScript") or next(
        (p for p in ("ops/cli/stack-kit.ps1", "tools/stack-kit.ps1") if (root / p).is_file()), "ops/cli/stack-kit.ps1")
    out: dict[str, Any] = {
        "version": 2,
        "package": package,
        "secrets": existing.get("secrets") or "ops/config",
        "modules": modules,
        "cli": {"aliases": {mid: mid for mid in modules}},
        "commands": {step: f"pwsh {launcher} {step}" for step in ("build", "test", "lint")},
    }
    if _profile_fits(root, "monorepo"):
        out["layout"] = {"profile": "monorepo"}
    return out


def merge(existing: dict[str, Any], drafted: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The existing manifest with the draft's ABSENT fields added; every declared field wins. A drafted
    module is the existing module at the same path, whatever its id."""
    import copy

    merged = copy.deepcopy(existing)
    added: list[str] = []

    def fill(into: dict[str, Any], src: dict[str, Any], at: str) -> None:
        for k, v in src.items():
            here = f"{at}.{k}" if at else k
            if k not in into:
                into[k] = copy.deepcopy(v)
                added.append(f"+ {here}: {json.dumps(v, ensure_ascii=False)}")
            elif isinstance(into[k], dict) and isinstance(v, dict):
                fill(into[k], v, here)

    by_path = {str(c.get("path")): mid for mid, c in (merged.get("modules") or {}).items() if isinstance(c, dict)}
    modules = merged.setdefault("modules", {})
    renamed: dict[str, str] = {}
    for mid, mod in (drafted.get("modules") or {}).items():
        if mod["path"] in by_path:
            renamed[mid] = by_path[mod["path"]]
            fill(modules[by_path[mod["path"]]], mod, f"modules.{by_path[mod['path']]}")
        else:
            new_id = mid if mid not in modules else f"{mid}-{len(modules)}"
            renamed[mid] = new_id
            modules[new_id] = {**mod, "secretsModule": mod["secretsModule"] if mid == new_id else new_id}
            added.append(f"+ modules.{new_id}: {json.dumps(modules[new_id], ensure_ascii=False)}")
    rest = {k: v for k, v in drafted.items() if k != "modules"}
    taken_targets = set(((merged.get("cli") or {}).get("aliases") or {}).values())
    rest["cli"] = {"aliases": {renamed.get(a, a): renamed.get(t, t) for a, t in ((rest.get("cli") or {}).get("aliases") or {}).items()
                               if renamed.get(t, t) not in taken_targets}}
    fill(merged, rest, "")
    return merged, added


def main(argv: list[str]) -> int:
    root = Path(os.environ.get(identity.env_name("PROJECT_ROOT")) or Path.cwd()).resolve()
    found = identity.find_manifest(root)
    existing = json.loads(found.read_text(encoding="utf-8")) if found else {}
    try:
        drafted = draft(root, existing)
    except DraftRefused as e:
        print(f"[draft] REFUSED: {e}", file=sys.stderr)
        return 1
    merged, added = merge(existing, drafted)
    target = found or root / identity.MANIFEST_FILENAME
    rel = target.relative_to(root).as_posix()
    print(f"[draft] {rel}: {len(added)} addition(s) from the tree's evidence; every declared field kept")
    for line in added:
        print(f"  {line}")
    if "--approve" in argv:
        i = argv.index("--approve")
        who = argv[i + 1] if i + 1 < len(argv) else ""
        if not who:
            print("[draft] --approve needs who approves (a name)", file=sys.stderr)
            return 2
        if not added:
            print("[draft] nothing to write")
            return 0
        from datetime import datetime, timezone

        merged["draft"] = {"approvedBy": who, "approvedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        target.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"[draft] wrote {rel} (approved by {who})")
        return 0
    if added:
        print(f"[draft] plan only -- write it with: {identity.KIT_NAME} init --approve <who>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
