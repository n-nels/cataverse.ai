"""
Data structures and utilities for PFO-Sec parameter prediction model.

Trains a multi-output LightGBM model for all 6 targets.
Supports two strategies:

- **shared** (default): native LightGBM multi-output regression with
  ``lgb.train()``, ``objective="regression"``, ``num_class=6``. Tree
  splits are shared across all targets. Supports early stopping.

- **separate**: one ``LGBMRegressor`` per target via
  ``MultiOutputRegressor``. Each target gets its own set of trees.
  Does not support early stopping.
"""

import logging
import re
from pathlib import Path
from typing import Any, NamedTuple

import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from lightgbm import LGBMRegressor
from scipy import stats
from scipy.special import inv_boxcox
from sklearn.metrics import root_mean_squared_error, r2_score
from sklearn.multioutput import MultiOutputRegressor
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# Default model directory
DEFAULT_MODEL_DIR = Path(__file__).parent / "models"

# Targets whose scale spans orders of magnitude — train in log space
LOG_TRANSFORM_TARGETS = [
    "pfo-sec_q_inf_au",
    "pfo-sec_k_a_s-1",
    "pfo-sec_k_s_s-1",
    "pfo-sec_k_p_s-1",
]


class ModelConfig(NamedTuple):
    """Training configuration."""

    n_estimators: int = 1000
    learning_rate: float = 0.05
    max_depth: int = 6
    early_stopping_rounds: int = 50


class TrainedModel(NamedTuple):
    """Container for trained model.

    ``model`` is a ``MultiOutputRegressor`` (strategy="separate") or a
    ``_StackedModel`` (strategy="shared").
    Calling ``model.predict(X)`` returns an (n_samples, n_targets) array
    in both cases.

    Use :func:`get_feature_importances` to extract importances
    regardless of strategy.
    """

    model: Any  # MultiOutputRegressor | _StackedModel
    config: ModelConfig
    target_names: list[str]
    metrics: dict  # {target_name: {rmse: float, r2: float}}
    lambdas: dict[str, float] | None = None  # Box-Cox lambdas per target, None = log transform


def sanitize_feature_names(columns: list[str]) -> list[str]:
    """
    Sanitize feature names for LightGBM.

    Removes characters that LightGBM doesn't support in feature names.

    Parameters
    ----------
    columns : list[str]
        Original column names.

    Returns
    -------
    list[str]
        Sanitized column names.
    """
    return [re.sub(r"[^\w\.\-]", "_", col) for col in columns]


def fit_boxcox_lambdas(
    y: pd.DataFrame,
    targets: list[str] | None = None,
) -> dict[str, float]:
    """
    Fit Box-Cox lambda for each target column.

    Parameters
    ----------
    y : pd.DataFrame
        Training targets in original scale.
    targets : list[str] | None
        Columns to fit. Defaults to ``LOG_TRANSFORM_TARGETS``.

    Returns
    -------
    dict[str, float]
        Mapping of column name to Box-Cox lambda.
    """
    if targets is None:
        targets = LOG_TRANSFORM_TARGETS
    lambdas: dict[str, float] = {}
    for col in targets:
        if col in y.columns:
            _, lam = stats.boxcox(np.maximum(y[col].values, 1e-12))
            lambdas[col] = lam
    return lambdas


def apply_target_transforms(
    y: pd.DataFrame,
    lambdas: dict[str, float] | None = None,
) -> pd.DataFrame:
    """
    Apply log or Box-Cox transform to specified target columns.

    If ``lambdas`` is provided, uses Box-Cox with those per-column lambdas.
    Otherwise falls back to ``np.log`` (the previous behavior).

    Parameters
    ----------
    y : pd.DataFrame
        Targets in original scale (one column per target).
    lambdas : dict[str, float] | None
        Box-Cox lambdas per column. If None, uses log transform.

    Returns
    -------
    pd.DataFrame
        Transformed targets.
    """
    yt = y.copy()
    if lambdas is not None:
        for col, lam in lambdas.items():
            if col in yt.columns:
                yt[col] = stats.boxcox(np.maximum(yt[col].values, 1e-12), lmbda=lam)
    else:
        for col in LOG_TRANSFORM_TARGETS:
            if col in yt.columns:
                yt[col] = np.log(np.maximum(yt[col], 1e-12))
    return yt


