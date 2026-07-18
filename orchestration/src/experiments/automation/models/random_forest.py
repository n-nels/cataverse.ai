"""
Random Forest model for PFO-Sec parameter prediction.

Trains a ``RandomForestRegressor`` per target via ``MultiOutputRegressor``.
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


@register_model("random_forest")
def train_random_forest(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_val: pd.DataFrame,
    config: ModelConfig | None = None,
    strategy: str = "shared",
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

    Returns
    -------
    TrainedModel
        Container with trained model, config, and per-target metrics.
    """
    if config is None:
        config = ModelConfig()

    target_names = list(y_train.columns)

    # Same Box-Cox transforms as LightGBM for fair comparison
    lambdas = fit_boxcox_lambdas(y_train)
    y_train_tfm = apply_target_transforms(y_train, lambdas)
    y_val_tfm = apply_target_transforms(y_val, lambdas)

    logger.info(
        "Training Random Forest on %d targets (Box-Cox lambdas: %s)",
        y_train.shape[1],
        {k: f"{v:.3f}" for k, v in lambdas.items()},
    )

    base = RandomForestRegressor(
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        random_state=42,
        verbose=0,
        n_jobs=-1,
    )
    model = MultiOutputRegressor(base)
    model.fit(X_train, y_train_tfm.values)

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
