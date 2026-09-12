#!/usr/bin/env python3
"""Entry point for the offline kinetics classification CLI.

Examples:
    python scripts\\run_kinetics_classification.py --folder nn1120-3_pd_ceo2_004
    python scripts\\run_kinetics_classification.py --path <file>.csv --classifier drawdown
    python scripts\\run_kinetics_classification.py --validate --classifier combined
"""

import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parent.parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.utils.kinetics.cli import main

if __name__ == "__main__":
    main()
