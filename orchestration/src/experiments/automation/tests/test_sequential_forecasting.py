"""Tests for sequential data and local ODE utilities."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AUTOMATION_DIR = Path(__file__).resolve().parent.parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from sequential_forecasting.data import (  # noqa: E402
    TARGET_COLUMNS,
    extract_reference_target,
    flatten_monomer_rows,
)
from sequential_forecasting.examples import (  # noqa: E402
    FIT_MISSING_FOR_CUTOFF,
    FIT_NOT_YET_ELIGIBLE,
    FIT_VALID,
    build_sequential_examples,
)
from sequential_forecasting.ode import (  # noqa: E402
    SecondaryPfoParameters,
    build_cutoff_forecast,
    remaining_curve_rmse,
    solve_secondary_pfo,
)


def _observation_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "File": ["delta5", "delta6", "delta7", "delta8"],
            "Delta_Group": ["delta5", "delta6", "delta7", "delta8"],
            "Peak_Name": ["monomer_sum"] * 4,
            "Time (s)": [1.0, 1.0005, 2.0, 3.0],
            "Cumulative_Peak_Area": [0.1, 0.2, 0.3, 0.4],
        }
    )


def test_flatten_monomer_rows_merges_tolerant_collisions():
    flattened, collisions = flatten_monomer_rows(
        _observation_frame(), time_tolerance_s=1e-3
    )

    assert len(flattened) == 3
    assert flattened["Time (s)"].tolist() == [1.0005, 2.0, 3.0]
    assert flattened["Cumulative_Peak_Area"].tolist() == [0.2, 0.3, 0.4]
    assert len(collisions) == 1
    assert collisions[0].retained_source_row == 1
    assert collisions[0].source_rows == (0, 1)


def test_successful_no_adsorption_gets_zero_reference_target():
    frame = _observation_frame()
    for column in TARGET_COLUMNS:
        frame[column] = np.nan

    reference = extract_reference_target(frame, successful=True)

    assert reference.status == "successful_no_adsorption"
    assert reference.values == (0.0,) * 6
    assert reference.final_time_s == 3.0


def test_reference_target_uses_latest_complete_parameter_time():
    frame = _observation_frame()
    for index, column in enumerate(TARGET_COLUMNS):
        frame[column] = [np.nan, np.nan, index + 1.0, index + 2.0]

    reference = extract_reference_target(frame, successful=True)

    assert reference.status == "fit_valid"
    assert reference.final_time_s == 3.0
    assert reference.values == (2.0, 3.0, 4.0, 5.0, 6.0, 0.2)


def test_examples_pass_q0_from_first_observation_and_exclude_future_rows():
    frame = _observation_frame().iloc[[0, 2, 3]].reset_index(drop=True)
    for index, column in enumerate(TARGET_COLUMNS):
        frame[column] = [np.nan, index + 1.0, index + 2.0]
    frame[TARGET_COLUMNS[-1]] = [np.nan, 99.0, 100.0]

    examples = build_sequential_examples(
        frame,
        experiment_id="experiment-1",
        successful=True,
        min_points=2,
    )

    assert len(examples) == 3
    assert examples[0].observation_times_s == (1.0,)
    assert examples[1].observation_times_s == (1.0, 2.0)
    assert examples[1].fit_status == FIT_VALID
    assert examples[1].q_0 == 0.1
    assert examples[1].reference_target[-1] == 0.1
    assert examples[0].fit_status == FIT_NOT_YET_ELIGIBLE
    assert examples[0].observation_times_s[-1] < examples[1].final_time_s


def test_examples_report_missing_fit_after_eligibility():
    frame = _observation_frame().iloc[[0, 2, 3]].reset_index(drop=True)
    for column in TARGET_COLUMNS:
        frame[column] = [np.nan, np.nan, 1.0]
    frame["pfo-sec_r^2"] = [np.nan, np.nan, 0.9]

    examples = build_sequential_examples(
        frame,
        experiment_id="experiment-2",
        successful=True,
        min_points=2,
    )

    assert examples[1].fit_status == FIT_MISSING_FOR_CUTOFF


def test_local_ode_preserves_initial_state_and_handles_duplicate_times():
    parameters = SecondaryPfoParameters(0.001, 1.0, 0.0001, 0.00005, 0.1, 0.2)

    q, p = solve_secondary_pfo([1.0, 2.0, 2.0, 3.0], parameters)

    assert q.shape == (4,)
    assert p.shape == (4,)
    assert q[0] == parameters.q_0
    assert p[0] == 0.0
    assert np.isfinite(q).all()
    assert np.isfinite(p).all()


def test_cutoff_forecast_keeps_full_trajectory_but_scores_future_only():
    parameters = SecondaryPfoParameters(0.001, 1.0, 0.0001, 0.00005, 0.1, 0.2)
    times = np.arange(1.0, 6.0)
    baseline, _ = solve_secondary_pfo(times, parameters)
    observed = baseline.copy()
    observed[:3] += 100.0

    forecast = build_cutoff_forecast(
        times,
        observed,
        cutoff_s=3.0,
        parameters=parameters,
    )
    rmse = remaining_curve_rmse(
        forecast.times_s,
        observed,
        forecast.predicted_area,
        cutoff_s=3.0,
    )

    assert forecast.times_s.tolist() == times.tolist()
    assert forecast.available_mask.tolist() == [True, True, True, False, False]
    assert forecast.remaining_mask.tolist() == [False, False, False, True, True]
    assert rmse == 0.0
    assert remaining_curve_rmse(times, observed, baseline, cutoff_s=5.0) is None
