"""Backend structured deploy paths (runtime / workspace)."""
from __future__ import annotations

import pytest

from lib.deploy_paths import (
    backend_deploy_path_candidates,
    deploy_path_summary,
    resolve_backend_deploy_path,
    resolve_deploy_path_base,
)

BASE = "/home/example/my-app/backend"
API = "test-app-api"
WORKER = "test-app-worker"


class TestBackendStructuredLayout:
    def test_runtime(self):
        assert (
            resolve_backend_deploy_path(
                base=BASE, container_name=API, kind="runtime", layout="structured"
            )
            == f"{BASE}/runtime/{API}"
        )

    def test_workspace(self):
        assert (
            resolve_backend_deploy_path(
                base=BASE, container_name=API, kind="workspace", layout="structured"
            )
            == f"{BASE}/workspace/{API}"
        )

    def test_runtime_and_workspace_differ(self):
        rt = resolve_backend_deploy_path(
            base=BASE, container_name=API, kind="runtime", layout="structured"
        )
        ws = resolve_backend_deploy_path(
            base=BASE, container_name=API, kind="workspace", layout="structured"
        )
        assert rt != ws

    def test_flat_layout(self):
        assert (
            resolve_backend_deploy_path(
                base=BASE, container_name=API, kind="runtime", layout="flat"
            )
            == f"{BASE}/{API}"
        )


class TestBackendCandidates:
    def test_three_candidates(self):
        c = backend_deploy_path_candidates(base=BASE, container_name=API)
        assert len(c) == 3
        assert f"{BASE}/runtime/{API}" in c
        assert f"{BASE}/workspace/{API}" in c
        assert f"{BASE}/{API}" in c


@pytest.mark.parametrize("container", [API, WORKER])
def test_multi_module_paths(container: str):
    p = resolve_backend_deploy_path(
        base=BASE, container_name=container, kind="runtime", layout="structured"
    )
    assert p.endswith(container)
    assert "/runtime/" in p


class TestDeployPathBaseInherit:
    BACKEND_BASE = "/home/administrator/stack-kit/backend"

    def test_worker_inherits_backend_base(self):
        assert (
            resolve_deploy_path_base(
                module_deploy_path=None,
                base_module_deploy_path=self.BACKEND_BASE,
            )
            == self.BACKEND_BASE
        )

    def test_explicit_module_base_wins(self):
        assert (
            resolve_deploy_path_base(
                module_deploy_path="/custom/path",
                base_module_deploy_path=self.BACKEND_BASE,
            )
            == "/custom/path"
        )

    def test_retrieval_runtime_from_inherited_base(self):
        base = resolve_deploy_path_base(
            module_deploy_path=None,
            base_module_deploy_path=self.BACKEND_BASE,
        )
        path = resolve_backend_deploy_path(
            base=base,
            container_name="sample-app-search",
            kind="runtime",
            layout="structured",
        )
        assert path == f"{self.BACKEND_BASE}/runtime/sample-app-search"


class TestDeployPathSummary:
    def test_structured(self):
        assert (
            deploy_path_summary(base=BASE, layout="structured")
            == f"{BASE}/runtime/<container>/"
        )

    def test_missing_base_hint(self):
        s = deploy_path_summary(
            base=None,
            server_base="/home/administrator",
            project="app",
        )
        assert "backend/runtime/<container>/" in s
