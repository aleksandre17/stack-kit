"""The secret scan (lib/secret_scan.py): each rule sees its shape, a placeholder is never one, an
example env file is never one, the operator's known leak is found by fingerprint, history is swept,
and no value is ever printed."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

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


def _repo(root: Path) -> list[str]:
    git = ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    return git


def _broken_repository(root: Path) -> None:
    """A repository git cannot read: its `.git` points at nothing (as a moved worktree's does)."""
    (root / ".git").write_text("gitdir: " + (root / "gone").as_posix() + "\n", encoding="utf-8")
    (root / "app.json").write_text('{"c": "Server=x;Password=Sup3rS3cret!;"}', encoding="utf-8")


def test_a_tree_git_cannot_list_is_not_run_never_clean(tmp_path: Path):
    """CWE-636: a scan that could not enumerate the tree scanned nothing -- it refuses, it never says clean."""
    _broken_repository(tmp_path)
    with pytest.raises(s.ScanError, match="ls-files") as raised:
        s.tree(tmp_path, {})
    assert not isinstance(raised.value, s.NotARepository)


def test_a_history_git_cannot_read_is_not_run_never_clean(tmp_path: Path):
    """CWE-390: a failed `git log` is a scan that did not happen, not an empty history."""
    _broken_repository(tmp_path)
    with pytest.raises(s.ScanError, match="git log"):
        s.history(tmp_path, {})


def test_a_tree_under_no_version_control_is_said_to_be_one(tmp_path: Path, monkeypatch):
    """Nothing tracked is a fact the scan states by its own name, never a clean verdict."""
    monkeypatch.delenv("GIT_DIR", raising=False)
    with pytest.raises(s.NotARepository, match="not under version control"):
        s.tree(tmp_path, {})


def test_a_large_text_file_is_scanned_and_a_binary_one_is_named_as_not_scanned(tmp_path: Path):
    """CWE-222/223: no size hides a secret, and a file the scan cannot read as text is named, never dropped."""
    git = _repo(tmp_path)
    (tmp_path / "seed.sql").write_text("-- filler\n" * 300_000 + "-- Server=x;Password=Sup3rS3cret!;\n", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64)
    subprocess.run([*git, "add", "-A"], check=True)
    assert (tmp_path / "seed.sql").stat().st_size > 2_000_000
    assert [f.path for f in s.tree(tmp_path, {})] == ["seed.sql"]
    assert [rel for rel, _why in s.UNSCANNED] == ["logo.png"]


def test_the_cli_names_every_file_it_did_not_scan(tmp_path: Path, monkeypatch, capsys):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from delivery_host import commit, host
    from lib import identity
    from lib.cli.main import main

    root = host(tmp_path)
    for name in ("a.png", "b.ico"):
        (root / name).write_bytes(b"IMG" + bytes(64))
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    commit(root, "two images\n")
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(root))
    monkeypatch.chdir(root)
    main(["scan", "secrets"])
    out = capsys.readouterr().out
    assert "NOT SCANNED: 2 tracked file(s) the scan cannot read as text -- a.png, b.ico" in out
