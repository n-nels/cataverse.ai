"""Tests for Phase 0 configuration and split artifact helpers."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
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
    DEFAULT_ODE_FIT_MODE,
    DEFAULT_ODE_TIMEOUT_SECONDS,
    RunConfig,
)
from sequential_forecasting.rf.splits import assignment_table  # noqa: E402
from sequential_forecasting.rf.validation import validate_rf_boundary  # noqa: E402


def test_run_config_contains_shared_selection_contract():
    config = RunConfig()

    assert config.data_root == r"X:\peakFit"
    assert config.exclude_folders == DEFAULT_EXCLUDE_FOLDERS
    assert config.minimum_fit_points == 4
    assert config.split_seed == 42
    assert config.target_order == TARGET_COLUMNS
    assert config.ode_fit_mode == DEFAULT_ODE_FIT_MODE
    assert config.ode_timeout_seconds == DEFAULT_ODE_TIMEOUT_SECONDS
    assert config.ode_prior_fit_carry_forward is False


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


def test_validate_rf_boundary_requires_held_out_prediction_provenance(tmp_path):
    assignments = pd.DataFrame(
        {
            "base_name": ["experiment-a", "experiment-b", "experiment-c"],
            "assignment": ["train", "validation", "test"],
            "json_path": ["a.json", "b.json", "c.json"],
            "csv_path": ["a.csv", "b.csv", "c.csv"],
        }
    )
    assignments.to_csv(tmp_path / "split_assignments.csv", index=False)
    predictions = pd.DataFrame(
        {
            "base_name": ["experiment-a", "experiment-b", "experiment-c"],
            "prediction_provenance": ["out_of_fold", "out_of_fold", "held_out_test"],
            "fold_id": [1, 2, None],
            "training_experiment_count": [1, 1, 1],
            **{column: [1.0, 2.0, 3.0] for column in TARGET_COLUMNS},
        }
    )
    prediction_path = tmp_path / "rf_predictions.csv"
    predictions.to_csv(prediction_path, index=False)
    prediction_hash = hashlib.sha256(prediction_path.read_bytes()).hexdigest()
    (tmp_path / "prediction_provenance.json").write_text(
        json.dumps(
            {
                "target_order": list(TARGET_COLUMNS),
                "sequential_target_order": list(TARGET_COLUMNS),
                "test_model_excludes_test_experiments": True,
                "prediction_csv_sha256": prediction_hash,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "split_fingerprint.json").write_text(
        json.dumps({"hash": "split-hash"}), encoding="utf-8"
    )
    (tmp_path / "dataset_fingerprint.json").write_text(
        json.dumps({"hash": "dataset-hash"}), encoding="utf-8"
    )

    report = validate_rf_boundary(tmp_path)

    assert report["valid"] is True
    assert report["assignment_counts"] == {"train": 1, "validation": 1, "test": 1}
    assert report["prediction_provenance_counts"] == {
        "out_of_fold": 2,
        "held_out_test": 1,
    }
