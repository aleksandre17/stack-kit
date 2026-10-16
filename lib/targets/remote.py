"""How a target is reached and what runs there -- each answered from its one declaration.

    ssh_args            the openssh options of a target (port, pinned host keys, identity reference)
    runtime_commands    the container engine and compose invocations: the target runtime's
                        (catalogs.targetRuntimes `engine`, `compose`), a target's `compose` over it
    repository_identity this repository's identity for the ownership marker
    health_urls         a target's declared health URLs for an environment
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from lib.targets.declaration import TargetError, reachable


def ssh_args(root: Path, name: str, target: dict[str, Any]) -> list[str]:
    """The openssh options (`-o`/`-F`, valid for ssh, scp and rsync -e) that reach the target."""
    t = reachable(name, target)
    ssh = t.get("ssh") or {}
    out = ["-o", f"Port={int(t.get('port') or 22)}"]
    out += ["-o", "StrictHostKeyChecking=accept-new" if ssh.get("hostKeys") == "accept-new" else "StrictHostKeyChecking=yes"]
    if ssh.get("knownHosts"):
        out += ["-o", f"UserKnownHostsFile={(root / ssh['knownHosts']).as_posix()}"]
    ref = str(ssh.get("identity") or "agent")
    key = ""
    if ref.startswith("env:"):
        key = os.environ.get(ref[4:], "")
        if not key:
            raise TargetError(f"target {name}: ssh.identity {ref} -- ${ref[4:]} is not set")
    elif ref.startswith("file:"):
        key = (root / ref[5:]).as_posix()
    if key:
        out += ["-o", f"IdentityFile={key}", "-o", "IdentitiesOnly=yes"]
    if ssh.get("config"):
        out += ["-F", (root / ssh["config"]).as_posix()]
    for opt in ssh.get("options") or []:
        out += ["-o", str(opt)]
    return out


def identity_kind(target: dict[str, Any]) -> str:
    ref = str((target.get("ssh") or {}).get("identity") or "agent")
    return ref.split(":", 1)[0] if ":" in ref else ref


def runtime_entry(target: dict[str, Any], manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    from lib import catalogs

    return catalogs.entry("targetRuntimes", str(target.get("runtime") or ""), manifest) or {}


def runtime_commands(target: dict[str, Any], manifest: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """{"engine": argv, "compose": argv} -- the one home of each invocation: the runtime's
    declaration, a target's own `compose` / `engine` over it (a host with only a standalone compose
    binary declares it there). A runtime that runs no stack answers empty lists."""
    entry = runtime_entry(target, manifest)
    return {"engine": [str(a) for a in (target.get("engine") or entry.get("engine") or [])],
            "compose": [str(a) for a in (target.get("compose") or entry.get("compose") or [])]}


def local_commands(manifest: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """The engine and compose invocations on THIS machine: the runtime flagged `local`."""
    from lib import catalogs

    entry = next((e for e in catalogs.entries("targetRuntimes", manifest) if e.get("local")), {})
    return {"engine": [str(a) for a in entry.get("engine") or []], "compose": [str(a) for a in entry.get("compose") or []]}


def runs_stack(target: dict[str, Any], manifest: dict[str, Any] | None = None) -> bool:
    return bool(runtime_entry(target, manifest).get("stack"))


def repository_identity(root: Path) -> str:
    """This repository's identity for the ownership marker: its origin, as host/path (an https and an
    ssh spelling of one remote are one repository; credentials never enter it); "" without one."""
    try:
        ran = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True)
    except OSError:
        return ""
    url = ran.stdout.strip() if ran.returncode == 0 else ""
    m = re.match(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^/:]+)[:/](.+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}".lower() if m else ""


def health_urls(target: dict[str, Any], environment: str) -> dict[str, str]:
    return dict((target.get("health") or {}).get(environment) or {})


def check_health_urls(urls: dict[str, str], *, attempts: int, pause: float, out=print) -> list[str]:
    """Every URL answers below 400, retried while a release starts; the failures, named."""
    import time
    import urllib.error
    import urllib.request

    failed = []
    for service, url in urls.items():
        last = ""
        for i in range(attempts):
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    if resp.status < 400:
                        out(f"[health] {service} {url} -> {resp.status}")
                        break
                    last = f"HTTP {resp.status}"
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
            except (urllib.error.URLError, OSError) as e:
                last = str(getattr(e, "reason", e))
            if i + 1 < attempts:
                time.sleep(pause)
        else:
            failed.append(f"{service} {url}: {last} after {attempts} attempt(s)")
    return failed
