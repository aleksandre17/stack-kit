"""A module's source into its remote-dev workspace, incrementally (ADR-001 amendment 13).

One exclude list (`excludes`): the kit's never-ship patterns (env files, keys, credential files --
config/delivery.json `neverShip` and `credentialPatterns`), the driver's `dev.excludes` and
`outputs`, the module's own `dev.excludes`, and the module's .gitignore. What it
names is never sent, and never deleted on the server either (a dependency directory the dev
container fills inside the workspace survives every sync).

What a module's build reads from ABOVE its directory -- a build tool's project-wide properties,
version pins or SDK pin -- is not in the module, so a workspace holding the module alone could not
build it. The driver names those files (`dev.inherited`); each is found the way the build tool finds
it, the nearest directory above the module up to the project root, and is sent to the workspace's
root -- unless the module has its own, which the tool would read first. Only the nearest of each
name is sent: a chain that imports a further file above it is not followed.

Two ways, chosen by what both ends have:
    rsync     over the target's ssh, when this machine and the server both have it
    index     a built-in fallback needing only ssh and tar: this machine's index (path -> size,
              mtime) against the workspace's, the changed files as one tar stream (mtimes kept, so
              the next comparison is equal), the removed ones deleted -- every deletion confined to
              the workspace. A file whose mtime moved but whose content did not (the hash recorded
              at its last send) is not sent again.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib.delivery.model import Service, defaults
from lib.delivery.transport import Transport, tar_of


@dataclass
class SyncResult:
    way: str
    sent: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged: int = 0

    def changed(self) -> list[str]:
        return [*self.sent, *self.deleted]

    def summary(self) -> str:
        if self.way == "rsync":  # rsync mirrors the module and names no file: only what it inherits is counted
            return f"rsync: the module mirrored (rsync names no file); {len(self.sent)} inherited file(s) sent beside it"
        return f"{self.way}: {len(self.sent)} sent, {len(self.deleted)} deleted, {self.unchanged} unchanged"


def _gitignore(module_dir: Path) -> list[str]:
    path = module_dir / ".gitignore"
    if not path.is_file():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip() and not ln.lstrip().startswith(("#", "!"))]


def excludes(service: Service, module_dir: Path) -> list[str]:
    """THE exclude list of a remote-dev sync -- its one source."""
    from lib.modules import driver_capability

    d = defaults()
    out = [*d["neverShip"], *d["credentialPatterns"], *(service.dev.get("excludes") or []),
           *(driver_capability(service.driver, "outputs", []) or []),
           *_gitignore(module_dir)]
    return list(dict.fromkeys(str(p) for p in out))


def excluded(rel: str, patterns: list[str]) -> bool:
    parts = rel.split("/")
    for raw in patterns:
        dir_only = raw.endswith("/")
        anchored = raw.startswith("/")
        p = raw.strip("/")
        if not p:
            continue
        if "/" in p or anchored:
            if fnmatch.fnmatch(rel, p) or rel.startswith(p + "/") or fnmatch.fnmatch(rel, p + "/*"):
                return True
            continue
        names = parts[:-1] if dir_only else parts
        if any(fnmatch.fnmatch(n, p) for n in names):
            return True
    return False


def inherited(service: Service, module_dir: Path, root: Path) -> dict[str, Path]:
    """workspace name -> the file above the module it is (the driver's or module's `dev.inherited`)."""
    top, here = root.resolve(), module_dir.resolve()
    out: dict[str, Path] = {}
    for name in service.dev.get("inherited") or []:
        if (here / name).is_file():
            continue
        d = here.parent
        while True:
            if (d / name).is_file():
                out[name] = d / name
                break
            if d == top or d.parent == d or top not in d.parents:
                break
            d = d.parent
    return out


def local_index(module_dir: Path, patterns: list[str],
                above: dict[str, Path] | None = None,
                sources: dict[str, Path] | None = None) -> dict[str, tuple[int, int, Path]]:
    out: dict[str, tuple[int, int, Path]] = {}
    for rel, p in (above or {}).items():
        if not excluded(rel, patterns):
            st = p.stat()
            out[rel] = (st.st_size, int(st.st_mtime), p)
    for prefix, source in (sources or {"": module_dir}).items():
        for p in sorted(source.rglob("*")):
            if not p.is_file():
                continue
            rel = posixpath.join(prefix, p.relative_to(source).as_posix()) if prefix else p.relative_to(source).as_posix()
            if excluded(rel, patterns):
                continue
            st = p.stat()
            out[rel] = (st.st_size, int(st.st_mtime), p)
    return out


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remote_has_rsync(transport: Transport) -> bool:
    return transport.has_rsync and transport.exec(["rsync", "--version"], readonly=True).code == 0


def sync(transport: Transport, module_dir: Path, workspace: str, patterns: list[str], *,
         cache: Path | None = None, full: bool = False, prefer_rsync: bool = True,
         above: dict[str, Path] | None = None, sources: dict[str, Path] | None = None) -> SyncResult:
    """The workspace made equal to the module's source and what it inherits from above, minus the
    excludes."""
    transport.mkdir(workspace)
    above = {rel: p for rel, p in (above or {}).items() if not excluded(rel, patterns)}
    sources = sources or {"": module_dir}
    multi_source = sources != {"": module_dir}
    if prefer_rsync and remote_has_rsync(transport):
        # rsync mirrors the module directory with --delete: the inherited files are kept out of its
        # reach, then sent beside it.
        for prefix, source in sources.items():
            remote = posixpath.join(workspace, prefix) if prefix else workspace
            excludes = list(patterns)
            if not prefix:
                excludes += [f"/{rel}" for rel in above]
            transport.rsync(source, remote, excludes)
        if above:
            transport.untar(workspace, tar_of(above))
        if not multi_source:
            return SyncResult("rsync", sent=sorted(above))
        mine = local_index(module_dir, patterns, above, sources)
        gone = sorted(rel for rel in transport.index(workspace) if rel not in mine and not excluded(rel, patterns))
        if gone:
            transport.remove_many(workspace, gone)
        return SyncResult("rsync", sent=sorted(above), deleted=gone)
    known: dict[str, str] = {}
    if cache is not None and cache.is_file() and not full:
        try:
            known = json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:
            known = {}
    mine = local_index(module_dir, patterns, above, sources)
    theirs = transport.index(workspace)
    result = SyncResult("index")
    send: dict[str, Path] = {}
    for rel, (size, mtime, path) in mine.items():
        have = theirs.get(rel)
        if have == (size, mtime):
            result.unchanged += 1
            continue
        if have and have[0] == size and known.get(rel) and known[rel] == _digest(path):
            result.unchanged += 1
            continue
        send[rel] = path
    gone = sorted(rel for rel in theirs if rel not in mine and not excluded(rel, patterns))
    if send:
        transport.untar(workspace, tar_of(send))
    if gone:
        transport.remove_many(workspace, gone)
    result.sent, result.deleted = sorted(send), gone
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        for rel in gone:
            known.pop(rel, None)
        known.update({rel: _digest(p) for rel, p in send.items()})
        cache.write_text(json.dumps(known, indent=0, sort_keys=True), encoding="utf-8")
    return result


def snapshot(module_dir: Path, patterns: list[str],
             above: dict[str, Path] | None = None, sources: dict[str, Path] | None = None) -> dict[str, tuple[int, int]]:
    """What a watcher compares between polls: the module's files and the ones it inherits."""
    return {rel: (size, mtime) for rel, (size, mtime, _p) in local_index(module_dir, patterns, above, sources).items()}


SEVERITY = {"hot-reload": 0, "restart": 1, "rebuild": 2}


def reaction(changed: list[str], rules: list[dict[str, Any]]) -> str:
    """The strongest declared reaction any changed path asks for (default hot-reload: the dev server
    reloads by itself)."""
    found = "hot-reload"
    for rel in changed:
        for rule in rules or []:
            if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel.rsplit("/", 1)[-1], g) for g in rule.get("globs") or []):
                if SEVERITY.get(str(rule.get("do")), 0) > SEVERITY[found]:
                    found = str(rule["do"])
                break
    return found
