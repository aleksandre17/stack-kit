"""Per-module credentials + global GCP fallback."""
from __future__ import annotations

import json
from pathlib import Path

from lib.credentials import global_gcp_credentials, module_credentials
from lib.project_context import ProjectContext

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "golden-consumer" / "geostat.ops.json"


def test_golden_consumer_multi_credentials() -> None:
    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
    creds = module_credentials(manifest, "api")
    assert len(creds) == 2
    assert creds[0]["file"] == "gcp-primary.json"
    assert creds[1]["envVar"] == "GCP_SECONDARY_CREDENTIALS"


def test_ui_module_uses_global_gcp_when_no_list(tmp_path: Path) -> None:
    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # UI (node-vite) module gets no global GCP fallback and declares no list.
    creds = module_credentials(manifest, "web")
    assert creds == []


def test_global_gcp_requires_feature() -> None:
    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
    off = {**manifest, "features": {"gcpCredentials": False}}
    assert global_gcp_credentials(off) == []


def test_project_context_module_credentials_list(tmp_path: Path) -> None:
    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ctx = ProjectContext(root=tmp_path, manifest=manifest)
    assert len(ctx.module_credentials_list("api")) == 2
