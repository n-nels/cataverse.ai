"""Tests for the initial regularized sequential correction model."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

AUTOMATION_DIR = Path(__file__).resolve().parent.parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from sequential_forecasting.data.contract import TARGET_COLUMNS  # noqa: E402
from sequential_forecasting.data.examples import build_sequential_examples  # noqa: E402
from sequential_forecasting.gated_blend_model import fit_gated_blend_model  # noqa: E402
from sequential_forecasting.sequential_model import (  # noqa: E402
    LEARNED_TARGET_COLUMNS,
    example_features,
    feature_names,
    feature_matrix,
    fit_correction_model,
    select_initial_model,
)
from sequential_forecasting.trajectory_extrapolation_model import (  # noqa: E402
    fit_trajectory_extrapolation_model,
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
        gated_blend_bin_counts=(),
        observations=None,
    )

    assert model.ridge_alpha in {0.1, 1.0}
    assert manifest["training_experiment_count"] == 2
    assert manifest["validation_experiment_count"] == 1
    assert manifest["test_used_for_selection"] is False
    assert set(manifest["candidate_results"]) == {"0.1", "1.0"}


def test_model_selection_scores_every_validation_cutoff_with_rf_fallback():
    """A candidate that never produces a valid prediction must still be
    scored on every validation cutoff (via RF fallback), not silently
    excluded — spec.md #12 forbids dropping invalid predictions unscored."""
    train_a, _ = _examples("train-1", "train", 0.0001)
    validation, _ = _examples("validation-1", "validation", 0.0003)
    examples = tuple(train_a) + tuple(validation)

    _, manifest = select_initial_model(
        examples,
        ridge_alphas=(1.0,),
        gated_blend_bin_counts=(),
        observations=None,
    )

    result = manifest["candidate_results"]["1.0"]
    assert result["valid_prediction_count"] == len(validation)


def test_gated_blend_shares_weight_across_ka_and_kp_and_prefers_ode_when_exact():
    train_a, _ = _examples("train-1", "train", 0.01)
    train_b, _ = _examples("train-2", "train", 0.02)
    examples = tuple(train_a) + tuple(train_b)

    model = fit_gated_blend_model(examples, bin_count=1)

    assert model.bin_count == 1
    # The fixture's current fit exactly equals the reference target, so the
    # clipped least-squares weight should fully prefer the ODE fit.
    for weights in model.weights.values():
        assert weights[0] == pytest.approx(1.0)

    prediction = model.predict_parameters(train_a[-1])
    assert prediction.parameters is not None
    assert prediction.parameters.q_0 == train_a[-1].q_0
    assert 0.0 <= prediction.parameters.k_p <= prediction.parameters.k_a


def test_gated_blend_falls_back_before_first_valid_fit():
    train_a, _ = _examples("train-1", "train", 0.01)
    train_b, _ = _examples("train-2", "train", 0.02)
    examples = tuple(train_a) + tuple(train_b)
    model = fit_gated_blend_model(examples, bin_count=1)

    prediction = model.predict_parameters(train_a[0])

    assert prediction.parameters is None
    assert prediction.reason is not None and "current_fit" in prediction.reason


def test_model_selection_can_select_gated_blend_candidate():
    train_a, _ = _examples("train-1", "train", 0.02)
    train_b, _ = _examples("train-2", "train", 0.02)
    validation, _ = _examples("validation-1", "validation", 0.02)
    examples = tuple(train_a) + tuple(train_b) + tuple(validation)

    model, manifest = select_initial_model(
        examples,
        ridge_alphas=(),
        gated_blend_bin_counts=(1,),
        observations=None,
    )

    assert manifest["selected_candidate"] == "gated_blend_1"
    assert manifest["learned_model_selected"] is True
    assert manifest["selected_gated_blend_bin_count"] == 1
    assert model.bin_count == 1


