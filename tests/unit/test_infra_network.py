"""The environment's network has one owner, and it is the environment.

`infra up` makes it when it is not there; the infra compose a host is scaffolded and the generated
stack compose both JOIN it as `external`. A compose that declared the same network its own could not
adopt a network it had not labelled itself -- which is every network on a target whose stack was
deployed before its infra came up, and docker then says only `found but has incorrect label
com.docker.compose.network set to ""`.
"""
from __future__ import annotations

import pytest

from delivery_host import ctx_for, host, manifest_of, server
from lib import extend, identity
from lib.delivery import infra

INFRA_BASE = "ops/compose/infra/docker-compose.base.yml"
NETWORK = "shop-staging"


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = host(tmp_path, manifest_extra={"stack": {"infra": {"services": ["postgres"]}}})
    m = manifest_of(root)
    extend.make(root, m, "infra-service", "postgres")
    extend.make(root, m, "init-ops-compose-infra-docker-composebaseyml")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
    return root


def _ran(t) -> list[tuple]:
    return [tuple(e[1]) for e in t.log if e[0] == "exec"]


def test_the_scaffolded_infra_compose_joins_the_environment_network_as_external(project):
    base = (project / INFRA_BASE).read_text(encoding="utf-8")
    network = base.split("networks:", 1)[1]
    assert "external: true" in network, "the infra stack joins the environment's network, never owns it"
    assert "STACK_KIT_NETWORK:?" in network, "no default invents a name the environment did not declare"


def test_infra_up_makes_the_environment_network_when_it_is_not_there(project, tmp_path):
    t = server(tmp_path)
    assert infra.act(ctx_for(project, t), "up") == 0
    ran = _ran(t)
    created = ran.index(("eng", "network", "create", NETWORK))
    started = next(i for i, a in enumerate(ran) if "up" in a and "-d" in a)
    assert created < started, "the network a compose joins exists before the compose that joins it"


def test_infra_up_leaves_a_network_that_is_already_there_exactly_as_it_is(project, tmp_path):
    t = server(tmp_path, networks=[NETWORK])
    assert infra.act(ctx_for(project, t), "up") == 0
    ran = _ran(t)
    assert ("eng", "network", "inspect", NETWORK) in ran
    assert not [a for a in ran if a[1:3] in (("network", "create"), ("network", "rm")) and NETWORK in a], (
        "a network that exists is adopted, whoever made it and whatever it carries"
    )


def test_the_environment_network_is_what_the_infra_run_is_given(project, tmp_path):
    t = server(tmp_path)
    assert infra.act(ctx_for(project, t), "sync") == 0
    runtime = t.read(f"{ctx_for(project, t).places.of('infra')}/.env.runtime").decode("utf-8")
    assert f"STACK_KIT_NETWORK={NETWORK}\n" in runtime, (
        "the compose asks for it with :? -- the run is what answers, so nothing is left to a default"
    )
