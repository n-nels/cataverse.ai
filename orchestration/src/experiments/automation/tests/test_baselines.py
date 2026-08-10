"""Tests for the required sequential forecasting baselines."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AUTOMATION_DIR = Path(__file__).resolve().parent.parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from sequential_forecasting.baselines import (  # noqa: E402
    baseline_prediction,
    evaluate_baselines,
    select_blend_weight,
)
from sequential_forecasting.data.contract import TARGET_COLUMNS  # noqa: E402
from sequential_forecasting.data.examples import build_sequential_examples  # noqa: E402


def _examples():
    frame = pd.DataFrame(
        {
            "Peak_Name": ["monomer_sum"] * 3,
            "Time (s)": [1.0, 2.0, 3.0],
            "Cumulative_Peak_Area": [0.2, 0.3, 0.4],
        }
    )
    fit_values = [0.001, 0.5, 0.0001, 0.00005, 0.4, 0.2]
    for column, value in zip(TARGET_COLUMNS, fit_values, strict=True):
        frame[column] = [np.nan, value, value]
    rf_prediction = (0.002, 0.6, 0.0002, 0.0001, 0.5, 0.2)
    return build_sequential_examples(
        frame,
        experiment_id="experiment-1",
        successful=True,
        min_points=2,
        assignment="validation",
        rf_prediction=rf_prediction,
        rf_prediction_provenance="out_of_fold",
    ), frame


def test_baselines_pass_through_known_q0_and_use_current_fit():
    examples, _ = _examples()

    rf = baseline_prediction(examples[0], "rf_only")
    current = baseline_prediction(examples[1], "current_ode")

    assert rf.source == "rf"
    assert rf.parameters is not None
    assert rf.parameters.q_0 == examples[0].q_0
    assert current.source == "current_ode"
    assert current.parameters is not None
    assert current.parameters.q_0 == examples[1].q_0


def test_blend_weight_uses_validation_examples_and_scores_all_baselines():
    examples, frame = _examples()
    weight, scores = select_blend_weight(examples, candidates=(0.0, 0.5, 1.0))
    observations = {
        "experiment-1": (
            frame["Time (s)"].to_numpy(dtype=float),
            frame["Cumulative_Peak_Area"].to_numpy(dtype=float),
        )
    }

    records = evaluate_baselines(examples, observations, blend_weight=weight)

    assert weight in {0.0, 0.5, 1.0}
    assert set(scores) == {"0.0", "0.5", "1.0"}
    assert len(records) == len(examples) * 3
    assert {record.baseline for record in records} == {
        "rf_only",
        "current_ode",
        "rf_ode_blend",
    }
    assert all(record.parameter_rmse is not None for record in records)
    assert all(record.curve_status in {"valid", "no_remaining_points"} for record in records)
