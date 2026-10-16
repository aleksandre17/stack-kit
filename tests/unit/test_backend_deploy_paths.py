"""Backend structured deploy paths (runtime / workspace)."""
from __future__ import annotations

import pytest

from lib.deploy_paths import (
    backend_deploy_path_candidates,
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


class TestDeployBaseSecretsFolder:
    """The folder a module without its own DEPLOY_PATH inherits from is the project's word, never the
    kit's: declared, else the primary API module's secrets folder, else none (ADR-001 amendment 7)."""

    MODULES = {"svc": {"role": "api", "secretsModule": "svc-secrets"}, "ui": {"role": "ui"}}

    def test_declared(self):
        from lib.resolution import deploy_base_secrets_folder

        manifest = {"stack": {"deployBaseSecretsModule": "shared"}, "modules": self.MODULES}
        assert deploy_base_secrets_folder(manifest) == "shared"

    def test_the_primary_api_modules_folder(self):
        from lib.resolution import deploy_base_secrets_folder

        assert deploy_base_secrets_folder({"modules": self.MODULES}) == "svc-secrets"

    def test_none_without_an_api(self):
        from lib.resolution import deploy_base_secrets_folder

        assert deploy_base_secrets_folder({"modules": {"ui": {"role": "ui"}}}) == ""


class TestDeployKindModules:
    """A layout migration finds its module by the deploy kind its driver declares, never by a driver
    name (ADR-001 amendment 8): `deployKind:<kind>` in the resolver's context."""

    def test_modules_by_the_kind_their_driver_deploys_as(self):
        from conftest import WORKING_ROOT
        from lib.resolution import context

        ctx = context(WORKING_ROOT)
        manifest_types = {k.split(":")[1]: v for k, v in ctx.items() if k.startswith("module:") and k.endswith(":type")}
        runtime = ctx.get("deployKind:runtime", "").splitlines()
        static = ctx.get("deployKind:static", "").splitlines()
        assert runtime and all(manifest_types[m] in ("java-boot", "node-api") for m in runtime)
        assert static and all(manifest_types[m] == "node-vite" for m in static)
