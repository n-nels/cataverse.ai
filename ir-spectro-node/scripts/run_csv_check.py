#!/usr/bin/env python3
"""Entry point for the CSV integrity check (torn or partially written files).

Examples:
    python scripts\run_csv_check.py --all
    python scripts\run_csv_check.py --folder nn1120-3_pd_ceo2_001 --subfolder _reprocess
"""

import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parent.parent
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.utils.csv_integrity import main

if __name__ == "__main__":
    raise SystemExit(main())
