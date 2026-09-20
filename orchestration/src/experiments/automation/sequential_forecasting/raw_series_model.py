"""Learned sequential model that reads the raw measurement series directly.

Every earlier candidate consumed the adsorption measurements only as a handful
of summary scalars (last value, mean, standard deviation, observed duration) or
as the history of previously stored parameter fits. None of them ever saw the
shape of the curve itself. This model does: the measurements collected so far
are resampled onto a fixed absolute-time grid, paired with an availability
mask, and handed to one supervised regressor that outputs the final parameter
vector end to end. It is not a blend of two existing estimates and it contains
no hand-tuned switching rule.

Three properties matter for correctness and are enforced here rather than
repaired afterwards:

* **No future information.** Only the prefix through the cutoff is read. The
  grid is masked beyond the last observed time, and `observation_fraction` is
  deliberately excluded because its denominator is the experiment's total
  observation count, which is not known during the experiment.
* **Physically valid outputs by construction.** The regressor predicts a
  latent vector that maps onto the fitter's own parameterization, so `k_a` is
  strictly positive and bounded, `k_p` is a bounded fraction of `k_a`, and the
  capacities are non-negative. Nothing can be driven onto a degenerate boundary
  by clipping, which is what flattened the trajectory-extrapolation forecasts.
* **Scale-aware fitting.** Each latent target is standardized before fitting,
  so the three rate constants carry the same weight as the two capacities
  instead of being invisible next to them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from .data.examples import FIT_VALID, SequentialExample
from .model_prediction import ModelPrediction
from .models.secondary_pfo import (
    SecondaryPfoParameters,
    validate_secondary_pfo_parameters,
)


MODEL_NAME = "raw_series"
ESTIMATOR_NAMES = ("gbm", "mlp")

# Bounds taken from the existing fitter, not invented here.
K_UPPER = 0.01
K_FLOOR = 1e-6
RATIO_EPSILON = 1e-4
CAPACITY_UPPER = 10.0

# Elapsed-second offsets from the first measurement. Log spaced because the
# schedules themselves are dense early and sparse late, and because the rate
# constants act on absolute seconds.
GRID_OFFSETS_S: tuple[float, ...] = tuple(
    float(value) for value in np.logspace(np.log10(60.0), np.log10(600_000.0), 24)
)

FIT_STATUS_FLAGS = (
    "fit_not_yet_eligible",
    "fit_missing_for_cutoff",
    "fit_partially_populated",
    "fit_missing_for_whole_experiment",
    "fit_failed",
    "fit_valid",
    "successful_no_adsorption",
)


def to_latent(values: np.ndarray) -> np.ndarray:
    """Map five kinetic parameters into the unconstrained fitting space."""
    values = np.atleast_2d(np.asarray(values, dtype=float))
    k_a = np.clip(values[:, 0], K_FLOOR, K_UPPER)
    ratio = np.where(
        values[:, 0] > 0.0,
        values[:, 3] / np.maximum(values[:, 0], K_FLOOR),
        0.5,
    )
    ratio = np.clip(ratio, RATIO_EPSILON, 1.0 - RATIO_EPSILON)
    return np.column_stack(
        [
            np.log(k_a),
            values[:, 1],
            values[:, 2],
            np.log(ratio / (1.0 - ratio)),
            values[:, 4],
        ]
    )


def from_latent(latent: np.ndarray) -> np.ndarray:
    """Map one latent vector back onto valid kinetic parameters."""
    latent = np.asarray(latent, dtype=float).reshape(-1)
    k_a = float(np.clip(np.exp(latent[0]), K_FLOOR, K_UPPER))
    ratio = float(1.0 / (1.0 + np.exp(-np.clip(latent[3], -30.0, 30.0))))
    return np.asarray(
        [
            k_a,
            float(np.clip(latent[1], 0.0, CAPACITY_UPPER)),
            float(np.clip(latent[2], 0.0, K_UPPER)),
            k_a * ratio,
            float(np.clip(latent[4], 0.0, CAPACITY_UPPER)),
        ],
        dtype=float,
    )


def _slope(times_s: np.ndarray, areas: np.ndarray) -> float:
    """Least-squares slope of area against log elapsed time."""
    if len(times_s) < 2:
        return 0.0
    x = np.log(np.maximum(times_s - times_s[0] + 1.0, 1.0))
    if float(np.ptp(x)) <= 0.0:
        return 0.0
    return float(np.polyfit(x, areas, 1)[0])


def series_feature_names() -> tuple[str, ...]:
    """Return the deterministic feature order."""
    return (
        *(f"grid_area_{index}" for index in range(len(GRID_OFFSETS_S))),
        *(f"grid_seen_{index}" for index in range(len(GRID_OFFSETS_S))),
        "q_0",
        "last_area",
        "area_gain",
        "area_mean",
        "area_std",
        "area_min",
        "area_max",
        "area_range",
        "area_completion",
        "slope_all",
        "slope_recent",
        "slope_first_half",
        "slope_second_half",
        "slope_change",
        "last_step",
        "recent_step_mean",
        "log_observation_count",
        "log_elapsed_s",
        "log_time_remaining_s",
        "log_final_time_s",
        "elapsed_time_fraction",
        *(f"rf_{index}" for index in range(5)),
        *(f"current_fit_{index}" for index in range(6)),
        *(f"current_fit_available_{index}" for index in range(6)),
        "fit_r_squared",
        "fit_rmse",
        *(f"fit_status_{status}" for status in FIT_STATUS_FLAGS),
    )


def series_features(example: SequentialExample) -> np.ndarray:
    """Build one fixed-length feature vector from the prefix alone."""
    times = np.asarray(example.observation_times_s, dtype=float)
    areas = np.asarray(example.observation_area, dtype=float)
    if times.size == 0 or not np.isfinite(times).all() or not np.isfinite(areas).all():
        raise ValueError(f"Invalid prefix observations for {example.cutoff_id}")
    if example.rf_prediction is None or len(example.rf_prediction) != 6:
        raise ValueError(f"RF prediction is unavailable for {example.experiment_id}")

    start_s = float(times[0])
    elapsed = times - start_s
    last_elapsed = float(elapsed[-1])
    grid = np.asarray(GRID_OFFSETS_S, dtype=float)
    seen = (grid <= last_elapsed).astype(float)
    if len(times) == 1:
        resampled = np.full(grid.shape, float(areas[0]))
    else:
        resampled = np.interp(np.minimum(grid, last_elapsed), elapsed, areas)

    area_min = float(np.min(areas))
    area_max = float(np.max(areas))
    area_range = area_max - area_min
    half = max(1, len(times) // 2)
    steps = np.diff(areas) if len(areas) > 1 else np.zeros(1)

    return np.concatenate(
        [
            resampled,
            seen,
            np.asarray(
                [
                    float(example.q_0),
                    float(areas[-1]),
                    float(areas[-1] - areas[0]),
                    float(np.mean(areas)),
                    float(np.std(areas)),
                    area_min,
                    area_max,
                    area_range,
                    float((areas[-1] - area_min) / area_range) if area_range > 0 else 0.0,
                    _slope(times, areas),
                    _slope(times[-4:], areas[-4:]),
                    _slope(times[:half], areas[:half]),
                    _slope(times[half:], areas[half:]),
                    _slope(times[half:], areas[half:]) - _slope(times[:half], areas[:half]),
                    float(steps[-1]),
                    float(np.mean(steps[-3:])),
                    float(np.log1p(example.observation_count)),
                    float(np.log1p(max(last_elapsed, 0.0))),
                    float(np.log1p(max(example.time_remaining_s, 0.0))),
                    float(np.log1p(max(example.final_time_s, 0.0))),
                    float(example.elapsed_time_fraction),
                    *[float(value) for value in example.rf_prediction[:-1]],
                    *[
                        0.0 if value is None else float(value)
                        for value in example.current_fit_values
                    ],
                    *[float(flag) for flag in example.current_fit_available],
                    0.0 if example.fit_r_squared is None else float(example.fit_r_squared),
                    0.0 if example.fit_rmse is None else float(example.fit_rmse),
                    *[
                        float(example.fit_status == status)
                        for status in FIT_STATUS_FLAGS
                    ],
                ],
                dtype=float,
            ),
        ]
    )


def series_feature_matrix(examples: tuple[SequentialExample, ...]) -> np.ndarray:
    """Stack prefix features in the shared feature order."""
    if not examples:
        raise ValueError("At least one example is required")
    matrix = np.vstack([series_features(example) for example in examples])
    if matrix.shape[1] != len(series_feature_names()):
        raise ValueError("Raw-series feature vector does not match its feature names")
    return matrix


@dataclass
class FittedRawSeriesModel:
    """One supervised regressor over the raw measurement prefix."""

    estimator_name: str
    feature_names: tuple[str, ...]
    feature_scaler: StandardScaler
    target_scaler: StandardScaler
    estimators: tuple[object, ...]
    require_valid_fit: bool = True
    training_row_count: int = 0
    training_experiment_count: int = 0
    hyperparameters: dict[str, object] = field(default_factory=dict)

    def predict_parameters(self, example: SequentialExample) -> ModelPrediction:
        """Return a complete ODE-compatible prediction with q_0 passed through."""
        if self.require_valid_fit and example.fit_status != FIT_VALID:
            return ModelPrediction(None, "invalid", f"current_fit_{example.fit_status}")
        try:
            features = self.feature_scaler.transform(
                series_features(example).reshape(1, -1)
            )
            scaled = np.asarray(
                [float(estimator.predict(features)[0]) for estimator in self.estimators]
            )
            latent = self.target_scaler.inverse_transform(scaled.reshape(1, -1))
            values = from_latent(latent)
            parameters = SecondaryPfoParameters.from_values(
                [*values.tolist(), float(example.q_0)]
            )
            validate_secondary_pfo_parameters(parameters)
        except (ValueError, TypeError, FloatingPointError) as error:
            return ModelPrediction(None, "invalid", str(error))
        return ModelPrediction(parameters, MODEL_NAME, None)


DEFAULT_ESTIMATOR_PARAMS: dict[str, dict[str, object]] = {
    "gbm": {
        "max_depth": 4,
        "max_iter": 300,
        "learning_rate": 0.06,
        "min_samples_leaf": 40,
        "l2_regularization": 1.0,
        "early_stopping": False,
    },
    "mlp": {
        "hidden_layer_sizes": (128, 64),
        "alpha": 1.0,
        "learning_rate_init": 3e-3,
        "max_iter": 800,
        "early_stopping": False,
    },
}


def _build_estimator(
    estimator_name: str,
    random_state: int,
    overrides: dict[str, object] | None = None,
) -> object:
    """Create one single-target regressor."""
    if estimator_name not in DEFAULT_ESTIMATOR_PARAMS:
        raise ValueError(f"Unknown estimator: {estimator_name}")
    params = {**DEFAULT_ESTIMATOR_PARAMS[estimator_name], **(overrides or {})}
    params["random_state"] = random_state
    if estimator_name == "gbm":
        return HistGradientBoostingRegressor(**params)
    return MLPRegressor(**params)


def fit_raw_series_model(
    examples: tuple[SequentialExample, ...],
    *,
    estimator_name: str = "gbm",
    require_valid_fit: bool = True,
    random_state: int = 42,
    estimator_params: dict[str, object] | None = None,
) -> FittedRawSeriesModel:
    """Fit the raw-series model on training experiments only.

    Every cutoff of a training experiment is one row. Rows are weighted by the
    reciprocal of their experiment's cutoff count so an experiment with a long
    measurement schedule does not outvote a short one.
    """
    if estimator_name not in ESTIMATOR_NAMES:
        raise ValueError(f"Unknown estimator: {estimator_name}")
    training = tuple(
        example
        for example in examples
        if example.assignment == "train"
        and (example.fit_status == FIT_VALID or not require_valid_fit)
    )
    if not training:
        raise ValueError("Raw-series model requires training examples")

    X = series_feature_matrix(training)
    targets = np.asarray(
        [example.reference_target[:-1] for example in training], dtype=float
    )
    y = to_latent(targets)
    feature_scaler = StandardScaler().fit(X)
    target_scaler = StandardScaler().fit(y)
    scaled_features = feature_scaler.transform(X)
    scaled_targets = target_scaler.transform(y)

    counts = pd.Series(example.experiment_id for example in training).value_counts()
    sample_weight = np.asarray(
        [1.0 / float(counts[example.experiment_id]) for example in training],
        dtype=float,
    )

    estimators: list[object] = []
    for index in range(scaled_targets.shape[1]):
        estimator = _build_estimator(estimator_name, random_state + index, estimator_params)
        if estimator_name == "mlp":
            # MLPRegressor does not accept sample weights; rows are already
            # close to balanced once the dominant 44-point schedule is
            # accounted for, and the weighting is reapplied for the tree model.
            estimator.fit(scaled_features, scaled_targets[:, index])
        else:
            estimator.fit(
                scaled_features,
                scaled_targets[:, index],
                sample_weight=sample_weight,
            )
        estimators.append(estimator)

    return FittedRawSeriesModel(
        estimator_name=estimator_name,
        feature_names=series_feature_names(),
        feature_scaler=feature_scaler,
        target_scaler=target_scaler,
        estimators=tuple(estimators),
        require_valid_fit=require_valid_fit,
        training_row_count=len(training),
        training_experiment_count=len({e.experiment_id for e in training}),
        hyperparameters={
            "estimator_name": estimator_name,
            "require_valid_fit": require_valid_fit,
            "grid_points": len(GRID_OFFSETS_S),
            "random_state": random_state,
            **{**DEFAULT_ESTIMATOR_PARAMS[estimator_name], **(estimator_params or {})},
        },
    )
