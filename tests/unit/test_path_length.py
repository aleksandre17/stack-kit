"""No tracked path is long enough to break a Windows checkout of the kit under a host's own folders
(found adopting a foreign project: `git submodule add` failed with "Filename too long" on a fixture).
Windows' MAX_PATH is 260; a host vendoring the kit two levels deep under a long user folder leaves the
kit's own paths about 80 characters."""
from __future__ import annotations

import subprocess
from pathlib import Path

LIMIT = 80


def test_no_tracked_path_is_longer_than_a_deep_windows_checkout_allows():
    root = Path(__file__).resolve().parents[2]
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True)
    paths = [p for p in listed.stdout.decode("utf-8", "replace").split("\0") if p]
    long = sorted((len(p), p) for p in paths if len(p) > LIMIT)
    assert not long, f"tracked paths over {LIMIT} characters: {long[-3:]}"
