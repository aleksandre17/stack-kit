"""The env-value policy (lib/config_policy.py): every rule refuses its failure, by key name -- a
value is never printed."""
from __future__ import annotations

from lib.config_policy import problems

CAT = {"keys": [
    {"key": "Jwt:Key", "sensitivity": "SECRET", "policy": {"required": True, "minLength": 32, "modules": ["api"]}},
    {"key": "Cors:Origins", "sensitivity": "INTERNAL", "policy": {"forbid": {"prod": ["[*]"]}}},
    {"key": "Public:Url", "sensitivity": "PUBLIC", "policy": {"format": "https-url", "required": ["prod"]}},
    {"key": "Pool:Size", "sensitivity": "INTERNAL", "policy": {"format": "positive-int"}},
    {"key": "Smtp:Host", "sensitivity": "INTERNAL", "policy": {"requires": ["Smtp:Password"]}},
    {"key": "Smtp:Password", "sensitivity": "SECRET"},
]}


def run(values, env="prod", folder="api"):
    return problems(CAT, values, folder=folder, environment=env)


def test_each_rule_refuses_its_failure_and_never_prints_a_value():
    found = run({"Jwt__Key": "short-secret-value", "Cors__Origins": "https://a.example, *",
                 "Public__Url": "http://localhost:5000", "Pool__Size": "0", "Smtp__Host": "mail.example"})
    text = "\n".join(found)
    assert "Jwt:Key is shorter than 32" in text
    assert "Cors:Origins holds a value prod forbids" in text
    assert "Public:Url is not https" in text and "Public:Url points at this machine" in text
    assert "Pool:Size is not a positive integer" in text
    assert "Smtp:Host is set, so Smtp:Password is required too" in text
    assert "short-secret-value" not in text and "mail.example" not in text


def test_required_placeholders_and_required_only_in_an_environment():
    assert any("Jwt:Key is required and is a placeholder" in p for p in run({"Jwt__Key": "CHANGE_ME"}))
    assert any("Jwt:Key is required and is not set" in p for p in run({}))
    assert not [p for p in run({}, folder="web") if "Jwt:Key" in p], "a key belongs to its modules only"
    assert any("Public:Url is required in prod" in p for p in run({}, folder="web"))
    assert not [p for p in run({}, env="dev", folder="web") if "Public:Url" in p]


def test_a_value_that_holds_passes():
    assert run({"Jwt__Key": "k7" * 20, "Cors__Origins": "https://a.example", "Public__Url": "https://app.example",
                "Pool__Size": "8", "Smtp__Host": "m", "Smtp__Password": "p"}) == []
