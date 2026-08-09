"""Tests for the Phase 2 RF-to-sequential example adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AUTOMATION_DIR = Path(__file__).resolve().parent.parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from sequential_forecasting.data.adapter import (  # noqa: E402
    build_examples_from_artifacts,
    write_examples_artifact,
)
from sequential_forecasting.data.contract import TARGET_COLUMNS  # noqa: E402


def _write_experiment(artifact_dir: Path, name: str, assignment: str) -> dict[str, str]:
    csv_path = artifact_dir / f"{name}_CarbonylPeakArea.csv"
    json_path = artifact_dir / f"{name}_expParams.json"
    frame = pd.DataFrame(
        {
            "Peak_Name": ["monomer_sum"] * 3,
            "Time (s)": [1.0, 2.0, 3.0],
            "Cumulative_Peak_Area": [0.1, 0.2, 0.3],
        }
    )
    for column in TARGET_COLUMNS:
        frame[column] = [np.nan, 1.0, 2.0]
    frame.to_csv(csv_path, index=False)
    json_path.write_text(
        json.dumps({"filename_flags": {"exp_success": True}}), encoding="utf-8"
    )
    return {
        "base_name": name,
        "assignment": assignment,
        "json_path": str(json_path),
        "csv_path": str(csv_path),
    }


def test_adapter_joins_rf_predictions_and_keeps_cutoffs_in_one_partition(tmp_path):
    assignments = [
        _write_experiment(tmp_path, "experiment-a", "train"),
        _write_experiment(tmp_path, "experiment-b", "test"),
    ]
    (tmp_path / "run_config.json").write_text(
        json.dumps({"minimum_fit_points": 2, "time_tolerance_s": 1e-3}),
        encoding="utf-8",
    )
    pd.DataFrame(assignments).to_csv(tmp_path / "split_assignments.csv", index=False)
    prediction_rows = []
    for index, assignment in enumerate(assignments):
        row = {
            "base_name": assignment["base_name"],
            "prediction_provenance": "out_of_fold"
            if assignment["assignment"] == "train"
            else "held_out_test",
        }
        row.update({column: float(index + 1) for column in TARGET_COLUMNS})
        prediction_rows.append(row)
    pd.DataFrame(prediction_rows).to_csv(tmp_path / "rf_predictions.csv", index=False)

    examples = build_examples_from_artifacts(tmp_path)

    assert len(examples) == 6
    for experiment_id, expected_assignment in (
        ("experiment-a", "train"),
        ("experiment-b", "test"),
    ):
        experiment_examples = [
            example for example in examples if example.experiment_id == experiment_id
        ]
        assert {example.assignment for example in experiment_examples} == {
            expected_assignment
        }
        assert {example.rf_prediction_provenance for example in experiment_examples} == {
            "out_of_fold" if expected_assignment == "train" else "held_out_test"
        }
        assert all(example.observation_fraction <= 1.0 for example in experiment_examples)

    output_dir = write_examples_artifact(examples, tmp_path / "examples")
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["example_count"] == 6
    assert manifest["experiment_count"] == 2
