"""The secret scan (lib/secret_scan.py): each rule sees its shape, a placeholder is never one, an
example env file is never one, the operator's known leak is found by fingerprint, history is swept,
and no value is ever printed."""
from __future__ import annotations

import subprocess
from pathlib import Path

from lib import secret_scan as s

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk0"


def rules(path: str, text: str, known=None) -> list[str]:
    return [f.rule for f in s.scan_path(path, text.encode(), known)]


def test_each_shape_is_seen():
    assert rules("a.cs", f'var t = "{JWT}";') == ["jwt"]
    assert rules("a.yml", "url: postgres://app:s3cr3tvalue@db:5432/app") == ["url-password"]
    assert rules("appsettings.json", '"Default": "Server=db;User Id=sa;Password=Sup3rS3cret!;"') == ["connection-string"]
    assert rules("k.txt", "-----BEGIN OPENSSH PRIVATE KEY-----") == ["private-key"]
    assert rules("ops/config/api/.env.prod", "A=b") == ["env-file"]
    assert rules("tools/helper.exe", "MZ\x90\x00") == ["tooling-binary"] and rules("tools/lib.jar", "PK\x03\x04") == ["tooling-binary"]


def test_a_placeholder_or_an_example_is_never_a_finding():
    assert rules("a.yml", "url: postgres://app:${DB_PASSWORD}@db/app") == []
    assert rules("a.json", '"Default": "Server=db;Password=__FROM_SECRET_STORE__;"') == []
    assert rules("a.md", "postgres://user:<password>@host/db") == []
    assert rules("ops/config/api/.env.example", "Password=changeme") == []
    assert rules("doc.md", "a token looks like eyJ...") == []


def test_a_known_leak_is_found_by_its_fingerprint_and_no_value_is_printed():
    leaked = "kR4nd0mL3akedT0ken99"
    found = s.scan_path("x.txt", f"key = {leaked}".encode(), {s.fingerprint(leaked)})
    assert [f.rule for f in found] == ["known-leak"] and leaked not in " ".join(map(str, found))
    assert "Sup3rS3cret" not in " ".join(map(str, s.scan_path("a.json", b"Password=Sup3rS3cret!;")))


def test_history_finds_what_the_tree_no_longer_holds(tmp_path: Path):
    git = ["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    (tmp_path / "app.json").write_text('{"c": "Server=x;Password=Sup3rS3cret!;"}', encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "oops"], check=True)
    (tmp_path / "app.json").write_text('{"c": "Server=x;Password=${DB_PASSWORD};"}', encoding="utf-8")
    subprocess.run([*git, "commit", "-qam", "fix"], check=True)
    assert s.tree(tmp_path, {}) == []
    hist = s.history(tmp_path, {})
    assert [f.rule for f in hist] == ["connection-string"] and "commit" in hist[0].where
    allowed = {"security": {"allow": [{"path": "app.json", "rule": "connection-string", "reason": "rotated 2026-10-16"}]}}
    assert s.history(tmp_path, allowed) == []
