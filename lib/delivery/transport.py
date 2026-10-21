"""How the delivery engine reaches a server: a handful of operations, four implementations.

    SshTransport        openssh (+ tar over the connection; rsync only for a sync, and only when
                        this machine has it) with the selected target's options
    LocalTransport      a directory on this machine standing in for the server: the same index/tar
                        code paths, no ssh -- how the sync fallback is proven end to end
    RecordingTransport  an in-memory server (files, directories, links) recording every operation,
                        answering `exec` from scripted responses: the engine's whole behaviour is
                        asserted without a server (ADR-001 amendment 13)
    DryRun              a plan: reads (and read-only commands) reach the real transport, every write
                        and every other command is printed instead of done

Every server path is absolute and POSIX, and rendered by the layout (lib/targets/layout.py) -- no
transport composes one. A remove is refused unless it lies strictly inside the confinement the
engine names (the project's environment directory, or a workspace).
"""
from __future__ import annotations

import io
import json
import os
import posixpath
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from lib.delivery.output import excerpt


class TransportError(RuntimeError):
    """A remote operation that failed, with what the server said."""


def under(path: str, base: str) -> bool:
    path, base = posixpath.normpath(path), posixpath.normpath(base)
    return path == base or path.startswith(base.rstrip("/") + "/")


def _safe_rel(rel: str) -> str:
    norm = posixpath.normpath(rel)
    if norm.startswith(("/", "../")) or norm in ("..", ".", ""):
        raise TransportError(f"refused: {rel!r} is not a path inside its base")
    return norm


@dataclass
class Result:
    code: int
    out: str = ""
    err: str = ""
    data: bytes = b""


def tar_of(files: dict[str, Path]) -> bytes:
    """One tar stream of {name in the archive: local file}, mtimes kept (the sync index compares them)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name in sorted(files):
            tar.add(str(files[name]), arcname=_safe_rel(name), recursive=False)
    return buf.getvalue()


def tar_bytes(members: dict[str, bytes], mode: int = 0o644) -> bytes:
    """One tar stream of {name: bytes} -- a release tree out of an archive, never touching the disk."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name in sorted(members):
            info = tarfile.TarInfo(_safe_rel(name))
            info.size, info.mode, info.mtime = len(members[name]), mode, 0
            tar.addfile(info, io.BytesIO(members[name]))
    return buf.getvalue()


def tree_tar(local_dir: Path) -> bytes:
    return tar_of({p.relative_to(local_dir).as_posix(): p for p in sorted(Path(local_dir).rglob("*")) if p.is_file()})


class Transport:
    """The operations the engine needs; every implementation confines removes to `confine`."""

    confine: str = "/"
    has_rsync: bool = False

    def mkdir(self, path: str) -> None: raise NotImplementedError
    def write(self, path: str, data: bytes, mode: str = "644") -> None: raise NotImplementedError
    def read(self, path: str) -> bytes | None: raise NotImplementedError
    def exists(self, path: str) -> bool: raise NotImplementedError
    def listdir(self, path: str) -> list[str]: raise NotImplementedError
    def mtime(self, path: str) -> float: raise NotImplementedError
    def link(self, target: str, path: str) -> None: raise NotImplementedError
    def readlink(self, path: str) -> str | None: raise NotImplementedError
    def untar(self, path: str, data: bytes) -> None: raise NotImplementedError
    def index(self, path: str) -> dict[str, tuple[int, int]]: raise NotImplementedError
    def rsync(self, local_dir: Path, path: str, excludes: list[str]) -> None: raise NotImplementedError
    def move(self, src: str, dst: str) -> None: raise NotImplementedError
    def exec(self, argv: list[str], cwd: str = "", env: dict[str, str] | None = None, stream: bool = False,
             readonly: bool = False) -> Result:
        raise NotImplementedError

    def put_tree(self, local_dir: Path, path: str) -> None:
        self.mkdir(path)
        self.untar(path, tree_tar(local_dir))

    def interactive(self, argv: list[str]) -> int:
        """A command attached to this terminal (a shell in a container); its exit code."""
        return self.exec(argv, stream=True).code

    def tunnel(self, forwards: list[tuple[int, int]]) -> int:
        """Local ports forwarded to the server's (until interrupted); its exit code."""
        raise TransportError("this transport opens no tunnel")

    def held(self, path: str, confine: str | None = None) -> None:
        base = confine or self.confine
        if not under(path, base) or posixpath.normpath(path) == posixpath.normpath(base):
            raise TransportError(f"refused: remove {path} -- not strictly inside {base}")

    def remove(self, path: str, confine: str | None = None) -> None:
        self.held(path, confine)
        self._remove(path)

    def remove_many(self, base: str, rels: list[str]) -> None:
        """Files under `base` (a workspace), each named relative to it, in one operation."""
        paths = [posixpath.join(base, _safe_rel(r)) for r in rels]
        for p in paths:
            self.held(p, base)
        if paths:
            self._remove_many(paths)

    def _remove(self, path: str) -> None: raise NotImplementedError

    def _remove_many(self, paths: list[str]) -> None:
        for p in paths:
            self._remove(p)


