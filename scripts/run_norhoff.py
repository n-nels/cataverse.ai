#!/usr/bin/env python3
"""Entry point for running the Norhof LN2 pump script."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys


SRC_PATH = Path(__file__).resolve().parent.parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


def main() -> None:
    """Run the Norhof LN2 pump control loop."""
    runpy.run_module("src.utils.norhof", run_name="__main__")


if __name__ == "__main__":
    main()
