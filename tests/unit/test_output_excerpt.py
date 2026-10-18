"""A failed tool's output, shown short and kept whole (lib/delivery/output.py, CWE-222): a short output is
shown as it is; a long one shows its END -- where a tool says why it failed -- behind a line naming how
much was cut and where the whole of it was kept."""
from __future__ import annotations

from pathlib import Path

from lib import identity
from lib.delivery.output import excerpt


def test_a_short_output_is_shown_whole():
    assert excerpt("  exit 1: no such image\n") == "exit 1: no such image"


def test_a_long_output_shows_its_end_says_the_cut_and_keeps_the_whole(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(identity.env_name("PROJECT_ROOT"), str(tmp_path))
    said = "pulling layer\n" * 200 + "Error: port 8080 is already allocated"
    shown = excerpt(said, limit=60)
    assert shown.endswith("Error: port 8080 is already allocated")
    assert f"[{len(said) - 60} earlier character(s) cut; the whole output: " in shown
    kept = Path(shown.split("the whole output: ", 1)[1].split("]", 1)[0])
    assert kept.read_text(encoding="utf-8") == said
    assert (tmp_path / identity.RUNS_DIR.split("/")[0] / ".gitignore").is_file()
