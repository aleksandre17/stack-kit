"""A credential-shaped value tracked in the tree stops validate and a deploy, not only `scan secrets`
(ADR-001 amendment 20). Found by a re-audit: the scan ran nowhere blocking, so a committed secret was
reported only to whoever asked. The fixture value is assembled at run time, so no file carries one."""
from __future__ import annotations

from pathlib import Path

from delivery_host import commit, host
from lib import identity

LEAK = "url: postgres://app:" + "s3cr3t" + "value@db.example.test/app\n"


def _leaky(tmp_path, monkeypatch):
    root = host(tmp_path)
    (root / "apps" / "edge" / "settings.yml").write_text(LEAK, encoding="utf-8")
    import subprocess

    subprocess.run(["git", "-C", str(root), "add", "apps/edge/settings.yml"], check=True)
    commit(root, "a leak\n")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
    return root


def test_validate_refuses_a_tracked_credential_and_prints_no_value(tmp_path, monkeypatch):
    from lib.validate_manifest import validate_manifest

    root = _leaky(tmp_path, monkeypatch)
    errs, _ = validate_manifest(root, pkg_root=Path(__file__).resolve().parents[2])
    found = [e for e in errs if e.startswith("security: apps/edge/settings.yml:1: url-password")]
    assert len(found) == 1 and "s3cr3t" not in " ".join(errs)


def test_a_deploy_refuses_a_checkout_that_tracks_a_credential_before_any_target_is_opened(tmp_path, monkeypatch, capsys):
    from lib.cli.main import main

    _leaky(tmp_path, monkeypatch)
    assert main(["deploy", "edge", "--env", "staging"]) == 5
    err = capsys.readouterr().err
    assert "1 credential-shaped value" in err and "s3cr3t" not in err
