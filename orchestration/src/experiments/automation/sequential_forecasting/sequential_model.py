"""Initial leakage-safe regularized correction model for sequential forecasts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .baselines import baseline_prediction
from .config import DEFAULT_ODE_TIMEOUT_SECONDS
from .data.adapter import build_examples_from_artifacts
from .data.contract import AREA_COLUMN, TARGET_COLUMNS, TIME_COLUMN
from .data.examples import SequentialExample
from .data.observations import flatten_monomer_rows
from .gated_blend_model import (
    DEFAULT_BIN_COUNTS as DEFAULT_GATED_BLEND_BIN_COUNTS,
    fit_gated_blend_model,
)
from .model_prediction import ModelPrediction
from .raw_series_model import (
    ESTIMATOR_NAMES as RAW_SERIES_ESTIMATORS,
    fit_raw_series_model,
)
from .models.secondary_pfo import (
    OdeForecastError,
    SecondaryPfoParameters,
    build_cutoff_forecast,
    remaining_curve_rmse,
    validate_secondary_pfo_parameters,
)
from .trajectory_extrapolation_model import (
    DEFAULT_MIN_TRAJECTORY_POINTS as DEFAULT_TRAJECTORY_MIN_POINTS,
    fit_trajectory_extrapolation_model,
)


MODEL_NAME = "ridge_correction"
LEARNED_TARGET_COLUMNS = TARGET_COLUMNS[:-1]
FIT_STATUS_FLAGS = (
    "fit_not_yet_eligible",
    "fit_missing_for_cutoff",
    "fit_partially_populated",
    "fit_missing_for_whole_experiment",
    "fit_failed",
    "fit_valid",
    "successful_no_adsorption",
)
DEFAULT_RIDGE_ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0)


def feature_names() -> tuple[str, ...]:
    """Return the deterministic cutoff-available feature order."""
    return (
        *(f"rf_{name}" for name in LEARNED_TARGET_COLUMNS),
        *(f"current_fit_{name}" for name in TARGET_COLUMNS),
        *(f"current_fit_available_{name}" for name in TARGET_COLUMNS),
        "fit_r_squared",
        "fit_rmse",
        "q_0",
        "observation_count",
        "observation_fraction",
        "elapsed_time_fraction",
        "time_remaining_s",
        "last_area",
        "mean_area",
        "std_area",
        "observed_duration_s",
        *(f"fit_status_{status}" for status in FIT_STATUS_FLAGS),
    )


def example_features(example: SequentialExample) -> np.ndarray:
    """Construct features using only data present at the current cutoff."""
    if example.rf_prediction is None or len(example.rf_prediction) != len(TARGET_COLUMNS):
        raise ValueError(f"RF prediction is unavailable for {example.experiment_id}")
    areas = np.asarray(example.observation_area, dtype=float)
    times = np.asarray(example.observation_times_s, dtype=float)
    if len(areas) == 0 or not np.isfinite(areas).all() or not np.isfinite(times).all():
        raise ValueError(f"Invalid prefix observations for {example.cutoff_id}")

    current_values = np.asarray(
        [0.0 if value is None else float(value) for value in example.current_fit_values],
        dtype=float,
    )
    current_available = np.asarray(example.current_fit_available, dtype=float)
    status_flags = np.asarray(
        [float(example.fit_status == status) for status in FIT_STATUS_FLAGS], dtype=float
    )
    return np.asarray(
        [
            *[float(value) for value in example.rf_prediction[:-1]],
            *current_values,
            *current_available,
            0.0 if example.fit_r_squared is None else float(example.fit_r_squared),
            0.0 if example.fit_rmse is None else float(example.fit_rmse),
            float(example.q_0),
            float(example.observation_count),
            float(example.observation_fraction),
            float(example.elapsed_time_fraction),
            float(example.time_remaining_s),
            float(areas[-1]),
            float(np.mean(areas)),
            float(np.std(areas)),
            float(times[-1] - times[0]),
            *status_flags,
        ],
        dtype=float,
    )


def feature_matrix(examples: tuple[SequentialExample, ...]) -> np.ndarray:
    """Construct a feature matrix in the shared feature order."""
    if not examples:
        raise ValueError("At least one example is required")
    matrix = np.vstack([example_features(example) for example in examples])
    if matrix.shape[1] != len(feature_names()):
        raise ValueError("Sequential feature vector does not match its feature names")
    return matrix


@dataclass
class FittedCorrectionModel:
    """Standardized multi-target Ridge correction model."""

    feature_names: tuple[str, ...]
    target_names: tuple[str, ...]
    feature_scaler: StandardScaler
    target_mean: np.ndarray
    target_scale: np.ndarray
    estimator: Ridge
    ridge_alpha: float

    def predict_delta(self, example: SequentialExample) -> np.ndarray:
        """Predict the correction to the first five RF parameters."""
        features = example_features(example).reshape(1, -1)
        scaled_features = self.feature_scaler.transform(features)
        scaled_delta = self.estimator.predict(scaled_features)
        return scaled_delta[0] * self.target_scale + self.target_mean

    def predict_parameters(self, example: SequentialExample) -> "ModelPrediction":
        """Return a complete ODE-compatible prediction with q_0 passed through."""
        try:
            if example.rf_prediction is None:
                raise ValueError("RF prediction is unavailable")
            rf_values = np.asarray(example.rf_prediction[:-1], dtype=float)
            corrected = rf_values + self.predict_delta(example)
            parameters = SecondaryPfoParameters.from_values(
                [*corrected.tolist(), float(example.q_0)]
            )
            validate_secondary_pfo_parameters(parameters)
        except (ValueError, TypeError, FloatingPointError) as error:
            return ModelPrediction(None, "invalid", str(error))
        return ModelPrediction(parameters, MODEL_NAME, None)


def fit_correction_model(
    examples: tuple[SequentialExample, ...],
    *,
    ridge_alpha: float,
) -> FittedCorrectionModel:
    """Fit the correction model using training examples only."""
    if ridge_alpha <= 0.0:
        raise ValueError("ridge_alpha must be positive")
    training = tuple(example for example in examples if example.assignment == "train")
    if not training:
        raise ValueError("Correction model requires training examples")
    X = feature_matrix(training)
    rf_values = np.asarray([example.rf_prediction[:-1] for example in training], dtype=float)
    targets = np.asarray([example.reference_target[:-1] for example in training], dtype=float)
    y = targets - rf_values
    feature_scaler = StandardScaler().fit(X)
    target_mean = np.mean(y, axis=0)
    target_scale = np.std(y, axis=0)
    target_scale = np.where(target_scale > 0.0, target_scale, 1.0)
    estimator = Ridge(alpha=ridge_alpha)
    experiment_counts = pd.Series(example.experiment_id for example in training).value_counts()
    sample_weight = np.asarray(
        [1.0 / float(experiment_counts[example.experiment_id]) for example in training],
        dtype=float,
    )
    estimator.fit(
        feature_scaler.transform(X),
        (y - target_mean) / target_scale,
        sample_weight=sample_weight,
    )
    return FittedCorrectionModel(
        feature_names=feature_names(),
        target_names=LEARNED_TARGET_COLUMNS,
        feature_scaler=feature_scaler,
        target_mean=target_mean,
        target_scale=target_scale,
        estimator=estimator,
        ridge_alpha=ridge_alpha,
    )


def _fingerprint_examples(examples: tuple[SequentialExample, ...]) -> str:
    """Fingerprint experiment/cutoff membership without raw data values."""
    payload = "\n".join(
        f"{example.experiment_id}|{example.cutoff_id}" for example in examples
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def reference_target_scales(examples: tuple[SequentialExample, ...]) -> np.ndarray:
    """Return per-target reference spread measured on training experiments.

    One row per training experiment, not per cutoff, so experiments with more
    cutoffs do not widen the scale. The scales convert per-target RMSE into a
    comparable quantity: without them a pooled parameter RMSE is dominated by
    `q_e`/`q_inf` and is blind to the three rate constants, which are four
    orders of magnitude smaller but drive the shape of the curve.
    """
    seen: dict[str, tuple[float, ...]] = {}
    for example in examples:
        if example.assignment != "train" or example.experiment_id in seen:
            continue
        seen[example.experiment_id] = tuple(
            float(value) for value in example.reference_target[:-1]
        )
    if not seen:
        raise ValueError("Reference scales require training examples")
    values = np.asarray(list(seen.values()), dtype=float)
    scales = np.std(values, axis=0)
    return np.where(scales > 0.0, scales, 1.0)


def _aggregate_scores(
    errors_by_group: dict[str, list[np.ndarray]],
    curve_by_group: dict[str, list[float]],
    target_scales: np.ndarray | None,
) -> dict[str, object]:
    """Aggregate one candidate's errors identically for every candidate.

    Shared by the learned-candidate and baseline evaluators so a candidate can
    never be ranked against a differently-computed score.

    `selection_score` is the equal-weighted mean of the early, middle, and late
    remaining-curve RMSEs. Curve accuracy is the stated objective (spec.md
    #14); weighting the three stages equally keeps early, middle, and late
    performance visible without assuming in advance which matters most. When no
    curve information is supplied, the scale-normalized parameter error is used
    instead so every candidate is still ranked on the same basis.
    """
    parameter_rmse_by_group = {
        group: float(np.sqrt(np.mean(np.asarray(errors) ** 2))) if errors else None
        for group, errors in errors_by_group.items()
    }
    curve_rmse_by_group = {
        group: float(np.mean(values)) if values else None
        for group, values in curve_by_group.items()
    }
    parameter_values = [error for errors in errors_by_group.values() for error in errors]
    overall_parameter = (
        float(np.sqrt(np.mean(np.asarray(parameter_values) ** 2)))
        if parameter_values
        else None
    )
    parameter_rmse_by_target: dict[str, float] | None = None
    avg_normalized_rmse: float | None = None
    avg_normalized_rmse_four: float | None = None
    if parameter_values:
        stacked = np.asarray(parameter_values, dtype=float)
        per_target = np.sqrt(np.mean(stacked**2, axis=0))
        parameter_rmse_by_target = {
            name: float(value)
            for name, value in zip(LEARNED_TARGET_COLUMNS, per_target, strict=True)
        }
        if target_scales is not None:
            normalized = per_target / target_scales
            avg_normalized_rmse = float(np.mean(normalized))
            # `q_inf` is exactly zero for 40% of experiments and near zero for
            # 70%, so its training spread is tiny and every method — including
            # predicting the training mean — scores above 3 on it. Left in the
            # average it dominates the figure the same way `q_e` dominated the
            # pooled RMSE this metric replaced, so the average over the four
            # better-determined parameters is reported alongside it.
            avg_normalized_rmse_four = float(np.mean(normalized[:4]))

    stage_curves = [value for value in curve_rmse_by_group.values() if value is not None]
    if stage_curves:
        selection_score = float(np.mean(stage_curves))
        selection_basis = "mean_stage_curve_rmse"
    else:
        selection_score = avg_normalized_rmse if avg_normalized_rmse is not None else overall_parameter
        selection_basis = (
            "avg_normalized_parameter_rmse"
            if avg_normalized_rmse is not None
            else "pooled_parameter_rmse"
        )
    return {
        "valid_prediction_count": len(parameter_values),
        "parameter_rmse": overall_parameter,
        "parameter_rmse_by_target": parameter_rmse_by_target,
        "avg_normalized_rmse": avg_normalized_rmse,
        "avg_normalized_rmse_four_parameters": avg_normalized_rmse_four,
        "parameter_rmse_by_progress": parameter_rmse_by_group,
        "curve_rmse_by_progress": curve_rmse_by_group,
        "curve_rmse_stage_mean": float(np.mean(stage_curves)) if stage_curves else None,
        "selection_basis": selection_basis,
        "selection_score": selection_score,
    }


def _evaluate_model(
    model: object,
    examples: tuple[SequentialExample, ...],
    observations: dict[str, tuple[np.ndarray, np.ndarray]] | None,
    *,
    timeout_seconds: float,
    target_scales: np.ndarray | None = None,
) -> dict[str, object]:
    """Evaluate one candidate on validation examples, with RF fallback.

    Every validation cutoff is scored, matching production inference
    (`inference.py`): when the candidate returns no valid parameters, the RF
    prediction is scored instead rather than the example being dropped.
    Silently dropping invalid predictions (spec.md #12 forbids exactly this)
    would let a candidate that fails on hard cutoffs look artificially more
    accurate than one, like RF-only, that is scored on every cutoff.
    """
    validation = tuple(example for example in examples if example.assignment == "validation")
    errors_by_group: dict[str, list[np.ndarray]] = {"early": [], "middle": [], "late": []}
    curve_by_group: dict[str, list[float]] = {"early": [], "middle": [], "late": []}
    forecast_cache: dict[tuple[str, tuple[float, ...]], tuple[np.ndarray, np.ndarray]] = {}
    model_valid_count = 0
    for example in validation:
        prediction = model.predict_parameters(example)
        if prediction.parameters is not None:
            model_valid_count += 1
            parameters = prediction.parameters
        else:
            parameters = baseline_prediction(example, "rf_only").parameters
        if parameters is None:
            continue
        errors = parameters.as_array()[:-1] - np.asarray(
            example.reference_target[:-1], dtype=float
        )
        group = "early" if example.observation_fraction < 1 / 3 else (
            "middle" if example.observation_fraction < 2 / 3 else "late"
        )
        errors_by_group[group].append(errors)
        if observations is None:
            continue
        times_s, observed_area = observations[example.experiment_id]
        key = (example.experiment_id, tuple(float(value) for value in parameters.as_array()))
        try:
            if key not in forecast_cache:
                forecast = build_cutoff_forecast(
                    times_s,
                    observed_area,
                    example.cutoff_time_s,
                    parameters,
                    final_time_s=example.final_time_s,
                    timeout_seconds=timeout_seconds,
                )
                forecast_cache[key] = (forecast.times_s, forecast.predicted_area)
            forecast_times, predicted_area = forecast_cache[key]
            curve = remaining_curve_rmse(
                forecast_times,
                observed_area[: len(forecast_times)],
                predicted_area,
                example.cutoff_time_s,
            )
            if curve is not None:
                curve_by_group[group].append(curve)
        except (OdeForecastError, ValueError):
            continue

    return {
        "validation_example_count": len(validation),
        "model_valid_prediction_count": model_valid_count,
        **_aggregate_scores(errors_by_group, curve_by_group, target_scales),
    }


def _evaluate_baseline(
    baseline: str,
    examples: tuple[SequentialExample, ...],
    observations: dict[str, tuple[np.ndarray, np.ndarray]],
    *,
    blend_weight: float = 0.5,
    timeout_seconds: float,
    target_scales: np.ndarray | None = None,
) -> dict[str, object]:
    """Evaluate a Phase 5 baseline on validation examples for comparison."""
    validation = tuple(example for example in examples if example.assignment == "validation")
    errors_by_group: dict[str, list[np.ndarray]] = {"early": [], "middle": [], "late": []}
    curve_by_group: dict[str, list[float]] = {"early": [], "middle": [], "late": []}
    forecast_cache: dict[tuple[str, tuple[float, ...]], tuple[np.ndarray, np.ndarray]] = {}
    for example in validation:
        prediction = baseline_prediction(example, baseline, blend_weight=blend_weight)
        if prediction.parameters is None:
            continue
        errors = prediction.parameters.as_array()[:-1] - np.asarray(
            example.reference_target[:-1], dtype=float
        )
        group = "early" if example.observation_fraction < 1 / 3 else (
            "middle" if example.observation_fraction < 2 / 3 else "late"
        )
        errors_by_group[group].append(errors)
        times_s, observed_area = observations[example.experiment_id]
        key = (example.experiment_id, tuple(float(value) for value in prediction.parameters.as_array()))
        try:
            if key not in forecast_cache:
                forecast = build_cutoff_forecast(
                    times_s,
                    observed_area,
                    example.cutoff_time_s,
                    prediction.parameters,
                    final_time_s=example.final_time_s,
                    timeout_seconds=timeout_seconds,
                )
                forecast_cache[key] = (forecast.times_s, forecast.predicted_area)
            forecast_times, predicted_area = forecast_cache[key]
            curve = remaining_curve_rmse(
                forecast_times,
                observed_area[: len(forecast_times)],
                predicted_area,
                example.cutoff_time_s,
            )
            if curve is not None:
                curve_by_group[group].append(curve)
        except (OdeForecastError, ValueError):
            continue

    return {
        "validation_example_count": len(validation),
        **_aggregate_scores(errors_by_group, curve_by_group, target_scales),
    }


_BASELINE_NAMES = ("rf_only", "current_ode", "rf_ode_blend")


def select_initial_model(
    examples: tuple[SequentialExample, ...],
    *,
    observations: dict[str, tuple[np.ndarray, np.ndarray]] | None = None,
    ridge_alphas: tuple[float, ...] = DEFAULT_RIDGE_ALPHAS,
    gated_blend_bin_counts: tuple[int, ...] = (),
    trajectory_min_points: tuple[int, ...] = (),
    raw_series_estimators: tuple[str, ...] = (),
    timeout_seconds: float = DEFAULT_ODE_TIMEOUT_SECONDS,
) -> tuple[object | None, dict[str, object]]:
    """Select the best candidate using validation evidence only.

    Candidates are Ridge corrections, elapsed-time-gated RF/ODE blends,
    per-experiment convergence extrapolations, and the three required
    baselines. Every learned candidate is scored with `_evaluate_model`,
    which falls back to RF for cutoffs the candidate cannot predict, so no
    candidate can look better merely by being scored on fewer, easier
    cutoffs.
    """
    target_scales = reference_target_scales(examples)
    candidates: dict[str, object] = {}
    fitted: dict[str, object] = {}
    for alpha in ridge_alphas:
        model = fit_correction_model(examples, ridge_alpha=alpha)
        key = str(float(alpha))
        fitted[key] = model
        candidates[key] = _evaluate_model(
            model,
            examples,
            observations,
            timeout_seconds=timeout_seconds,
            target_scales=target_scales,
        )
    for bin_count in gated_blend_bin_counts:
        model = fit_gated_blend_model(examples, bin_count=bin_count)
        key = f"gated_blend_{bin_count}"
        fitted[key] = model
        candidates[key] = _evaluate_model(
            model,
            examples,
            observations,
            timeout_seconds=timeout_seconds,
            target_scales=target_scales,
        )
    for min_points in trajectory_min_points:
        model = fit_trajectory_extrapolation_model(min_trajectory_points=min_points)
        key = f"trajectory_{min_points}"
        fitted[key] = model
        candidates[key] = _evaluate_model(
            model,
            examples,
            observations,
            timeout_seconds=timeout_seconds,
            target_scales=target_scales,
        )
    for estimator_name in raw_series_estimators:
        for require_valid_fit in (True, False):
            model = fit_raw_series_model(
                examples,
                estimator_name=estimator_name,
                require_valid_fit=require_valid_fit,
            )
            suffix = "gated" if require_valid_fit else "always"
            key = f"raw_series_{estimator_name}_{suffix}"
            fitted[key] = model
            candidates[key] = _evaluate_model(
                model,
                examples,
                observations,
                timeout_seconds=timeout_seconds,
                target_scales=target_scales,
            )
    if observations is not None:
        for baseline in _BASELINE_NAMES:
            candidates[baseline] = _evaluate_baseline(
                baseline,
                examples,
                observations,
                timeout_seconds=timeout_seconds,
                target_scales=target_scales,
            )
    valid_candidates = {
        key: result
        for key, result in candidates.items()
        if result["selection_score"] is not None
    }
    if not valid_candidates:
        raise ValueError("No sequential candidate produced validation predictions")
    selected_key = min(
        valid_candidates,
        key=lambda key: float(valid_candidates[key]["selection_score"]),
    )
    learned_model_selected = selected_key not in _BASELINE_NAMES
    is_gated_blend = learned_model_selected and selected_key.startswith("gated_blend_")
    is_trajectory = learned_model_selected and selected_key.startswith("trajectory_")
    is_raw_series = learned_model_selected and selected_key.startswith("raw_series_")
    selected_alpha = (
        float(selected_key)
        if learned_model_selected
        and not is_gated_blend
        and not is_trajectory
        and not is_raw_series
        else None
    )
    selected_bin_count = int(selected_key.split("_")[-1]) if is_gated_blend else None
    selected_trajectory_min_points = int(selected_key.split("_")[-1]) if is_trajectory else None
    if not learned_model_selected:
        model_name = selected_key
    elif is_gated_blend:
        model_name = "gated_blend"
    elif is_trajectory:
        model_name = "trajectory_extrapolation"
    elif is_raw_series:
        model_name = selected_key
    else:
        model_name = MODEL_NAME
    manifest = {
        "model_name": model_name,
        "selected_ridge_alpha": selected_alpha,
        "selected_gated_blend_bin_count": selected_bin_count,
        "selected_trajectory_min_points": selected_trajectory_min_points,
        "selected_candidate": selected_key,
        "learned_model_selected": learned_model_selected,
        "candidate_results": candidates,
        "training_experiment_count": len({
            example.experiment_id for example in examples if example.assignment == "train"
        }),
        "validation_experiment_count": len({
            example.experiment_id for example in examples if example.assignment == "validation"
        }),
        "training_example_fingerprint": _fingerprint_examples(
            tuple(example for example in examples if example.assignment == "train")
        ),
        "validation_example_fingerprint": _fingerprint_examples(
            tuple(example for example in examples if example.assignment == "validation")
        ),
        "test_used_for_selection": False,
        "selection_metric": "mean of early/middle/late remaining-curve RMSE",
        "reference_target_scales": {
            name: float(value)
            for name, value in zip(LEARNED_TARGET_COLUMNS, target_scales, strict=True)
        },
        "feature_names": list(feature_names()),
        "target_names": list(LEARNED_TARGET_COLUMNS),
    }
    return (fitted[selected_key] if learned_model_selected else None), manifest


def train_initial_model(
    artifact_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
    ridge_alphas: tuple[float, ...] = DEFAULT_RIDGE_ALPHAS,
    gated_blend_bin_counts: tuple[int, ...] = DEFAULT_GATED_BLEND_BIN_COUNTS,
    trajectory_min_points: tuple[int, ...] = DEFAULT_TRAJECTORY_MIN_POINTS,
    raw_series_estimators: tuple[str, ...] = RAW_SERIES_ESTIMATORS,
    timeout_seconds: float | None = None,
) -> Path:
    """Train and persist the validation-selected initial correction model."""
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
    model, manifest = select_initial_model(
        examples,
        observations=observations,
        ridge_alphas=ridge_alphas,
        gated_blend_bin_counts=gated_blend_bin_counts,
        trajectory_min_points=trajectory_min_points,
        raw_series_estimators=raw_series_estimators,
        timeout_seconds=(
            float(config.get("ode_timeout_seconds", DEFAULT_ODE_TIMEOUT_SECONDS))
            if timeout_seconds is None
            else timeout_seconds
        ),
    )
    output_path = Path(output_dir) if output_dir is not None else artifact_path / "sequential_model"
    output_path.mkdir(parents=True, exist_ok=True)
    if model is not None:
        joblib.dump(model, output_path / "model.joblib")
    else:
        (output_path / "model_not_selected.txt").write_text(
            "Validation selected a required baseline instead of a learned candidate.\n",
            encoding="utf-8",
        )
    (output_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return output_path