def _examples_with_csv(tmp_path, name: str, assignment: str, rf_offset: float, fit_values=None):
    """Build examples backed by a real CSV so `csv_path` is populated.

    Trajectory extrapolation re-reads `example.csv_path` to recover the
    per-row rolling-fit history, unlike the other candidates, which only use
    the single current-cutoff snapshot already carried on the example.
    """
    fit_values = list(fit_values) if fit_values is not None else [
        0.001, 0.5, 0.0001, 0.00005, 0.4, 0.2,
    ]
    frame = pd.DataFrame(
        {
            "Peak_Name": ["monomer_sum"] * 3,
            "Time (s)": [1.0, 2.0, 3.0],
            "Cumulative_Peak_Area": [0.2, 0.3, 0.4],
        }
    )
    for column, value in zip(TARGET_COLUMNS, fit_values, strict=True):
        frame[column] = [np.nan, value, value]
    csv_path = tmp_path / f"{name}.csv"
    frame.to_csv(csv_path, index=False)
    rf_prediction = tuple(value + rf_offset for value in fit_values[:-1]) + (fit_values[-1],)
    return build_sequential_examples(
        frame,
        experiment_id=name,
        successful=True,
        min_points=2,
        assignment=assignment,
        csv_path=str(csv_path),
        rf_prediction=rf_prediction,
        rf_prediction_provenance="out_of_fold",
    )


def test_trajectory_extrapolation_predicts_when_sufficient_history(tmp_path):
    examples = _examples_with_csv(tmp_path, "traj-1", "train", 0.01)
    model = fit_trajectory_extrapolation_model(min_trajectory_points=2)

    prediction = model.predict_parameters(examples[-1])

    assert prediction.parameters is not None
    assert prediction.parameters.q_0 == examples[-1].q_0
    assert prediction.parameters.k_a == pytest.approx(0.001)
    assert prediction.parameters.k_p == pytest.approx(0.00005)
    assert 0.0 <= prediction.parameters.k_p <= prediction.parameters.k_a


def test_trajectory_extrapolation_falls_back_before_first_valid_fit(tmp_path):
    examples = _examples_with_csv(tmp_path, "traj-gate", "train", 0.01)
    model = fit_trajectory_extrapolation_model(min_trajectory_points=2)

    # examples[0] has only one observation; its own cutoff has no fit yet.
    prediction = model.predict_parameters(examples[0])

    assert prediction.parameters is None
    assert prediction.reason == "current_fit_fit_not_yet_eligible"


def test_trajectory_extrapolation_falls_back_when_history_is_short(tmp_path):
    examples = _examples_with_csv(tmp_path, "traj-2", "train", 0.01)
    model = fit_trajectory_extrapolation_model(min_trajectory_points=2)

    # Only one fit-valid row exists in the prefix through the second cutoff.
    prediction = model.predict_parameters(examples[1])

    assert prediction.parameters is None
    assert prediction.reason == "insufficient_trajectory_points"

    strict_model = fit_trajectory_extrapolation_model(min_trajectory_points=3)
    strict_prediction = strict_model.predict_parameters(examples[-1])
    assert strict_prediction.parameters is None
    assert strict_prediction.reason == "insufficient_trajectory_points"


def test_trajectory_extrapolation_clips_kp_into_ka_bound(tmp_path):
    # k_p (0.005) exceeds k_a (0.001) in the raw stored fit; a real fitter
    # would never emit this, but the extrapolation must repair it by
    # construction rather than trust independently-extrapolated coupling.
    examples = _examples_with_csv(
        tmp_path,
        "traj-3",
        "train",
        0.0,
        fit_values=[0.001, 0.5, 0.0001, 0.005, 0.4, 0.2],
    )
    model = fit_trajectory_extrapolation_model(min_trajectory_points=2)

    prediction = model.predict_parameters(examples[-1])

    assert prediction.parameters is not None
    assert prediction.parameters.k_p == pytest.approx(prediction.parameters.k_a)


def test_model_selection_can_select_trajectory_candidate(tmp_path):
    train_a = _examples_with_csv(tmp_path, "traj-train-1", "train", 0.02)
    train_b = _examples_with_csv(tmp_path, "traj-train-2", "train", 0.02)
    validation = _examples_with_csv(tmp_path, "traj-validation-1", "validation", 0.02)
    examples = tuple(train_a) + tuple(train_b) + tuple(validation)

    model, manifest = select_initial_model(
        examples,
        ridge_alphas=(),
        gated_blend_bin_counts=(),
        trajectory_min_points=(2,),
        observations=None,
    )

    assert manifest["selected_candidate"] == "trajectory_2"
    assert manifest["learned_model_selected"] is True
    assert manifest["selected_trajectory_min_points"] == 2
    assert model.min_trajectory_points == 2
