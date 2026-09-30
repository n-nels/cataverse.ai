#!/usr/bin/env python3
"""Entry point for the offline kinetics model-fitting CLI.

Examples:
    python scripts\\run_kinetics_fit.py --folder nn1120-3_pd_ceo2_004 --model pfo --peak-names cluster_sum
    python scripts\\run_kinetics_fit.py --path <file>.csv --model secondary_pfo --peak-names monomer_sum
"""

import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parent.parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.utils.kinetics.fit_cli import main

if __name__ == "__main__":
    main()
