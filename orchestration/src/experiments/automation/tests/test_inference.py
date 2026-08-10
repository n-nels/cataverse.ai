"""Tests for cutoff-by-cutoff sequential inference."""

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
from sequential_forecasting.data.examples import build_sequential_examples  # noqa: E402
from sequential_forecasting.inference import (  # noqa: E402
    load_inference_artifacts,
    run_sequential_inference,
)
from sequential_forecasting.models.secondary_pfo import (  # noqa: E402
    SecondaryPfoParameters,
)
from sequential_forecasting.sequential_model import ModelPrediction  # noqa: E402


def _frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "Peak_Name": ["monomer_sum"] * 4,
            "Time (s)": [1.0, 1.7, 3.2, 5.5],
            "Cumulative_Peak_Area": [0.2, 0.3, 0.4, 0.5],
            "pfo-sec_r^2": [np.nan, 0.2, 0.9, 0.95],
        }
    )
    values = [0.001, 0.5, 0.0001, 0.00005, 0.4, 0.2]
    for column, value in zip(TARGET_COLUMNS, values, strict=True):
        frame[column] = [np.nan, np.nan, value, value]
    return frame


class _CandidateModel:
    """Small learned-model double used to exercise update and fallback paths."""

    def predict_parameters(self, example):
        if example.fit_status != "fit_valid":
            return ModelPrediction(None, "ridge_correction", "induced_fit_failure")
        return ModelPrediction(
            SecondaryPfoParameters(0.001, 0.5, 0.0001, 0.00005, 0.4, example.q_0),
            "ridge_correction",
            None,
        )


def test_inference_is_ordered_and_falls_back_after_failed_fit():
    frame = _frame()
    examples = build_sequential_examples(
        frame,
        experiment_id="experiment-1",
        successful=True,
        min_points=3,
        assignment="test",
        csv_path="experiment-1.csv",
        json_path="experiment-1.json",
        rf_prediction=(0.002, 0.6, 0.0002, 0.0001, 0.5, 0.9),
        rf_prediction_provenance="held_out_test",
    )
    times = frame["Time (s)"].to_numpy(dtype=float)
    areas = frame["Cumulative_Peak_Area"].to_numpy(dtype=float)

    records = run_sequential_inference(
        examples,
        {"experiment-1": (times, areas)},
        model=_CandidateModel(),
        model_manifest={
            "selected_candidate": "ridge_correction",
            "learned_model_selected": True,
        },
    )

    assert [record.observation_count for record in records] == [1, 2, 3, 4]
    assert records[1].fit_status == "fit_failed"
    assert records[1].prediction_source == "rf"
    assert records[1].fallback_reason == "current_fit_fit_failed"
    assert records[2].prediction_source == "sequential"
    assert records[2].prediction[-1] == 0.2
    assert records[2].parameter_validation_status == "valid"
    assert records[2].input_observation_area == (0.2, 0.3, 0.4)
    assert records[2].curve_times_s == tuple(times.tolist())
    assert records[2].curve_status == "valid"


def test_rf_only_manifest_has_no_active_learned_model(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "selected_candidate": "rf_only",
                "learned_model_selected": False,
            }
        ),
        encoding="utf-8",
    )

    artifacts = load_inference_artifacts(tmp_path)

    assert artifacts.model is None
    assert artifacts.manifest["selected_candidate"] == "rf_only"
