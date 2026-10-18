"""What a failed tool said, shown short and kept whole (CWE-222): a message carries the END of a long output
-- a compose, engine, ssh or rsync run prints its progress first and why it failed last -- with the cut
stated, and the whole output is written beside the run records so nothing it said is lost."""
from __future__ import annotations

from datetime import datetime, timezone

from lib.project_root import find_project_root
from lib.runs import runs_dir

#: The most of an output a message carries, in characters: enough for a tool's closing error lines.
LIMIT = 1200


def excerpt(text: str, limit: int = LIMIT) -> str:
    """`text` whole when it is short; else its last `limit` characters, behind a line saying how much was
    cut and where the whole of it was kept."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"[{len(text) - limit} earlier character(s) cut; {_kept(text)}] ...{text[-limit:]}"


def _kept(text: str) -> str:
    try:
        held = runs_dir(find_project_root()) / "output"
        held.mkdir(exist_ok=True)
        path = held / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.log"
        path.write_text(text, encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        return f"the whole output was NOT kept ({e})"
    return f"the whole output: {path}"
