"""The fixture host every delivery test uses: a project whose only module is of a driver declared in
the PROJECT's registry (the kit ships none of it), on a shared platform root that already holds
other projects' tier-first folders. Its server is a recording transport with a fake engine."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lib import identity
from lib.delivery import fake_server
from lib.delivery.context import open_delivery
from lib.delivery.transport import RecordingTransport

ROOT = "/srv/platform"
FOREIGN = [f"{ROOT}/backend/other-api/app.jar", f"{ROOT}/frontend/other-app/index.html",
           f"{ROOT}/infra/other/compose.yml", f"{ROOT}/backups/2026-01-01/dump.sql"]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def host(tmp_path: Path, *, target_extra: dict | None = None, manifest_extra: dict | None = None) -> Path:
    """A project whose only module is of a driver declared in the PROJECT's registry."""
    root = tmp_path / "proj"
    (root / "drivers" / "fixture-svc").mkdir(parents=True)
    (root / "drivers" / "registry.json").write_text(json.dumps({"fixture-svc": {
        "label": "a driver no kit ships", "roles": ["edge"], "commands": {"build": "build.py"},
        "package": {"command": "build", "artifacts": ["out/**"]},
        "container": {"template": "Recipe.tpl", "port": 9000, "artifact": "out/*.bin"},
        "dev": {"image": "fixture/dev:{toolchain.version|1}", "command": ["serve"], "port": 9000,
                "caches": {"deps": "/deps"}, "build": ["compile"],
                "reactions": [{"globs": ["*.cfg"], "do": "restart"}, {"globs": ["src/*.code"], "do": "rebuild"}]},
    }}), encoding="utf-8")
    (root / "drivers" / "fixture-svc" / "build.py").write_text(
        "from pathlib import Path\nout = Path('apps/edge/out'); out.mkdir(parents=True, exist_ok=True)\n"
        "(out / 'app.bin').write_text(Path('apps/edge/src/main.code').read_text())\n", encoding="utf-8")
    (root / "drivers" / "fixture-svc" / "Recipe.tpl").write_text(
        "FROM fixture/run:{toolchain.version|1}\nCOPY {artifact} /app.bin\nEXPOSE {port}\nENV HOME=${HOME}\n", encoding="utf-8")
    (root / "apps" / "edge" / "src").mkdir(parents=True)
    (root / "apps" / "edge" / "src" / "main.code").write_text("v1\n", encoding="utf-8")
    (root / "apps" / "edge" / ".gitignore").write_text("out/\n*.log\n", encoding="utf-8")
    (root / "ops" / "config" / "edge").mkdir(parents=True)
    (root / "ops" / "config" / "edge" / ".env").write_text("SHARED=1\n", encoding="utf-8")
    (root / "ops" / "config" / "edge" / ".env.staging").write_text("WHERE=staging\n", encoding="utf-8")
    (root / "ops" / "config" / "edge" / ".env.dev").write_text("WHERE=dev\n", encoding="utf-8")
    (root / "ops" / "config" / "edge" / "gateway.p12").write_bytes(b"\x00binary-credential")
    (root / "ops" / "config" / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (root / "ops" / "deploy").mkdir(parents=True)
    target = {"runtime": "fixture-compose", "host": "h.example", "user": "deployer", "root": ROOT,
              "ports": {"staging": {"edge": [18080]}, "dev": {"edge": [18081]}}, "keep": 2,
              "healthWait": {"retries": 3, "interval": 0}, **(target_extra or {})}
    (root / "ops" / "deploy" / "targets.json").write_text(json.dumps(
        {"schema": 1, "defaults": {"staging": "box", "dev": "box", "prod": "box"}, "targets": {"box": target}}), encoding="utf-8")
    manifest = {"version": 2, "project": "shop", "secrets": "ops/config", "drivers": {"registry": "drivers/registry.json"},
                "deploy": {"targets": "ops/deploy/targets.json"},
                "catalogs": {"tiers": [{"id": "edge"}], "roles": [{"id": "edge", "tier": "edge", "deployOrder": 0}],
                             "environments": [{"id": "staging", "after": "dev", "requireClean": True,
                                               "rollbackOnFailure": True}],
                             "targetRuntimes": [{"id": "fixture-compose", "engine": ["eng"], "compose": ["eng-compose"],
                                                 "stack": True}]},
                "modules": {"edge": {"type": "fixture-svc", "role": "edge", "path": "apps/edge", "secretsModule": "edge",
                                     "toolchain": {"version": "7"},
                                     "credentials": [{"file": "gateway.p12", "mount": "/certs/gateway.p12",
                                                      "envVar": "GATEWAY_CERT"}]}},
                **(manifest_extra or {})}
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", "-A")
    _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "fixture")
    return root


def manifest_of(root: Path) -> dict:
    return json.loads((root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))


def server(tmp_path: Path, **state) -> RecordingTransport:
    t = RecordingTransport()
    for f in FOREIGN:
        t.write(f, b"another project's")
    tmp_path.mkdir(parents=True, exist_ok=True)
    record = tmp_path / "server.json"
    if state:
        base = fake_server._load(fake_server.state_file(record))
        base.update(state)
        fake_server.state_file(record).write_text(json.dumps(base), encoding="utf-8")
    t.responses = fake_server.responses(t, record)
    t.log.clear()
    return t


def ctx_for(root: Path, t: RecordingTransport, env: str = "staging"):
    return open_delivery(root, manifest_of(root), environment=env, transport=t, out=lambda s: None, sleep=lambda s: None)


def packaged(root: Path) -> Path:
    from lib import package
    from lib.cli import tools

    assert tools.driver_command("edge", "build", []) == 0
    return package.pack(root, manifest_of(root), "edge")


def commit(root: Path, text: str) -> None:
    (root / "apps" / "edge" / "src" / "main.code").write_text(text, encoding="utf-8")
    _git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qam", text.strip())
