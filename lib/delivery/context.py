"""One delivery run's context: the project, the environment, the selected target and its rendered
places, the transport that reaches it, and the commands that run there -- each from its one home.

Nothing downstream reads a declaration file or a root: it asks this object. `places.of(kind,
service)` is the only way to a remote path; `compose(...)` / `engine(...)` the only way to a command.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from lib import catalogs, identity, naming, targets
from lib.delivery.output import excerpt
from lib.delivery.transport import DryRun, LocalTransport, RecordingTransport, SshTransport, Transport

#: A test or a rehearsal hands the engine a transport by naming it: `record:<file>` (an in-memory server
#: kept in a JSON file between runs) or `local:<dir>` (a directory standing in for the server).
TRANSPORT_VAR = identity.env_name("TRANSPORT")


class DeliveryError(RuntimeError):
    """A delivery that must not go on, with why; `code` is the CLI's exit code for it."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Delivery:
    root: Path
    manifest: dict[str, Any]
    project: str
    environment: str
    target_name: str
    target: dict[str, Any]
    places: targets.Places
    transport: Transport
    commands: dict[str, list[str]]
    repository: str
    out: Callable[[str], None] = print
    sleep: Callable[[float], None] = time.sleep
    plan: bool = False
    _close: Callable[[], None] | None = field(default=None, repr=False)

    @property
    def secrets_root(self) -> Path:
        from lib.manifest_defaults import default_field

        return self.root / str(self.manifest.get("secrets") or default_field("secrets") or "ops/config")

    def flag(self, name: str) -> bool:
        return bool((catalogs.entry("environments", self.environment, self.manifest) or {}).get(name))

    def compose(self, *args: str) -> list[str]:
        if not self.commands["compose"]:
            raise DeliveryError(f"target {self.target_name}: runtime '{self.target.get('runtime')}' runs no compose stack")
        return [*self.commands["compose"], "-f", self.places.of("stackCompose"), *args]

    def engine(self, *args: str) -> list[str]:
        if not self.commands["engine"]:
            raise DeliveryError(f"target {self.target_name}: runtime '{self.target.get('runtime')}' declares no engine")
        return [*self.commands["engine"], *args]

    def run(self, argv: list[str], *, readonly: bool = False, check: bool = True, stream: bool = False):
        r = self.transport.exec(argv, readonly=readonly, stream=stream)
        if check and r.code != 0:
            raise DeliveryError(f"{' '.join(argv[:4])} ...: exit {r.code}: {excerpt(r.err or r.out)}")
        return r

    def dry(self) -> "Delivery":
        """The same run, planned: reads reach the server, every change is printed instead."""
        clone = Delivery(**{k: getattr(self, k) for k in self.__dataclass_fields__ if k != "_close"})
        clone.transport, clone.plan = DryRun(self.transport, self.out), True
        return clone

    def close(self) -> None:
        if self._close:
            self._close()


def _transport(server: str, ssh_args: list[str], confine: str) -> tuple[Transport, Callable[[], None] | None]:
    named = os.environ.get(TRANSPORT_VAR, "")
    if named.startswith("record:"):
        path = Path(named[len("record:"):])
        t = RecordingTransport.load(path)
        t.confine = confine
        from lib.delivery import fake_server

        t.responses = fake_server.responses(t, path)
        return t, (lambda: t.dump(path))
    if named.startswith("local:"):
        return LocalTransport(Path(named[len("local:"):]), confine), None
    return SshTransport(server, ssh_args, confine), None


def open_delivery(root: Path, manifest: dict[str, Any], *, environment: str = "", target: str = "",
                  transport: Transport | None = None, out: Callable[[str], None] = print,
                  sleep: Callable[[float], None] | None = None) -> Delivery:
    """The context of one run: the environment asked for (else the catalog's deploy default), the
    target asked for (else the environment's default), refused while it is pending."""
    environment = environment or identity.env("ENVIRONMENT") or catalogs.default_environment("deploy", manifest)
    catalogs.require("environments", environment, manifest, what="--env")
    data = targets.load(root, manifest)
    if data is None:
        raise DeliveryError(f"no deploy targets are declared (manifest `deploy.targets`)", 2)
    try:
        name, t = targets.select(data, target or identity.env("TARGET"), environment, manifest)
        targets.reachable(name, t)
    except targets.TargetError as e:
        raise DeliveryError(str(e), 2) from e
    from lib import catalogs as _c

    pending = (_c.entry("targetRuntimes", str(t.get("runtime") or ""), manifest) or {}).get("pending")
    if pending:
        raise DeliveryError(f"target {name}: runtime '{t.get('runtime')}' is pending: {pending}", 2)
    project = naming.project_slug(manifest, root)
    places = targets.Places(t, project=project, environment=environment, environments=catalogs.ids("environments", manifest))
    if transport is None:
        transport, closer = _transport(targets.server(name, t), targets.ssh_args(root, name, t), places.environment_dir)
    else:
        closer = None
        transport.confine = places.environment_dir
    return Delivery(root=root, manifest=manifest, project=project, environment=environment, target_name=name,
                    target=t, places=places, transport=transport, commands=targets.runtime_commands(t, manifest),
                    repository=targets.repository_identity(root), out=out, sleep=sleep or time.sleep, _close=closer)
