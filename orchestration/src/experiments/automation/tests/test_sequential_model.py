"""Tests for the initial regularized sequential correction model."""

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
from sequential_forecasting.sequential_model import (  # noqa: E402
    LEARNED_TARGET_COLUMNS,
    example_features,
    feature_names,
    feature_matrix,
    fit_correction_model,
    select_initial_model,
)


def _examples(name: str, assignment: str, rf_offset: float):
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
    rf_prediction = (
        0.001 + rf_offset,
        0.5 + rf_offset,
        0.0001 + rf_offset,
        0.00005 + rf_offset,
        0.4 + rf_offset,
        0.2,
    )
    return build_sequential_examples(
        frame,
        experiment_id=name,
        successful=True,
        min_points=2,
        assignment=assignment,
        rf_prediction=rf_prediction,
        rf_prediction_provenance="out_of_fold",
    ), frame


def test_features_are_cutoff_available_and_model_passes_through_q0():
    examples, _ = _examples("train-1", "train", 0.0001)
    vector = example_features(examples[0])

    assert len(vector) == len(feature_names())
    assert vector[feature_names().index("observation_count")] == 1.0
    model = fit_correction_model(examples, ridge_alpha=1.0)
    prediction = model.predict_parameters(examples[-1])
    assert prediction.parameters is not None
    assert prediction.parameters.q_0 == examples[-1].q_0
    assert feature_matrix(examples).shape == (len(examples), len(feature_names()))
    assert len(model.target_names) == len(LEARNED_TARGET_COLUMNS)


def test_model_selection_uses_train_fit_and_validation_selection_only():
    train_a, _ = _examples("train-1", "train", 0.0001)
    train_b, _ = _examples("train-2", "train", 0.0002)
    validation, _ = _examples("validation-1", "validation", 0.0003)
    examples = tuple(train_a) + tuple(train_b) + tuple(validation)

    model, manifest = select_initial_model(
        examples,
        ridge_alphas=(0.1, 1.0),
        observations=None,
    )

    assert model.ridge_alpha in {0.1, 1.0}
    assert manifest["training_experiment_count"] == 2
    assert manifest["validation_experiment_count"] == 1
    assert manifest["test_used_for_selection"] is False
    assert set(manifest["candidate_results"]) == {"0.1", "1.0"}
