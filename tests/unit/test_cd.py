"""CD is generated from the manifest and its deploy targets (ADR-001 amendment 11): build once,
promote the same bytes dev -> prod, every step the command a developer runs. Nothing here has run on
GitHub; the workflow's shape and its commands are what is proven."""
from __future__ import annotations

import http.server
import json
import shutil
import tarfile
import threading
from pathlib import Path

import pytest

from conftest import WORKING_ROOT
from lib import ci_gen, identity, package, targets
from lib.project_context import ProjectContext

TARGET = {"runtime": "docker-compose", "host": "h.example.test", "user": "deploy", "root": "/srv/apps",
          "ssh": {"knownHosts": "ops/deploy/known_hosts"}}


def _host(tmp_path: Path, document: dict | None) -> Path:
    root = tmp_path / "cd-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    if document is not None:
        (root / "ops" / "deploy").mkdir(parents=True, exist_ok=True)
        (root / "ops" / "deploy" / "known_hosts").write_text("# pinned\n", encoding="utf-8")
        (root / "ops" / "deploy" / "targets.json").write_text(json.dumps(document), encoding="utf-8")
        mf = root / identity.MANIFEST_FILENAME
        manifest = json.loads(mf.read_text(encoding="utf-8"))
        manifest["deploy"] = {"targets": "ops/deploy/targets.json"}
        mf.write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _render(root: Path) -> str:
    return ci_gen.render(ProjectContext.discover(root))


def _job(text: str, name: str) -> str:
    start = text.index(f"\n  {name}:\n")
    nxt = text.find("\n  ", start + len(name) + 4)
    while nxt != -1 and text[nxt + 3] == " ":
        nxt = text.find("\n  ", nxt + 1)
    return text[start: nxt if nxt != -1 else len(text)]


TWO = {"schema": 1, "defaults": {"dev": "stage", "prod": "live"},
       "targets": {"stage": {**TARGET, "host": "stage.example.test"}, "live": TARGET}}


def test_build_once_and_promote_the_same_bytes_dev_then_prod(tmp_path):
    text = _render(_host(tmp_path, TWO))
    dev, prod = _job(text, "deploy-dev"), _job(text, "deploy-prod")
    assert "needs: [api, search, worker, web, svc]" in dev and "needs: [deploy-dev]" in prod
    assert "environment: 'dev'" in dev and "environment: 'prod'" in prod  # GitHub Environments gate them
    assert "group: 'deploy-live-prod'" in prod and "cancel-in-progress: false" in prod
    assert "inputs.environment == 'prod'" in prod and "workflow_dispatch:" in text and "type: choice" in text
    for job in (dev, prod):
        assert "name: package-api" in job
        assert not any(f" mod api {s}'" in job for s in ("build", "test", "lint")), "a deploy job builds"
    # CD runs the same CLI an operator runs -- the packaged archive, never its own deploy logic
    assert "'pwsh tools/stack-kit.ps1 deploy api --env prod --target live --yes --artifact $(ls .stack-kit/artifacts/api-*.tgz)'" in prod
    assert "'pwsh tools/stack-kit.ps1 targets --health --target live --env prod'" in prod
    assert "'pwsh tools/stack-kit.ps1 targets --verify --target live --env prod'" in prod
    assert "secrets.STACK_KIT_SSH_KEY_LIVE" in prod and "ssh-add -" in prod
    assert "secrets.STACK_KIT_ENV_API_PROD" in prod and "umask 077" in prod
    assert "name: stack-kit-runs-deploy-prod" in prod and "if: always()" in prod


def test_every_package_carries_an_sbom_and_a_provenance_attestation(tmp_path):
    api = _job(_render(_host(tmp_path, TWO)), "api")
    assert "pwsh tools/stack-kit.ps1 package api" in api
    assert "anchore/sbom-action@" in api and "actions/attest-build-provenance@" in api
    assert "id-token: write" in api and "attestations: write" in api
    assert "subject-path: '.stack-kit/artifacts/api-*.tgz'" in api


def test_every_packaging_driver_is_deployed_by_the_kit_release(tmp_path):
    text = _render(_host(tmp_path, TWO))
    for mid in ("api", "search", "worker", "web", "svc"):
        assert f" deploy {mid} --env prod --target live --yes" in text, mid


