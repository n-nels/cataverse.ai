#!/usr/bin/env python3
"""Entry point for launching the OPUS ZMQ server."""

from pathlib import Path
import sys

SRC_PATH = Path(__file__).resolve().parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.instrument.main import main as run_opus_server  # type: ignore


def main() -> None:
    """Start the OPUS server using the refactored layout."""
    run_opus_server()


if __name__ == "__main__":
    main()
