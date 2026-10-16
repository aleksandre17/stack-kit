#!/usr/bin/env python3
"""Build once, promote the same bytes (ADR-001 amendments 11, 13).

A driver declares how its module is packaged (registry `package`: a driver `command` with `args`,
`{out}` the module's staging directory, and the `artifacts` it leaves -- globs from the module
directory, or `{out}` itself) and how a release of it runs (`container`: a recipe template, or a
static image serving it). `pack` turns what the package step left into ONE archive per commit,
`.stack-kit/artifacts/<module>-<release>.tgz`, sha256 beside it:

    release.json          the provenance: module, release id, commit, `git describe`, dirty, services,
                          and what the module's `package.exclude` kept out (`excluded`)
    <service>/...         each service's tree: its artifacts (under its `context`) and its recipe --
                          the module's own Dockerfile, or the driver's template rendered for it

The release id is the commit (`-dirty` when the checkout was): a deploy of it ships exactly these
bytes, and a release to an environment that requires a clean checkout refuses a dirty one.

    package.py plan <module>      the declared package command (JSON) and its staging dir
    package.py pack <module>      archive what the package step left; prints the archive
"""
from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Any

if __name__ == "__main__":  # run as a file: the kit root, not lib/, is what `lib.` resolves from
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.stdout.reconfigure(encoding="utf-8")

from lib import identity  # noqa: E402

OUT = "{out}"
RELEASE_JSON = "release.json"


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


def exclusions(manifest: dict, module_id: str) -> list[str]:
    """The module's `package.exclude`: files kept out of every archive -- and so every image -- of it,
    whatever its driver (gitignore-style patterns, from the artifact's root: the module, or `{out}`)."""
    cfg = (manifest.get("modules") or {}).get(module_id) or {}
    return [str(g) for g in ((cfg.get("package") or {}).get("exclude") or []) if str(g).strip()]


def _kept(files: list[tuple[Path, str]], patterns: list[str]) -> tuple[list[tuple[Path, str]], list[str]]:
    """(the files a package keeps, the ones its exclusions keep out -- named as the archive would)."""
    from lib.delivery.sync import excluded

    if not patterns:
        return files, []
    kept: list[tuple[Path, str]] = []
    out: list[str] = []
    for path, rel in files:
        inner = rel[len(OUT) + 1:] if rel.startswith(OUT + "/") else rel
        if excluded(inner, patterns):
            out.append(inner)
        else:
            kept.append((path, rel))
    return kept, sorted(out)


def staging(root: Path, module_id: str) -> Path:
    return artifacts_dir(root) / module_id


def plan(root: Path, manifest: dict, module_id: str) -> dict:
    spec = declared(manifest, module_id)
    out = staging(root, module_id).as_posix()
    return {"command": spec["command"], "args": [str(a).replace(OUT, out) for a in spec.get("args") or []],
            "out": out}


def _git(root: Path, *args: str) -> str:
    ran = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return ran.stdout.strip() if ran.returncode == 0 else ""


def provenance(root: Path) -> dict[str, Any]:
    """The commit a package is of: its sha, `git describe --tags --always --dirty`, and whether the
    checkout was dirty (tracked changes). No commit, no package."""
    sha = _git(root, "rev-parse", "--short=12", "HEAD")
    if not sha:
        raise PackageError("no commit to name the artifact by: a package is always of a commit")
    dirty = bool(_git(root, "status", "--porcelain", "--untracked-files=no"))
    return {"sha": sha, "commit": _git(root, "rev-parse", "HEAD"), "dirty": dirty,
            "revision": _git(root, "describe", "--tags", "--always", "--dirty") or sha,
            "id": sha + ("-dirty" if dirty else "")}


def revision(root: Path) -> str:
    return provenance(root)["id"]


def _files(module_dir: Path, out: Path, globs: list[str]) -> list[tuple[Path, str]]:
    """(file, its module-relative name; `{out}/...` for the staging directory's) per declared artifact."""
    found: dict[str, Path] = {}
    for g in globs:
        if g == OUT:
            for p in sorted(out.rglob("*")) if out.is_dir() else []:
                if p.is_file():
                    found[f"{OUT}/" + p.relative_to(out).as_posix()] = p
            continue
        for p in sorted(module_dir.rglob("*")) if module_dir.is_dir() else []:
            rel = p.relative_to(module_dir).as_posix()
            if p.is_file() and (fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g.replace("**/", ""))):
                found[rel] = p
    return sorted(((p, rel) for rel, p in found.items()), key=lambda x: x[1])


def _tree(files: list[tuple[Path, str]], context: str) -> dict[str, Path]:
    """A service's tree: the artifacts under its context, re-rooted there (`{out}` is a context root)."""
    out: dict[str, Path] = {}
    for path, rel in files:
        rel = rel[len(OUT) + 1:] if rel.startswith(OUT + "/") else rel
        ctx = context.strip("/")
        if not ctx:
            out[rel] = path
        elif rel.startswith(ctx + "/"):
            out[rel[len(ctx) + 1:]] = path
    return out


