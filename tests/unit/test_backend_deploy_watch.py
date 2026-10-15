"""be deploy watch — contracts (no Gradle/SSH)."""
from __future__ import annotations

from pathlib import Path

from lib.deploy_paths import resolve_backend_deploy_path


def test_deploy_watch_targets_runtime(pkg_root: Path) -> None:
    p = resolve_backend_deploy_path(
        base="/home/u/stack-kit/backend",
        container_name="test-app-api",
        kind="runtime",
        layout="structured",
    )
    assert "/runtime/" in p
    assert "/workspace/" not in p


def test_deploy_watch_script_exists(pkg_root: Path) -> None:
    assert (pkg_root / "toolkit" / "deploy" / "deploy-watch.sh").is_file()


def test_deploy_sh_routes_watch(pkg_root: Path) -> None:
    text = (pkg_root / "drivers" / "java-boot" / "sh" / "deploy.sh").read_text(encoding="utf-8")
    assert '[[ "${1:-}" == "watch" ]]' in text
    assert "deploy_watch_main" in text


def test_deploy_watch_not_dev_watch(pkg_root: Path) -> None:
    watch = (pkg_root / "toolkit" / "deploy" / "deploy-watch.sh").read_text(encoding="utf-8")
    dev = (pkg_root / "toolkit" / "deploy" / "dev-remote.sh").read_text(encoding="utf-8")
    assert "bootJar" in watch or "deploy_step_build" in watch
    assert "deploy_watch_poll" in watch
    assert "dev_watch_poll" in dev
    assert "rsync" in dev
