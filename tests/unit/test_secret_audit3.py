"""Found by the third independent audit of 2.5.0: a known exposure is the value at a key path, never a
name on a line; the scan reads what Windows tools write and every file history names; a reader of some
other `X_FILE` is not a reader of this key; a module cannot make its own reach check pass; a non-root
runtime is handed its secret; outside every module, a `package.json` alone is not a web app. Every value
here is a fixture assembled at run time."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib import secret_scan as s

GATE = {"id": "no-config-secret", "paths": r"\.json$",
        "forbids": r"\"\w*(Key|Password)\"\s*:\s*\"(?!__[A-Z0-9_]+__\")[^\"]{8,}\"",
        "because": "a fixture", "instead": "a placeholder",
        "proves": {"path": "a.json", "text": "\"Key\": \"0123456789abcdef\""},
        "admits": {"path": "a.json", "text": "\"Key\": \"__JWT_KEY__\""}}
KNOWN = "known" + "0123456789abcdef"
NEW = "fresh" + "fedcba9876543210"


def _repo(tmp_path: Path, files: dict, exposures: list) -> tuple:
    git = ["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    for rel, data in files.items():
        (tmp_path / rel).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    (tmp_path / "gates.json").write_text(json.dumps({"schema_version": 1, "gates": [GATE]}), encoding="utf-8")
    (tmp_path / "keys.json").write_text(json.dumps({"version": 1, "keys": [], "knownExposures": [
        {"key": k, "file": f} for f, k in exposures]}), encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture"], check=True)
    return tmp_path, {"security": {"secretPatterns": "gates.json"}, "config": {"keys": "keys.json"}}


def test_a_new_secret_under_another_key_with_the_same_leaf_is_a_finding_not_known(tmp_path):
    settings = json.dumps({"Jwt": {"Key": KNOWN}, "Signing": {"Key": NEW}}, indent=2)
    root, manifest = _repo(tmp_path, {"appsettings.json": settings}, [("appsettings.json", "Jwt:Key")])
    assert [f.line for f in s.tree(root, manifest)] == [6], "Signing:Key is not Jwt:Key"
    assert len(s.KNOWN) == 1


def test_in_a_one_line_document_the_known_value_hides_only_itself(tmp_path):
    settings = json.dumps({"Jwt": {"Key": KNOWN}, "Signing": {"Key": NEW}})
    root, manifest = _repo(tmp_path, {"appsettings.json": settings}, [("appsettings.json", "Jwt:Key")])
    found = s.tree(root, manifest)
    assert len(found) == 1 and len(s.KNOWN) == 1, "two secrets on one line: one known, one found"
    assert NEW not in s.as_json(found) + "".join(map(str, found)), "a value is never printed"
    history = s.history(root, manifest)
    assert len(history) == 1, "history judges by the value too"


def test_a_utf16_file_and_a_quoted_name_are_read(tmp_path):
    utf16 = ("\ufeff" + json.dumps({"Smtp": {"Password": NEW}})).encode("utf-16-le")
    root, manifest = _repo(tmp_path, {"w.json": b"\xff\xfe" + utf16[2:], "Caf\u00e9.json": json.dumps({"Key": NEW})}, [])
    rules = sorted((f.path, f.rule) for f in s.tree(root, manifest))
    assert ("w.json", "no-config-secret") in rules, "a UTF-16 file is text"
    assert any(f.path == "Caf\u00e9.json" for f in s.history(root, manifest)), "a name git quotes is still scanned"


def test_the_built_in_set_knows_cloud_and_forge_tokens_and_a_password_named_first():
    def rules(text):
        return [f.rule for f in s.scan_path("a.txt", text.encode())]
    assert rules("id = " + "AKIA" + "ABCDEFGHIJKLMNOP") == ["aws-access-key"]
    assert rules("t = " + "ghp_" + "a" * 36) == ["github-token"]
    assert rules("Password=" + "Sup3rS3cret" + ";Server=db;") == ["connection-string-password-first"]


def test_a_reader_of_some_other_x_file_is_not_a_reader_of_this_key(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from delivery_host import host, manifest_of, with_driver
    from lib import identity, secret_reach

    root = host(tmp_path)
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
    (root / "ops" / "config").mkdir(parents=True, exist_ok=True)
    (root / "ops" / "config" / "keys.json").write_text(json.dumps({"version": 1, "keys": [
        {"key": "Jwt:Key", "env": ["Jwt__Key"], "sensitivity": "SECRET", "owner": "ops", "allowedSource": "server",
         "rotation": "on restore", "policy": {"required": True, "generate": {"bytes": 32}, "modules": ["edge"]}}]}),
        encoding="utf-8")
    m = manifest_of(root)
    m["config"] = {"keys": "ops/config/keys.json"}
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")
    with_driver(root, generatedSecrets={"reads": {"glob": "**/*.code", "pattern": r"@env@_FILE"}})
    main = root / "apps" / "edge" / "src" / "main.code"
    main.write_text("const LOG_FILE = '/var/log/a.log'\n", encoding="utf-8")
    assert len(secret_reach.problems(root, m)[0]) == 1, "LOG_FILE reads no generated key"
    main.write_text("key = read(env('Jwt__Key_FILE'))\n", encoding="utf-8")
    assert secret_reach.problems(root, m) == ([], [])


def test_a_module_cannot_declare_its_drivers_reading_by_becoming_an_image(tmp_path):
    from lib.delivery.model import ModelError, module_services

    manifest = {"modules": {"api": {"type": "dotnet-aspnet", "path": "api", "container": {
        "template": "", "image": "x:1", "generatedSecrets": {"reads": {"glob": "**/*", "pattern": "."}}}}}}
    with pytest.raises(ModelError, match="its driver's declaration"):
        module_services(manifest, "api")


def test_every_runtime_given_a_generated_secret_declares_the_uid_it_runs_as():
    registry = json.loads((Path(__file__).resolve().parents[2] / "drivers" / "registry.json").read_text(encoding="utf-8"))
    for driver in ("dotnet-aspnet", "node-api", "java-boot"):
        assert isinstance(registry[driver]["container"]["generatedSecrets"].get("uid"), int), driver


def test_outside_every_module_a_package_json_alone_is_not_a_web_app(tmp_path):
    from lib import tracked_outputs
    from lib.modules import driver_registry

    for rel, text in {"apps/api/x.cs": "x", ".github/actions/notify/package.json": "{}",
                      ".github/actions/notify/dist/index.js": "x", "site/package.json": "{}", "site/angular.json": "{}",
                      "site/dist/main.js": "x"}.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    manifest = {"modules": {"api": {"type": "dotnet-aspnet", "path": "apps/api"}, "ui": {"type": "node-spa", "path": "web"}}}
    found = tracked_outputs.problems(tmp_path, manifest, driver_registry())
    assert [f.split(":")[0] for f in found] == ["site/dist/"], found