# ── the real one ─────────────────────────────────────────────────────────────

class SshTransport(Transport):
    """openssh with the target's options; one connection reused (ControlMaster where supported)."""

    def __init__(self, server: str, ssh_args: list[str], confine: str) -> None:
        self.server = server
        self.confine = confine
        self.args = list(ssh_args)
        if os.name != "nt":  # Windows' openssh has no ControlMaster
            control = Path(tempfile.gettempdir()) / f"stack-kit-ssh-{abs(hash(server)) % 10**8}"
            self.args += ["-o", "ControlMaster=auto", "-o", f"ControlPath={control.as_posix()}", "-o", "ControlPersist=60"]
        self.has_rsync = shutil.which("rsync") is not None

    def _ssh(self, script: str, data: bytes | None = None, stream: bool = False) -> Result:
        argv = ["ssh", *self.args, self.server, "bash", "-c", shlex.quote(script)]
        if stream:
            return Result(subprocess.run(argv).returncode)
        try:
            ran = subprocess.run(argv, input=data, capture_output=True)
        except OSError as e:
            raise TransportError(f"{self.server}: ssh could not start: {e}") from e
        if ran.returncode == 255:
            raise TransportError(f"{self.server}: unreachable: {excerpt(ran.stderr.decode('utf-8', 'replace'))}")
        return Result(ran.returncode, ran.stdout.decode("utf-8", "replace"), ran.stderr.decode("utf-8", "replace"), ran.stdout)

    def _ok(self, script: str, data: bytes | None = None) -> Result:
        r = self._ssh(script, data)
        if r.code != 0:
            raise TransportError(f"{self.server}: {script.splitlines()[0][:120]}: {excerpt(r.err)}")
        return r

    def mkdir(self, path: str) -> None:
        self._ok(f"mkdir -p {shlex.quote(path)}")

    def write(self, path: str, data: bytes, mode: str = "644") -> None:
        q, tmp = shlex.quote(path), shlex.quote(path + ".stack-kit-tmp")
        self._ok(f"mkdir -p {shlex.quote(posixpath.dirname(path))} && umask 077 && cat > {tmp} && chmod {mode} {tmp} && mv -f {tmp} {q}", data)

    def read(self, path: str) -> bytes | None:
        r = self._ssh(f"cat {shlex.quote(path)} 2>/dev/null")
        return r.data if r.code == 0 else None

    def exists(self, path: str) -> bool:
        return self._ssh(f"test -e {shlex.quote(path)} || test -L {shlex.quote(path)}").code == 0

    def listdir(self, path: str) -> list[str]:
        r = self._ssh(f"ls -1A {shlex.quote(path)} 2>/dev/null")
        return sorted(x for x in r.out.splitlines() if x) if r.code == 0 else []

    def mtime(self, path: str) -> float:
        r = self._ssh(f"stat -c %Y {shlex.quote(path)} 2>/dev/null")
        return float(r.out.strip() or 0) if r.code == 0 else 0.0

    def link(self, target: str, path: str) -> None:
        q, tmp = shlex.quote(path), shlex.quote(path + ".stack-kit-tmp")
        self._ok(f"ln -sfn {shlex.quote(target)} {tmp} && mv -Tf {tmp} {q}")

    def readlink(self, path: str) -> str | None:
        r = self._ssh(f"readlink {shlex.quote(path)}")
        return (r.out.strip() or None) if r.code == 0 else None

    def untar(self, path: str, data: bytes) -> None:
        self._ok(f"mkdir -p {shlex.quote(path)} && tar -xf - -C {shlex.quote(path)}", data)

    def index(self, path: str) -> dict[str, tuple[int, int]]:
        # A directory not there yet holds nothing (the first sync); one `find` cannot read fully is a failure,
        # never an empty index -- that would resend everything and delete nothing, silently.
        q = shlex.quote(path)
        r = self._ok(f"[ -d {q} ] || exit 0; cd {q} && find . -type f -printf '%P\\t%s\\t%T@\\n'")
        out = {}
        for line in r.out.splitlines():
            rel, size, mtime = line.rsplit("\t", 2)
            out[rel] = (int(size), int(float(mtime)))
        return out

    def rsync(self, local_dir: Path, path: str, excludes: list[str]) -> None:
        self.mkdir(path)
        rsh = " ".join(["ssh", *(shlex.quote(a) for a in self.args)])
        argv = ["rsync", "-az", "--delete", "-e", rsh, *(f"--exclude={e}" for e in excludes),
                f"{local_dir.as_posix()}/", f"{self.server}:{path}/"]
        ran = subprocess.run(argv, capture_output=True, text=True)
        if ran.returncode != 0:
            raise TransportError(f"{self.server}: rsync to {path}: {excerpt(ran.stderr)}")

    def move(self, src: str, dst: str) -> None:
        self._ok(f"mkdir -p {shlex.quote(posixpath.dirname(dst))} && mv -T {shlex.quote(src)} {shlex.quote(dst)}")

    def _remove(self, path: str) -> None:
        self._ok(f"rm -rf -- {shlex.quote(path)}")

    def _remove_many(self, paths: list[str]) -> None:
        # The list goes through stdin, NUL-separated, never on the command line: a command line has a length limit
        # (Windows 32 767 characters -- WinError 206 on a workspace with many files gone), and NUL is the one byte no
        # path can hold, so no name splits or escapes. Each path was already held inside the workspace by remove_many.
        self._ok("xargs -0 rm -f --", data=b"\0".join(p.encode("utf-8") for p in paths))

    def interactive(self, argv: list[str]) -> int:
        return subprocess.run(["ssh", "-t", *self.args, self.server, *(shlex.quote(a) for a in argv)]).returncode

    def tunnel(self, forwards: list[tuple[int, int]]) -> int:
        spec = [a for local, remote in forwards for a in ("-L", f"{local}:127.0.0.1:{remote}")]
        return subprocess.run(["ssh", "-N", *spec, *self.args, self.server]).returncode

    def exec(self, argv: list[str], cwd: str = "", env: dict[str, str] | None = None, stream: bool = False,
             readonly: bool = False) -> Result:
        prefix = f"cd {shlex.quote(cwd)} && " if cwd else ""
        assigns = " ".join(f"{k}={shlex.quote(v)}" for k, v in (env or {}).items())
        return self._ssh(prefix + (assigns + " " if assigns else "") + " ".join(shlex.quote(a) for a in argv), stream=stream)


