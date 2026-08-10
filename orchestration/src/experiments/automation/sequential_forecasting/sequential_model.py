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
from .models.secondary_pfo import (
    OdeForecastError,
    SecondaryPfoParameters,
    build_cutoff_forecast,
    remaining_curve_rmse,
    validate_secondary_pfo_parameters,
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


@dataclass(frozen=True)
class ModelPrediction:
    """Structured correction-model prediction result."""

    parameters: SecondaryPfoParameters | None
    source: str
    reason: str | None


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


def _evaluate_model(
    model: FittedCorrectionModel,
    examples: tuple[SequentialExample, ...],
    observations: dict[str, tuple[np.ndarray, np.ndarray]] | None,
    *,
    timeout_seconds: float,
) -> dict[str, object]:
    """Evaluate one candidate on validation examples only."""
    validation = tuple(example for example in examples if example.assignment == "validation")
    errors_by_group: dict[str, list[np.ndarray]] = {"early": [], "middle": [], "late": []}
    curve_by_group: dict[str, list[float]] = {"early": [], "middle": [], "late": []}
    forecast_cache: dict[tuple[str, tuple[float, ...]], tuple[np.ndarray, np.ndarray]] = {}
    for example in validation:
        prediction = model.predict_parameters(example)
        if prediction.parameters is None:
            continue
        errors = prediction.parameters.as_array()[:-1] - np.asarray(
            example.reference_target[:-1], dtype=float
        )
        group = "early" if example.observation_fraction < 1 / 3 else (
            "middle" if example.observation_fraction < 2 / 3 else "late"
        )
        errors_by_group[group].append(errors)
        if observations is None:
            continue
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
    early_curve = curve_rmse_by_group["early"]
    selection_score = (
        overall_parameter + early_curve
        if overall_parameter is not None and early_curve is not None
        else overall_parameter
    )
    return {
        "validation_example_count": len(validation),
        "valid_prediction_count": len(parameter_values),
        "parameter_rmse": overall_parameter,
        "parameter_rmse_by_progress": parameter_rmse_by_group,
        "curve_rmse_by_progress": curve_rmse_by_group,
        "selection_score": selection_score,
    }


def _evaluate_baseline(
    baseline: str,
    examples: tuple[SequentialExample, ...],
    observations: dict[str, tuple[np.ndarray, np.ndarray]],
    *,
    blend_weight: float = 0.5,
    timeout_seconds: float,
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

    errors = [error for values in errors_by_group.values() for error in values]
    parameter_rmse = float(np.sqrt(np.mean(np.asarray(errors) ** 2))) if errors else None
    parameter_by_progress = {
        group: float(np.sqrt(np.mean(np.asarray(values) ** 2))) if values else None
        for group, values in errors_by_group.items()
    }
    curve_by_progress = {
        group: float(np.mean(values)) if values else None
        for group, values in curve_by_group.items()
    }
    early_curve = curve_by_progress["early"]
    selection_score = (
        parameter_rmse + early_curve
        if parameter_rmse is not None and early_curve is not None
        else parameter_rmse
    )
    return {
        "validation_example_count": len(validation),
        "valid_prediction_count": len(errors),
        "parameter_rmse": parameter_rmse,
        "parameter_rmse_by_progress": parameter_by_progress,
        "curve_rmse_by_progress": curve_by_progress,
        "selection_score": selection_score,
    }


def select_initial_model(
    examples: tuple[SequentialExample, ...],
    *,
    observations: dict[str, tuple[np.ndarray, np.ndarray]] | None = None,
    ridge_alphas: tuple[float, ...] = DEFAULT_RIDGE_ALPHAS,
    timeout_seconds: float = DEFAULT_ODE_TIMEOUT_SECONDS,
) -> tuple[FittedCorrectionModel, dict[str, object]]:
    """Select Ridge regularization using validation evidence only."""
    candidates: dict[str, object] = {}
    fitted: dict[float, FittedCorrectionModel] = {}
    for alpha in ridge_alphas:
        model = fit_correction_model(examples, ridge_alpha=alpha)
        fitted[alpha] = model
        candidates[str(float(alpha))] = _evaluate_model(
            model,
            examples,
            observations,
            timeout_seconds=timeout_seconds,
        )
    if observations is not None:
        for baseline in ("rf_only", "current_ode", "rf_ode_blend"):
            candidates[baseline] = _evaluate_baseline(
                baseline,
                examples,
                observations,
                timeout_seconds=timeout_seconds,
            )
    valid_candidates = {
        alpha: result
        for alpha, result in candidates.items()
        if result["selection_score"] is not None
    }
    if not valid_candidates:
        raise ValueError("No correction-model candidate produced validation predictions")
    selected_key = min(
        valid_candidates,
        key=lambda key: float(valid_candidates[key]["selection_score"]),
    )
    selected_alpha = float(selected_key) if selected_key not in {
        "rf_only",
        "current_ode",
        "rf_ode_blend",
    } else None
    manifest = {
        "model_name": MODEL_NAME,
        "selected_ridge_alpha": selected_alpha,
        "selected_candidate": selected_key,
        "learned_model_selected": selected_alpha is not None,
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
        "feature_names": list(feature_names()),
        "target_names": list(LEARNED_TARGET_COLUMNS),
    }
    return (fitted[selected_alpha] if selected_alpha is not None else None), manifest


def train_initial_model(
    artifact_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
    ridge_alphas: tuple[float, ...] = DEFAULT_RIDGE_ALPHAS,
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
            "Validation selected a required baseline instead of the Ridge correction model.\n",
            encoding="utf-8",
        )
    (output_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return output_path
