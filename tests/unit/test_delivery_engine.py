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

from delivery_host import FOREIGN, ROOT, commit, ctx_for, host, manifest_of, packaged, server  # noqa: E402,F401


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = host(tmp_path)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
    return root


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


# ── drift and reconciliation (OpenGitOps: continuously reconciled) ─────────────

def test_verify_names_each_drift_read_only_and_a_deploy_undoes_it(project, tmp_path):
    t = server(tmp_path)
    ctx = ctx_for(project, t)
    archive = packaged(project)
    release.release(ctx, "edge", archive)
    assert tree.verify(ctx) == []
    env = f"{ROOT}/shop/staging/stack/env/edge.env"
    t.write(env, b"WHERE=edited-on-the-host\n", "600")
    st = fake_server._load(fake_server.state_file(tmp_path / "server.json"))
    st["containers"] = {}
    fake_server.state_file(tmp_path / "server.json").write_text(json.dumps(st), encoding="utf-8")
    t.log.clear()
    drift = tree.verify(ctx)
    assert t.changes() == [], "verify changed the host"
    assert any("edge: env file differs" in d for d in drift), drift
    assert any("edge: runs nothing, its current release says shop-staging-edge:" in d for d in drift), drift
    assert not any("edited-on-the-host" in d for d in drift), "a value is never printed"
    release.release(ctx, "edge", archive)
    assert tree.verify(ctx) == []


# ── what a release must pass (ADR-001 amendment 14) ───────────────────────────

def test_a_release_image_runs_unprivileged_with_a_health_probe(project, tmp_path):
    from lib import package

    meta, trees = package.read(packaged(project))
    assert meta["module"] == "edge"
    recipe = trees["edge"]["Dockerfile"].decode()
    assert "FROM fixture/run:7" in recipe


def test_a_floating_image_is_refused_and_a_digest_where_declared(project, tmp_path, monkeypatch):
    from lib.delivery.checks import image_tag

    assert image_tag("minio/minio") and image_tag("minio/minio:latest")
    assert image_tag("minio/minio:RELEASE.2024-01-01") is None
    assert image_tag("minio/minio:RELEASE.2024-01-01", require_digest=True)
    assert image_tag("minio/minio@sha256:" + "a" * 64, require_digest=True) is None
    m = manifest_of(project)
    m["stack"] = {"services": {"store": {"image": "minio/minio:latest", "tier": "edge"}}}
    (project / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")
    commit(project, "with a stack service\n")
    with pytest.raises(DeliveryError, match="`latest` floats") as e:
        release.release(ctx_for(project, server(tmp_path)), "edge", packaged(project))
    assert e.value.code == 5