# ── a directory standing in for the server ───────────────────────────────────

class LocalTransport(Transport):
    """Server paths mapped under a local directory (`/srv/p` -> <base>/srv/p): the sync's index and
    tar code runs exactly as against a server, without ssh. `exec` answers from `responses`."""

    def __init__(self, base: Path, confine: str = "/", responses: Callable[..., Result] | None = None) -> None:
        self.base, self.confine, self.responses = Path(base), confine, responses
        self.log: list[tuple] = []

    def _p(self, path: str) -> Path:
        return self.base / posixpath.normpath(path).lstrip("/")

    def mkdir(self, path: str) -> None:
        self._p(path).mkdir(parents=True, exist_ok=True)

    def write(self, path: str, data: bytes, mode: str = "644") -> None:
        p = self._p(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def read(self, path: str) -> bytes | None:
        p = self._p(path)
        return p.read_bytes() if p.is_file() else None

    def exists(self, path: str) -> bool:
        return self._p(path).exists()

    def listdir(self, path: str) -> list[str]:
        p = self._p(path)
        return sorted(x.name for x in p.iterdir()) if p.is_dir() else []

    def mtime(self, path: str) -> float:
        p = self._p(path)
        return p.stat().st_mtime if p.exists() else 0.0

    def link(self, target: str, path: str) -> None:
        self.write(path + ".link", target.encode("utf-8"))

    def readlink(self, path: str) -> str | None:
        data = self.read(path + ".link")
        return data.decode("utf-8") if data is not None else None

    def untar(self, path: str, data: bytes) -> None:
        dest = self._p(path)
        dest.mkdir(parents=True, exist_ok=True)
        self.log.append(("untar", path))
        with tarfile.open(fileobj=io.BytesIO(data), mode="r") as tar:
            for m in tar.getmembers():
                out = dest / _safe_rel(m.name)
                if not out.resolve().is_relative_to(dest.resolve()) or not m.isfile():
                    raise TransportError(f"refused: tar member {m.name}")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(tar.extractfile(m).read())
                os.utime(out, (m.mtime, m.mtime))

    def index(self, path: str) -> dict[str, tuple[int, int]]:
        base = self._p(path)
        return {p.relative_to(base).as_posix(): (p.stat().st_size, int(p.stat().st_mtime))
                for p in sorted(base.rglob("*")) if p.is_file()} if base.is_dir() else {}

    def move(self, src: str, dst: str) -> None:
        self._p(dst).parent.mkdir(parents=True, exist_ok=True)
        self._p(src).rename(self._p(dst))

    def _remove(self, path: str) -> None:
        p = self._p(path)
        self.log.append(("remove", path))
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()

    def exec(self, argv: list[str], cwd: str = "", env: dict[str, str] | None = None, stream: bool = False,
             readonly: bool = False) -> Result:
        self.log.append(("exec", tuple(argv)))
        return self.responses(argv, cwd, env or {}) if self.responses else Result(0)


# ── the recording one ────────────────────────────────────────────────────────

@dataclass
class RecordingTransport(Transport):
    """An in-memory server: `files` (path -> bytes), `dirs`, `links` (path -> target), the operation
    log, and `responses` -- a function answering each `exec` (default: exit 0, no output)."""

    confine: str = "/"
    files: dict[str, bytes] = field(default_factory=dict)
    modes: dict[str, str] = field(default_factory=dict)
    dirs: set[str] = field(default_factory=set)
    links: dict[str, str] = field(default_factory=dict)
    log: list[tuple] = field(default_factory=list)
    responses: Callable[[list[str], str, dict[str, str]], Result] | None = None
    clock: int = 0
    mtimes: dict[str, int] = field(default_factory=dict)

    def _tick(self, path: str) -> None:
        self.clock += 1
        self.mtimes[posixpath.normpath(path)] = self.clock

    def _mkdirs(self, path: str) -> None:
        path = posixpath.normpath(path)
        while path not in ("/", "") and path not in self.dirs:
            self.dirs.add(path)
            self._tick(path)
            path = posixpath.dirname(path)

    def mkdir(self, path: str) -> None:
        self.log.append(("mkdir", posixpath.normpath(path)))
        self._mkdirs(path)

    def write(self, path: str, data: bytes, mode: str = "644") -> None:
        path = posixpath.normpath(path)
        self.log.append(("write", path, mode))
        self._mkdirs(posixpath.dirname(path))
        self.files[path], self.modes[path] = data, mode
        self._tick(path)

    def read(self, path: str) -> bytes | None:
        return self.files.get(posixpath.normpath(path))

    def exists(self, path: str) -> bool:
        p = posixpath.normpath(path)
        return p in self.files or p in self.dirs or p in self.links

    def listdir(self, path: str) -> list[str]:
        p = posixpath.normpath(path)
        return sorted({q[len(p) + 1:].split("/")[0] for q in (*self.files, *self.dirs, *self.links) if q.startswith(p + "/")})

    def mtime(self, path: str) -> float:
        return float(self.mtimes.get(posixpath.normpath(path), 0))

    def link(self, target: str, path: str) -> None:
        path = posixpath.normpath(path)
        self.log.append(("link", target, path))
        self._mkdirs(posixpath.dirname(path))
        self.links[path] = target
        self._tick(path)

    def readlink(self, path: str) -> str | None:
        return self.links.get(posixpath.normpath(path))

    def untar(self, path: str, data: bytes) -> None:
        path = posixpath.normpath(path)
        self.log.append(("untar", path))
        self._mkdirs(path)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r") as tar:
            for m in tar.getmembers():
                if m.isfile():
                    p = posixpath.join(path, _safe_rel(m.name))
                    self._mkdirs(posixpath.dirname(p))
                    self.files[p] = tar.extractfile(m).read()
                    self.mtimes[p] = int(m.mtime)
        self._tick(path)

    def index(self, path: str) -> dict[str, tuple[int, int]]:
        p = posixpath.normpath(path)
        return {q[len(p) + 1:]: (len(v), int(self.mtimes.get(q, 0))) for q, v in self.files.items() if q.startswith(p + "/")}

    def rsync(self, local_dir: Path, path: str, excludes: list[str]) -> None:
        raise TransportError("the recording transport has no rsync")

    def move(self, src: str, dst: str) -> None:
        src, dst = posixpath.normpath(src), posixpath.normpath(dst)
        self.log.append(("move", src, dst))
        for table in (self.files, self.links, self.mtimes, self.modes):
            for q in [q for q in table if q == src or q.startswith(src + "/")]:
                table[dst + q[len(src):]] = table.pop(q)
        for q in [q for q in self.dirs if q == src or q.startswith(src + "/")]:
            self.dirs.discard(q)
            self.dirs.add(dst + q[len(src):])
        self._mkdirs(posixpath.dirname(dst))
        self._tick(dst)

    def _remove(self, path: str) -> None:
        p = posixpath.normpath(path)
        self.log.append(("remove", p))
        for table in (self.files, self.links, self.mtimes, self.modes):
            for q in [q for q in table if q == p or q.startswith(p + "/")]:
                del table[q]
        self.dirs = {q for q in self.dirs if not (q == p or q.startswith(p + "/"))}

    def exec(self, argv: list[str], cwd: str = "", env: dict[str, str] | None = None, stream: bool = False,
             readonly: bool = False) -> Result:
        self.log.append(("exec", tuple(argv), cwd, tuple(sorted((env or {}).items()))))
        return self.responses(argv, cwd, env or {}) if self.responses else Result(0)

    def interactive(self, argv: list[str]) -> int:
        self.log.append(("interactive", tuple(argv)))
        return 0

    def tunnel(self, forwards: list[tuple[int, int]]) -> int:
        self.log.append(("tunnel", tuple(forwards)))
        return 0

    def changes(self) -> list[tuple]:
        """The operations that changed the server's content (what idempotence is asserted on)."""
        return [e for e in self.log if e[0] in ("write", "link", "untar", "move", "remove")]

    # A recording transport survives a process boundary (the CLI's acceptance tests) as JSON.
    def dump(self, path: Path) -> None:
        path.write_text(json.dumps({
            "confine": self.confine, "files": {k: v.decode("utf-8", "replace") for k, v in self.files.items()},
            "modes": self.modes, "dirs": sorted(self.dirs), "links": self.links, "clock": self.clock,
            "mtimes": self.mtimes, "log": [list(map(_jsonable, e)) for e in self.log]}, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "RecordingTransport":
        if not path.is_file():
            return cls()
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(confine=d.get("confine", "/"), files={k: v.encode("utf-8") for k, v in d.get("files", {}).items()},
                   modes=d.get("modes", {}), dirs=set(d.get("dirs", [])), links=d.get("links", {}),
                   clock=d.get("clock", 0), mtimes=d.get("mtimes", {}), log=[tuple(e) for e in d.get("log", [])])


def _jsonable(x: Any) -> Any:
    return [list(i) if isinstance(i, tuple) else i for i in x] if isinstance(x, tuple) else x


# ── a plan ───────────────────────────────────────────────────────────────────

class DryRun(Transport):
    """The plan of an operation: what it reads it reads from the real transport; what it would write,
    link, move, remove or run (unless `readonly`) it prints, exactly, and does not do."""

    def __init__(self, real: Transport, out: Callable[[str], None]) -> None:
        self.real, self.out, self.confine, self.has_rsync = real, out, real.confine, real.has_rsync
        self.steps: list[str] = []

    def _say(self, line: str) -> None:
        self.steps.append(line)
        self.out(f"  plan: {line}")

    def mkdir(self, path: str) -> None:
        if not self.real.exists(path):
            self._say(f"mkdir {path}")

    def write(self, path: str, data: bytes, mode: str = "644") -> None:
        self._say(f"write {path} ({len(data)} bytes, mode {mode})")

    def read(self, path: str) -> bytes | None: return self.real.read(path)
    def exists(self, path: str) -> bool: return self.real.exists(path)
    def listdir(self, path: str) -> list[str]: return self.real.listdir(path)
    def mtime(self, path: str) -> float: return self.real.mtime(path)
    def readlink(self, path: str) -> str | None: return self.real.readlink(path)
    def index(self, path: str) -> dict[str, tuple[int, int]]: return self.real.index(path)

    def link(self, target: str, path: str) -> None:
        self._say(f"link {path} -> {target}")

    def untar(self, path: str, data: bytes) -> None:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r") as tar:
            n = len([m for m in tar.getmembers() if m.isfile()])
        self._say(f"unpack {n} file(s) into {path}")

    def rsync(self, local_dir: Path, path: str, excludes: list[str]) -> None:
        self._say(f"rsync {local_dir.as_posix()}/ -> {path}/ (delete, {len(excludes)} exclude(s))")

    def move(self, src: str, dst: str) -> None:
        self._say(f"move {src} -> {dst}")

    def _remove(self, path: str) -> None:
        self._say(f"remove {path}")

    def interactive(self, argv: list[str]) -> int:
        self._say("attach: " + " ".join(shlex.quote(a) for a in argv))
        return 0

    def tunnel(self, forwards: list[tuple[int, int]]) -> int:
        self._say("tunnel " + ", ".join(f"localhost:{a} -> server:{b}" for a, b in forwards))
        return 0

    def _remove_many(self, paths: list[str]) -> None:
        self._say(f"remove {len(paths)} file(s): " + ", ".join(paths[:5]) + (" ..." if len(paths) > 5 else ""))

    def exec(self, argv: list[str], cwd: str = "", env: dict[str, str] | None = None, stream: bool = False,
             readonly: bool = False) -> Result:
        if readonly:
            return self.real.exec(argv, cwd, env, stream=False, readonly=True)
        self._say(("cd " + cwd + " && " if cwd else "") + " ".join(shlex.quote(a) for a in argv))
        return Result(0)
