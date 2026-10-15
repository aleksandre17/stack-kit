"""Backend dev-remote contracts (no SSH/rsync execution)."""
from __future__ import annotations

from pathlib import Path

def test_dockerfile_dev_remote_exists(backend_dir: Path) -> None:
    be = backend_dir
    assert (be / "src" / "Dockerfile.dev.remote").is_file()
    assert (be / "worker" / "Dockerfile.dev.remote").is_file()


def test_dev_remote_excludes_gradle_build(pkg_root: Path) -> None:
    text = (pkg_root / "toolkit" / "deploy" / "dev-remote.sh").read_text(encoding="utf-8")
    assert ".gradle/" in text
    assert "build/" in text
    assert "app.jar" in text


def test_dev_requires_structured_layout(pkg_root: Path) -> None:
    text = (pkg_root / "toolkit" / "deploy" / "dev-remote.sh").read_text(encoding="utf-8")
    assert "DEPLOY_LAYOUT=structured" in text


def test_dev_sh_subcommands(pkg_root: Path) -> None:
    text = (pkg_root / "drivers" / "java-boot" / "sh" / "dev.sh").read_text(encoding="utf-8")
    for sub in ("bootstrap", "sync", "watch", "restart"):
        assert sub in text
