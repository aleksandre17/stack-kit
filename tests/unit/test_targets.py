"""Deploy targets are declared configuration; the kit holds no server, ssh or remote path (ADR-001
amendment 9). Every answer below comes from a targets file the test writes -- nothing is inferred."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import WORKING_ROOT
from lib import identity, targets
from lib.migrate_legacy import carry

PROD = {"runtime": "docker-compose", "host": "deploy.example.test", "user": "svc", "port": 2222,
        "root": "/srv/apps", "ssh": {"identity": "agent", "knownHosts": "ops/deploy/known_hosts"}}


def _host(tmp_path: Path, document: dict, local: dict | None = None) -> Path:
    root = tmp_path / "targets-host"
    shutil.copytree(WORKING_ROOT, root, symlinks=True)
    (root / "ops" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / "ops" / "deploy" / "known_hosts").write_text("# pinned\n", encoding="utf-8")
    (root / "ops" / "deploy" / "targets.json").write_text(json.dumps(document), encoding="utf-8")
    if local is not None:
        (root / "ops" / "deploy" / "targets.local.json").write_text(json.dumps(local), encoding="utf-8")
    mf = root / identity.MANIFEST_FILENAME
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["deploy"] = {"targets": "ops/deploy/targets.json"}
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _manifest(root: Path) -> dict:
    return json.loads((root / identity.MANIFEST_FILENAME).read_text(encoding="utf-8"))


def _doc(**named) -> dict:
    return {"schema": 1, "defaults": {"prod": "prod", "dev": "stage"} if "stage" in named else {"prod": "prod"},
            "targets": named}


@pytest.fixture
def resolver(tmp_path, monkeypatch):
    made = []

    def make(document: dict, local: dict | None = None, **env: str):
        from lib.resolution import Resolver

        made.append(1)
        root = _host(tmp_path / str(len(made)), document, local)
        monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
        for k in ("TARGET", "ENVIRONMENT"):
            monkeypatch.delenv(identity.env_name(k), raising=False)
        for k, v in env.items():
            monkeypatch.setenv(identity.env_name(k), v)
        return Resolver(root)
    return make


# ── the declaration ──────────────────────────────────────────────────────────

def test_a_reachable_target_without_a_root_is_refused_naming_the_field(tmp_path):
    root = _host(tmp_path, _doc(prod={k: v for k, v in PROD.items() if k != "root"}))
    assert any("targets.prod.root: required" in p for p in targets.problems(root, _manifest(root)))


def test_a_pending_target_needs_only_its_runtime_and_reason(tmp_path):
    root = _host(tmp_path, _doc(prod={"runtime": "iis", "pending": "no host yet"}))
    assert targets.problems(root, _manifest(root)) == []
    assert targets.notices(root, _manifest(root)) == ["target prod: pending -- no host yet"]


def test_a_secret_is_never_a_value_of_a_targets_file(tmp_path):
    armoured = {**PROD, "description": "-----BEGIN OPENSSH PRIVATE KEY----- x"}
    root = _host(tmp_path, _doc(prod=armoured))
    assert any("private key material" in p for p in targets.problems(root, _manifest(root)))
    root2 = _host(tmp_path / "b", _doc(prod={**PROD, "password": "x"}))
    found = targets.problems(root2, _manifest(root2))
    assert any("names a secret" in p for p in found) and any("password" in p for p in found)


def test_host_key_checking_is_set_by_host_keys_alone(tmp_path):
    root = _host(tmp_path, _doc(prod={**PROD, "ssh": {"options": ["StrictHostKeyChecking=no"]}}))
    assert any("hostKeys" in p for p in targets.problems(root, _manifest(root)))


def test_an_unknown_layout_placeholder_is_refused(tmp_path):
    root = _host(tmp_path, _doc(prod={**PROD, "layout": {"unit": "{@environment}/{nope}"}}))
    assert any("unknown placeholder(s) nope" in p for p in targets.problems(root, _manifest(root)))


# ── selection and answers ────────────────────────────────────────────────────

def test_selection_by_flag_then_environment_default(resolver):
    stage = {**PROD, "host": "stage.example.test"}
    assert resolver(_doc(prod=PROD, stage=stage), ENVIRONMENT="dev").target()[0] == "stage"
    assert resolver(_doc(prod=PROD, stage=stage), TARGET="prod", ENVIRONMENT="dev").target()[0] == "prod"
    assert resolver(_doc(prod=PROD, stage=stage)).target()[0] == "prod"
    with pytest.raises(ValueError, match="no target 'qa'"):
        resolver(_doc(prod=PROD), TARGET="qa").target()


def _places(target: dict, env: str = "prod") -> "targets.Places":
    return targets.Places(target, project="golden-consumer", environment=env, environments=["dev", "prod"])


class _Svc:
    def __init__(self, sid: str, tier: str) -> None:
        self.id, self.tier = sid, tier


def test_the_default_layout_is_one_project_tree_split_by_environment_and_tier(resolver):
    r = resolver(_doc(prod=PROD))
    assert _places(PROD).of("unit", _Svc("api", "backend")) == "/srv/apps/golden-consumer/prod/backend/api"
    assert _places(PROD, "dev").of("workspace", _Svc("app", "frontend")) == "/srv/apps/golden-consumer/dev/frontend/app/workspace"
    assert _places(PROD).of("backups") == "/srv/apps/golden-consumer/prod/backups"
    assert r.compose_project("dev") == "golden-consumer-dev"


def test_a_target_layout_overrides_the_default_inside_the_project():
    t = {**PROD, "layout": {"unit": "{@environment}/svc/{service}"}}
    assert _places(t).of("unit", _Svc("api", "backend")) == "/srv/apps/golden-consumer/prod/svc/api"


@pytest.mark.parametrize("layout", [{"unit": "{root}/shared/{service}"}, {"unit": "{@environment}/../../other/{service}"},
                                    {"project": "{root}"}, {"project": "/etc/{project}"}])
def test_a_path_outside_the_projects_own_directory_is_refused_everywhere(tmp_path, layout):
    escaping = {**PROD, "layout": layout}
    root = _host(tmp_path / "v", _doc(prod=escaping))
    assert any("outside the project's directory" in p or "not strictly inside the target's root" in p
               for p in targets.problems(root, _manifest(root))), targets.problems(root, _manifest(root))
    with pytest.raises(ValueError):
        _places(escaping).of("unit", _Svc("api", "backend"))


def test_a_host_port_is_one_services_on_its_host_across_targets_and_environments(tmp_path):
    a = {**PROD, "ports": {"prod": {"api": [8080]}, "dev": {"api": [8080]}}}
    root = _host(tmp_path, _doc(prod=a))
    found = targets.problems(root, _manifest(root))
    assert any("host port 8080 on deploy.example.test is already" in p for p in found), found
    ok = {**PROD, "ports": {"prod": {"api": [8080]}, "dev": {"api": [18080]}}}
    root2 = _host(tmp_path / "ok", _doc(prod=ok))
    assert not [p for p in targets.problems(root2, _manifest(root2)) if "port" in p]


def test_a_per_machine_override_is_merged_over_the_tracked_file(resolver):
    r = resolver(_doc(prod=PROD), local={"targets": {"prod": {"host": "10.0.0.5"}}})
    assert targets.server(*r.target()) == "svc@10.0.0.5" and r.target()[1]["root"] == "/srv/apps"


def test_a_pending_target_refuses_every_deploy_with_its_reason_and_nothing_else(resolver):
    r = resolver(_doc(prod={"runtime": "iis", "pending": "IIS delivery is not built"}))
    assert r.ssh_args() == [] and r.compose_project("prod") == "golden-consumer-prod"
    from lib.delivery.context import DeliveryError, open_delivery

    with pytest.raises(DeliveryError, match="pending: IIS delivery is not built") as e:
        open_delivery(r.root, r.manifest, environment="prod")
    assert e.value.code == 2


def test_ssh_is_strict_against_the_pinned_file_and_trusts_first_use_only_when_declared(resolver, monkeypatch):
    r = resolver(_doc(prod=PROD))
    args = r.ssh_args()
    assert "Port=2222" in args and "StrictHostKeyChecking=yes" in args
    assert any(a.startswith("UserKnownHostsFile=") and a.endswith("ops/deploy/known_hosts") for a in args)
    assert not any("IdentityFile" in a for a in args)  # agent: no key named
    tofu = {**PROD, "ssh": {"hostKeys": "accept-new", "identity": "env:DEPLOY_KEY_PATH"}}
    monkeypatch.setenv("DEPLOY_KEY_PATH", "/keys/deploy")
    args = resolver(_doc(prod=tofu)).ssh_args()
    assert "StrictHostKeyChecking=accept-new" in args and "IdentityFile=/keys/deploy" in args
    monkeypatch.delenv("DEPLOY_KEY_PATH")
    with pytest.raises(ValueError, match="DEPLOY_KEY_PATH is not set"):
        resolver(_doc(prod=tofu)).ssh_args()


# ── migration: the former homes, carried once, then gone ─────────────────────

def test_migrate_declares_deploy_env_as_a_target_and_invents_nothing(tmp_path):
    root = tmp_path / "m"
    secrets = root / "ops" / "config"
    (secrets / "api").mkdir(parents=True)
    (secrets / "deploy.env").write_text(
        "DEPLOY_SERVER=ops@203.0.113.7\nDEPLOY_SSH_OPTIONS=-o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30\n"
        "DEPLOY_SSH_IDENTITY_FILE=ops/config/ssh/id_ed25519\nDEPLOY_PROJECT=Shop_Front\nCOMPOSE_API_SERVICE=x-api\n",
        encoding="utf-8")
    (secrets / "api" / ".env.deploy").write_text("DEPLOY_PATH=/home/ops/backend/shop-api\nDEPLOY_HOST_PORT=8090\n", encoding="utf-8")
    (secrets / "api" / ".env.prod").write_text("DB=postgres\nDOCKER_NETWORK=old-net\n", encoding="utf-8")
    manifest = {"modules": {"api": {"type": "dotnet-aspnet", "role": "api", "path": "api", "secretsModule": "api"}}}
    changes = carry(root, secrets, manifest, apply=False)
    assert not (root / "ops" / "deploy" / "targets.json").exists() and "deploy" not in manifest
    assert any("INFERRED" in c for c in changes), "an inferred root was written silently"
    assert any("COMPOSE_API_SERVICE: dropped" in c for c in changes)
    carry(root, secrets, manifest, apply=True)
    assert manifest["project"] == "shop_front" and manifest["deploy"]["targets"] == "ops/deploy/targets.json"
    t = json.loads((root / "ops" / "deploy" / "targets.json").read_text(encoding="utf-8"))["targets"]["prod"]
    assert (t["host"], t["user"], t["root"]) == ("203.0.113.7", "ops", "/home/ops")
    assert t["ssh"] == {"identity": "file:ops/config/ssh/id_ed25519", "hostKeys": "accept-new",
                        "options": ["ServerAliveInterval=30"]}
    assert t["ports"] == {"prod": {"api": [8090]}}
    assert t["legacyLayout"] == {"environment": "prod", "units": {"api": "{root}/backend/shop-api"}}
    assert not (secrets / "deploy.env").exists() and not (secrets / "api" / ".env.deploy").exists()
    assert (secrets / "api" / ".env.prod").read_text(encoding="utf-8") == "DB=postgres\n"
    from lib import legacy

    assert legacy.found(secrets, manifest) == {}


def test_a_former_home_is_a_validate_error_naming_migrate_by_key_name(tmp_path):
    from lib import legacy

    secrets = tmp_path / "ops" / "config"
    secrets.mkdir(parents=True)
    (secrets / "deploy.env").write_text("DEPLOY_SERVER=a@b\nDEPLOY_PROJECT=x\n", encoding="utf-8")
    found = legacy.problems(tmp_path, secrets, {"modules": {}, "stack": {"networkName": "n"}})
    assert any("deploy.env: the file itself, DEPLOY_PROJECT, DEPLOY_SERVER" in p and "migrate --apply" in p for p in found)
    assert any("stack.networkName" in p for p in found)
    assert not any("a@b" in p for p in found)


# ── runtime config: what the application reads, never a secret ───────────────

SECRET_ROW = {"key": "Jwt:Key", "sensitivity": "SECRET", "owner": "ops", "allowedSource": "env",
              "rotation": "every 90 days", "env": ["JWT_KEY"]}


def _runtime_host(tmp_path: Path, files: dict[str, str], items: list[dict]) -> tuple[Path, dict]:
    root = tmp_path / "rc"
    root.mkdir()
    (root / "ops").mkdir()
    (root / "ops" / "keys.json").write_text(json.dumps({"keys": [SECRET_ROW]}), encoding="utf-8")
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    manifest = {"config": {"keys": "ops/keys.json"}, "modules": {"api": {"runtimeConfig": items}}}
    return root, manifest


def test_a_runtime_config_file_may_not_carry_or_name_a_secret(tmp_path):
    from lib.config_keys import runtime_config_problems

    root, manifest = _runtime_host(tmp_path, {
        "cfg/appsettings.Production.json": json.dumps({"Jwt": {"Key": "real-signing-key", "Issuer": "x"}}),
        "cfg/env.js": "window.env = { JWT_KEY: 'abc' };\n",
        "cfg/clean.json": json.dumps({"Logging": {"LogLevel": "Warning"}}),
    }, [{"from": "cfg/appsettings.Production.json", "to": "appsettings.Production.json", "environments": ["prod"]},
        {"from": "cfg/env.js", "to": "env.js", "environments": ["dev"]},
        {"from": "cfg/clean.json", "to": "x.json", "environments": ["prod"]},
        {"from": "cfg/missing.json", "to": "y.json", "environments": ["prod"]}])
    found = runtime_config_problems(root, manifest)
    assert any("[0]" in f and "carries SECRET Jwt:Key" in f for f in found), found
    assert any("[1]" in f and "names SECRET Jwt:Key" in f for f in found), found
    assert not any("[2]" in f for f in found)
    assert any("[3].from: cfg/missing.json is not there" in f for f in found)
    assert all("real-signing-key" not in f and "abc" not in f for f in found), "a value reached a report"


@pytest.mark.parametrize("to", ["/etc/app.json", "../escape.json", "conf/../../x", "C:/x"])
def test_a_runtime_config_destination_stays_inside_the_units_runtime(to):
    from lib.schema_check import validate as schema_validate

    schema = json.loads((Path(__file__).resolve().parents[2] / "manifest.schema.json").read_text(encoding="utf-8"))
    item = schema["properties"]["modules"]["additionalProperties"]["properties"]["runtimeConfig"]["items"]
    assert schema_validate({"from": "a", "to": to, "environments": ["prod"]}, item), to
    assert schema_validate({"from": "a", "to": "conf/nginx.conf", "environments": ["prod"]}, item) == []
