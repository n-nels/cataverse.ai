"""Tests for Phase 0 configuration and split artifact helpers."""

from __future__ import annotations

from datetime import datetime
import sys
from pathlib import Path

import pandas as pd

AUTOMATION_DIR = Path(__file__).resolve().parent.parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from extract import ExperimentRecord  # noqa: E402
from load import Dataset, DatasetSplit  # noqa: E402
from sequential_forecasting.data.contract import TARGET_COLUMNS  # noqa: E402
from sequential_forecasting.config import (  # noqa: E402
    DEFAULT_EXCLUDE_FOLDERS,
    RunConfig,
)
from sequential_forecasting.rf.splits import assignment_table  # noqa: E402


def test_run_config_contains_shared_selection_contract():
    config = RunConfig()

    assert config.data_root == r"X:\peakFit"
    assert config.exclude_folders == DEFAULT_EXCLUDE_FOLDERS
    assert config.minimum_fit_points == 4
    assert config.split_seed == 42
    assert config.target_order == TARGET_COLUMNS


def test_assignment_table_persists_one_partition_per_experiment(tmp_path):
    names = ["experiment-a", "experiment-b", "experiment-c"]
    frame = pd.DataFrame({"feature": [1.0, 2.0, 3.0]}, index=names)
    targets = pd.DataFrame({"target": [1.0, 2.0, 3.0]}, index=names)
    records = [
        ExperimentRecord(
            base_name=name,
            datetime=datetime(2026, 1, index + 1),
            json_path=tmp_path / f"{name}_expParams.json",
            csv_path=tmp_path / f"{name}_CarbonylPeakArea.csv",
            json_data={},
        )
        for index, name in enumerate(names)
    ]
    dataset = Dataset(X=frame, y=targets, records=records)
    splits = DatasetSplit(
        X_train=frame.iloc[[0]],
        y_train=targets.iloc[[0]],
        X_val=frame.iloc[[1]],
        y_val=targets.iloc[[1]],
        X_test=frame.iloc[[2]],
        y_test=targets.iloc[[2]],
    )

    assignments = assignment_table(splits, dataset)

    assert assignments["base_name"].tolist() == names
    assert assignments["assignment"].tolist() == ["train", "validation", "test"]
    assert assignments["csv_path"].str.endswith("_CarbonylPeakArea.csv").all()
