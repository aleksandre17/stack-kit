"""Found by the fourth audit: a settings file with a fake `gates` key hid every secret in it (C3); a known
exposure was whatever value stood at its key, so a new secret written there read as known (H1); a class
library outside every module tracked bin/ and obj/ unflagged (M4); a compose `build:` was read only in
one field order (L1). Every fixture secret is assembled at run time; no value is ever printed."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lib import compose_refs
from lib import secret_scan as s

SECRET = "Sup3r" + "S3cretValue" + "0123456789"
NEW = "fresh" + "fedcba9876543210"
OLD = "known" + "0123456789abcdef"
JWT = "eyJ" + "hbGciOiJIUzI1" + ".eyJ" + "zdWIiOiIxMjM0" + "." + "c2lnbmF0dXJlLXZhbHVl"


def _repo(tmp_path: Path, files: dict) -> Path:
    git = ["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t"]
    tmp_path.mkdir(parents=True, exist_ok=True)
    subprocess.run([*git, "init", "-q"], check=True)
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture"], check=True)
    return tmp_path


# --- C3 -----------------------------------------------------------------------------------------------------
def test_a_fake_gates_key_hides_no_secret_beside_it(tmp_path):
    fake = {"gates": [{"id": "x", "forbids": "x", "proves": {"path": "a", "text": "x"}, "admits": {"path": "a", "text": "y"}}],
            "ConnectionStrings": {"Db": f"Server=db;Database=app;User Id=sa;Password={SECRET};"},
            "Jwt": {"Token": JWT}}
    root = _repo(tmp_path, {"appsettings.json": json.dumps(fake, indent=2)})
    assert s.calibration_document((root / "appsettings.json").read_text(encoding="utf-8")), "the shape is the gate contract's"
    rules = sorted(f.rule for f in s.tree(root, {}))
    assert rules == ["connection-string", "jwt"], rules
    assert sorted(f.rule for f in s.history(root, {})) == ["connection-string", "jwt"], "history scans it too"
    assert SECRET not in "".join(map(str, s.tree(root, {}))), "a value is never printed"


def test_only_the_specimens_of_a_gate_document_are_exempt(tmp_path):
    doc = {"gates": [{"id": "no-jwt", "forbids": "eyJ", "proves": {"path": "a.json", "text": f"t = {JWT}"},
                      "admits": {"path": "a.json", "text": "t = __TOKEN__"}}],
           "note": f"Server=db;Password={SECRET};"}
    root = _repo(tmp_path, {"policy/edit-gates.json": json.dumps(doc, indent=2)})
    note = next(n for n, line in enumerate((root / "policy/edit-gates.json").read_text(encoding="utf-8").splitlines(), 1)
                if '"note"' in line)
    assert [(f.rule, f.line) for f in s.tree(root, {})] == [("connection-string", note)], "the specimen is calibration, the note is not"


# --- H1 -----------------------------------------------------------------------------------------------------
GATE = {"id": "no-config-secret", "paths": r"\.json$",
        "forbids": r"\"\w*(Key|Password)\"\s*:\s*\"(?!__[A-Z0-9_]+__\")[^\"]{8,}\"",
        "because": "a fixture", "instead": "a placeholder",
        "proves": {"path": "a.json", "text": "\"Key\": \"0123456789abcdef\""},
        "admits": {"path": "a.json", "text": "\"Key\": \"__JWT_KEY__\""}}


def _exposed(tmp_path: Path, value: str, row: dict) -> tuple[Path, dict]:
    root = _repo(tmp_path, {"appsettings.json": json.dumps({"Jwt": {"Key": value}}, indent=2),
                            "gates.json": json.dumps({"gates": [GATE]}),
                            "keys.json": json.dumps({"version": 1, "keys": [], "knownExposures": [
                                {"key": "Jwt:Key", "file": "appsettings.json", "tracking": "T-1", **row}]})})
    return root, {"security": {"secretPatterns": "gates.json"}, "config": {"keys": "keys.json"}}


def test_a_new_value_at_a_tracked_key_is_a_finding(tmp_path):
    root, manifest = _exposed(tmp_path, NEW, {"fingerprint": s.fingerprint(OLD)})
    assert [f.rule for f in s.tree(root, manifest)] == ["no-config-secret"] and s.KNOWN == [], "NEW is not OLD"
    assert len(s.history(root, manifest)) == 1 and s.KNOWN == []


def test_the_fingerprinted_value_itself_is_known_and_a_value_containing_it_is_not(tmp_path):
    root, manifest = _exposed(tmp_path, OLD, {"fingerprint": s.fingerprint(OLD)})
    assert s.tree(root, manifest) == [] and len(s.KNOWN) == 1
    assert s.unfingerprinted(root, manifest) == []
    root2, manifest2 = _exposed(tmp_path / "b", "x" + OLD + "y", {"fingerprint": s.fingerprint(OLD)})
    assert len(s.tree(root2, manifest2)) == 1 and s.KNOWN == [], "a different secret containing a tracked one"


def test_a_row_without_a_fingerprint_still_matches_and_is_warned_with_a_way_that_never_prints(tmp_path):
    root, manifest = _exposed(tmp_path, OLD, {})
    assert s.tree(root, manifest) == [] and len(s.KNOWN) == 1, "an existing host keeps working"
    warned = s.unfingerprinted(root, manifest)
    assert len(warned) == 1 and "scan secrets --fingerprint appsettings.json Jwt:Key" in warned[0]
    assert s.fingerprint_at(root, "appsettings.json", "Jwt:Key") == s.fingerprint(OLD)
    assert s.fingerprint_at(root, "appsettings.json", "Jwt__Key") == s.fingerprint(OLD)
    assert OLD not in warned[0]


def test_the_catalogue_schema_takes_a_fingerprint():
    schema = json.loads((Path(__file__).resolve().parents[2] / "config" / "config-keys.schema.json").read_text(encoding="utf-8"))
    row = schema["properties"]["knownExposures"]["items"]["properties"]
    assert row["fingerprint"]["pattern"] == "^[0-9a-f]{64}$"


# --- M4 -----------------------------------------------------------------------------------------------------
def _outputs(tmp_path: Path, files: dict) -> list[str]:
    from lib import tracked_outputs
    from lib.modules import driver_registry

    root = _repo(tmp_path, files)
    manifest = {"modules": {"api": {"type": "dotnet-aspnet", "path": "apps/api"}, "ui": {"type": "node-spa", "path": "web"}}}
    return [f.split(":")[0] for f in tracked_outputs.problems(root, manifest, driver_registry())]


def test_a_class_library_outside_every_module_that_tracks_bin_and_obj_is_flagged(tmp_path):
    found = _outputs(tmp_path, {"apps/api/x.cs": "x",
                                "libs/Shared/Shared.csproj": '<Project Sdk="Microsoft.NET.Sdk"></Project>',
                                "libs/Shared/bin/Debug/Shared.dll": "x", "libs/Shared/obj/project.assets.json": "{}"})
    assert found == ["libs/Shared/bin/", "libs/Shared/obj/"], found


def test_a_javascript_action_with_its_committed_dist_stays_unflagged(tmp_path):
    assert _outputs(tmp_path, {"apps/api/x.cs": "x", ".github/actions/notify/package.json": "{}",
                               ".github/actions/notify/dist/index.js": "x"}) == []


# --- L1 -----------------------------------------------------------------------------------------------------
def test_a_build_block_is_read_in_any_field_order_and_in_its_short_form():
    text = ("services:\n"
            "  api:\n    build:\n      args:\n        A: \"1\"\n      target: dev\n      dockerfile: Dockerfile.dev\n"
            "      context: ../../apps/api\n    image: x\n"
            "  ui:\n    build: ./web   # the short form\n"
            "  edge:\n    build: { dockerfile: edge.Dockerfile, context: ./edge }\n"
            "  plain:\n    build:\n      context: ./plain\n")
    assert compose_refs.references(text) == [("../../apps/api", "Dockerfile.dev"), ("./web", "Dockerfile"),
                                             ("./edge", "edge.Dockerfile"), ("./plain", "Dockerfile")]


def test_the_cli_prints_a_fingerprint_never_the_value_and_warns_of_a_row_without_one(tmp_path, monkeypatch, capsys):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from delivery_host import commit, host, manifest_of
    from lib import identity
    from lib.cli.main import main

    root = host(tmp_path)
    (root / "apps" / "edge" / "s.json").write_text(json.dumps({"Jwt": {"Key": OLD}}), encoding="utf-8")
    (root / "keys.json").write_text(json.dumps({"version": 1, "keys": [], "knownExposures": [
        {"key": "Jwt:Key", "file": "apps/edge/s.json", "tracking": "T-1"}]}), encoding="utf-8")
    m = manifest_of(root)
    m["config"] = {"keys": "keys.json"}
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    commit(root, "an exposure\n")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
    assert main(["scan", "secrets", "--fingerprint", "apps/edge/s.json", "Jwt:Key"]) == 0
    out = capsys.readouterr().out
    assert s.fingerprint(OLD) in out and OLD not in out
    main(["scan", "secrets"])
    out = capsys.readouterr().out
    assert "[warn] knownExposures: apps/edge/s.json Jwt:Key has no fingerprint" in out and OLD not in out
