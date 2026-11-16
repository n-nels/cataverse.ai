#!/usr/bin/env python3
"""Entry point for launching the OPUS ZMQ server."""

import os
os.environ.setdefault("MPLBACKEND", "Agg") # disable tkinter backend for matplotlib
# One BLAS thread: the 24-peak joint fit is ill-conditioned, and multithreaded
# BLAS rounding moves it by up to ~1e-3 au per peak area between runs. Pinned,
# a refit of the same spectrum is reproducible (docs/spec-live-migration.md O3).
# Must be set before numpy is imported.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
from pathlib import Path
import sys

SRC_PATH = Path(__file__).resolve().parent.parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.instrument.main import main as run_opus_server  # type: ignore


def main() -> None:
    """Start the OPUS server using the refactored layout."""
    run_opus_server()


if __name__ == "__main__":
    main()
