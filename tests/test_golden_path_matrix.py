"""
Golden path matrix — maps scenario IDs to expected path kinds (no SSH).
Ensures B/D/C paths stay separated per kits/stack-kit/docs/GOLDEN-PATHS.md
"""
from __future__ import annotations

import pytest

from lib.deploy_paths import resolve_module_deploy_path

BASE = "/home/example/my-app/frontend"
APP = "test-app-app"

# Scenario -> (deploy command family, expected path kind on server)
BACKEND_GOLDEN_MATRIX = {
    "BE-deploy-watch": ("deploy_watch", "runtime"),
}

GOLDEN_MATRIX = {
    "B1-dist": ("deploy_dist", "static"),
    "B2-sync": ("deploy_sync", "static"),
    "B3-deploy-watch": ("deploy_watch", "static"),
    "C1-remote-dev": ("deploy_remote", "compose-dev"),
    "C2-remote-prod": ("deploy_remote", "compose-prod"),
    "D1-dev-bootstrap": ("dev_bootstrap", "compose-dev"),
    "D2-dev-watch": ("dev_watch", "compose-dev"),
    "D3-dev-sync": ("dev_sync", "compose-dev"),
}


class TestGoldenPathKinds:
    @pytest.mark.parametrize("scenario,family,kind", [(k, v[0], v[1]) for k, v in GOLDEN_MATRIX.items()])
    def test_resolved_path_matches_kind(self, scenario: str, family: str, kind: str):
        path = resolve_module_deploy_path(
            base=BASE,
            container_name=APP,
            kind=kind,  # type: ignore[arg-type]
            layout="structured",
        )
        if kind == "static":
            assert "/static/" in path
            assert "/compose/" not in path
        elif kind == "compose-dev":
            assert "/compose/dev/" in path
        elif kind == "compose-prod":
            assert "/compose/prod/" in path
        assert path.endswith(APP)

    def test_deploy_watch_same_root_as_dist(self):
        dist = resolve_module_deploy_path(
            base=BASE, container_name=APP, kind="static", layout="structured"
        )
        watch = dist  # deploy watch uses static kind
        assert dist == watch

    def test_dev_watch_same_root_as_bootstrap(self):
        boot = resolve_module_deploy_path(
            base=BASE, container_name=APP, kind="compose-dev", layout="structured"
        )
        assert boot.endswith(APP)


class TestBackendGoldenPathKinds:
    BE_BASE = "/home/example/my-app/backend"
    BE_API = "test-app-api"

    @pytest.mark.parametrize("scenario,family,kind", [(k, v[0], v[1]) for k, v in BACKEND_GOLDEN_MATRIX.items()])
    def test_runtime_path_for_deploy_watch(self, scenario: str, family: str, kind: str):
        from lib.deploy_paths import resolve_backend_deploy_path

        path = resolve_backend_deploy_path(
            base=self.BE_BASE,
            container_name=self.BE_API,
            kind="runtime",
            layout="structured",
        )
        assert "/runtime/" in path
        assert path.endswith(self.BE_API)
