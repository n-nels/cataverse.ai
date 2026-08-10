"""Tests for Phase 8 metric aggregation and split coverage."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AUTOMATION_DIR = Path(__file__).resolve().parent.parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from sequential_forecasting.data.contract import TARGET_COLUMNS  # noqa: E402
from sequential_forecasting.data.examples import build_sequential_examples  # noqa: E402
from sequential_forecasting.evaluation import evaluate_records  # noqa: E402


def test_evaluation_uses_shared_test_cutoffs_and_strict_curve_suffix():
    frame = pd.DataFrame(
        {
            "Peak_Name": ["monomer_sum"] * 3,
            "Time (s)": [1.0, 2.5, 5.0],
            "Cumulative_Peak_Area": [0.2, 0.3, 0.4],
        }
    )
    values = [0.001, 0.5, 0.0001, 0.00005, 0.4, 0.2]
    for column, value in zip(TARGET_COLUMNS, values, strict=True):
        frame[column] = [np.nan, value, value]
    examples = build_sequential_examples(
        frame,
        experiment_id="experiment-1",
        successful=True,
        min_points=2,
        assignment="test",
    )
    prediction = list(examples[0].reference_target)
    baseline_records = [
        {
            "experiment_id": example.experiment_id,
            "cutoff_id": example.cutoff_id,
            "prediction": prediction,
            "prediction_source": "rf",
            "fallback_reason": None,
            "curve_rmse": 0.0,
            "curve_status": "valid",
        }
        for example in examples
    ]
    inference_records = [
        {
            "experiment_id": example.experiment_id,
            "cutoff_id": example.cutoff_id,
            "prediction": prediction,
            "prediction_source": "rf",
            "fallback_reason": None,
            "curve_times_s": frame["Time (s)"].tolist(),
            "curve_predicted_area": frame["Cumulative_Peak_Area"].tolist(),
            "curve_status": "valid",
        }
        for example in examples
    ]

    result = evaluate_records(
        examples,
        {
            "experiment-1": (
                frame["Time (s)"].to_numpy(dtype=float),
                frame["Cumulative_Peak_Area"].to_numpy(dtype=float),
            )
        },
        {
            "rf_only": baseline_records,
            "current_ode": baseline_records,
            "rf_ode_blend": baseline_records,
            "selected_model": inference_records,
        },
    )

    selected = result["methods"]["selected_model"]["overall"]
    assert selected["count"] == 3
    assert selected["valid_curve_count"] == 2
    assert selected["parameter"]["aggregate"]["avg_rmse"] == 0.0
    assert selected["curve_rmse"] == 0.0
