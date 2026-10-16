"""A UI module's release is an image built from its driver's recipe (ADR-001 amendment 18): the
pinned unprivileged nginx with the built app and its rendered server config COPYed in -- one recipe
for the local stack, a dev release and prod. Proven with the golden host on a recording transport;
nothing here has built a real image."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import WORKING_ROOT
from lib import identity, package
from lib.project_context import ProjectContext

TARGET = {"runtime": "docker-compose", "host": "h.example.test", "user": "deploy", "root": "/srv/apps",
          "ssh": {"knownHosts": "ops/deploy/known_hosts"}}
HEALTH = {"health_interval": "15s", "health_retries": "5", "health_start": "60s"}
TWO = {"schema": 1, "defaults": {"dev": "stage", "prod": "live"},
       "targets": {"stage": {**TARGET, "host": "stage.example.test"}, "live": TARGET}}


def _commit(root: Path, message: str) -> None:
    git = ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
    if not (root / ".git").exists():
        subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", message], check=True)


def _ui_host(tmp_path: Path, monkeypatch) -> tuple[Path, dict, str]:
    """The golden host with deploy targets, its UI module proxying /api/ to the api, committed."""
    root = tmp_path / "ui-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    (root / "ops" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / "ops" / "deploy" / "known_hosts").write_text("# pinned\n", encoding="utf-8")
    (root / "ops" / "deploy" / "targets.json").write_text(json.dumps(TWO), encoding="utf-8")
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["deploy"] = {"targets": "ops/deploy/targets.json"}
    web = next(m for m, c in manifest["modules"].items() if c["type"] == "node-vite")
    manifest["modules"][web]["container"] = {"proxy": {"api": "api"}}
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    dist = root / manifest["modules"][web]["path"] / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
    (dist / "assets" / "app-1a2b3c4d.js").write_text("fetch('/api/x')", encoding="utf-8")
    _commit(root, "c")
    return root, manifest, web


def test_a_ui_release_is_an_image_built_from_its_drivers_recipe_hardened_and_proxied(tmp_path, monkeypatch):
    root, manifest, web = _ui_host(tmp_path, monkeypatch)
    _, trees = package.read(package.pack(root, manifest, web))
    (svc,) = trees
    conf = trees[svc]["server.conf"].decode()
    assert "location /api/ {" in conf and "proxy_pass http://api:8080;" in conf and "root /usr/share/nginx/html;" in conf
    assert 'X-Content-Type-Options "nosniff"' in conf and "Referrer-Policy" in conf and "gzip on;" in conf
    assert "immutable" in conf and 'Cache-Control "no-cache"' in conf and "listen 8080;" in conf
    recipe = trees[svc]["Dockerfile"].decode()
    assert "FROM nginxinc/nginx-unprivileged:1.27-alpine" in recipe and "\nUSER nginx\n" in recipe
    assert "COPY dist/ /usr/share/nginx/html/" in recipe and "COPY server.conf /etc/nginx/conf.d/default.conf" in recipe
    assert "HEALTHCHECK" in recipe and "http://127.0.0.1:8080/healthz" in recipe and "EXPOSE 8080" in recipe
    dist = root / manifest["modules"][web]["path"] / "dist"
    (dist / "assets" / "app-1a2b3c4d.js").write_text("fetch('http://10.20.30.40:8080/api')", encoding="utf-8")
    with pytest.raises(package.PackageError, match="10.20.30.40"):
        package.pack(root, manifest, web)
    (dist / "assets" / "app-1a2b3c4d.js").write_text("fetch('/api/x')", encoding="utf-8")
    # The Angular application builder writes dist/<name>/browser/: a root without index.html is refused.
    (dist / "shop" / "browser").mkdir(parents=True)
    (dist / "index.html").rename(dist / "shop" / "browser" / "index.html")
    with pytest.raises(package.PackageError, match="dist/shop/browser"):
        package.pack(root, manifest, web)
    manifest["modules"][web]["container"]["serve"] = "dist/shop/browser"
    _, trees = package.read(package.pack(root, manifest, web))
    assert "COPY dist/shop/browser/ /usr/share/nginx/html/" in trees[svc]["Dockerfile"].decode()
    # The recipe and the config it COPYs are both rendered into the host, each under its sources' header,
    # each the bytes the release ships.
    from lib import projections

    projections.write(root, manifest)
    for name, inside in (("server.conf", "location /api/ {"), ("Dockerfile", "COPY server.conf ")):
        data = (root / f"ops/containers/{web}/{name}").read_bytes()
        first, rest = data.decode("utf-8").split("\n", 1)
        assert first.startswith("# generated by ") and inside in rest
        assert projections.body(data) == trees[svc][name]


def test_a_ui_release_ships_builds_and_rolls_back_like_any_build_service(tmp_path, monkeypatch):
    from delivery_host import server
    from lib.delivery import release, running
    from lib.delivery.context import open_delivery

    root, manifest, web = _ui_host(tmp_path, monkeypatch)
    first = package.pack(root, manifest, web)
    t = server(tmp_path / "srv")
    ctx = open_delivery(root, manifest, environment="dev", transport=t, out=lambda s: None, sleep=lambda s: None)
    assert release.release(ctx, web, first) == 0
    (svc,) = running.find(ctx, [web])
    assert svc.kind == "build"
    rid1 = running.current_release(ctx, svc)
    stack_file = f"{ctx.places.of('stack')}/compose.yml"
    doc = json.loads(t.read(stack_file))["services"][svc.id]
    assert doc["image"].endswith(f"-{svc.id}:{rid1}") and doc["build"]["context"].endswith(f"/releases/{rid1}")
    assert not [v for v in doc.get("volumes") or [] if "/releases/" in v]  # nothing of the release is mounted
    unit = ctx.places.unit(svc)
    assert t.read(f"{unit['releases']}/{rid1}/server.conf") and t.read(f"{unit['releases']}/{rid1}/Dockerfile")
    assert any(e[0] == "exec" and "build" in e[1] and svc.id in e[1] for e in t.log)
    (root / manifest["modules"][web]["path"] / "v2.txt").write_text("2", encoding="utf-8")
    _commit(root, "v2")
    assert release.release(ctx, web, package.pack(root, manifest, web)) == 0
    assert running.current_release(ctx, svc) != rid1
    assert release.rollback(ctx, [web]) == 0
    assert running.current_release(ctx, svc) == rid1
    assert json.loads(t.read(stack_file))["services"][svc.id]["image"].endswith(f":{rid1}")


def test_the_local_stack_builds_the_ui_from_the_same_recipe(tmp_path, monkeypatch):
    from compose.manifest_compose import build_manifest_stack_services, load_compose_catalog
    from lib.cli.verbs.project import stage_releases

    root, manifest, web = _ui_host(tmp_path, monkeypatch)
    ctx = ProjectContext(root=root, manifest=manifest)
    compose_dir = root / "ops" / "compose" / "stack"
    fmt = {"compose_slug": "g", "api_service": "g-api", "app_service": "g-app", "worker_service": "g-worker",
           "worker_image": "g-worker", "network_key": "g-net", "network_name": "g-net"}
    from lib.compose_identity import resolve_module_service_name
    from lib.delivery.model import module_services

    (sid,) = [s.id for s in module_services(manifest, web)]
    local, api = (resolve_module_service_name(m, manifest, root) for m in (web, "api"))
    for profile in ("dev", "prod"):
        body = build_manifest_stack_services(ctx=ctx, profile=profile, compose_dir=compose_dir, fmt_global=fmt,
                                             fmt_extra=HEALTH, features={}, compose_cat=load_compose_catalog())
        block = body[body.index(f"  {local}:\n"):]
        block = block[:block.find("\n  ", block.index("restart:"))]
        assert f"context: ../../../.stack-kit/local/{web}/{sid}\n" in block and "dockerfile: Dockerfile" in block
        assert ':8080"' in block and "target: " not in block
        # the proxied api, under the service id its rendered config names (its name on a target's stack)
        assert f"links:\n      - {api}:api\n" in block
    assert stage_releases(ctx) == 0
    staged = root / ".stack-kit" / "local" / web / sid
    _, trees = package.read(package.pack(root, manifest, web))
    assert (staged / "Dockerfile").read_bytes() == trees[sid]["Dockerfile"]
    assert (staged / "server.conf").read_bytes() == trees[sid]["server.conf"]
    assert (staged / "dist" / "index.html").is_file()


def test_a_retired_static_declaration_is_refused_naming_the_recipe():
    from lib.delivery.model import ModelError, module_services

    manifest = {"modules": {"web": {"type": "node-spa", "role": "ui", "path": "w",
                                    "container": {"static": {"image": "nginx:1"}}}}}
    with pytest.raises(ModelError, match="retired in 2.4.0"):
        module_services(manifest, "web")
