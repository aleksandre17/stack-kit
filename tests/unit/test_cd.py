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
    assert "needs: [api, search, worker]" in dev and "needs: [deploy-dev]" in prod
    assert "environment: 'stage'" in dev and "environment: 'live'" in prod
    assert "group: 'deploy-live-prod'" in prod and "cancel-in-progress: false" in prod
    for job in (dev, prod):
        assert "unpack api .stack-kit/artifacts/api-*.tgz" in job and "name: package-api" in job
        assert not any(f" mod api {s}'" in job for s in ("build", "test", "lint")), "a deploy job builds"
    assert "'pwsh tools/stack-kit.ps1 mod api deliver release --env prod --target live --no-build'" in prod
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


def test_a_module_whose_release_cannot_promote_is_named_never_deployed(tmp_path):
    text = _render(_host(tmp_path, TWO))
    assert "web (node-vite): packaging is pending" in text and "svc (node-api): packaging is pending" in text
    assert " mod web deliver" not in text and " mod svc deliver" not in text


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

def test_a_package_is_one_archive_per_commit_and_unpacks_to_the_same_bytes(tmp_path, monkeypatch):
    import subprocess

    root = tmp_path / "pkg"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    git = ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "c"], check=True)
    manifest = json.loads((root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    mid = next(m for m, c in manifest["modules"].items() if c["type"] == "java-boot")
    libs = root / manifest["modules"][mid]["path"] / "build" / "libs"
    libs.mkdir(parents=True)
    (libs / "app-1.0-boot.jar").write_bytes(b"JAR-BYTES")
    archive = package.pack(root, manifest, mid)
    assert archive.name.startswith(f"{mid}-") and archive.with_suffix(".tgz.sha256").is_file()
    (libs / "app-1.0-boot.jar").unlink()
    assert package.unpack(root, manifest, mid, archive)
    assert (libs / "app-1.0-boot.jar").read_bytes() == b"JAR-BYTES"
    archive.write_bytes(archive.read_bytes() + b"x")
    with pytest.raises(package.PackageError, match="sha256 differs"):
        package.unpack(root, manifest, mid, archive)


def test_an_archive_member_that_escapes_its_module_is_refused(tmp_path):
    root = tmp_path / "esc"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    manifest = json.loads((root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    mid = next(iter(manifest["modules"]))
    evil = tmp_path / "evil.tgz"
    payload = tmp_path / "x.txt"
    payload.write_text("x", encoding="utf-8")
    with tarfile.open(evil, "w:gz") as tar:
        tar.add(payload, arcname="../../outside.txt")
    with pytest.raises(package.PackageError, match="escapes its place"):
        package.unpack(root, manifest, mid, evil)


def test_a_pending_package_names_its_reason():
    manifest = json.loads((WORKING_ROOT / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    mid = next(m for m, c in manifest["modules"].items() if c["type"] == "node-vite")
    with pytest.raises(package.PackageError, match="per environment"):
        package.plan(WORKING_ROOT, manifest, mid)


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
        doc = {"targets": {"live": {**TARGET, "health": {"prod": {"api": f"{base}/ok"}}}}}
        assert targets.health(doc, ["--env", "prod"], attempts=1, pause=0.01) == 0
        doc["targets"]["live"]["health"]["prod"]["web"] = f"{base}/down"
        assert targets.health(doc, ["--env", "prod"], attempts=2, pause=0.01) == 1
        assert "FAILED web" in capsys.readouterr().out
        pending = {"targets": {"live": {"runtime": "iis", "pending": "not yet"}}}
        assert targets.health(pending, ["--env", "prod"], attempts=1) == 2
    finally:
        server.shutdown()


def test_a_packaged_module_whose_release_cannot_promote_gets_its_package_and_no_deploy(tmp_path):
    root = _host(tmp_path, TWO)
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    (root / "apps" / "edge").mkdir(parents=True)
    manifest["modules"]["edge"] = {"type": "dotnet-aspnet", "role": "api", "path": "apps/edge", "secretsModule": "edge"}
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    text = _render(root)
    assert "edge (dotnet-aspnet): its release does not deploy a packaged artifact (no `promotes`)" in text
    assert "pwsh tools/stack-kit.ps1 package edge" in _job(text, "edge")
    assert " mod edge deliver" not in text and "unpack edge" not in text
