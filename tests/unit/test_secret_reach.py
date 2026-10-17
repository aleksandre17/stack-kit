"""A generated secret reaches the app only if the app's code reads it -- refused otherwise (amendment 20).

Found by an audit of the first host: the kit made a JWT key on the server and handed it as
`Jwt__Key_FILE`, which ASP.NET Core does not read, so the app signed its tokens with a committed key
while every check was green. A driver now declares the form its runtime reads and what reading it
looks like in code; a module given a secret its code never reads is refused by validate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import identity, secret_reach  # noqa: E402

from delivery_host import host, manifest_of, with_driver  # noqa: E402

READS = {"directoryEnv": "Secrets__Dir", "reads": {"glob": "**/*.code", "pattern": r"load_secrets\(",
                                                    "how": "call load_secrets(dir) at startup"}}


def a_host(tmp_path, monkeypatch, reads=READS, code="print('hi')\n", under=""):
    root = host(tmp_path / under if under else tmp_path)
    # The driver registry is the current project's composed with the kit's: stand in the project.
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
    (root / "ops" / "config").mkdir(parents=True, exist_ok=True)
    (root / "ops" / "config" / "keys.json").write_text(json.dumps({"version": 1, "keys": [
        {"key": "Api:Key", "env": ["Api__Key"], "sensitivity": "SECRET", "owner": "ops", "allowedSource": "server",
         "rotation": "on restore", "policy": {"required": True, "generate": {"bytes": 32}, "modules": ["edge"]}}]}),
        encoding="utf-8")
    m = manifest_of(root)
    m["config"] = {"keys": "ops/config/keys.json"}
    if reads is not None:
        with_driver(root, generatedSecrets=reads)
    (root / identity.MANIFEST_FILENAME).write_text(json.dumps(m), encoding="utf-8")
    (root / "apps" / "edge" / "src" / "main.code").write_text(code, encoding="utf-8")
    return root, m


def test_a_secret_the_code_never_reads_is_refused_with_what_reading_it_looks_like(tmp_path, monkeypatch):
    root, m = a_host(tmp_path, monkeypatch)
    errors, warnings = secret_reach.problems(root, m)
    assert len(errors) == 1 and "Api:Key" in errors[0] and "Secrets__Dir" in errors[0]
    assert "call load_secrets(dir) at startup" in errors[0]


def test_a_secret_the_code_reads_passes(tmp_path, monkeypatch):
    root, m = a_host(tmp_path, monkeypatch, code="load_secrets(env('Secrets__Dir'))\n")
    assert secret_reach.problems(root, m) == ([], [])


def test_a_driver_that_declares_no_reading_cannot_be_given_a_generated_secret(tmp_path, monkeypatch):
    # Found by a re-audit: it was only warned about, so a secret could still be made and ignored.
    root, m = a_host(tmp_path, monkeypatch, reads=None)
    errors, warnings = secret_reach.problems(root, m)
    assert len(errors) == 1 and "<NAME>_FILE" in errors[0] and "declares no way" in errors[0] and warnings == []


def test_a_host_under_a_directory_named_like_an_output_is_still_read(tmp_path, monkeypatch):
    # Found by a re-audit: output directories were skipped by absolute path, so a host checked out
    # under `.../dist/` or `.../bin/` had every file skipped and was refused though its code read the key.
    root, m = a_host(tmp_path, monkeypatch, code="load_secrets(env('Secrets__Dir'))\n", under="bin")
    assert secret_reach.problems(root, m) == ([], [])
    (root / "apps" / "edge" / "src" / "main.code").write_text("print('hi')\n", encoding="utf-8")
    (root / "apps" / "edge" / "bin").mkdir()
    (root / "apps" / "edge" / "bin" / "old.code").write_text("load_secrets(x)\n", encoding="utf-8")
    assert len(secret_reach.problems(root, m)[0]) == 1, "what a toolchain wrote inside the module is never its code"
