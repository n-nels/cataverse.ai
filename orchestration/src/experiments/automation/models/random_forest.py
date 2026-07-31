"""
Random Forest model for PFO-Sec parameter prediction.

Supports two strategies:

- **separate** (default): one ``RandomForestRegressor`` per target via
  ``MultiOutputRegressor``. Each target gets its own set of trees.

- **shared**: a single ``RandomForestRegressor`` trained on 2D
  ``y``. Trees are shared across all targets via scikit-learn's native
  multi-output support.

Same Box-Cox target transforms as LightGBM for fair comparison.
"""

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import root_mean_squared_error, r2_score
from sklearn.multioutput import MultiOutputRegressor

from model import (
    ModelConfig,
    TrainedModel,
    fit_boxcox_lambdas,
    apply_target_transforms,
    inverse_target_transforms,
    register_model,
)

logger = logging.getLogger(__name__)


def _train_shared(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    config: ModelConfig,
) -> RandomForestRegressor:
    """Train a single ``RandomForestRegressor`` on 2D ``y`` (shared trees)."""
    model = RandomForestRegressor(
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        min_samples_split=config.min_samples_split,
        min_samples_leaf=config.min_child_samples,
        max_features=config.colsample_bytree,
        max_samples=config.subsample if config.subsample < 1.0 else None,
        random_state=config.random_state,
        verbose=0,
        n_jobs=-1,
    )
    model.fit(X_train, y_train.values)
    return model


def _train_separate(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    config: ModelConfig,
) -> MultiOutputRegressor:
    """Train one ``RandomForestRegressor`` per target via ``MultiOutputRegressor``."""
    base = RandomForestRegressor(
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        min_samples_split=config.min_samples_split,
        min_samples_leaf=config.min_child_samples,
        max_features=config.colsample_bytree,
        max_samples=config.subsample if config.subsample < 1.0 else None,
        random_state=config.random_state,
        verbose=0,
        n_jobs=-1,
    )
    model = MultiOutputRegressor(base, n_jobs=-1)
    model.fit(X_train, y_train.values)
    return model


@register_model("random_forest")
def train_random_forest(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_val: pd.DataFrame,
    config: ModelConfig | None = None,
    strategy: str = "separate",
) -> TrainedModel:
    """
    Train a multi-output Random Forest model for all targets.

    Uses default hyperparameters (baseline). Grid search to follow.

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
        ``"separate"`` (default) or ``"shared"``.

    Returns
    -------
    TrainedModel
        Container with trained model, config, and per-target metrics.
    """
    if config is None:
        config = ModelConfig()._replace(
            n_estimators=1809,
            max_depth=23,
            min_child_samples=1,
            subsample=0.922465,
            colsample_bytree=0.348978,
            random_state=72,
        )

    target_names = list(y_train.columns)

    # Same Box-Cox transforms as LightGBM for fair comparison
    lambdas = fit_boxcox_lambdas(y_train)
    y_train_tfm = apply_target_transforms(y_train, lambdas)
    y_val_tfm = apply_target_transforms(y_val, lambdas)

    logger.info(
        "Training Random Forest (strategy=%s) on %d targets (Box-Cox lambdas: %s)",
        strategy,
        y_train.shape[1],
        {k: f"{v:.3f}" for k, v in lambdas.items()},
    )

    if strategy == "shared":
        model = _train_shared(X_train, y_train_tfm, config)
    elif strategy == "separate":
        model = _train_separate(X_train, y_train_tfm, config)
    else:
        raise ValueError(f"Unknown strategy: {strategy!r}. Choose 'shared' or 'separate'.")

    # Evaluate on validation set
    y_pred_tfm = model.predict(X_val)
    y_pred = inverse_target_transforms(y_pred_tfm, target_names, lambdas)
    y_val_orig = y_val.values

    all_metrics = {}
    for i, target_name in enumerate(target_names):
        rmse = float(root_mean_squared_error(y_val_orig[:, i], y_pred[:, i]))
        r2 = float(r2_score(y_val_orig[:, i], y_pred[:, i]))
        all_metrics[target_name] = {"rmse": rmse, "r2": r2}
        logger.info("%s - RMSE: %.6f, R\u00b2: %.4f", target_name, rmse, r2)

    avg_rmse = sum(m["rmse"] for m in all_metrics.values()) / len(all_metrics)
    avg_r2 = sum(m["r2"] for m in all_metrics.values()) / len(all_metrics)
    logger.info("Aggregate - Avg RMSE: %.6f, Avg R\u00b2: %.4f", avg_rmse, avg_r2)

    return TrainedModel(
        model=model,
        config=config,
        target_names=target_names,
        metrics=all_metrics,
        lambdas=lambdas,
    )