@pytest.mark.parametrize("document,reason", [
    (None, "no deploy targets are declared"),
    ({"schema": 1, "defaults": {"dev": "stage", "prod": "live"},
      "targets": {"stage": TARGET, "live": {"runtime": "iis", "pending": "IIS delivery is not built"}}},
     "target live (prod) is pending: IIS delivery is not built"),
    ({"schema": 1, "defaults": {"prod": "live"}, "targets": {"live": TARGET}}, "no `defaults.dev` target"),
])
def test_without_reachable_dev_and_prod_targets_it_is_ci_only_and_says_why(tmp_path, document, reason):
    text = _render(_host(tmp_path, document))
    assert "# CD: none -- CI and packaging only, because:" in text and reason in text
    assert "deploy-dev:" not in text and "deploy-prod:" not in text


# ── the commands behind the steps ────────────────────────────────────────────

def _committed(tmp_path: Path, name: str) -> tuple[Path, dict]:
    import subprocess

    root = tmp_path / name
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    git = ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "c"], check=True)
    return root, json.loads((root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))


def test_a_package_is_one_archive_per_commit_with_its_provenance_and_recipe(tmp_path):
    root, manifest = _committed(tmp_path, "pkg")
    mid = next(m for m, c in manifest["modules"].items() if c["type"] == "java-boot")
    libs = root / manifest["modules"][mid]["path"] / "build" / "libs"
    libs.mkdir(parents=True)
    (libs / "app-1.0-boot.jar").write_bytes(b"JAR-BYTES")
    (libs / "app-1.0-plain.jar").write_bytes(b"PLAIN")
    archive = package.pack(root, manifest, mid)
    assert archive.name.startswith(f"{mid}-") and archive.with_suffix(".tgz.sha256").is_file()
    meta, trees = package.read(archive)
    assert meta["module"] == mid and meta["dirty"] is False and meta["commit"]
    (svc,) = trees
    assert trees[svc]["build/libs/app-1.0-boot.jar"] == b"JAR-BYTES"
    recipe = trees[svc]["Dockerfile"].decode()
    assert "COPY --chown=10001:10001 build/libs/app-1.0-boot.jar /app/app.jar" in recipe and "eclipse-temurin:17-jre" in recipe
    archive.write_bytes(archive.read_bytes() + b"x")
    with pytest.raises(package.PackageError, match="sha256 differs"):
        package.read(archive)


def test_an_archive_member_that_escapes_its_service_is_refused(tmp_path):
    evil = tmp_path / "evil.tgz"
    payload = tmp_path / "x.txt"
    payload.write_text("x", encoding="utf-8")
    with tarfile.open(evil, "w:gz") as tar:
        tar.add(payload, arcname="api/../../outside.txt")
    with pytest.raises(package.PackageError, match="escapes its service"):
        package.read(evil)


def test_a_driver_without_a_package_step_names_it():
    manifest = {"modules": {"x": {"type": "no-such-driver", "path": "x"}}}
    with pytest.raises(package.PackageError, match="declares no package step"):
        package.plan(WORKING_ROOT, manifest, "x")


class _Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200 if self.path == "/ok" else 503)
        self.end_headers()

    def log_message(self, *a):
        pass


