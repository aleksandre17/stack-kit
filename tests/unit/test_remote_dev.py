"""Remote dev (ADR-001 amendment 13): the index + tar sync end to end through a local directory
standing in for the server (no ssh, the same code path), its one exclude list, the declared
reactions, `dev up` / `down` against the recorded server, and a watch that survives a lost
connection -- all through the fixture driver the kit does not ship."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from lib import identity
from lib.delivery import dev, running, sync
from lib.delivery.transport import LocalTransport, TransportError
from delivery_host import ROOT, ctx_for, host, server

WS = f"{ROOT}/shop/dev/edge/edge/workspace"


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = host(tmp_path)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
    return root


def _edge(ctx):
    return running.find(ctx, ["edge"])[0]


def _touch(path: Path, text: str, bump: int = 5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    t = time.time() + bump
    os.utime(path, (t, t))


def test_the_tar_fallback_syncs_incrementally_and_deletes_only_inside_the_workspace(project, tmp_path):
    remote = tmp_path / "remote"
    t = LocalTransport(remote, confine=f"{ROOT}/shop/dev")
    ctx = ctx_for(project, server(tmp_path), "dev")
    edge = _edge(ctx)
    src = project / "apps" / "edge"
    _touch(src / "src" / "extra.code", "x")
    _touch(src / "app.cfg", "cfg")
    _touch(src / ".env.local", "SECRET=1")
    _touch(src / "out" / "built.bin", "generated")
    _touch(src / "debug.log", "log")
    _touch(src / "keys" / "deploy.pem", "-----")
    pats = sync.excludes(edge, src)
    cache = tmp_path / "cache.json"
    first = sync.sync(t, src, WS, pats, cache=cache)
    assert first.way == "index"
    assert sorted(first.sent) == [".gitignore", "app.cfg", "src/extra.code", "src/main.code"]
    ws = remote / WS.lstrip("/")
    assert not (ws / ".env.local").exists() and not (ws / "out").exists() and not (ws / "keys").exists()
    (ws / "node_deps").mkdir()
    (ws / "node_deps" / "made-on-server").write_text("kept")  # what the dev container makes is not ours to delete
    pats.append("node_deps/")
    again = sync.sync(t, src, WS, pats, cache=cache)
    assert again.sent == [] and again.deleted == [] and again.unchanged == 4
    _touch(src / "app.cfg", "cfg2", bump=20)
    (src / "src" / "extra.code").unlink()
    third = sync.sync(t, src, WS, pats, cache=cache)
    assert third.sent == ["app.cfg"] and third.deleted == ["src/extra.code"]
    assert (ws / "app.cfg").read_text() == "cfg2" and not (ws / "src" / "extra.code").exists()
    assert (ws / "node_deps" / "made-on-server").read_text() == "kept"
    assert all(str(e[1]).startswith(WS) for e in t.log if e[0] == "remove")
    with pytest.raises(TransportError, match="refused"):
        t.remove_many(WS, ["../escape"])


def test_one_exclude_list_never_ships_secrets(project):
    ctx = ctx_for(project, server(project.parent), "dev")
    pats = sync.excludes(_edge(ctx), project / "apps" / "edge")
    for secret in (".env", ".env.prod", "api.env", "gateway.p12", "a/b/service-account-x.json", "id_ed25519", "x.key"):
        assert sync.excluded(secret, pats), secret
    assert sync.excluded("out/app.bin", pats) and sync.excluded("debug.log", pats)
    assert not sync.excluded("src/main.code", pats)


def test_reactions_are_the_drivers_declared_ones(project):
    rules = ctx_for(project, server(project.parent), "dev")
    rules = _edge(rules).dev["reactions"]
    assert sync.reaction(["src/main.code"], rules) == "rebuild"
    assert sync.reaction(["app.cfg"], rules) == "restart"
    assert sync.reaction(["README.md"], rules) == "hot-reload"
    assert sync.reaction(["README.md", "app.cfg", "src/x.code"], rules) == "rebuild"


def test_dev_up_runs_the_workspace_and_down_returns_to_nothing(project, tmp_path):
    t = server(tmp_path)
    ctx = ctx_for(project, t, "dev")
    assert dev.up(ctx, ["edge"]) == 0
    compose = json.loads(t.read(f"{ROOT}/shop/dev/stack/compose.yml"))
    svc = compose["services"]["edge"]
    assert svc["image"] == "fixture/dev:7" and svc["command"] == ["serve"] and svc["ports"] == ["18081:9000"]
    assert f"{WS}:/workspace" in svc["volumes"] and "shop-dev-edge-deps:/deps" in svc["volumes"]
    assert compose["volumes"] == {"shop-dev-edge-deps": {"name": "shop-dev-edge-deps"}}
    assert t.read(f"{WS}/src/main.code").strip() == b"v1" and not t.exists(f"{WS}/out")
    assert dev.status(ctx, ["edge"])[0].split()[2] == "workspace"
    assert dev.down(ctx, ["edge"]) == 0
    assert "edge" not in json.loads(t.read(f"{ROOT}/shop/dev/stack/compose.yml"))["services"]
    with pytest.raises(Exception, match="workspace environment"):
        dev.up(ctx_for(project, t, "staging"), ["edge"])


def test_watch_syncs_reacts_and_survives_a_lost_connection(project, tmp_path):
    t = server(tmp_path)
    ctx = ctx_for(project, t, "dev")
    dev.up(ctx, ["edge"])
    src = project / "apps" / "edge"
    ticks = {"n": 0}
    real_index = t.index

    def sleep(_s):
        ticks["n"] += 1
        if ticks["n"] == 2:
            _touch(src / "src" / "main.code", "v2\n", bump=30)
        if ticks["n"] == 6:
            def broken(path):
                t.index = real_index
                raise TransportError("h.example: unreachable: connection reset")
            t.index = broken
            _touch(src / "app.cfg", "while away", bump=40)
    ctx.sleep = sleep
    lines = []
    ctx.out = lines.append
    reconnects = []
    assert dev.watch(ctx, ["edge"], poll=0, stop=lambda: ticks["n"] > 14, reconnect=lambda: reconnects.append(1)) == 0
    assert t.read(f"{WS}/src/main.code").strip() == b"v2" and t.read(f"{WS}/app.cfg") == b"while away"
    ran = [e[1] for e in t.log if e[0] == "exec"]
    assert any(r[-3:] == ("edge", "compile") or r[-2:] == ("edge", "compile") for r in ran), ran
    assert reconnects and any("full sync done" in ln for ln in lines), lines


def test_tunnel_forwards_the_declared_dev_ports(project, tmp_path):
    t = server(tmp_path)
    assert dev.tunnel(ctx_for(project, t, "dev"), ["edge"]) == 0
    assert ("tunnel", ((18081, 18081),)) in t.log


def test_a_node_spa_dev_server_runs_the_script_its_module_names():
    # A host whose `start` script does what a container cannot (a local HTTPS certificate) names the
    # script remote dev runs; the default stays `start`.
    from lib.delivery.model import module_services

    def command(node):
        manifest = {"modules": {"web": {"type": "node-spa", "role": "ui", "path": "web", **({"node": node} if node else {})}}}
        return " ".join(module_services(manifest, "web")[0].dev["command"])

    assert "npm run start -- --host" in command(None)
    assert "npm run start:container -- --host" in command({"scripts": {"dev": "start:container"}})


def test_dev_down_hands_a_releases_secrets_to_its_runtime_before_it_comes_back_up(project, tmp_path, monkeypatch):
    # Found by a re-audit: a secret made while the workspace ran was the deploy user's, and the release
    # it returned to ran as another uid and could not read it.
    t = server(tmp_path)
    ctx = ctx_for(project, t, "dev")
    assert dev.up(ctx, ["edge"]) == 0
    order = []
    monkeypatch.setattr(running, "current_release", lambda c, s: "r1")
    monkeypatch.setattr(running, "hand_over_secrets", lambda c, svc, rid: order.append(("hand", [s.id for s in svc], rid)))
    monkeypatch.setattr(running, "up", lambda c, ids: order.append(("up", ids)))
    assert dev.down(ctx, ["edge"]) == 0
    assert order == [("hand", ["edge"], "r1"), ("up", ["edge"])]
