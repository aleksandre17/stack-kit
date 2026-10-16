"""pytest fixtures for stack-kit package tests.

The suite validates the kit's *machinery* (manifest resolution, driver
registry, compose/config generation, deploy-path logic) against a **synthetic,
self-contained reference consumer** under ``tests/fixtures/golden-consumer``.

Why a synthetic fixture and not the live consumer manifest:
  * The kit is a reusable package. Coupling its tests to whatever
    ``stack-kit.json`` happens to sit at the real project root makes the
    suite break every time the consumer's module set changes (this is exactly
    what produced the long-standing red baseline — the tests asserted one
    adopting project's module ids, which is a consumer brand in kit code).
  * Pointing every manifest-driven test at a fixture the kit *owns* means the
    suite exercises the kit's logic deterministically, independent of any
    consumer. This is the standard "golden fixture" pattern for a library.

The fixture deliberately models a *representative* multi-module consumer
under ROLE-NAMED, project-neutral ids — ``api`` (java-boot, env-profiles
config-gen, two credentials), ``search`` (java-boot, simple config-gen, qdrant),
``worker`` (java-boot worker, postgres + flyway, rabbitmq), ``web`` (node-vite
ui) and ``svc`` (node-api) — so that every code path stays covered:
env-profiles config-gen, simple config-gen, postgres datastores, credentials,
stack-deploy ordering, vscode-gen, layout-v2, migrate-layout.

Override ``STACK_KIT_PROJECT_ROOT`` to point the suite at a real consumer when
you want to smoke-test an adoption (documented in tests/README.md).
"""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "golden-consumer"

# Make the kit root importable for *in-process* tests regardless of the cwd
# pytest was launched from. `lib` is a namespace package (no __init__.py); it is
# only importable while the kit root is on sys.path. Running `python -m pytest`
# from the kit dir put cwd (== kit root) on sys.path implicitly, so imports
# resolved; running from the repo root did not, producing 22 collection errors
# (`ModuleNotFoundError: No module named 'lib'`). Anchoring sys.path here — to a
# path derived from this file, never from cwd — makes collection deterministic
# for either invocation. SSOT: the same PKG that the subprocess helper exports.
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

# Never collect inside the synthetic consumer fixture. It contains a junction
# (kits/stack-kit -> the real kit) that would otherwise make pytest recurse
# infinitely back into this tree. The fixture holds data, not tests.
collect_ignore = ["fixtures"]


def pytest_ignore_collect(collection_path, config):  # noqa: ARG001
    return "fixtures" in Path(str(collection_path)).parts

def _disposable_copy(source: Path) -> Path:
    """A copy of the reference consumer the suite may write into (ADR-001 decision 7).

    The tracked fixture is the specimen, never the workbench: generators the suite exercises write
    their outputs into the project they are pointed at, and pointing them at the tracked tree left
    `git status` dirty after every run -- a test that rewrites what it reads stops being a test of
    the kit and starts being a test of its own previous run. The kit link is recreated in the copy.
    """
    root = Path(tempfile.mkdtemp(prefix="stack-kit-fixture-")) / source.name
    shutil.copytree(source, root, ignore=shutil.ignore_patterns("kits", "__pycache__", ".pytest_cache"))
    atexit.register(shutil.rmtree, root.parent, True)
    return root


# Allow an explicit override (manual adoption smoke-test); otherwise a disposable copy of the
# self-contained synthetic consumer is the project root for the suite.
WORKING_ROOT = _disposable_copy(FIXTURE_ROOT)
REPO = Path(os.environ["STACK_KIT_PROJECT_ROOT"]).resolve() if os.environ.get(
    "STACK_KIT_PROJECT_ROOT"
) else WORKING_ROOT


def _link_kit_into_fixture(fixture_root: Path, kit_root: Path) -> None:
    """Materialise ``<fixture>/kits/stack-kit`` -> the real kit.

    The fixture manifest declares ``"package": "kits/stack-kit"`` so that the
    package-boundary tests (``package == "kits/stack-kit"`` *and* it resolves
    to this kit) both hold. The link target is gitignored (junction/symlink),
    so we recreate it at session start — keeps the fixture self-healing without
    committing a platform-specific link.
    """
    link = fixture_root / "kits" / "stack-kit"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists():
        # Already linked (or a stale real dir) — trust it if it resolves.
        try:
            if (link / "drivers" / "registry.json").is_file():
                return
        except OSError:
            pass
    if sys.platform.startswith("win"):
        # Directory junction — no admin privilege required (unlike symlink).
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(kit_root)],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        os.symlink(kit_root, link, target_is_directory=True)


