#!/usr/bin/env python3
"""Entry point for the offline refit CLI.

Examples:
    python scripts\run_refit.py --dry-run
    python scripts\run_refit.py --plot
    python scripts\run_refit.py --plot --output-folder _test-1 --no-lower-split
    python scripts\run_refit.py --folder nn1120-4_pd_ceo2_000 \
        --measurements "*-021" --delta-groups delta10 --plot
"""

import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parent.parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.utils.ir_fitting.refit_cli import main

if __name__ == "__main__":
    main()