def _artifact(tree: dict[str, Any], spec: dict[str, Any], where: str) -> str:
    pattern = spec.get("artifact")
    if not pattern:
        return ""
    excluded = [str(x) for x in spec.get("artifactExclude") or []]
    hits = sorted(r for r in tree if fnmatch.fnmatch(r, str(pattern))
                  and not any(fnmatch.fnmatch(r.rsplit("/", 1)[-1], x) for x in excluded))
    if len(hits) != 1:
        raise PackageError(f"{where}: the recipe needs exactly one `{pattern}` in the release, found "
                           f"{len(hits)}{': ' + ', '.join(hits) if hits else ''}")
    return hits[0]


def recipe(root: Path, manifest: dict, service: Any, tree: dict[str, Any], *, artifact: str | None = None) -> dict[str, bytes]:
    """The files a service's release adds to its artifacts: its container recipe (the module's own
    Dockerfile, else the driver's template rendered for this module), or its static server config.
    `artifact`: the artifact's name when no tree is packaged yet (a projection: its declared glob)."""
    from lib import templating
    from lib.delivery.model import driver_home

    cfg = manifest["modules"][service.module]
    spec = service.spec
    where = f"modules.{service.module} service {service.id}"
    if service.kind == "build":
        if spec.get("dockerfile"):
            own = root / cfg["path"] / str(spec["dockerfile"])
            if not own.is_file():
                raise PackageError(f"{where}: container.dockerfile {spec['dockerfile']} is not there")
            return {"Dockerfile": own.read_bytes()}
        template = driver_home(service.driver) / str(spec["template"])
        if not template.is_file():
            raise PackageError(f"{where}: driver template {spec['template']} is not there")
        extra = {"artifact": artifact if artifact is not None else _artifact(tree, spec, where), "port": str(spec.get("port") or ""),
                 "entry": templating.render(str(spec.get("entry") or ""), cfg),
                 "healthcheck": _probe(spec, where)}
        return {"Dockerfile": templating.render(template.read_text(encoding="utf-8"), cfg, extra).encode("utf-8")}
    if service.kind == "static" and (spec.get("static") or {}).get("config"):
        conf = driver_home(service.driver) / str(spec["static"]["config"])
        extra = {"port": str(spec.get("port") or ""), "mount": str(spec["static"].get("mount") or ""),
                 "proxy": _proxy_blocks(manifest, spec, where)}
        return {".stack-kit/static.conf": templating.render(conf.read_text(encoding="utf-8"), cfg, extra).encode("utf-8")}
    return {}


def _probe(spec: dict, where: str) -> str:
    """The recipe's health probe: the driver's `probe.http` when the service declares its
    `healthPath`, else `probe.tcp` (the port answers) -- never a path the application may not serve."""
    probe = spec.get("probe") or {}
    if not probe:
        return ""
    if spec.get("healthPath"):
        if not probe.get("http"):
            raise PackageError(f"{where}: healthPath is declared but the driver declares no probe.http")
        return str(probe["http"]).replace("{path}", str(spec["healthPath"])).replace("{port}", str(spec.get("port") or ""))
    return str(probe.get("tcp") or "").replace("{port}", str(spec.get("port") or ""))


def _proxy_blocks(manifest: dict, spec: dict, where: str) -> str:
    """Same-origin reverse proxy locations: each declared path to its service on the environment's
    network, by the service id and its declared internal port (no CORS, no address baked in)."""
    from lib.delivery.model import all_services

    proxy = spec.get("proxy") or {}
    if not proxy:
        return ""
    by_id = {s.id: s for s in all_services(manifest)}
    blocks = []
    for path, sid in sorted(proxy.items()):
        target = by_id.get(str(sid))
        if target is None or not target.spec.get("port"):
            raise PackageError(f"{where}: container.proxy {path} names '{sid}', which is no service with a declared port")
        loc = "/" + str(path).strip("/") + "/"
        blocks.append(f"    location {loc} {{\n"
                      f"        proxy_pass http://{sid}:{int(target.spec['port'])};\n"
                      "        proxy_set_header Host $host;\n"
                      "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
                      "        proxy_set_header X-Forwarded-Proto $scheme;\n"
                      "        proxy_http_version 1.1;\n"
                      "    }")
    return "\n".join(blocks)


