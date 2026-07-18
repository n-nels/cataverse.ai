"""
Model interface, data structures, and shared utilities for PFO-Sec parameter prediction.

Defines the model interface that all model implementations satisfy,
shared evaluation/visualization helpers, and a registry for model discovery.

Current models:
- ``lightgbm`` — :mod:`models.lightgbm`
- ``random_forest`` — :mod:`models.random_forest`
"""

import logging
import re
import sys
from pathlib import Path
from typing import Any, Callable, NamedTuple

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import inv_boxcox
from sklearn.metrics import root_mean_squared_error, r2_score

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

# Type alias for a model trainer function
# Signature: (X_train, y_train, X_val, y_val, config) -> TrainedModel
ModelTrainer = Callable[
    [pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Any],
    "TrainedModel",
]

# Model registry — maps name to trainer function
MODEL_REGISTRY: dict[str, ModelTrainer] = {}


def register_model(name: str) -> Callable[[ModelTrainer], ModelTrainer]:
    """Decorator to register a model trainer in the global registry."""
    def decorator(fn: ModelTrainer) -> ModelTrainer:
        MODEL_REGISTRY[name] = fn
        return fn
    return decorator


class ModelConfig(NamedTuple):
    """Training configuration.

    Fields shared across models; unused fields are silently ignored
    by models that don't need them.
    """

    n_estimators: int = 1000
    learning_rate: float = 0.05
    max_depth: int = 6
    early_stopping_rounds: int = 50


class TrainedModel(NamedTuple):
    """Container for a trained model.

    ``model`` must expose a ``predict(X) -> np.ndarray`` method that
    returns an ``(n_samples, n_targets)`` array in original-scale values.
    """

    model: Any
    config: ModelConfig
    target_names: list[str]
    metrics: dict
    lambdas: dict[str, float] | None = None


def sanitize_feature_names(columns: list[str]) -> list[str]:
    """
    Sanitize feature names for libraries with strict naming rules.

    Removes characters that LightGBM doesn't support in feature names.
    """
    return [re.sub(r"[^\w\.\-]", "_", col) for col in columns]


def fit_boxcox_lambdas(
    y: pd.DataFrame,
    targets: list[str] | None = None,
) -> dict[str, float]:
    """Fit Box-Cox lambda for each target column."""
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
    """Apply log or Box-Cox transform to specified target columns."""
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
    """Invert log or Box-Cox transform."""
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
    y_pred_tfm = trained_model.model.predict(X_test)
    y_pred = inverse_target_transforms(y_pred_tfm, trained_model.target_names, trained_model.lambdas)
    y_test_orig = y_test.values

    test_metrics = {}
    for i, target_name in enumerate(y_test.columns):
        rmse = float(root_mean_squared_error(y_test_orig[:, i], y_pred[:, i]))
        r2 = float(r2_score(y_test_orig[:, i], y_pred[:, i]))
        test_metrics[target_name] = {"rmse": rmse, "r2": r2}
        logger.info("Test %s - RMSE: %.6f, R\u00b2: %.4f", target_name, rmse, r2)

    avg_rmse = sum(m["rmse"] for m in test_metrics.values()) / len(test_metrics)
    avg_r2 = sum(m["r2"] for m in test_metrics.values()) / len(test_metrics)
    test_metrics["aggregate"] = {"avg_rmse": avg_rmse, "avg_r2": avg_r2}
    logger.info("Test Aggregate - Avg RMSE: %.6f, Avg R\u00b2: %.4f", avg_rmse, avg_r2)

    return test_metrics


def evaluate_baseline(
    y_train: pd.DataFrame,
    y_test: pd.DataFrame,
) -> dict:
    """
    Evaluate a mean-prediction baseline on the test set.

    Predicts the training-set mean for every test sample — a no-information
    baseline that any real model should meaningfully outperform.
    """
    lambdas = fit_boxcox_lambdas(y_train)
    y_train_tfm = apply_target_transforms(y_train, lambdas)
    baseline_tfm = np.tile(y_train_tfm.mean().values, (len(y_test), 1))
    baseline = inverse_target_transforms(baseline_tfm, list(y_test.columns), lambdas)

    baseline_metrics = {}
    for i, target_name in enumerate(y_test.columns):
        rmse = float(root_mean_squared_error(y_test.iloc[:, i], baseline[:, i]))
        r2 = float(r2_score(y_test.iloc[:, i], baseline[:, i]))
        baseline_metrics[target_name] = {"rmse": rmse, "r2": r2}
        logger.info("Baseline %s - RMSE: %.6f, R\u00b2: %.4f", target_name, rmse, r2)

    avg_rmse = sum(m["rmse"] for m in baseline_metrics.values()) / len(baseline_metrics)
    avg_r2 = sum(m["r2"] for m in baseline_metrics.values()) / len(baseline_metrics)
    baseline_metrics["aggregate"] = {"avg_rmse": avg_rmse, "avg_r2": avg_r2}
    logger.info("Baseline Aggregate - Avg RMSE: %.6f, Avg R\u00b2: %.4f", avg_rmse, avg_r2)

    return baseline_metrics


def get_feature_importances(
    trained_model: TrainedModel,
    importance_type: str = "gain",
) -> np.ndarray:
    """Extract feature importances regardless of model type.

    Supported model types:
    - ``MultiOutputRegressor`` (sklearn) — averages per-target importances
    - Any model with ``feature_importances_`` attribute

    Parameters
    ----------
    trained_model : TrainedModel
        Trained model container.
    importance_type : str
        Type of importance (used by LightGBM boosters; ignored for sklearn).

    Returns
    -------
    np.ndarray
        Feature importance array of shape ``(n_features,)``.
    """
    model = trained_model.model
    if hasattr(model, "estimators_"):
        return np.mean(
            [est.feature_importances_ for est in model.estimators_], axis=0
        )
    if hasattr(model, "feature_importances_"):
        return model.feature_importances_
    raise TypeError(f"Model type {type(model)} does not expose feature_importances_")


def save_model(
    trained_model: TrainedModel,
    feature_names: list[str],
    target_names: list[str],
    model_name: str = "lightgbm",
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
    model_name : str
        Name for the serialized file (``{model_name}.joblib``).
    model_dir : str | Path | None
        Directory to save model. Defaults to module-relative ``models/``.

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

    model_path = save_dir / f"{model_name}.joblib"
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
    import models.lightgbm  # noqa: F401 — ensure model classes are importable for deserialization
    # Backward compat: old serialized models reference model._StackedModel
    if not hasattr(sys.modules[__name__], "_StackedModel"):
        setattr(sys.modules[__name__], "_StackedModel", models.lightgbm._StackedModel)
    artifacts = joblib.load(model_path)
    return TrainedModel(
        model=artifacts["model"],
        config=artifacts["config"],
        target_names=artifacts["target_names"],
        metrics=artifacts["metrics"],
        lambdas=artifacts.get("lambdas"),
    )