def inverse_target_transforms(
    values: np.ndarray,
    target_names: list[str],
    lambdas: dict[str, float] | None = None,
) -> np.ndarray:
    """
    Invert log or Box-Cox transform.

    If ``lambdas`` is provided, uses inverse Box-Cox.
    Otherwise falls back to ``np.exp`` (the previous behavior).

    Parameters
    ----------
    values : np.ndarray
        Predicted or baseline values in transformed space, shape (n, n_targets).
    target_names : list[str]
        Column names corresponding to each column of ``values``.
    lambdas : dict[str, float] | None
        Box-Cox lambdas per column. If None, uses exp transform.

    Returns
    -------
    np.ndarray
        Values in original scale.
    """
    result = values.copy()
    if lambdas is not None:
        for i, name in enumerate(target_names):
            if name in lambdas:
                result[:, i] = inv_boxcox(result[:, i], lambdas[name])
    else:
        for i, name in enumerate(target_names):
            if name in LOG_TRANSFORM_TARGETS:
                result[:, i] = np.exp(result[:, i])
    return result


def _sanitize_xy(
    X_train: pd.DataFrame,
    X_val: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sanitize feature names and return copies."""
    clean_names = sanitize_feature_names(list(X_train.columns))
    X_tr = X_train.copy()
    X_tr.columns = clean_names
    X_v = X_val.copy()
    X_v.columns = clean_names
    return X_tr, X_v


def _train_separate(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    config: ModelConfig,
) -> MultiOutputRegressor:
    """Train one ``LGBMRegressor`` per target via ``MultiOutputRegressor``."""
    base = LGBMRegressor(
        n_estimators=config.n_estimators,
        learning_rate=config.learning_rate,
        max_depth=config.max_depth,
        random_state=42,
        verbose=-1,
    )
    model = MultiOutputRegressor(base, n_jobs=-1)
    model.fit(X_train, y_train.values)
    return model


class _StackedModel:
    """Wrapper around a single ``LGBMRegressor`` trained on stacked data.

    LightGBM's Python API doesn't natively support multi-output regression
    with shared tree splits. This wrapper implements the "stacking trick":
    each sample is replicated ``n_targets`` times with an added
    ``target_index`` feature (0 … n_targets-1), and a single model is
    trained on the flattened (n × n_targets) rows.

    If ``y_scaler`` is provided, targets are scaled before training and
    ``.predict()`` automatically inverts the scaling so downstream code
    always works with original-scale values.
    """

    def __init__(self, base_model: LGBMRegressor, n_targets: int, y_scaler: StandardScaler | None = None):
        self.base_model = base_model
        self.n_targets = n_targets
        self.y_scaler = y_scaler

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict all targets, reshape to (n, n_targets).

        If a ``y_scaler`` was fitted, predictions are inverted to the
        original target scale.
        """
        n = len(X)
        target_idx = np.tile(np.arange(self.n_targets), n)
        X_aug = np.column_stack([np.repeat(X.values, self.n_targets, axis=0), target_idx])
        X_aug = pd.DataFrame(
            X_aug, columns=list(X.columns) + ["target_index"],
        )
        y_flat = self.base_model.predict(X_aug)
        y_pred = y_flat.reshape(-1, self.n_targets)
        if self.y_scaler is not None:
            y_pred = self.y_scaler.inverse_transform(y_pred)
        return y_pred

    @property
    def feature_importances_(self) -> np.ndarray:
        """Return feature importances (excluding target_index)."""
        return self.base_model.feature_importances_[:self._n_features]


def _train_shared(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_val: pd.DataFrame,
    config: ModelConfig,
) -> _StackedModel:
    """Train a single model with shared tree splits across targets.

    Uses the stacking trick: each row is replicated ``n_targets`` times
    with a ``target_index`` feature, so tree splits consider all targets
    together.

    Targets are z-scored (:class:`~sklearn.preprocessing.StandardScaler`)
    before training so all 6 output dimensions contribute equally to the
    shared L2 loss. ``predict()`` automatically inverts the scaling.
    """
    n_targets = y_train.shape[1]

    # Scale targets so each dimension contributes equally to the loss
    scaler = StandardScaler()
    y_train_scaled = scaler.fit_transform(y_train)
    y_val_scaled = scaler.transform(y_val)

    base = LGBMRegressor(
        n_estimators=config.n_estimators,
        learning_rate=config.learning_rate,
        max_depth=config.max_depth,
        random_state=42,
        verbose=-1,
    )

    # Stack validation set for early stopping
    n_val = len(X_val)
    X_val_stacked = np.repeat(X_val.values, n_targets, axis=0)
    y_val_flat = y_val_scaled.ravel(order="C")
    target_idx_val = np.tile(np.arange(n_targets), n_val)
    X_val_aug = np.column_stack([X_val_stacked, target_idx_val])

    # Stack training set
    n_train = len(X_train)
    X_train_stacked = np.repeat(X_train.values, n_targets, axis=0)
    y_train_flat = y_train_scaled.ravel(order="C")
    target_idx_train = np.tile(np.arange(n_targets), n_train)
    X_train_aug = np.column_stack([X_train_stacked, target_idx_train])

    # Build DataFrames so LightGBM has proper feature names
    aug_columns = list(X_train.columns) + ["target_index"]
    X_train_aug = pd.DataFrame(X_train_aug, columns=aug_columns)
    X_val_aug = pd.DataFrame(X_val_aug, columns=aug_columns)

    base.fit(
        X_train_aug, y_train_flat,
        eval_set=[(X_val_aug, y_val_flat)],
        eval_metric="l2",
        callbacks=[
            lgb.early_stopping(config.early_stopping_rounds),
            lgb.log_evaluation(0),
        ],
    )

    wrapped = _StackedModel(base, n_targets, y_scaler=scaler)
    wrapped._n_features = X_train.shape[1]
    wrapped._feature_names = list(X_train.columns)
    return wrapped


def train_all_targets(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_val: pd.DataFrame,
    config: ModelConfig | None = None,
    strategy: str = "shared",
) -> TrainedModel:
    """
    Train a multi-output LightGBM model for all targets.

    Parameters
    ----------
    X_train : pd.DataFrame
        Training features.
    y_train : pd.DataFrame
        Training targets (one column per target).
    X_val : pd.DataFrame
        Validation features.
    y_val : pd.DataFrame
        Validation targets (one column per target).
    config : ModelConfig | None
        Training configuration. Uses defaults if None.
    strategy : str
        ``"shared"`` (default) — native LightGBM multi-output with
        shared tree splits and early stopping.

        ``"separate"`` — one ``LGBMRegressor`` per target via
        ``MultiOutputRegressor`` (no early stopping).

    Returns
    -------
    TrainedModel
        Container with trained model, config, and per-target metrics.
    """
    if config is None:
        config = ModelConfig()

    target_names = list(y_train.columns)

    # Fit Box-Cox lambdas on training targets
    lambdas = fit_boxcox_lambdas(y_train)
    y_train_tfm = apply_target_transforms(y_train, lambdas)
    y_val_tfm = apply_target_transforms(y_val, lambdas)

    # Sanitize feature names for LightGBM
    X_train_clean, X_val_clean = _sanitize_xy(X_train, X_val)

    logger.info(
        "Training model (strategy=%s) on %d targets (Box-Cox lambdas: %s)",
        strategy, y_train.shape[1],
        {k: f"{v:.3f}" for k, v in lambdas.items()},
    )

    # Dispatch to selected strategy
    if strategy == "shared":
        model = _train_shared(X_train_clean, y_train_tfm, X_val_clean, y_val_tfm, config)
    elif strategy == "separate":
        model = _train_separate(X_train_clean, y_train_tfm, config)
    else:
        raise ValueError(f"Unknown strategy: {strategy!r}. Choose 'shared' or 'separate'.")

    # Evaluate per-target on validation set (invert to original scale)
    y_pred_tfm = model.predict(X_val_clean)  # (n_samples, n_targets) in transf. space
    y_pred = inverse_target_transforms(y_pred_tfm, target_names, lambdas)
    y_val_orig = y_val.values  # already in original scale

    all_metrics = {}
    for i, target_name in enumerate(target_names):
        rmse = float(root_mean_squared_error(y_val_orig[:, i], y_pred[:, i]))
        r2 = float(r2_score(y_val_orig[:, i], y_pred[:, i]))
        all_metrics[target_name] = {"rmse": rmse, "r2": r2}
        logger.info("%s - RMSE: %.6f, R²: %.4f", target_name, rmse, r2)

    # Compute aggregate metrics
    avg_rmse = sum(m["rmse"] for m in all_metrics.values()) / len(all_metrics)
    avg_r2 = sum(m["r2"] for m in all_metrics.values()) / len(all_metrics)
    logger.info("Aggregate - Avg RMSE: %.6f, Avg R²: %.4f", avg_rmse, avg_r2)

    return TrainedModel(
        model=model,
        config=config,
        target_names=target_names,
        metrics=all_metrics,
        lambdas=lambdas,
    )


def evaluate_on_test(
    trained_model: TrainedModel,
    X_test: pd.DataFrame,
    y_test: pd.DataFrame,
) -> dict:
    """
    Evaluate trained model on test set.

    Parameters
    ----------
    trained_model : TrainedModel
        Trained model container.
    X_test : pd.DataFrame
        Test features.
    y_test : pd.DataFrame
        Test targets (one column per target).

    Returns
    -------
    dict
        Test metrics per target and aggregates.
    """
    # Sanitize feature names for LightGBM
    clean_feature_names = sanitize_feature_names(list(X_test.columns))
    X_test_clean = X_test.copy()
    X_test_clean.columns = clean_feature_names

    # Predict in transformed space, then invert to original scale
    y_pred_tfm = trained_model.model.predict(X_test_clean)
    y_pred = inverse_target_transforms(y_pred_tfm, trained_model.target_names, trained_model.lambdas)

    y_test_orig = y_test.values  # already in original scale

    test_metrics = {}
    for i, target_name in enumerate(y_test.columns):
        rmse = float(root_mean_squared_error(y_test_orig[:, i], y_pred[:, i]))
        r2 = float(r2_score(y_test_orig[:, i], y_pred[:, i]))
        test_metrics[target_name] = {"rmse": rmse, "r2": r2}
        logger.info("Test %s - RMSE: %.6f, R²: %.4f", target_name, rmse, r2)

    # Aggregate
    avg_rmse = sum(m["rmse"] for m in test_metrics.values()) / len(test_metrics)
    avg_r2 = sum(m["r2"] for m in test_metrics.values()) / len(test_metrics)
    test_metrics["aggregate"] = {"avg_rmse": avg_rmse, "avg_r2": avg_r2}
    logger.info("Test Aggregate - Avg RMSE: %.6f, Avg R²: %.4f", avg_rmse, avg_r2)

    return test_metrics


def evaluate_baseline(
    y_train: pd.DataFrame,
    y_test: pd.DataFrame,
) -> dict:
    """
    Evaluate a mean-prediction baseline on the test set.

    Predicts the training-set mean for every test sample — a no-information
    baseline that any real model should meaningfully outperform.

    Parameters
    ----------
    y_train : pd.DataFrame
        Training targets (one column per target).
    y_test : pd.DataFrame
        Test targets (one column per target).

    Returns
    -------
    dict
        Baseline metrics per target and aggregates.
    """
    # Compute baseline mean in transformed space (matches training space)
    lambdas = fit_boxcox_lambdas(y_train)
    y_train_tfm = apply_target_transforms(y_train, lambdas)
    baseline_tfm = np.tile(y_train_tfm.mean().values, (len(y_test), 1))  # (n_test, n_targets)
    # Invert to original scale for comparison
    baseline = inverse_target_transforms(baseline_tfm, list(y_test.columns), lambdas)

    baseline_metrics: dict = {}
    for i, target_name in enumerate(y_test.columns):
        rmse = float(root_mean_squared_error(y_test.iloc[:, i], baseline[:, i]))
        r2 = float(r2_score(y_test.iloc[:, i], baseline[:, i]))
        baseline_metrics[target_name] = {"rmse": rmse, "r2": r2}
        logger.info("Baseline %s - RMSE: %.6f, R²: %.4f", target_name, rmse, r2)

    avg_rmse = sum(m["rmse"] for m in baseline_metrics.values()) / len(baseline_metrics)
    avg_r2 = sum(m["r2"] for m in baseline_metrics.values()) / len(baseline_metrics)
    baseline_metrics["aggregate"] = {"avg_rmse": avg_rmse, "avg_r2": avg_r2}
    logger.info("Baseline Aggregate - Avg RMSE: %.6f, Avg R²: %.4f", avg_rmse, avg_r2)

    return baseline_metrics


def get_feature_importances(
    trained_model: TrainedModel,
    importance_type: str = "gain",
) -> np.ndarray:
    """Extract feature importances regardless of training strategy.

    For ``MultiOutputRegressor`` (separate strategy), importances are
    averaged across the per-target estimators.

    For ``lgb.Booster`` (shared strategy), the single importance vector
    (already aggregated across targets) is returned directly.

    Parameters
    ----------
    trained_model : TrainedModel
        Trained model container.
    importance_type : str
        Type of importance (``"gain"`` or ``"split"``). Ignored for
        ``MultiOutputRegressor`` (always uses ``feature_importances_``).

    Returns
    -------
    np.ndarray
        Feature importance array of shape ``(n_features,)``.
    """
    model = trained_model.model
    if isinstance(model, MultiOutputRegressor):
        # Average across per-target estimators
        arr = np.mean(
            [est.feature_importances_ for est in model.estimators_], axis=0
        )
        return arr
    elif isinstance(model, _StackedModel):
        return model.feature_importances_
    else:
        raise TypeError(f"Unknown model type: {type(model)}")


def save_model(
    trained_model: TrainedModel,
    feature_names: list[str],
    target_names: list[str],
    model_dir: str | Path | None = None,
) -> Path:
    """
    Save trained model to disk.

    Parameters
    ----------
    trained_model : TrainedModel
        Trained model container.
    feature_names : list[str]
        Names of feature columns.
    target_names : list[str]
        Names of target columns.
    model_dir : str | Path | None
        Directory to save model. Defaults to module-relative models/.

    Returns
    -------
    Path
        Path to saved model file.
    """
    save_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    artifacts = {
        "model": trained_model.model,
        "config": trained_model.config,
        "target_names": trained_model.target_names,
        "metrics": trained_model.metrics,
        "lambdas": trained_model.lambdas,
        "feature_names": sanitize_feature_names(feature_names),
    }

    model_path = save_dir / "lightgbm.joblib"
    joblib.dump(artifacts, model_path)
    logger.info("Saved model to %s", model_path)

    return model_path


def load_model(model_path: str | Path) -> TrainedModel:
    """
    Load trained model from disk.

    Parameters
    ----------
    model_path : str | Path
        Path to saved model file.

    Returns
    -------
    TrainedModel
        Loaded model container.
    """
    artifacts = joblib.load(model_path)
    return TrainedModel(
        model=artifacts["model"],
        config=artifacts["config"],
        target_names=artifacts["target_names"],
        metrics=artifacts["metrics"],
        lambdas=artifacts.get("lambdas"),
    )
