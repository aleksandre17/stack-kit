"""Infra remote path — per-consumer slug under global DEPLOY_PROJECT root."""
from __future__ import annotations

import pytest

from lib.deploy_paths import (
    infra_deploy_path_candidates,
    normalize_infra_slug,
    resolve_infra_deploy_path,
)


class TestInfraSlug:
    def test_normalize(self):
        assert normalize_infra_slug("Sample-App-Stack") == "sample-app-stack"


class TestResolveInfraDeployPath:
    def test_explicit(self):
        assert (
            resolve_infra_deploy_path(
                deploy_path="/home/admin/app/infra/my-app",
                server_base=None,
                global_project=None,
                consumer_slug="my-app",
            )
            == "/home/admin/app/infra/my-app"
        )

    def test_explicit_wrong_slug_raises(self):
        with pytest.raises(ValueError, match="/infra/my-app"):
            resolve_infra_deploy_path(
                deploy_path="/home/admin/app/infra/other",
                server_base="/home/admin",
                global_project="app",
                consumer_slug="my-app",
            )

    def test_fallback(self):
        assert (
            resolve_infra_deploy_path(
                deploy_path=None,
                server_base="/home/administrator",
                global_project="app",
                consumer_slug="sample-app-stack",
            )
            == "/home/administrator/app/infra/sample-app-stack"
        )


class TestCandidates:
    def test_one_path(self):
        c = infra_deploy_path_candidates(
            server_base="/home/administrator",
            global_project="app",
            consumer_slug="myshop",
        )
        assert c == ["/home/administrator/app/infra/myshop"]
