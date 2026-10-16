"""The delivery engine against an in-memory server (ADR-001 amendment 13): releases, `current`,
rollback, prune, idempotence, the ownership marker on a shared root with foreign tier-first folders,
the port preflight, migrate-layout -- through a fixture driver the kit does not ship, a tier, an
environment and a target runtime all declared by the host alone (open/closed)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib import identity
from lib.delivery import fake_server, legacy_layout, manage, preflight, release, running, tree
from lib.delivery.context import DeliveryError, open_delivery
from lib.delivery.transport import RecordingTransport, Result

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


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = host(tmp_path)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
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


def foreign_intact(t: RecordingTransport) -> None:
    for f in FOREIGN:
        assert t.read(f) == b"another project's", f
    touched = [e for e in t.log if e[0] in ("write", "link", "untar", "move", "remove", "mkdir")]
    outside = [e for e in touched if not any(str(p).startswith(f"{ROOT}/shop") for p in e[1:3] if isinstance(p, str)
                                             and p.startswith("/"))]
    assert not outside, outside


# ── a release ────────────────────────────────────────────────────────────────

def test_a_release_lands_in_the_layout_and_a_second_one_changes_nothing(project, tmp_path):
    archive = packaged(project)
    meta = json.loads(subprocess.run([sys.executable, "-c", "import tarfile,sys;t=tarfile.open(sys.argv[1]);"
                                      "print(t.extractfile('release.json').read().decode())", str(archive)],
                                     capture_output=True, text=True).stdout)
    assert meta["module"] == "edge" and not meta["dirty"] and meta["revision"]
    t = server(tmp_path)
    ctx = ctx_for(project, t)
    assert release.release(ctx, "edge", archive) == 0
    unit = f"{ROOT}/shop/staging/edge/edge"
    rid = meta["id"]
    assert t.readlink(f"{unit}/current") == f"{unit}/releases/{rid}"
    recipe = t.read(f"{unit}/releases/{rid}/Dockerfile").decode()
    assert "FROM fixture/run:7" in recipe and "COPY out/app.bin /app.bin" in recipe and "${HOME}" in recipe
    env = f"{ROOT}/shop/staging/stack/env/edge.env"
    assert t.read(env) == b"SHARED=1\nWHERE=staging\n" and t.modes[env] == "600"
    assert t.read(f"{unit}/runtime/credentials/gateway.p12") == b"\x00binary-credential"
    compose = json.loads(t.read(f"{ROOT}/shop/staging/stack/compose.yml"))
    svc = compose["services"]["edge"]
    assert compose["name"] == "shop-staging" and svc["container_name"] == "shop-staging-edge"
    assert svc["image"] == f"shop-staging-edge:{rid}" and svc["ports"] == ["18080:9000"]
    assert f"{unit}/runtime/credentials/gateway.p12:/certs/gateway.p12:ro" in svc["volumes"]
    assert svc["environment"]["GATEWAY_CERT"] == "/certs/gateway.p12" and "gateway.p12" not in json.dumps(svc.get("env_file"))
    assert compose["networks"]["default"] == {"name": "shop-staging", "external": True}
    ran = [e[1] for e in t.log if e[0] == "exec"]
    assert ("eng", "network", "create", "shop-staging") in ran
    assert ("eng-compose", "-f", f"{ROOT}/shop/staging/stack/compose.yml", "up", "-d", "edge") in ran
    assert json.loads(t.read(f"{ROOT}/shop/.stack-kit-project"))["project"] == "shop"
    foreign_intact(t)
    t.log.clear()
    assert release.release(ctx, "edge", archive) == 0
    assert t.changes() == [], t.changes()
    assert not [e for e in t.log if e[0] == "exec" and "build" in e[1]]


def test_prune_keeps_the_declared_number_and_never_current(project, tmp_path):
    t = server(tmp_path)
    ctx = ctx_for(project, t)
    ids = []
    for n in range(3):
        if n:
            commit(project, f"v{n + 1}\n")
        archive = packaged(project)
        ids.append(archive.name[len("edge-"):-len(".tgz")])
        assert release.release(ctx, "edge", archive) == 0
    assert release.releases_of(ctx, running.find(ctx, ["edge"])[0]) == [ids[2], ids[1]]
    assert release.rollback(ctx, ["edge"]) == 0
    assert running.current_release(ctx, running.find(ctx, ["edge"])[0]) == ids[1]


def test_an_unhealthy_release_rolls_back_where_the_environment_declares_it(project, tmp_path):
    t = server(tmp_path)
    ctx = ctx_for(project, t)
    first = packaged(project)
    assert release.release(ctx, "edge", first) == 0
    commit(project, "v2\n")
    second = packaged(project)
    st = fake_server._load(fake_server.state_file(tmp_path / "server.json"))
    st["health"] = {"edge": "unhealthy"}
    fake_server.state_file(tmp_path / "server.json").write_text(json.dumps(st), encoding="utf-8")
    with pytest.raises(DeliveryError) as e:
        release.release(ctx, "edge", second)
    assert e.value.code == 6
    edge = running.find(ctx, ["edge"])[0]
    assert running.current_release(ctx, edge) == first.name[len("edge-"):-len(".tgz")]


def test_a_dirty_package_is_refused_where_a_clean_commit_is_required(project, tmp_path):
    (project / "apps" / "edge" / "src" / "main.code").write_text("uncommitted\n", encoding="utf-8")
    archive = packaged(project)
    assert archive.name.endswith("-dirty.tgz")
    with pytest.raises(DeliveryError) as e:
        release.release(ctx_for(project, server(tmp_path)), "edge", archive)
    assert e.value.code == 5
    assert release.release(ctx_for(project, server(tmp_path), "dev"), "edge", archive) == 0


def test_an_archive_without_provenance_is_refused(project, tmp_path):
    import tarfile

    bare = tmp_path / "edge-bare.tgz"
    with tarfile.open(bare, "w:gz") as tar:
        tar.add(str(project / "apps" / "edge" / "src" / "main.code"), arcname="edge/main.code")
    from lib.package import PackageError

    with pytest.raises(PackageError, match="provenance"):
        release.release(ctx_for(project, server(tmp_path)), "edge", bare)


# ── the shared root and the marker ───────────────────────────────────────────

def test_an_unmarked_non_empty_project_directory_is_never_claimed(project, tmp_path):
    t = server(tmp_path)
    t.write(f"{ROOT}/shop/somebody/file", b"x")
    with pytest.raises(DeliveryError) as e:
        tree.init(ctx_for(project, t))
    assert e.value.code == 3
    assert not t.exists(f"{ROOT}/shop/.stack-kit-project")
    with pytest.raises(DeliveryError) as e:
        manage.nuke(ctx_for(project, t))
    assert e.value.code == 3 and t.read(f"{ROOT}/shop/somebody/file") == b"x"


def test_another_projects_marker_is_refused(project, tmp_path):
    t = server(tmp_path)
    t.write(f"{ROOT}/shop/.stack-kit-project", json.dumps({"project": "other"}).encode())
    with pytest.raises(DeliveryError, match="belongs to project 'other'"):
        tree.init(ctx_for(project, t))


def test_init_is_idempotent_and_verify_reports_drift_without_deleting(project, tmp_path):
    t = server(tmp_path)
    ctx = ctx_for(project, t)
    tree.init(ctx)
    t.log.clear()
    tree.init(ctx)
    assert t.changes() == []
    assert tree.verify(ctx) == []
    t.write(f"{ROOT}/shop/staging/stray.txt", b"?")
    assert tree.verify(ctx) == [f"undeclared: {ROOT}/shop/staging/stray.txt (reported, never deleted)"]
    assert t.exists(f"{ROOT}/shop/staging/stray.txt")
    foreign_intact(t)


def test_nuke_stays_inside_the_environment(project, tmp_path):
    t = server(tmp_path)
    ctx = ctx_for(project, t)
    release.release(ctx, "edge", packaged(project))
    tree.init(ctx_for(project, t, "dev"))
    assert manage.nuke(ctx) == 0
    assert not t.exists(f"{ROOT}/shop/staging") and t.exists(f"{ROOT}/shop/dev")
    assert t.exists(f"{ROOT}/shop/.stack-kit-project")
    foreign_intact(t)


def test_no_remove_can_reach_outside_the_environment(project, tmp_path):
    from lib.delivery.transport import TransportError

    t = server(tmp_path)
    ctx = ctx_for(project, t)
    for path in (ROOT, f"{ROOT}/backend", f"{ROOT}/shop", f"{ROOT}/shop/staging"):
        with pytest.raises(TransportError, match="refused"):
            ctx.transport.remove(path)


# ── ports ────────────────────────────────────────────────────────────────────

def test_a_port_another_project_publishes_is_refused_and_many_unrelated_are_not(project, tmp_path):
    busy = {str(p): f"proj{p}" for p in range(20000, 20200)}
    t = server(tmp_path, foreign={**busy, "18080": "someone-else"})
    with pytest.raises(DeliveryError, match="published by compose project 'someone-else'") as e:
        preflight.ports(ctx_for(project, t))
    assert e.value.code == 4
    t = server(tmp_path / "b", foreign=busy, listening=[22, 80, 443, 5432])
    assert preflight.ports(ctx_for(project, t)) == []
    t = server(tmp_path / "c", listening=[18080])
    with pytest.raises(DeliveryError, match="outside the container engine"):
        preflight.ports(ctx_for(project, t))


# ── migrate-layout ───────────────────────────────────────────────────────────

def test_migrate_layout_plans_then_applies_only_the_declared_paths(tmp_path, monkeypatch):
    root = host(tmp_path, target_extra={"legacyLayout": {
        "environment": "staging", "units": {"edge": "{root}/backend/shop-edge"},
        "places": {"infra": "{root}/infra/shop"}}})
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    t = server(tmp_path)
    t.write(f"{ROOT}/backend/shop-edge/runtime/app.cfg", b"old")
    t.write(f"{ROOT}/infra/shop/compose.yml", b"infra")
    t.log.clear()
    ctx = ctx_for(root, t)
    moves = legacy_layout.plan(ctx)
    assert [(m.src, m.dst, m.state) for m in moves] == [
        (f"{ROOT}/backend/shop-edge", f"{ROOT}/shop/staging/edge/edge", "planned"),
        (f"{ROOT}/infra/shop", f"{ROOT}/shop/staging/infra", "planned")]
    assert t.changes() == []
    legacy_layout.apply(ctx, moves)
    assert t.read(f"{ROOT}/shop/staging/edge/edge/runtime/app.cfg") == b"old"
    assert not t.exists(f"{ROOT}/backend/shop-edge") and t.read(f"{ROOT}/backend/other-api/app.jar")
    assert t.read(f"{ROOT}/infra/other/compose.yml")


def test_migrate_layout_refuses_a_shared_folder_of_the_root(tmp_path, monkeypatch):
    root = host(tmp_path, target_extra={"legacyLayout": {"environment": "staging", "units": {"edge": "{root}/backend"}}})
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    with pytest.raises(DeliveryError, match="direct child of the shared root"):
        legacy_layout.plan(ctx_for(root, server(tmp_path)))


def test_migrate_layout_refuses_a_source_another_project_marked(tmp_path, monkeypatch):
    root = host(tmp_path, target_extra={"legacyLayout": {"environment": "staging", "units": {"edge": "{root}/backend/x"}}})
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    t = server(tmp_path)
    t.write(f"{ROOT}/backend/x/.stack-kit-project", json.dumps({"project": "other"}).encode())
    moves = legacy_layout.plan(ctx_for(root, t))
    assert moves[0].state.startswith("refused") and "another project's" in moves[0].state
    with pytest.raises(DeliveryError):
        legacy_layout.apply(ctx_for(root, t), moves)
    assert t.exists(f"{ROOT}/backend/x/.stack-kit-project")


def test_the_target_compose_invocation_is_the_declared_one(project, tmp_path):
    t = server(tmp_path)
    data = json.loads((project / "ops" / "deploy" / "targets.json").read_text())
    data["targets"]["box"]["compose"] = ["standalone-compose"]
    (project / "ops" / "deploy" / "targets.json").write_text(json.dumps(data), encoding="utf-8")
    ctx = ctx_for(project, t)
    assert ctx.compose("ps")[:1] == ["standalone-compose"]
    t.responses = lambda argv, cwd, env: Result(127, "", "not found") if argv[0] == "standalone-compose" else Result(0, "1")
    with pytest.raises(DeliveryError, match="targets.box.compose") as e:
        preflight.runtime(ctx)
    assert e.value.code == 4
