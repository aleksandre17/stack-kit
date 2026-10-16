#!/usr/bin/env python3
"""Build once, promote the same bytes (ADR-001 amendment 11).

A driver declares how its module is packaged (registry `package`: a driver `command` with `args`,
`{out}` the module's staging directory, and the `artifacts` it leaves -- globs from the module
directory, or `{out}` itself). `pack` gathers them into ONE archive named by the commit,
`.stack-kit/artifacts/<module>-<sha>.tgz`, with its sha256 beside it; `unpack` puts the same bytes
back where the driver's release reads them, so a deploy that `promotes` (registry rung field) runs
without building. A developer runs exactly what CI runs: `stack-kit package <module>` /
`stack-kit unpack <module> <archive>`.

    package.py plan <module>             the declared package command (JSON) and its staging dir
    package.py pack <module>             archive what the package step left; prints the archive
    package.py unpack <module> <archive> restore it into the module, verifying its sha256
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

if __name__ == "__main__":  # run as a file: the kit root, not lib/, is what `lib.` resolves from
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.stdout.reconfigure(encoding="utf-8")

from lib import identity  # noqa: E402


class PackageError(ValueError):
    """A module that cannot be packaged as declared, or an archive that is not what it claims."""


def artifacts_dir(root: Path) -> Path:
    """`.stack-kit/artifacts/`, beside the run records (the `.stack-kit/` tree ignores itself)."""
    return root / identity.RUNS_DIR.split("/")[0] / "artifacts"


def declared(manifest: dict, module_id: str) -> dict:
    from lib.modules import driver_capability

    cfg = (manifest.get("modules") or {}).get(module_id)
    if not isinstance(cfg, dict):
        raise PackageError(f"no module '{module_id}'")
    spec = driver_capability(str(cfg.get("type") or ""), "package", None)
    if isinstance(spec, dict) and spec.get("pending"):
        raise PackageError(f"driver '{cfg.get('type')}' packages nothing yet: {spec['pending']}")
    if not isinstance(spec, dict) or not spec.get("command"):
        raise PackageError(f"driver '{cfg.get('type')}' declares no package step")
    return spec


def staging(root: Path, module_id: str) -> Path:
    return artifacts_dir(root) / module_id


def plan(root: Path, manifest: dict, module_id: str) -> dict:
    spec = declared(manifest, module_id)
    out = staging(root, module_id).as_posix()
    return {"command": spec["command"], "args": [str(a).replace("{out}", out) for a in spec.get("args") or []],
            "out": out}


def revision(root: Path) -> str:
    ran = subprocess.run(["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True)
    sha = ran.stdout.strip() if ran.returncode == 0 else ""
    if not sha:
        raise PackageError("no commit to name the artifact by: a package is always of a commit")
    return sha


def _files(module_dir: Path, out: Path, globs: list[str]) -> list[tuple[Path, str]]:
    """(file, its name inside the archive) for every declared artifact."""
    found: list[tuple[Path, str]] = []
    for g in globs:
        if g == "{out}":
            found += [(p, "{out}/" + p.relative_to(out).as_posix()) for p in sorted(out.rglob("*")) if p.is_file()]
            continue
        for p in sorted(module_dir.rglob("*")):
            rel = p.relative_to(module_dir).as_posix()
            if p.is_file() and (fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g.replace("**/", ""))):
                found.append((p, rel))
    return found


def pack(root: Path, manifest: dict, module_id: str) -> Path:
    spec = declared(manifest, module_id)
    module_dir = root / manifest["modules"][module_id]["path"]
    out = staging(root, module_id)
    files = _files(module_dir, out, list(spec.get("artifacts") or []))
    if not files:
        raise PackageError(f"{module_id}: the package step left none of {spec.get('artifacts')} -- run it first "
                           f"(`{identity.KIT_NAME} package {module_id}`)")
    archive = artifacts_dir(root) / f"{module_id}-{revision(root)}.tgz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tar:
        for path, name in files:
            tar.add(path, arcname=name, recursive=False)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".tgz.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    return archive


def unpack(root: Path, manifest: dict, module_id: str, archive: Path) -> list[str]:
    """The archive's files back where the release reads them; refused if its sha256 disagrees or a
    member would land outside the module (or its staging directory)."""
    side = archive.with_suffix(".tgz.sha256")
    if side.is_file():
        want = side.read_text(encoding="utf-8").split()[0]
        if hashlib.sha256(archive.read_bytes()).hexdigest() != want:
            raise PackageError(f"{archive.name}: sha256 differs from {side.name} -- not the bytes that were packaged")
    module_dir = (root / manifest["modules"][module_id]["path"]).resolve()
    out = staging(root, module_id).resolve()
    placed = []
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar.getmembers():
            base, name = (out, m.name[len("{out}/"):]) if m.name.startswith("{out}/") else (module_dir, m.name)
            dest = (base / name).resolve()
            if not dest.is_relative_to(base) or not m.isfile():
                raise PackageError(f"{archive.name}: member {m.name} escapes its place -- refused")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(tar.extractfile(m).read())
            placed.append(dest.relative_to(root.resolve()).as_posix())
    return placed


def main(argv: list[str]) -> int:
    from lib.project_context import ProjectContext

    ctx = ProjectContext.discover()
    try:
        if argv[:1] == ["plan"] and len(argv) == 2:
            print(json.dumps(plan(ctx.root, ctx.manifest, argv[1])))
        elif argv[:1] == ["pack"] and len(argv) == 2:
            print(pack(ctx.root, ctx.manifest, argv[1]).relative_to(ctx.root).as_posix())
        elif argv[:1] == ["unpack"] and len(argv) == 3:
            for rel in unpack(ctx.root, ctx.manifest, argv[1], Path(argv[2]).resolve()):
                print(f"  unpacked {rel}")
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except PackageError as e:
        print(f"[package] ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
