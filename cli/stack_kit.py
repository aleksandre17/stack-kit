#!/usr/bin/env python3
"""The stack-kit CLI entry point: every launcher (cli/stack-kit.ps1, cli/stack-kit.sh, a host's
ops/cli/stack-kit.*) runs this file, and this file runs lib/cli."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.dont_write_bytecode = True

from lib.cli.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