def _write_volatile_secrets(fixture_root: Path) -> None:
    """Create the gitignored ``deploy.env`` the suite reads.

    ``**/deploy.env`` is gitignored by the kit (never commit real secrets), so
    the fixture's copy can't be committed. Its identity values are fixed and
    drive compose-service naming + migrate-rename assertions, so we write a
    deterministic copy at session start from the committed ``.example``-shaped
    template, with the canonical service names the tests expect.
    """
    secrets = fixture_root / "ops" / "config"
    secrets.mkdir(parents=True, exist_ok=True)
    template = secrets / "deploy.env.fixture"
    target = secrets / "deploy.env"
    if template.is_file():
        target.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")


@pytest.fixture(scope="session", autouse=True)
def _fixture_project(request: pytest.FixtureRequest) -> None:
    """Prepare the synthetic consumer + wire the kit CLI env for the session."""
    if REPO == WORKING_ROOT:
        _link_kit_into_fixture(WORKING_ROOT, PKG)
        _write_volatile_secrets(WORKING_ROOT)
    os.environ.setdefault("STACK_KIT_PROJECT_ROOT", str(REPO))
    os.environ["STACK_KIT_KIT_ROOT"] = str(PKG)


def kit_cli_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment a kit child process needs to behave like the in-process tests.

    Single source of truth for the three things a subprocess invocation of a kit
    CLI (``lib/resolve_cli.py``, ``lib/validate_manifest.py``, …) depends on:

    * ``PYTHONPATH`` -> the kit root, so the child resolves ``from lib.x import``
      (the scripts import the kit's namespace package; without this the child
      dies with ``ModuleNotFoundError: No module named 'lib'``).
    * ``STACK_KIT_PROJECT_ROOT`` -> the synthetic fixture, so manifest resolution
      hits the kit-owned fixture and not whatever ``stack-kit.json`` happens
      to sit at the real repo root.
    * ``STACK_KIT_KIT_ROOT`` -> the kit, so registry/driver-path resolution works.

    Derived entirely from ``PKG``/``REPO`` (file-anchored), never from cwd, so it
    is identical whether pytest is launched from the kit dir or the repo root.
    """
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join([str(PKG), existing]) if existing else str(PKG)
    env["STACK_KIT_PROJECT_ROOT"] = str(REPO)
    env["STACK_KIT_KIT_ROOT"] = str(PKG)
    if extra:
        env.update(extra)
    return env


def run_kit_cli(
    *args: str,
    script: str = "resolve_cli.py",
    check: bool = True,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke a kit CLI as a child process, deterministically.

    Centralises cwd + env for *every* subprocess test so the child resolves
    ``lib`` and the fixture manifest exactly like the in-process tests do —
    independent of the cwd pytest was launched from (DRY; the harness, not each
    test, owns the invocation contract).

    cwd is pinned to the synthetic fixture (the project root the kit is being
    exercised against); env carries PYTHONPATH/STACK_KIT_* via :func:`kit_cli_env`.
    """
    cmd = [sys.executable, str(PKG / "lib" / script), *args]
    return subprocess.run(
        cmd,
        cwd=str(REPO),
        env=kit_cli_env(env_extra),
        capture_output=True,
        text=True,
        check=check,
    )


@pytest.fixture
def kit_cli():
    """Fixture wrapper around :func:`run_kit_cli` for tests that prefer injection."""
    return run_kit_cli


def repo_module(repo_root: Path, manifest: dict, module_id: str) -> Path:
    parts = manifest["modules"][module_id]["path"].split("/")
    return repo_root.joinpath(*parts)


def repo_secrets(repo_root: Path, manifest: dict) -> Path:
    parts = manifest.get("secrets", "ops/config").split("/")
    return repo_root.joinpath(*parts)


@pytest.fixture
def compose_service_names(manifest: dict) -> dict[str, str]:
    """Abstract service names from manifest slug defaults (not project brands)."""
    slug = "test-app"
    return {
        "api": f"{slug}-api",
        "app": f"{slug}-app",
        "worker": f"{slug}-worker",
    }


@pytest.fixture
def pkg_root() -> Path:
    return PKG


@pytest.fixture
def repo_root() -> Path:
    return REPO


@pytest.fixture
def manifest(repo_root: Path) -> dict:
    import json

    path = repo_root / "stack-kit.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def registry(pkg_root: Path) -> dict:
    import json

    path = pkg_root / "drivers" / "registry.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def secrets_root(repo_root: Path, manifest: dict) -> Path:
    return repo_secrets(repo_root, manifest)


@pytest.fixture
def frontend_dir(repo_root: Path, manifest: dict) -> Path:
    return repo_module(repo_root, manifest, "web")


@pytest.fixture
def backend_dir(repo_root: Path, manifest: dict) -> Path:
    return repo_module(repo_root, manifest, "api")


@pytest.fixture
def catalog_path(repo_root: Path, manifest: dict) -> Path:
    rel = manifest.get("compose", {}).get("catalog", "ops/compose/catalog.json")
    return repo_root.joinpath(*rel.split("/"))