def test_health_passes_the_declared_endpoints_and_names_a_failing_one(capsys):
    server = http.server.HTTPServer(("127.0.0.1", 0), _Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        urls = {"api": f"{base}/ok"}
        assert targets.check_health_urls(urls, attempts=1, pause=0.01) == []
        urls["web"] = f"{base}/down"
        failed = targets.check_health_urls(urls, attempts=2, pause=0.01)
        assert len(failed) == 1 and failed[0].startswith("web ")
    finally:
        server.shutdown()


def test_a_module_whose_driver_does_not_release_through_the_kit_gets_its_package_and_no_deploy(tmp_path, monkeypatch):
    root = _host(tmp_path, TWO)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    reg = root / "ops" / "drivers"
    reg.mkdir(parents=True)
    (reg / "registry.json").write_text(json.dumps({"own-pack": {
        "label": "packages, releases by hand", "roles": ["api"], "commands": {"build": "b.py"},
        "package": {"command": "build", "artifacts": ["out/**"]}, "delivery": {"release": {"pending": "by hand"}}}}),
        encoding="utf-8")
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    (root / "apps" / "edge").mkdir(parents=True)
    manifest["drivers"] = {"registry": "ops/drivers/registry.json"}
    manifest["modules"]["edge"] = {"type": "own-pack", "role": "api", "path": "apps/edge", "secretsModule": "edge"}
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    text = _render(root)
    assert "edge (own-pack): its release is pending -- by hand" in text
    assert "pwsh tools/stack-kit.ps1 package edge" in _job(text, "edge")
    assert " deploy edge " not in text


def test_a_static_release_is_hardened_and_proxies_its_api_same_origin(tmp_path, monkeypatch):
    root, manifest = _committed(tmp_path, "spa")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    web = next(m for m, c in manifest["modules"].items() if c["type"] == "node-vite")
    manifest["modules"][web]["container"] = {"proxy": {"api": "api"}}
    dist = root / manifest["modules"][web]["path"] / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
    (dist / "assets" / "app-1a2b3c4d.js").write_text("fetch('/api/x')", encoding="utf-8")
    _, trees = package.read(package.pack(root, manifest, web))
    (svc,) = trees
    conf = trees[svc][".stack-kit/static.conf"].decode()
    assert "location /api/ {" in conf and "proxy_pass http://api:8080;" in conf
    assert 'X-Content-Type-Options "nosniff"' in conf and "Referrer-Policy" in conf and "gzip on;" in conf
    assert "immutable" in conf and 'Cache-Control "no-cache"' in conf and "listen 8080;" in conf
    (dist / "assets" / "app-1a2b3c4d.js").write_text("fetch('http://10.20.30.40:8080/api')", encoding="utf-8")
    with pytest.raises(package.PackageError, match="10.20.30.40"):
        package.pack(root, manifest, web)


def test_a_built_recipe_runs_unprivileged_and_probes_its_port_or_its_declared_path(tmp_path, monkeypatch):
    root, manifest = _committed(tmp_path, "img")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    mid = next(m for m, c in manifest["modules"].items() if c["type"] == "java-boot")
    libs = root / manifest["modules"][mid]["path"] / "build" / "libs"
    libs.mkdir(parents=True)
    (libs / "app.jar").write_bytes(b"J")
    _, trees = package.read(package.pack(root, manifest, mid))
    recipe = next(iter(trees.values()))["Dockerfile"].decode()
    assert "USER 10001" in recipe and "HEALTHCHECK" in recipe and "/dev/tcp/127.0.0.1/8080" in recipe
    manifest["modules"][mid]["container"] = {"healthPath": "/actuator/health"}
    _, trees = package.read(package.pack(root, manifest, mid))
    assert "GET /actuator/health HTTP/1.0" in next(iter(trees.values()))["Dockerfile"].decode()


def test_ci_runs_the_db_tests_beside_a_healthy_database_after_migrating_it(tmp_path, monkeypatch):
    root = _host(tmp_path, None)
    mf = root / identity.MANIFEST_FILENAME
    m = json.loads(mf.read_text(encoding="utf-8"))
    m["ci"] = {**(m.get("ci") or {}), "database": {"image": "postgres:16-alpine", "env": {"POSTGRES_PASSWORD": "ci"},
                                                  "port": 5432, "health": "pg_isready -U postgres",
                                                  "url": "postgres://postgres:ci@localhost:5432/postgres",
                                                  "migrate": "pwsh tools/stack-kit.ps1 migrations check", "modules": ["api"]}}
    mf.write_text(json.dumps(m), encoding="utf-8")
    text = _render(root)
    api, web = _job(text, "api"), _job(text, "web")
    assert "services:" in api and "image: 'postgres:16-alpine'" in api and "--health-cmd" in api and "pg_isready" in api
    assert "DATABASE_URL: 'postgres://postgres:ci@localhost:5432/postgres'" in api
    assert api.index("name: migrate") < api.index("name: build")
    assert "services:" not in web and "DATABASE_URL" not in web


def test_ci_audits_the_dependencies_of_every_driver_that_declares_how():
    text = _render(_host(Path(__import__("tempfile").mkdtemp()), None))
    assert "pwsh tools/stack-kit.ps1 mod web audit" in _job(text, "web")
    assert "pwsh tools/stack-kit.ps1 mod api audit" in _job(text, "api"), "java-boot declares its audit (amendment 16.2)"
    root = _host(Path(__import__("tempfile").mkdtemp()), None)
    (root / "ops" / "drivers").mkdir(parents=True, exist_ok=True)
    (root / "ops" / "drivers" / "registry.json").write_text(json.dumps(
        {"bare": {"label": "x", "roles": ["api"], "commands": {"build": "b.py"}}}), encoding="utf-8")
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["drivers"] = {"registry": "ops/drivers/registry.json"}
    manifest["modules"]["api"]["type"] = "bare"
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    assert " mod api audit" not in _job(_render(root), "api"), "a driver that declares no audit has none (an optional step)"
