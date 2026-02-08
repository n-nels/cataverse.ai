#!/usr/bin/env python3
"""Simple CLI wrapper around the peak fitting workflow."""

from pathlib import Path
import sys

SRC_PATH = Path(__file__).resolve().parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.analysis.peak_fitting import main as run_peak_fit  # type: ignore


def main() -> None:
    """Route CLI args to the existing peak fitting entry point."""
    run_peak_fit()


if __name__ == "__main__":
    main()
