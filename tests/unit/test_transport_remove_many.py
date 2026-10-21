"""SshTransport.remove_many: a workspace with many files gone is removed through stdin, never one huge command line."""
import subprocess

from lib.delivery.transport import SshTransport


class _Ran:
    def __init__(self):
        self.returncode, self.stdout, self.stderr = 0, b"", b""


def test_many_paths_go_through_stdin_nul_separated_and_the_command_line_stays_short(monkeypatch):
    seen = {}

    def run(argv, input=None, capture_output=False):
        seen["argv"], seen["input"] = argv, input
        return _Ran()

    monkeypatch.setattr(subprocess, "run", run)
    t = SshTransport("user@host", [], confine="/srv/ws")
    rels = [f"wwwroot/assets/chunk-{i:05d}-with-a-long-hashed-name.js" for i in range(5000)]

    t.remove_many("/srv/ws", rels)

    command_line = " ".join(seen["argv"])
    assert len(command_line) < 1000  # was ~300 000 characters: past Windows' 32 767 (WinError 206)
    assert command_line.endswith("'xargs -0 rm -f --'")
    paths = seen["input"].split(b"\0")
    assert len(paths) == 5000 and paths[0] == b"/srv/ws/wwwroot/assets/chunk-00000-with-a-long-hashed-name.js"


def test_a_name_with_spaces_or_quotes_reaches_rm_whole(monkeypatch):
    seen = {}
    monkeypatch.setattr(subprocess, "run", lambda argv, input=None, capture_output=False: seen.update(input=input) or _Ran())
    t = SshTransport("user@host", [], confine="/srv/ws")

    t.remove_many("/srv/ws", ["a b/c'd.txt"])

    assert seen["input"] == "/srv/ws/a b/c'd.txt".encode("utf-8")
