#!/usr/bin/env python3
"""CLI entry for stack-kit config-gen."""
from __future__ import annotations

import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from lib.config_gen import main

if __name__ == "__main__":
    raise SystemExit(main())
