#!/usr/bin/env python3
"""Entry point for the offline baseline-experiment CLI.

Examples:
    python scripts\\run_baseline_experiment.py
    python scripts\\run_baseline_experiment.py --with-twin
    python scripts\\run_baseline_experiment.py --anchor-prominence-frac 0.9
    python scripts\\run_baseline_experiment.py --folder nn1120-3_pd_ceo2_004 \\
        --measurements "*-000" --delta-groups delta10 --run-name probe
"""

import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parent.parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.utils.ir_fitting.baseline_cli import main

if __name__ == "__main__":
    main()
