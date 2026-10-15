"""Deploy path resolution — all layout/mode/kind combinations."""
from __future__ import annotations

import pytest

from lib.deploy_paths import deploy_path_candidates, resolve_module_deploy_path

BASE = "/home/example/my-app/frontend"
CONTAINER = "test-app-app"


class TestStructuredLayout:
    def test_static(self):
        assert (
            resolve_module_deploy_path(
                base=BASE, container_name=CONTAINER, kind="static", layout="structured"
            )
            == f"{BASE}/static/{CONTAINER}"
        )

    def test_compose_dev(self):
        assert (
            resolve_module_deploy_path(
                base=BASE, container_name=CONTAINER, kind="compose-dev", layout="structured"
            )
            == f"{BASE}/compose/dev/{CONTAINER}"
        )

    def test_compose_prod(self):
        assert (
            resolve_module_deploy_path(
                base=BASE, container_name=CONTAINER, kind="compose-prod", layout="structured"
            )
            == f"{BASE}/compose/prod/{CONTAINER}"
        )

    def test_static_and_compose_dev_differ(self):
        static = resolve_module_deploy_path(
            base=BASE, container_name=CONTAINER, kind="static", layout="structured"
        )
        dev = resolve_module_deploy_path(
            base=BASE, container_name=CONTAINER, kind="compose-dev", layout="structured"
        )
        assert static != dev


class TestFlatLayout:
    def test_appends_container(self):
        assert (
            resolve_module_deploy_path(
                base=BASE, container_name=CONTAINER, kind="static", layout="flat"
            )
            == f"{BASE}/{CONTAINER}"
        )


class TestFullPathMode:
    def test_uses_base_as_is(self):
        full = f"{BASE}/static/{CONTAINER}"
        assert (
            resolve_module_deploy_path(
                base=full,
                container_name=CONTAINER,
                kind="static",
                layout="structured",
                path_mode="full",
            )
            == full
        )


class TestCandidates:
    def test_four_candidates(self):
        c = deploy_path_candidates(base=BASE, container_name=CONTAINER)
        assert len(c) == 4
        assert f"{BASE}/static/{CONTAINER}" in c
        assert f"{BASE}/compose/dev/{CONTAINER}" in c


@pytest.mark.parametrize(
    "kind",
    ["static", "compose-dev", "compose-prod"],
)
def test_trailing_slash_base(kind: str):
    p = resolve_module_deploy_path(
        base=f"{BASE}/",
        container_name=CONTAINER,
        kind=kind,  # type: ignore[arg-type]
        layout="structured",
    )
    assert "//" not in p.replace("://", "")
