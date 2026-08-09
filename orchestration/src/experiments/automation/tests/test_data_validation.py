"""Tests for Phase 1 data-contract validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AUTOMATION_DIR = Path(__file__).resolve().parent.parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from sequential_forecasting.data.contract import TARGET_COLUMNS  # noqa: E402
from sequential_forecasting.data.validation import validate_experiment  # noqa: E402


def test_validate_experiment_checks_realistic_prefix_contract(tmp_path):
    csv_path = tmp_path / "experiment-1_CarbonylPeakArea.csv"
    json_path = tmp_path / "experiment-1_expParams.json"
    frame = pd.DataFrame(
        {
            "File": ["delta5", "delta6", "delta7", "delta8"],
            "Delta_Group": ["delta5", "delta6", "delta7", "delta8"],
            "Peak_Name": ["monomer_sum"] * 4,
            "Time (s)": [1.0, 1.0005, 2.0, 3.0],
            "Cumulative_Peak_Area": [0.1, 0.2, 0.3, 0.4],
            "pfo-sec_r^2": [np.nan, np.nan, 0.9, 0.95],
            "pfo-sec_rmse": [np.nan, np.nan, 0.1, 0.05],
        }
    )
    for index, column in enumerate(TARGET_COLUMNS):
        frame[column] = [np.nan, np.nan, index + 1.0, index + 2.0]
    frame.to_csv(csv_path, index=False)
    json_path.write_text(
        json.dumps({"filename_flags": {"exp_success": True}}), encoding="utf-8"
    )
    row = pd.Series(
        {
            "base_name": "experiment-1",
            "assignment": "train",
            "json_path": str(json_path),
            "csv_path": str(csv_path),
        }
    )

    summary, statuses = validate_experiment(
        row,
        min_points=2,
        time_tolerance_s=1e-3,
    )

    assert summary["cutoff_count"] == 3
    assert summary["collision_count"] == 1
    assert summary["reference_status"] == "fit_valid"
    assert statuses["fit_not_yet_eligible"] == 1
    assert statuses["fit_valid"] == 2
