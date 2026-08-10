"""Required RF/ODE baseline forecasts and shared evaluation metrics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .config import DEFAULT_ODE_TIMEOUT_SECONDS
from .data.adapter import build_examples_from_artifacts
from .data.contract import AREA_COLUMN, TARGET_COLUMNS, TIME_COLUMN
from .data.examples import FIT_VALID, SequentialExample
from .data.observations import flatten_monomer_rows
from .models.secondary_pfo import (
    OdeForecastError,
    SecondaryPfoParameters,
    build_cutoff_forecast,
    remaining_curve_rmse,
    validate_secondary_pfo_parameters,
)


BASELINE_NAMES = ("rf_only", "current_ode", "rf_ode_blend")
DEFAULT_BLEND_CANDIDATES = (0.0, 0.25, 0.5, 0.75, 1.0)


@dataclass(frozen=True)
class BaselinePrediction:
    """One baseline parameter prediction and its provenance."""

    parameters: SecondaryPfoParameters | None
    source: str
    fallback_reason: str | None = None


@dataclass(frozen=True)
class BaselineRecord:
    """Auditable parameter and remaining-curve scores for one cutoff."""

    baseline: str
    experiment_id: str
    cutoff_id: str
    assignment: str | None
    cutoff_time_s: float
    observation_count: int
    progress_group: str
    prediction: tuple[float, ...] | None
    prediction_source: str
    fallback_reason: str | None
    parameter_rmse: float | None
    parameter_errors: tuple[float, ...] | None
    curve_rmse: float | None
    curve_status: str


def _parameters_from_values(
    values: Iterable[float | None] | None,
    q_0: float,
) -> SecondaryPfoParameters | None:
    """Convert a complete six-value vector while passing through known q_0."""
    if values is None:
        return None
    values_list = list(values)
    if len(values_list) != len(TARGET_COLUMNS) or any(
        value is None or not np.isfinite(float(value)) for value in values_list
    ):
        return None
    values_list[-1] = q_0
    parameters = SecondaryPfoParameters.from_values(values_list)
    try:
        validate_secondary_pfo_parameters(parameters)
    except ValueError:
        return None
    return parameters


def baseline_prediction(
    example: SequentialExample,
    baseline: str,
    *,
    blend_weight: float = 0.5,
) -> BaselinePrediction:
    """Create one RF-only, current-ODE, or RF/ODE-blend prediction."""
    if baseline not in BASELINE_NAMES:
        raise ValueError(f"Unknown baseline: {baseline}")
    rf_parameters = _parameters_from_values(example.rf_prediction, example.q_0)
    ode_parameters = (
        _parameters_from_values(example.current_fit_values, example.q_0)
        if example.fit_status == FIT_VALID
        else None
    )

    if baseline == "rf_only":
        if rf_parameters is None:
            return BaselinePrediction(None, "invalid", "rf_prediction_invalid")
        return BaselinePrediction(rf_parameters, "rf")

    if baseline == "current_ode":
        if ode_parameters is not None:
            return BaselinePrediction(ode_parameters, "current_ode")
        if rf_parameters is not None:
            return BaselinePrediction(
                rf_parameters,
                "rf_fallback",
                f"current_fit_{example.fit_status}",
            )
        return BaselinePrediction(None, "invalid", "current_fit_and_rf_invalid")

    if not 0.0 <= blend_weight <= 1.0:
        raise ValueError("blend_weight must be in [0, 1]")
    if rf_parameters is None and ode_parameters is None:
        return BaselinePrediction(None, "invalid", "rf_prediction_and_current_fit_invalid")
    if rf_parameters is None:
        return BaselinePrediction(
            ode_parameters,
            "current_ode_fallback",
            "rf_prediction_invalid",
        )
    if ode_parameters is None:
        return BaselinePrediction(
            rf_parameters,
            "rf_fallback",
            f"current_fit_{example.fit_status}",
        )

    blended = (1.0 - blend_weight) * rf_parameters.as_array() + blend_weight * ode_parameters.as_array()
    blended_parameters = _parameters_from_values(blended.tolist(), example.q_0)
    if blended_parameters is None:
        return BaselinePrediction(
            ode_parameters,
            "current_ode_fallback",
            "blended_prediction_invalid",
        )
    return BaselinePrediction(blended_parameters, "rf_ode_blend")


def select_blend_weight(
    examples: Iterable[SequentialExample],
    candidates: Iterable[float] = DEFAULT_BLEND_CANDIDATES,
) -> tuple[float, dict[str, float]]:
    """Select blend weight using validation experiments only."""
    validation_examples = [example for example in examples if example.assignment == "validation"]
    if not validation_examples:
        raise ValueError("Blend-weight selection requires validation examples")

    scores: dict[str, float] = {}
    for weight in candidates:
        squared_errors: list[float] = []
        for example in validation_examples:
            prediction = baseline_prediction(
                example, "rf_ode_blend", blend_weight=float(weight)
            ).parameters
            if prediction is None:
                continue
            errors = prediction.as_array() - np.asarray(example.reference_target, dtype=float)
            squared_errors.extend((errors**2).tolist())
        if not squared_errors:
            raise ValueError("No valid validation predictions available for blend selection")
        scores[str(float(weight))] = float(np.sqrt(np.mean(squared_errors)))
    selected = min(scores, key=scores.get)
    return float(selected), scores


def _progress_group(observation_fraction: float) -> str:
    """Return a stable early/middle/late progress group."""
    if observation_fraction < 1.0 / 3.0:
        return "early"
    if observation_fraction < 2.0 / 3.0:
        return "middle"
    return "late"


def _score_prediction(
    example: SequentialExample,
    baseline: str,
    prediction: BaselinePrediction,
    times_s: np.ndarray,
    observed_area: np.ndarray,
    *,
    timeout_seconds: float,
    forecast_cache: dict[
        tuple[str, float, tuple[float, ...]], tuple[np.ndarray, np.ndarray]
    ],
) -> BaselineRecord:
    """Score one parameter prediction and its strict future curve suffix."""
    parameters = prediction.parameters
    parameter_rmse: float | None = None
    parameter_errors: tuple[float, ...] | None = None
    curve_rmse: float | None = None
    curve_status = "prediction_invalid"
    if parameters is not None:
        errors = parameters.as_array() - np.asarray(example.reference_target, dtype=float)
        parameter_errors = tuple(float(value) for value in errors)
        parameter_rmse = float(np.sqrt(np.mean(errors**2)))
        try:
            parameter_key = tuple(float(value) for value in parameters.as_array())
            cache_key = (example.experiment_id, example.final_time_s, parameter_key)
            if cache_key not in forecast_cache:
                forecast = build_cutoff_forecast(
                    times_s,
                    observed_area,
                    example.cutoff_time_s,
                    parameters,
                    final_time_s=example.final_time_s,
                    timeout_seconds=timeout_seconds,
                )
                forecast_cache[cache_key] = (
                    forecast.times_s,
                    forecast.predicted_area,
                )
            forecast_times, predicted_area = forecast_cache[cache_key]
            curve_rmse = remaining_curve_rmse(
                forecast_times,
                observed_area[: len(forecast_times)],
                predicted_area,
                example.cutoff_time_s,
            )
            curve_status = "valid" if curve_rmse is not None else "no_remaining_points"
        except (OdeForecastError, ValueError) as error:
            curve_status = f"forecast_failed:{error}"

    return BaselineRecord(
        baseline=baseline,
        experiment_id=example.experiment_id,
        cutoff_id=example.cutoff_id,
        assignment=example.assignment,
        cutoff_time_s=example.cutoff_time_s,
        observation_count=example.observation_count,
        progress_group=_progress_group(example.observation_fraction),
        prediction=(tuple(float(value) for value in parameters.as_array()) if parameters else None),
        prediction_source=prediction.source,
        fallback_reason=prediction.fallback_reason,
        parameter_rmse=parameter_rmse,
        parameter_errors=parameter_errors,
        curve_rmse=curve_rmse,
        curve_status=curve_status,
    )


def evaluate_baselines(
    examples: tuple[SequentialExample, ...],
    observations_by_experiment: dict[str, tuple[np.ndarray, np.ndarray]],
    *,
    blend_weight: float,
    timeout_seconds: float = DEFAULT_ODE_TIMEOUT_SECONDS,
) -> tuple[BaselineRecord, ...]:
    """Evaluate all required baselines on identical examples and cutoffs."""
    records: list[BaselineRecord] = []
    forecast_cache: dict[
        tuple[str, float, tuple[float, ...]], tuple[np.ndarray, np.ndarray]
    ] = {}
    for baseline in BASELINE_NAMES:
        for example in examples:
            times_s, observed_area = observations_by_experiment[example.experiment_id]
            prediction = baseline_prediction(
                example,
                baseline,
                blend_weight=blend_weight,
            )
            record = _score_prediction(
                example,
                baseline,
                prediction,
                times_s,
                observed_area,
                timeout_seconds=timeout_seconds,
                forecast_cache=forecast_cache,
            )
            records.append(record)
    return tuple(records)


def _summary(records: tuple[BaselineRecord, ...]) -> dict[str, object]:
    """Aggregate records by baseline, assignment, and progress group."""
    grouped: dict[tuple[str, str | None, str], list[BaselineRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.baseline, record.assignment, record.progress_group)].append(record)

    summary: dict[str, object] = {}
    for (baseline, assignment, progress), rows in sorted(grouped.items(), key=str):
        key = f"{baseline}|{assignment}|{progress}"
        parameter_rows = [row for row in rows if row.parameter_errors is not None]
        curve_rows = [row.curve_rmse for row in rows if row.curve_rmse is not None]
        errors = (
            np.asarray([row.parameter_errors for row in parameter_rows], dtype=float)
            if parameter_rows
            else np.empty((0, len(TARGET_COLUMNS)))
        )
        summary[key] = {
            "baseline": baseline,
            "assignment": assignment,
            "progress_group": progress,
            "count": len(rows),
            "valid_parameter_count": len(parameter_rows),
            "valid_curve_count": len(curve_rows),
            "parameter_rmse": float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
            "parameter_rmse_by_target": (
                {
                    target: float(np.sqrt(np.mean(errors[:, index] ** 2)))
                    for index, target in enumerate(TARGET_COLUMNS)
                }
                if len(errors)
                else None
            ),
            "curve_rmse": float(np.mean(curve_rows)) if curve_rows else None,
            "prediction_source_counts": pd.Series(
                [row.prediction_source for row in rows]
            ).value_counts().to_dict(),
            "curve_status_counts": pd.Series(
                [row.curve_status for row in rows]
            ).value_counts().to_dict(),
        }
    return summary


def run_baselines(
    artifact_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
    timeout_seconds: float | None = None,
) -> Path:
    """Build examples, select blend weight on validation, and write results."""
    artifact_path = Path(artifact_dir)
    examples = build_examples_from_artifacts(artifact_path)
    config = json.loads((artifact_path / "run_config.json").read_text(encoding="utf-8"))
    observations: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for example in examples:
        if example.experiment_id in observations:
            continue
        flattened, _ = flatten_monomer_rows(pd.read_csv(example.csv_path))
        timeline = flattened.loc[flattened[TIME_COLUMN] <= example.final_time_s]
        observations[example.experiment_id] = (
            timeline[TIME_COLUMN].to_numpy(dtype=float),
            timeline[AREA_COLUMN].to_numpy(dtype=float),
        )

    blend_weight, blend_scores = select_blend_weight(examples)
    records = evaluate_baselines(
        examples,
        observations,
        blend_weight=blend_weight,
        timeout_seconds=(
            float(config.get("ode_timeout_seconds", DEFAULT_ODE_TIMEOUT_SECONDS))
            if timeout_seconds is None
            else timeout_seconds
        ),
    )
    output_path = Path(output_dir) if output_dir is not None else artifact_path / "baselines"
    output_path.mkdir(parents=True, exist_ok=True)
    with (output_path / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), default=str) + "\n")
    manifest = {
        "baseline_names": list(BASELINE_NAMES),
        "example_count": len(examples),
        "record_count": len(records),
        "blend_weight": blend_weight,
        "blend_validation_scores": blend_scores,
        "summary": _summary(records),
    }
    (output_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return output_path
