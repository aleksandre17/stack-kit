"""TLS on a private network (lib/delivery/tls.py), against a recorded server: the CA is made once on
the target, never replaced, its key never read back; a leaf carries its SANs and lands where the edge
reads it; the truststore is public and password-less."""
from __future__ import annotations

import pytest

from delivery_host import ROOT, ctx_for, host, server
from lib import identity
from lib.delivery import tls
from lib.delivery.context import DeliveryError
from lib.delivery.transport import Result


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = host(tmp_path)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    return root


def _scripts(t):
    return [e[1][2] for e in t.log if e[0] == "exec" and e[1][:2] == ("sh", "-c")]


def test_the_ca_is_made_once_on_the_target_and_its_key_never_read(project, tmp_path):
    t = server(tmp_path)
    tls.ca(ctx_for(project, t))
    (script,) = _scripts(t)
    assert "umask 077" in script and "if [ -s " in script and "CA:TRUE" in script
    assert f"{ROOT}/shop/staging/infra/tls/ca/ca.key" in script
    assert not [e for e in t.log if e[0] == "read" and "ca.key" in str(e)]


def test_a_leaf_carries_its_names_and_lands_where_the_edge_reads_it(project, tmp_path):
    t = server(tmp_path)
    tls.leaf(ctx_for(project, t), "app.lan", ["10.0.0.5", "app"])
    (script,) = _scripts(t)
    assert "subjectAltName=DNS:app.lan,IP:10.0.0.5,DNS:app" in script and "serverAuth" in script and "-days 397" in script
    assert f"{ROOT}/shop/staging/infra/tls/live/app.lan.crt" in script
    with pytest.raises(DeliveryError, match="neither a host name nor an IP"):
        tls.leaf(ctx_for(project, t), "app.lan", ["bad name"])
    t.responses = lambda argv, cwd, env: Result(3)
    with pytest.raises(DeliveryError, match="no CA yet"):
        tls.leaf(ctx_for(project, t), "app.lan", [])


def test_the_truststore_is_public_and_password_less(project, tmp_path):
    t = server(tmp_path)
    t.write(f"{ROOT}/shop/staging/infra/tls/ca/ca.crt", b"-----BEGIN CERTIFICATE-----")
    t.write(f"{ROOT}/shop/staging/infra/tls/public/truststore.p12", b"p12")
    out = tls.truststore(ctx_for(project, t), tmp_path / "out")
    assert sorted(p.name for p in out) == ["shop-staging-ca.crt", "shop-staging-truststore.p12"]
    assert "-nokeys" in _scripts(t)[0] and "-passout pass:" in _scripts(t)[0]