def pack(root: Path, manifest: dict, module_id: str) -> Path:
    from lib.delivery.model import module_services

    spec = declared(manifest, module_id)
    module_dir = root / manifest["modules"][module_id]["path"]
    files = _files(module_dir, staging(root, module_id), list(spec.get("artifacts") or []))
    patterns = exclusions(manifest, module_id)
    files, kept_out = _kept(files, patterns)
    if not files:
        raise PackageError(f"{module_id}: the package step left none of {spec.get('artifacts')} -- run it first "
                           f"(`{identity.KIT_NAME} package {module_id}`)")
    prov = provenance(root)
    members: dict[str, bytes] = {}
    services: dict[str, Any] = {}
    for service in module_services(manifest, module_id):
        tree = _tree(files, service.context)
        if not tree:
            raise PackageError(f"{module_id}: service {service.id} has no artifact under its context "
                               f"'{service.context or '.'}'")
        if service.kind == "static" and service.spec.get("builtChecks"):
            from lib.delivery.checks import built_static

            baked = built_static({rel: p.read_bytes() for rel, p in tree.items()}, service.spec.get("allowBaked"))
            if baked:
                raise PackageError(f"{module_id}: the built app carries addresses -- they are runtime config, "
                                   f"not the bundle's (container.allowBaked lists any that must stay):\n  " + "\n  ".join(baked))
        if service.kind == "static" and service.spec.get("serve"):
            # A static server whose root holds no index.html answers 403 at `/` while its own health
            # probe stays green -- refused here, naming where the build really put the app.
            served = str(service.spec["serve"]).strip("/")
            if f"{served}/index.html" not in tree:
                found = sorted(rel.rsplit("/", 1)[0] for rel in tree if rel.endswith("/index.html"))
                raise PackageError(f"{module_id}: service {service.id} serves {served}/, which holds no index.html "
                                   f"(`/` would answer 403)" + (f"; the build put it under {', '.join(found)} -- declare "
                                   f"modules.{module_id}.container.serve" if found else ""))
        added = recipe(root, manifest, service, tree)
        for rel, path in tree.items():
            members[f"{service.id}/{rel}"] = path.read_bytes()
        for rel, data in added.items():
            members[f"{service.id}/{rel}"] = data
        services[service.id] = {"kind": service.kind, "files": len(tree) + len(added)}
    meta = {"schema": 1, "module": module_id, **prov, "services": services,
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if patterns:  # the provenance says what the module kept out, and by which rule
        meta["excluded"] = {"patterns": patterns, "files": kept_out}
    archive = artifacts_dir(root) / f"{module_id}-{prov['id']}.tgz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in [(RELEASE_JSON, (json.dumps(meta, indent=1, sort_keys=True) + "\n").encode("utf-8")),
                           *sorted(members.items())]:
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".tgz.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    return archive


def read(archive: Path) -> tuple[dict[str, Any], dict[str, dict[str, bytes]]]:
    """(provenance, {service: {path: bytes}}) of an archive -- refused when its sha256 disagrees with
    the sidecar, when it carries no provenance, or when a member would escape its service."""
    side = archive.with_suffix(".tgz.sha256")
    if not archive.is_file():
        raise PackageError(f"{archive}: no such archive")
    if side.is_file():
        want = side.read_text(encoding="utf-8").split()[0]
        if hashlib.sha256(archive.read_bytes()).hexdigest() != want:
            raise PackageError(f"{archive.name}: sha256 differs from {side.name} -- not the bytes that were packaged")
    meta: dict[str, Any] | None = None
    trees: dict[str, dict[str, bytes]] = {}
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            data = tar.extractfile(m).read()
            if m.name == RELEASE_JSON:
                meta = json.loads(data.decode("utf-8"))
                continue
            sid, _, rel = m.name.partition("/")
            if not rel or rel.startswith("/") or ".." in rel.split("/"):
                raise PackageError(f"{archive.name}: member {m.name} escapes its service -- refused")
            trees.setdefault(sid, {})[rel] = data
    if not meta or not meta.get("id") or not meta.get("commit"):
        raise PackageError(f"{archive.name}: carries no provenance (release.json) -- a release is always of a "
                           f"packaged commit (`{identity.KIT_NAME} package <module>`)")
    return meta, trees


def latest(root: Path, module_id: str) -> Path | None:
    """The archive of this checkout's commit, when it was packaged already (build once)."""
    try:
        prov = provenance(root)
    except PackageError:
        return None
    path = artifacts_dir(root) / f"{module_id}-{prov['id']}.tgz"
    return path if path.is_file() and not prov["dirty"] else None


def main(argv: list[str]) -> int:
    from lib.project_context import ProjectContext

    ctx = ProjectContext.discover()
    try:
        if argv[:1] == ["plan"] and len(argv) == 2:
            print(json.dumps(plan(ctx.root, ctx.manifest, argv[1])))
        elif argv[:1] == ["pack"] and len(argv) == 2:
            print(pack(ctx.root, ctx.manifest, argv[1]).relative_to(ctx.root).as_posix())
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except PackageError as e:
        print(f"[package] ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
