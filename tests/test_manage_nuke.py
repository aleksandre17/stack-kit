"""Manage nuke — scoped image removal, no global docker image prune."""
from __future__ import annotations

from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
MANAGE_SH = PKG / "drivers" / "java-boot" / "sh" / "manage.sh"
MANAGE_REMOTE = PKG / "toolkit" / "bash" / "manage-remote.sh"


def test_manage_sh_no_global_image_prune() -> None:
    text = MANAGE_SH.read_text(encoding="utf-8")
    assert 'docker image prune -f' not in text
    assert "manage_prune_deployed_images" in text


def test_manage_remote_prune_helper() -> None:
    text = MANAGE_REMOTE.read_text(encoding="utf-8")
    assert "manage_prune_deployed_images" in text
    assert "docker images -q" in text
    assert 'docker image prune -f' not in text


def test_manifest_schema_validates_consumer() -> None:
    import json

    from conftest import run_kit_cli

    # Validate against the kit-owned synthetic fixture, not whatever geostat.ops.json
    # sits at the real repo root. The harness pins cwd + env (PYTHONPATH so the child
    # can import `lib`, GEOSTAT_PROJECT_ROOT -> fixture) so this is cwd-independent.
    r = run_kit_cli(script="validate_manifest.py", check=False)
    assert r.returncode == 0, r.stderr or r.stdout
    assert "OK" in r.stdout
    schema = json.loads((PKG / "manifest.schema.json").read_text(encoding="utf-8"))
    assert "stack-deploy" in schema["properties"]["stack"]["properties"]["composeModules"]["description"]
